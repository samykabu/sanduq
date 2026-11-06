"""Append-only log of the receipts the dispatcher writes, next to each checkpoint.

A checkpoint's receipts are JSON anyone can edit. Every save appends the hash of each receipt it changed (or
removed) to `<feature>/workflow/receipt-log.jsonl`. A receipt found on disk that no longer matches its last
logged hash was edited outside the dispatcher: the save logs that as an `outside-edit` entry instead of adopting
it silently, and the gate refuses a receipt whose newest entry is not the dispatcher's. The base branch keeps
what was merged, so the gate also requires the PR's log to extend the base's.

shortcut: someone can still forge a matching dispatcher line by hand; the gate lists every entry the PR added so
review sees each receipt it recorded. Storage the agent cannot write (a check run) would close this.
"""
import hashlib
import json
import os
import uuid

from wf_core import WorkflowError, git, replace_file, require

LOG = 'workflow/receipt-log.jsonl'
DISPATCHER, OUTSIDE = 'dispatcher', 'outside-edit'


def receipt_hash(receipt):
    """Hash of a receipt's parsed content, so line endings and key order never matter."""
    return hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode('utf-8')).hexdigest()


def parse(text, label=LOG):
    entries = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            entry = None
        require(isinstance(entry, dict) and isinstance(entry.get('stage'), str) and entry.get('by') in (DISPATCHER, OUTSIDE)
                and (entry.get('sha256') is None or isinstance(entry.get('sha256'), str)),
                'RECEIPT_LOG_INVALID: ' + label + ' line ' + str(number) + ' is not a receipt-log entry')
        entries.append(entry)
    return entries


def latest(entries):
    newest = {}
    for entry in entries:
        newest[entry['stage']] = entry
    return newest


def read_entries(feature_dir):
    path = feature_dir / LOG
    return parse(path.read_text(encoding='utf-8'), str(path)) if path.is_file() else None


def changes(last, receipts, by, at):
    """Entries that bring `last` (stage -> newest entry) up to `receipts`; updates `last` in place."""
    added = []
    for stage in sorted(set(receipts) | {s for s, e in last.items() if e.get('sha256')}):
        value = receipt_hash(receipts[stage]) if stage in receipts else None
        if value != (last.get(stage) or {}).get('sha256'):
            last[stage] = {'v': 1, 'stage': stage, 'sha256': value, 'by': by, 'at': at}
            added.append(last[stage])
    return added


def record(feature_dir, on_disk, receipts, at):
    """Log the receipts a save writes. Call after the checkpoint is written: a crash in between leaves a receipt
    unlogged, which the next save logs. With no log yet (a feature started before the log existed) the first save
    starts it from the receipts it writes; nothing older can be vouched for."""
    entries = read_entries(feature_dir)
    last = latest(entries or [])
    added = changes(last, on_disk, OUTSIDE, at) if entries else []
    added += changes(last, receipts, DISPATCHER, at)
    if not added:
        return []
    path = feature_dir / LOG
    text = path.read_text(encoding='utf-8') if path.is_file() else ''
    if text and not text.endswith('\n'):
        text += '\n'
    text += ''.join(json.dumps(entry, sort_keys=True, separators=(',', ':')) + '\n' for entry in added)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with open(temporary, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
        replace_file(temporary, path)
    finally:
        if temporary.exists():
            os.unlink(temporary)
    return added


def base_entries(root, feature, base):
    """The log as merged on the base branch, or None when the base has none (or no base is known)."""
    if not base:
        return None
    try:
        text = git(root, 'show', git(root, 'merge-base', 'HEAD', base) + ':' + feature + '/' + LOG)
    except WorkflowError:
        return None
    return parse(text, base + ':' + feature + '/' + LOG)


def check(root, feature, receipts, base=None):
    """Gate check: every receipt is the one the dispatcher last logged, and the log extends the base's."""
    entries = read_entries(root / feature)
    merged = base_entries(root, feature, base)
    if entries is None:
        require(merged is None, 'RECEIPT_LOG_MISSING: ' + feature + '/' + LOG + ' is on the base branch but '
                'not in this PR; restore it from the base branch')
        return {'entries': 0, 'added': [], 'warnings': [
            'RECEIPT_LOG_ABSENT: ' + feature + ' has no receipt log (started before Workflow 2.1.0); the next '
            'save through the dispatcher starts one']}
    merged = merged or []
    require(entries[:len(merged)] == merged,
            'RECEIPT_LOG_REWRITTEN: ' + feature + '/' + LOG + ' changes or removes entries already merged on '
            'the base branch; restore them from the base branch')
    newest = latest(entries)
    for stage in sorted(set(receipts) | set(newest)):
        entry = newest.get(stage) or {}
        value = receipt_hash(receipts[stage]) if stage in receipts else None
        require(value == entry.get('sha256') and entry.get('by') == DISPATCHER,
                'RECEIPT_EDITED_OUTSIDE_DISPATCHER: ' + stage + ': ' +
                ('the receipt was logged as edited outside the dispatcher at ' + str(entry.get('at'))
                 if entry.get('by') == OUTSIDE and value == entry.get('sha256') else
                 'the receipt in checkpoint.json differs from the last one the dispatcher logged in ' + LOG) +
                '; revert the edit, or re-record the stage through the dispatcher')
    added = entries[len(merged):]
    superseded = [e for e in added if e['by'] == OUTSIDE]
    return {'entries': len(entries), 'added': [{k: e.get(k) for k in ('stage', 'by', 'at')} for e in added],
            'warnings': ['RECEIPT_OUTSIDE_EDIT_SUPERSEDED: ' + e['stage'] + ' was edited outside the dispatcher at '
                         + str(e.get('at')) + ' and re-recorded through it since' for e in superseded]}
