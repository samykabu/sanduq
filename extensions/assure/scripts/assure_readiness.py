#!/usr/bin/env python3
"""Mechanical checks on <feature>/qa/assertions.json before Analyze records. Exit 1 on any error.

Deterministic only: it proves the record is well formed, cited files and literal test names exist, task ids
exist, and fixture/emulated evidence is not used for a real boundary. It cannot prove a test covers an assertion."""
import argparse
import json
import re
import sys
from pathlib import Path
try:
    from sanduq_freshness import MANUAL_TASKS
except ModuleNotFoundError:
    # Source checkout only; release archives bundle the canonical helper.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/shared'))
    from sanduq_freshness import MANUAL_TASKS

SCHEMA = 'assure-readiness/1'
RECORD = 'qa/assertions.json'
ENUMS = {'risk': {'critical', 'major', 'minor'},
         'layer': {'unit', 'integration', 'api-contract', 'e2e', 'native', 'os-contract', 'manual', 'visual'},
         'boundary': {'real', 'any'}, 'evidence': {'real', 'fixture', 'emulated'},
         'disposition': {'reuse', 'extend', 'add', 'not-applicable'}}
REQUIRED = ('id', 'requirement', 'risk', 'observable', 'layer', 'boundary', 'evidence', 'disposition')
# Test-economy wording only. Bare "runtime" or "cost" is not a waiver: a product requirement can be about either.
# Product words such as reduced-motion, a budget export or a cut-over do not match. shortcut: a keyword screen catches
# common phrasing, not a paraphrase; the cited basis and human review decide.
ECONOMY = re.compile(
    r'\b(?:minimi[sz]e|minimi[sz]ing|fewer|smallest|leanest)(?![-\w])[^.\n]{0,30}\b(?:tests?|suite)\b'
    r'|\b(?:reduce|reduced|reducing|trim|cut)(?![-\w])\s+(?:the |our )?(?:number of )?(?:tests?|suite)\b'
    r'|\b(?:test|tests|runtime|run-time|time|ci|cost|suite)\s+budget\b|\btoo (?:many|slow)\b'
    r'|\b(?:test count|suite runtime|test runtime|execution time|time limit)\b', re.I)
# Groups: 1-2 triple-quoted, 3 "...", 4 '...', 5 `...`, 6 // or /* */ comment, 7 # comment.
SOURCE = re.compile(r"""(?s)(\"\"\"|\'\'\')(.*?)\1|"((?:\\.|[^"\\\n])*)"|'((?:\\.|[^'\\\n])*)'|`((?:\\.|[^`\\])*)`"""
                    r"""|(//[^\n]*|/\*.*?\*/)|(\#[^\n]*)""")
# Documents and JSON data are never tests; YAML stays allowed because some runners use YAML flows.
NOT_TESTS = {'.md', '.markdown', '.mdx', '.rst', '.txt', '.json'}
BLOCK = re.compile(r'<!-- qa-prepare:start -->(.*?)<!-- qa-prepare:end -->', re.S)
TASK = re.compile(r'^\s*- \[[ xX]\] (T\d+)\b(.*)$', re.M)


def norm(text):
    return ' '.join(str(text).lower().split())


def norm_space(text):
    return ' '.join(str(text).split())


def has_identity(text, name, suffix):
    """True when `name` is a whole string literal or a whole identifier in code, ignoring comments.
    shortcut: regex scan, not a parser (a Rust lifetime can pair with a later quote); a match shows the
    name exists in code, never that the test exercises the assertion."""
    name, code, last = norm_space(name), [], 0
    for m in SOURCE.finditer(text):
        code.append(text[last:m.start()])
        last = m.end()
        if m.group(7) and suffix != '.py':
            code.append(m.group(7))  # `#` opens a comment only in Python; Rust attributes and C# regions stay code
        literal = next((m.group(i) for i in (2, 3, 4, 5) if m.group(i) is not None), None)
        if literal is not None and norm_space(literal) == name:
            return True
    code.append(text[last:])
    return bool(re.fullmatch(r'[A-Za-z_][\w$]*', name)) and bool(
        re.search(r'(?<![\w$])' + re.escape(name) + r'(?![\w$])', ' '.join(code)))


