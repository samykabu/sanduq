"""Content fingerprints: file hashes with git text attributes, the advisory hash cache, the Project
sync-state projection and the source inventory."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
import uuid
from pathlib import Path
from sanduq_hash import byte_sensitive, portable_files, text_attributes
from wf_core import (DEFAULT_SYNC_STATE, SYNC_BINDING_PREFIX, SYNC_ADMINISTRATIVE, WorkflowError, require, read,
                     replace_file, write, inside, portable_label, canonical_path, git, OPERATIONAL_DIRS, _memo, RACY_NS)
import wf_core  # the operation memo lives only there; read it through the module


def sync_state_label(root):
    """The configured Project Sync state file (`stateFile`), root-relative; the default when unset or invalid."""
    def label():
        try:
            config = read(Path(root) / '.specify/extensions/project/config.json', {})
            return canonical_path(root, config['stateFile'])
        except (ValueError, TypeError, KeyError, WorkflowError):
            return DEFAULT_SYNC_STATE
    return _memo('sync-state', root, label)


def sync_entry(content, feature):
    """The feature's entry in the state file bytes: None when absent, and the bytes themselves when unreadable."""
    try:
        state = json.loads(content.decode('utf-8-sig'))
    except ValueError:
        return content
    return state.get(feature.rsplit('/', 1)[-1]) if isinstance(state, dict) else content