def inside(root, value):
    """Resolved path when `value` stays inside root (links resolved), else None."""
    try:
        path = (root / value).resolve()
        path.relative_to(root.resolve())
        return path
    except (ValueError, OSError):
        return None


def check(root, feature):
    """Return (errors, warnings, data); each error is {code, assertion, message}."""
    root, feature = Path(root).resolve(), Path(feature)
    feature = feature if feature.is_absolute() else root / feature
    errors, warnings = [], []
    # The directory holding every feature (for example specs/): another feature's records are not proof.
    features_dir = feature.resolve().parent if feature.resolve().parent != root else feature.resolve()
    err = lambda code, a, msg: errors.append({'code': code, 'assertion': a, 'message': msg})
    path = feature / RECORD
    if not path.is_file():
        err('readiness-missing', None, f'{RECORD} is required before Analyze can record')
        return errors, warnings, []
    try:
        doc = json.loads(path.read_text(encoding='utf-8-sig'))
    except ValueError as exc:
        err('readiness-invalid-json', None, str(exc))
        return errors, warnings, []
    if not isinstance(doc, dict) or doc.get('schema') != SCHEMA:
        err('schema-unsupported', None, f'schema must be {SCHEMA}')
        return errors, warnings, []
    rows = doc.get('assertions')
    if not isinstance(rows, list) or not rows:
        err('assertions-empty', None, 'assertions must be a non-empty list')
        return errors, warnings, []
    spec = (feature / 'spec.md').read_text(encoding='utf-8-sig') if (feature / 'spec.md').is_file() else ''
    tasks_text = (feature / 'tasks.md').read_text(encoding='utf-8-sig') if (feature / 'tasks.md').is_file() else ''
    # Analyze freshness ignores the User Manual block, so a task inside it cannot back a QA row.
    tasks_text = MANUAL_TASKS.sub(b'', tasks_text.encode('utf-8')).decode('utf-8')
    task_ids = {m.group(1) for m in TASK.finditer(tasks_text)}
    ids, identities, cited, gaps = set(), set(), set(), set()
    for index, row in enumerate(rows):
        label = row.get('id') if isinstance(row, dict) and isinstance(row.get('id'), str) else f'#{index}'
        if not isinstance(row, dict):
            err('field-invalid', label, 'assertion must be an object')
            continue
        bad = False
        for field in REQUIRED:
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                err('field-missing', label, f'{field} is required'); bad = True
            elif field in ENUMS and value not in ENUMS[field]:
                err('field-invalid', label, f'{field} must be one of {sorted(ENUMS[field])}'); bad = True
        if bad:
            continue
        if label in ids:
            err('assertion-duplicate-id', label, 'id repeats')
        ids.add(label)
        identity = (norm(row['requirement']), norm(row['observable']), row['layer'])
        if identity in identities:
            err('assertion-duplicate-identity', label, 'same requirement, observable and layer as another assertion')
        identities.add(identity)
        if not re.search(r'(?<![\w-])' + re.escape(row['requirement'].strip()) + r'(?![\w-])', spec):
            err('requirement-unknown', label, f"{row['requirement']} is not in spec.md")
        cited.add(row['requirement'].strip())
        disposition, proof, tasks = row['disposition'], row.get('proof') or [], row.get('tasks') or []
        if disposition in ('extend', 'add'):
            gaps.add(label)
        if not isinstance(proof, list) or not isinstance(tasks, list):
            err('field-invalid', label, 'proof and tasks must be lists'); continue
        if row['boundary'] == 'real' and row['evidence'] != 'real':
            err('real-boundary-evidence', label, f"{row['evidence']} evidence cannot close a real boundary")
        if disposition == 'not-applicable':
            basis = row.get('basis')
            if proof or tasks:
                err('na-has-proof-or-tasks', label, 'not-applicable carries no proof or tasks')
            source = inside(root, basis.get('source', '')) if isinstance(basis, dict) and basis.get('source') else None
            quoted = basis.get('cite') if isinstance(basis, dict) else ''
            if ECONOMY.search(str(row.get('reason') or '')) or (row['risk'] == 'critical' and ECONOMY.search(str(quoted or ''))):
                err('na-waiver', label, 'test economy (count, budget, minimising the suite) cannot make an assertion not '
                    'applicable; a critical assertion needs a product-scope basis')
            if not (str(row.get('reason') or '').strip() and source and source.is_file()
                    and basis.get('cite') and norm(basis['cite']) in norm(source.read_text(encoding='utf-8-sig', errors='replace'))):
                err('na-unsupported', label, 'reason plus basis {source, cite} quoting an existing in-root file is required')
            continue
        if disposition == 'add' and proof:
            err('add-with-proof', label, 'add means no existing proof; use extend or reuse')
        if disposition in ('reuse', 'extend') and not proof:
            err('proof-required', label, f'{disposition} needs at least one proof entry')
        if disposition in ('extend', 'add') and not tasks:
            err('task-required', label, f'{disposition} needs a linked task id in tasks.md')
        for task in tasks:
            if task not in task_ids:
                err('task-unknown', label, f'{task} is not a task in tasks.md')
        for item in proof:
            where = item.get('path') if isinstance(item, dict) else None
            name = item.get('name') if isinstance(item, dict) else None
            if not (isinstance(where, str) and where and isinstance(name, str) and name.strip()):
                err('field-missing', label, 'each proof needs path and name'); continue
            target = inside(root, where)
            if target is None:
                err('proof-path-outside-root', label, where); continue
            if not target.is_file():
                err('proof-path-missing', label, where); continue
            if target.is_relative_to(feature.resolve()) or target.is_relative_to(features_dir):
                err('proof-path-in-feature', label, f'{where} is a feature record or document, not a test'); continue
            if target.is_relative_to(root / '.specify') or target.suffix.lower() in NOT_TESTS:
                err('proof-path-not-test', label, f'{where} is project governance or a document/JSON file, not a test'); continue
            if not has_identity(target.read_text(encoding='utf-8-sig', errors='replace'), name, target.suffix):
                err('proof-name-not-found', label, f'"{name}" is not a whole test name or identifier in code in {where} '
                    '(comments and partial matches do not count)')
    for block in BLOCK.findall(tasks_text):
        for match in TASK.finditer(block):
            if not any(re.search(r'(?<![\w-])' + re.escape(i) + r'(?![\w-])', match.group(2)) for i in gaps):
                err('block-task-uncovered', match.group(1), 'qa-prepare task cites no extend or add assertion id')
    for token in sorted(set(re.findall(r'\b(?:FR|SC)-\d+\b', spec)) - cited):
        warnings.append({'code': 'requirement-unreferenced', 'assertion': None, 'message': token})
    return errors, warnings, rows


def proof_paths(root, feature):
    """Repo-relative proof files plus not-applicable basis files, for freshness outputs (clean check only)."""
    doc = json.loads((Path(feature) / RECORD).read_text(encoding='utf-8-sig'))
    root = Path(root).resolve()
    found = [p['path'] for row in doc['assertions'] for p in row.get('proof') or []]
    found += [row['basis']['source'] for row in doc['assertions'] if row['disposition'] == 'not-applicable']
    return sorted({inside(root, value).relative_to(root).as_posix() for value in found})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check',))
    parser.add_argument('--feature', required=True, type=Path)
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    errors, warnings, rows = check(args.repo_root, args.feature)
    if args.json:
        print(json.dumps({'ok': not errors, 'errors': errors, 'warnings': warnings, 'assertions': len(rows),
                          'semantic': 'not-verified'}))
    else:
        print('error ' + '\nerror '.join(f"{e['code']} [{e['assertion'] or '-'}] {e['message']}" for e in errors)
              if errors else f'ok assertions={len(rows)} (semantic coverage not verified)')
        for w in warnings:
            print(f"warning {w['code']} {w['message']}")
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