def sync_projection(content, feature):
    entry = sync_entry(content, feature)
    if isinstance(entry, bytes):
        return SYNC_BINDING_PREFIX + hashlib.sha256(entry).hexdigest()  # unreadable: every byte counts
    if isinstance(entry, dict):
        entry = {key: value for key, value in entry.items() if not SYNC_ADMINISTRATIVE.fullmatch(key)}
    canonical = json.dumps(entry, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return SYNC_BINDING_PREFIX + hashlib.sha256(canonical.encode()).hexdigest()


def sync_binding(root, feature):
    """The current binding fingerprint of the configured state file for `feature` (None when the file is missing)."""
    label = sync_state_label(root)
    return fingerprint_files(root, [label], feature=feature)[label]


HASH_CACHE = '.specify/workflow/runtime/hash-cache.json'


def cached_fingerprints(root, paths):
    """`fingerprint_files(root, paths)` for an advisory check (W18). A regular file whose size, mtime and git text
    attribute equal its cache entry, with an mtime over 2 s old, keeps the cached hash; every other file is hashed
    and stored if it stayed unchanged meanwhile. Byte-sensitive files are never stored: their portable hash can
    follow the index. The cache keeps only the paths of the last call."""
    location = root / HASH_CACHE
    try:
        cache = read(location, {})
    except ValueError:
        cache = {}
    cache = cache if isinstance(cache, dict) else {}
    canonical = {label: canonical_path(root, label) for label in sorted(set(paths))}
    attributes = git_text_attributes(root, sorted(set(canonical.values())))

    def key(name):
        try:
            info = os.stat(root / name)
        except OSError:
            return None
        if not stat.S_ISREG(info.st_mode) or time.time_ns() - info.st_mtime_ns <= RACY_NS:
            return None
        return [info.st_size, info.st_mtime_ns, attributes.get(name)]

    result, stored, misses = {}, {}, {}
    for label, name in canonical.items():
        current, entry = key(name), cache.get(name)
        if current and isinstance(entry, list) and len(entry) == 4 and entry[:3] == current                 and isinstance(entry[3], str):
            result[label], stored[name] = entry[3], entry
        else:
            misses[label] = current
    if misses:
        hashed = fingerprint_files(root, list(misses))
        result.update(hashed)
        for label, before in misses.items():
            name = canonical[label]
            if before is None or hashed[label] is None:
                continue
            try:
                sensitive = byte_sensitive(name, (root / name).read_bytes(), attributes.get(name))
            except OSError:
                continue
            if not sensitive and key(name) == before:
                stored[name] = before + [hashed[label]]
    if stored != cache:
        try:
            write(location, stored)
        except OSError:
            pass  # advisory: the next call hashes again
    return result


def normalized_text(content):
    """Markdown read for a drift decision: CRLF, trailing spaces or tabs and final newlines carry no meaning."""
    return re.sub(rb'[ \t]+(?=\n|\Z)', b'', content.replace(b'\r\n', b'\n')).rstrip(b'\n')


def text_fingerprints(root, paths):
    """Whitespace-normalised hashes of the Markdown paths, used only to decide drift, never stored as the hash."""
    hashes = fingerprint_files(root, [path for path in paths if portable_label(path).lower().endswith('.md')],
                               normalize=True)
    return {path: value for path, value in hashes.items() if value is not None}


def fingerprint_files(root, paths, normalize=False, feature=None, like=None):
    """Byte hashes of `paths`. With `feature`, the configured Project Sync state hashes as that feature's binding
    projection (`sync_projection`), except where `like` (the fingerprints compared against) holds a legacy raw hash,
    which stays byte-exact."""
    result = {}
    paths = sorted(set(paths))
    state = sync_state_label(root) if feature and not normalize else None
    # Legacy labels with Windows separators keep their identity in the result but are read through the
    # canonical path. Labels naming one file each keep their own entry (and the same hash); conflicting role
    # data for such labels is refused when a receipt is ingested (`canonical_receipt`).
    canonical = {relative: canonical_path(root, relative) for relative in paths}
    contents = portable_files(root, sorted(set(canonical.values())), attributes=git_text_attributes)
    # Byte-sensitive files read as their committed blob when the working tree
    # differs only by checkout conversion, so a Windows autocrlf checkout and a
    # clean CI checkout of the same commit fingerprint identically.
    for relative in paths:
        content = contents[canonical[relative]]
        if content is not None and canonical[relative] == state \
                and str((like or {}).get(relative, SYNC_BINDING_PREFIX)).startswith(SYNC_BINDING_PREFIX):
            result[relative] = sync_projection(content, feature)
        elif content is not None:
            # Checkbox bookkeeping must not invalidate task publication or planning.
            if canonical[relative].rsplit('/', 1)[-1] == 'tasks.md':
                content = re.sub(rb'(?m)^(\s*- )\[[ xX]\]', rb'\1[ ]', content)
                # Routing comments are operational metadata. Route policy changes
                # invalidate future dispatch, not earlier semantic task receipts.
                # A marker drops together with the newline that precedes it, so a
                # final task line annotated without a terminal newline, or one an
                # earlier release joined to its marker, hashes like the original.
                marker = rb'[ \t]*<!-- sanduq-delegation \{[^\r\n]*\} -->[ \t]*(?=\r?\n|\Z)'
                content = re.sub(rb'(?<=[^ \t\r\n])' + marker + rb'\r?\n\Z', b'', content)
                content = re.sub(rb'\A' + marker + rb'(?:\r?\n)?', b'', content)
                content = re.sub(rb'(?:\r?\n)?' + marker, b'', content)
            if normalize:
                content = normalized_text(content)
            result[relative] = hashlib.sha256(content).hexdigest()
        else:
            result[relative] = None
    return result


def git_text_attributes(root, paths):
    """`text_attributes`, asking git only about paths this operation has not asked about yet."""
    if wf_core._OPERATION is None:
        return text_attributes(root, paths)
    known = _memo('attributes', root, dict)
    missing = sorted(set(paths) - set(known))
    if missing:
        known.update(text_attributes(root, missing))
    return {path: known[path] for path in paths if path in known}


def prefetch_attributes(root, labels):
    """One `check-attr` for every label a command is about to fingerprint, instead of one per receipt."""
    if wf_core._OPERATION is None:
        return
    canonical = set()
    for label in labels:
        try:
            canonical.add(canonical_path(root, label))
        except WorkflowError:
            pass  # the fingerprint itself reports an invalid label
    git_text_attributes(root, canonical)


def source_fingerprints(root):
    """Inventory code and build inputs, including additions and deletion tombstones (once per operation)."""
    def inventory():
        paths = git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0')
        excluded = {'.git', 'node_modules', '__pycache__', 'dist', 'build', 'coverage', 'obj'}
        selected = []
        for path in filter(None, paths):
            parts = Path(path).parts
            if parts[0] in OPERATIONAL_DIRS or any(p in excluded for p in parts): continue
            if Path(path).name.startswith('.env') or Path(path).suffix.lower() in ('.pem', '.key', '.p12', '.pfx'): continue
            selected.append(path)
        return fingerprint_files(root, selected)
    return dict(_memo('source', root, inventory))


def inventory_label(stage, claim_id, suffix=None):
    """Feature-relative side file of a receipt's source inventory; a rewrite gets a new suffix, never the same name."""
    return 'workflow/inventory/' + stage + '-' + str(claim_id) + ('-' + suffix if suffix else '') + '.json'


def store_source_inventory(root, feature, label, inventory):
    """Write a receipt's source inventory beside the checkpoint; the receipt keeps only its path and hash."""
    target = inside(root, feature + '/' + label)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(inventory, indent=0, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')
    temp = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_bytes(data)
    replace_file(temp, target)
    return {'path': label, 'sha256': hashlib.sha256(data).hexdigest()}


def source_fingerprints_of(root, receipt, feature=None):
    """A receipt's source inventory: the legacy inline `source_fingerprints`, or its `source_inventory` side file.

    A side file that is missing or does not match its recorded hash raises SOURCE_INVENTORY_INVALID.
    `feature` defaults to the folder of the checkpoint the receipt belongs to (`specs/<f>`)."""
    reference = receipt.get('source_inventory')
    if not reference:
        return receipt.get('source_fingerprints') or {}
    require(isinstance(reference, dict) and isinstance(reference.get('path'), str), 'SOURCE_INVENTORY_INVALID: ' + repr(reference))
    require(feature, 'SOURCE_INVENTORY_INVALID: the feature is required to read ' + reference['path'])
    label = feature + '/' + reference['path']
    try:
        data = inside(root, label).read_bytes()
    except OSError as exc:
        raise WorkflowError('SOURCE_INVENTORY_INVALID: ' + label + ': ' + str(exc)) from exc
    require(hashlib.sha256(data).hexdigest() == reference.get('sha256'), 'SOURCE_INVENTORY_INVALID: ' + label +
            ' does not match its recorded sha256')
    try:
        value = json.loads(data.decode('utf-8'))
    except ValueError as exc:
        raise WorkflowError('SOURCE_INVENTORY_INVALID: ' + label + ': ' + str(exc)) from exc
    require(isinstance(value, dict), 'SOURCE_INVENTORY_INVALID: ' + label)
    return value
