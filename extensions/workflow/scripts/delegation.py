#!/usr/bin/env python3
"""Policy, task metadata and skill discovery for opt-in workflow delegation."""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import yaml

TYPES = ('discovery', 'implementation', 'qa', 'documentation', 'review', 'coordination')
DEFAULT_TIERS = {'discovery': 'high', 'implementation': 'standard', 'qa': 'light',
                 'documentation': 'documentation', 'review': 'review', 'coordination': 'light'}
MODEL_PROFILES = ('high', 'standard', 'light', 'documentation', 'review')
STAGE_TYPES = {
    'scope': 'discovery', 'specify': 'discovery', 'clarify': 'discovery',
    'plan': 'discovery', 'tasks': 'discovery', 'qa_analyze': 'qa',
    'manual_analyze': 'documentation', 'analyze': 'review',
    'taskstoissues': 'coordination', 'execute': 'coordination',
    'verify': 'qa', 'review': 'review', 'qa_document': 'qa',
    'manual_update': 'documentation', 'ready': 'coordination', 'pr': 'coordination',
}
TASK_LINE = re.compile(r'^(\s*- \[([ xX])\]\s+(T\d{3,})\b.*)$')
MARKER = re.compile(r'^\s*<!-- sanduq-delegation (\{[^\n]+\}) -->\s*$')
INLINE_MARKER = re.compile(r'[ \t]*(<!-- sanduq-delegation \{[^\n]+\} -->)[ \t]*$')
OVERRIDE_KEY = re.compile(r'^specs/[^/]+/T\d{3,}$')


class DelegationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DelegationError(message)


def feature_identity(root, feature):
    """Return the one POSIX ``specs/<name>`` identity for any --feature spelling."""
    root = Path(root).resolve()
    text = str(feature).strip().replace('\\', '/')
    require(text, 'DELEGATION_FEATURE_INVALID')
    if Path(text).is_absolute():
        resolved = Path(text).resolve()
        require(resolved.is_relative_to(root), 'DELEGATION_FEATURE_INVALID: ' + str(feature))
        text = resolved.relative_to(root).as_posix()
    require(not re.match(r'^[A-Za-z]:|^/', text), 'DELEGATION_FEATURE_INVALID: ' + str(feature))
    parts = [part for part in text.split('/') if part not in ('', '.')]
    require(len(parts) == 2 and parts[0] == 'specs' and parts[1] != '..' and
            ':' not in parts[1], 'DELEGATION_FEATURE_INVALID: ' + str(feature))
    return 'specs/' + parts[1]


def process_alive(pid):
    """True unless this host proves ``pid`` has exited; unknown answers count as alive."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if os.name == 'nt':
        # os.kill(pid, 0) terminates the process on Windows, so ask the kernel.
        import ctypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no such process
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


# A lock file with no readable owner is only stale once it is this old: its
# creator writes the owner record immediately after the exclusive create.
LOCK_UNREADABLE_STALE_SECONDS = 60


def lock_owner(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def lock_is_stale(path, owner):
    """A lock is stale only when its recorded owner provably died on this host."""
    if owner is None or not isinstance(owner.get('pid'), int):
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            return False
        return age >= LOCK_UNREADABLE_STALE_SECONDS
    if owner.get('host') != socket.gethostname():
        return False
    return not process_alive(owner['pid'])


def recover_stale_lock(path):
    """Remove ``path`` only if it still holds the dead owner that was inspected.

    Unlinking after a check is not atomic: another stealer may already have
    replaced the lock with a live one. A single rename captures exactly one
    file; if the captured owner is not the dead one inspected, it goes back.
    """
    owner = lock_owner(path)
    if not lock_is_stale(path, owner):
        return False
    captured = path.with_name(path.name + '.stale-' + uuid.uuid4().hex)
    try:
        os.rename(path, captured)
    except OSError:
        return False
    if lock_owner(captured) == owner and lock_is_stale(captured, lock_owner(captured)):
        captured.unlink(missing_ok=True)
        return True
    try:
        # Put a live owner back without replacing any newer lock.
        os.link(captured, path)
        captured.unlink(missing_ok=True)
    except OSError:
        # A newer lock exists; the displaced owner detects the loss in
        # lock_held() and refuses to write.
        captured.unlink(missing_ok=True)
    return False


def lock_held(path, token):
    owner = lock_owner(path)
    return bool(owner and owner.get('token') == token)


def release_owned_lock(path, token):
    """Release our lock after transient Windows readers close their handles.

    Opening a lock file to inspect its owner can briefly prevent unlink on
    Windows. Recheck the token on every retry so a replacement lock is never
    removed by the former owner.
    """
    deadline = time.monotonic() + 5
    while True:
        owner = lock_owner(path)
        if owner is not None:
            if owner.get('token') != token:
                return
            try:
                path.unlink(missing_ok=True)
                return
            except PermissionError:
                pass
        elif not path.exists():
            return
        if time.monotonic() >= deadline:
            raise DelegationError('DELEGATION_LOCK_RELEASE_BUSY: could not release ' + str(path) +
                                  '; check that no process still has the file open')
        time.sleep(0.02)


@contextmanager
def file_lock(path, timeout, busy):
    """Exclusive cross-process lock that recovers a dead owner's lock file.

    Yields the owner token; callers that write shared state call lock_held()
    before their final write so a displaced owner never overwrites a newer one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except (FileExistsError, PermissionError):
            if recover_stale_lock(path):
                continue
            if time.monotonic() >= deadline:
                owner = lock_owner(path) or {}
                raise DelegationError(
                    busy + ': retry the command; held by pid ' + str(owner.get('pid')) + ' on ' +
                    str(owner.get('host')) + '. A lock whose owner has exited on this host is '
                    'recovered automatically; otherwise inspect that process before removing ' +
                    str(path)) from None
            time.sleep(0.05)
    try:
        os.write(fd, json.dumps({'pid': os.getpid(), 'host': socket.gethostname(),
                                 'token': token, 'created': time.time()}).encode())
        os.close(fd)
        yield token
    finally:
        release_owned_lock(path, token)


# Upgrade and install hold these while they snapshot, change and may roll back
# the project's managed files, including every delegation ledger.
MAINTENANCE_LOCKS = ('upgrade.lock', 'install.lock')


def maintenance_in_progress(root, owners=()):
    """Name the upgrade or install lock held by a process other than ``owners``.

    A lock with no readable owner yet counts as held: its creator writes the
    owner immediately after the exclusive create.
    """
    runtime = Path(root) / '.specify/workflow/runtime'
    for name in MAINTENANCE_LOCKS:
        path = runtime / name
        if not path.exists():
            continue
        pid = (lock_owner(path) or {}).get('pid')
        if pid is not None and pid in owners:
            continue
        return name
    return None


def require_no_maintenance(root, owners=()):
    held = maintenance_in_progress(root, owners)
    if held is None:
        return
    # These locks are never recovered automatically: a crashed upgrade or
    # install leaves its lock behind, and waiting will not clear it.
    lock = '.specify/workflow/runtime/' + held
    owner = lock_owner(Path(root) / lock) or {}
    pid = owner.get('pid')
    who = ('pid ' + str(pid) + (' (created ' + str(owner['created']) + ')' if owner.get('created') else '')
           if pid is not None else 'a process that has not recorded its pid')
    check = ('check with "tasklist /FI \\"PID eq ' + str(pid) + '\\"" on Windows or "ps -p ' + str(pid) +
             '" elsewhere' if pid is not None else 'check for a running upgrade.py or install.py')
    raise DelegationError(
        'WORKFLOW_UPGRADE_IN_PROGRESS: ' + lock + ' is held by ' + who + '. If that process is '
        'still running, retry once it finishes. If it is not (' + check + '), the upgrade or '
        'install crashed and the lock is stale: delete ' + lock + ', then rerun the upgrade or '
        'install, because its rollback may not have completed')


def validate_candidate(candidate):
    require(isinstance(candidate, dict) and
            set(candidate) in ({'harness', 'tier'}, {'harness', 'model'}),
            'DELEGATION_CANDIDATE_INVALID')
    require(candidate['harness'] in ('selected', 'codex', 'claude'), 'DELEGATION_HARNESS_INVALID')
    if 'tier' in candidate:
        require(candidate['tier'] in MODEL_PROFILES, 'DELEGATION_TIER_INVALID')
    else:
        require(candidate['model'] is None or
                isinstance(candidate['model'], str) and candidate['model'].strip(), 'DELEGATION_MODEL_INVALID')


def validate_route(route):
    require(isinstance(route, dict) and set(route) == {'preferred', 'fallbacks'},
            'DELEGATION_ROUTE_INVALID')
    validate_candidate(route['preferred'])
    require(isinstance(route['fallbacks'], list) and len(route['fallbacks']) <= 5,
            'DELEGATION_FALLBACKS_INVALID')
    for candidate in route['fallbacks']:
        validate_candidate(candidate)


def validate_delegation(config):
    require(isinstance(config, dict) and set(config) ==
            {'enabled', 'install_scope', 'stronger_retry', 'models', 'routes', 'overrides'},
            'DELEGATION_POLICY_INVALID')
    require(type(config['enabled']) is bool, 'DELEGATION_SELECTION_INVALID')
    require(config['install_scope'] in ('project', 'global'), 'DELEGATION_SCOPE_INVALID')
    require(type(config['stronger_retry']) is int and config['stronger_retry'] in (0, 1),
            'DELEGATION_RETRY_INVALID')
    models = config['models']
    require(isinstance(models, dict) and set(models) == {'codex', 'claude'},
            'DELEGATION_MODELS_INVALID')
    for harness in ('codex', 'claude'):
        require(isinstance(models[harness], dict) and
                set(models[harness]) == set(MODEL_PROFILES),
                'DELEGATION_MODELS_INVALID: ' + harness)
        require(all(isinstance(value, str) and value.strip() for value in models[harness].values()),
                'DELEGATION_MODEL_INVALID: ' + harness)
    routes = config['routes']
    require(isinstance(routes, dict) and set(routes) == set(TYPES), 'DELEGATION_ROUTES_INVALID')
    for route in routes.values():
        validate_route(route)
    require(isinstance(config['overrides'], dict), 'DELEGATION_OVERRIDES_INVALID')
    for key, route in config['overrides'].items():
        require(isinstance(key, str) and OVERRIDE_KEY.fullmatch(key),
                'DELEGATION_OVERRIDE_KEY_INVALID: ' + str(key))
        validate_route(route)
    return config


TASK_PREFIX = re.compile(r'^\s*(?:- \[[ xX]\]\s+)?(?:T\d{3,}\b\s*)?(?:\[[^\]]*\]\s*)*', re.I)
TYPE_MARKERS = (('implementation', r'\[(?:impl|implement|implementation|code)\]'),
                ('qa', r'\[(?:qa|test|tests|tdd)\]'),
                ('documentation', r'\[(?:doc|docs|documentation|manual)\]'),
                ('review', r'\[review\]'))
# Nouns that turn a leading "test", "review", "audit" or "inspect" into the
# name of something being built: "Audit log retention", "Review queue API",
# "Test runner integration" are implementation work.
COMPOUND_HEADS = (r'(?:logs?|logging|trails?|queues?|apis?|endpoints?|services?|tables?|models?|'
                  r'pages?|screens?|ui|components?|records?|events?|history|workflows?|status|'
                  r'forms?|panels?|widgets?|features?|flows?|pipelines?|jobs?|tools?|tooling|'
                  r'modes?|dashboards?|views?|requests?|threads?|steps?|stages?|dialogs?|modals?|'
                  r'buttons?|links?|runners?|frameworks?|environments?|env|config|configuration|'
                  r'infrastructure|infra|containers?|databases?|db|servers?|accounts?|users?|'
                  r'reporters?|matrix|schema|state|store|entries|entry|trigger|hooks?)')
# A documentation file named as the direct object or destination: a README,
# changelog or contributing guide with or without its extension, a path under a
# top-level docs/ folder, or any Markdown, reStructuredText or AsciiDoc file. A
# code file under a nested docs folder ("src/docs/parser.py") is not one.
DOC_FILE = (r'(?:(?:readme|changelog|contributing)(?:\.(?:md|mdx|rst|txt|adoc))?|'
            r'docs?/[\w./-]*[\w-]|(?:[\w.-]+/)*[\w.-]+\.(?:md|mdx|rst|adoc))')
DOC_END = r'(?:\s+(?:for|with|to|in|on|about|of)\b|\s*[.:;]?$)'
# Only the task's leading action decides unmarked work, so a domain noun such
# as "audit logging" or "review queue" never reroutes an implementation task,
# whether it leads the description or not.
LEADING_ACTIONS = (
    ('qa', r'(?:run|execute)\s+(?:[\w/-]+\s+){0,4}?(?:tests?|test suites?|suites?|checks)\b|'
           r'(?:write|add|create)\s+(?:[\w/-]+\s+){0,3}?tests?(?:\s+(?:for|of|to|in|covering|that)\b|\s*[.:;]?$)|'
           r'smoke[- ]test\b|test\b(?!\s+(?:data|fixtures?|harness|helpers?|utils?|utilities|'
           r'factor(?:y|ies)|doubles?|mocks?|suites?|coverage|plans?|results?|' + COMPOUND_HEADS[3:-1] +
           r')\b)|capture\s+(?:[\w/-]+\s+){0,2}?screenshots?\b'),
    ('documentation', r'document\s+(?:the|how|why|all|each|every|our|a|an)\b|'
                      r'document\s+(?:[\w/-]+\s+){0,4}?(?:in|into|to|under)\s+' + DOC_FILE + DOC_END + '|'
                      r'(?:write|update|add|create|revise)\s+(?:the\s+)?' + DOC_FILE +
                      r'(?:\s+(?:section|page|entry))?' + DOC_END + '|'
                      r'(?:write|update|add|create|revise)\s+(?:[\w/-]+\s+){0,3}?'
                      r'(?:docs?|documentation|readme|user manual|manual|release notes|changelog|guide)'
                      r'(?:\s+(?:section|page|entry))?' + DOC_END),
    ('review', r'(?:review|audit|inspect)\b(?!\s+' + COMPOUND_HEADS + r'\b)'),
)
# A leading check that also asks for code changes ("Inspect the parser and fix
# the crash") is implementation work that happens to start with a check.
MIXED_IMPLEMENTATION = re.compile(
    r'(?:\band\b|\bthen\b|&|,|;)\s+(?:then\s+)?(?:fix|fixes|implement|build|refactor|remove|'
    r'migrate|wire|patch|resolve|rewrite|change|correct|repair)\b')


def task_type(description):
    """Classify explicit task markers, then only an unambiguous leading action.

    Anything unclear stays implementation, the route every task can take.
    ``[Impl]`` (or ``[Implementation]``, ``[Code]``) forces implementation.
    """
    value = description.casefold()
    prefix = TASK_PREFIX.match(value)[0]
    for work_type, marker in TYPE_MARKERS:
        if re.search(marker, prefix):
            return work_type
    action = value[len(prefix):].strip()
    for work_type, pattern in LEADING_ACTIONS:
        if re.match(pattern, action):
            return 'implementation' if MIXED_IMPLEMENTATION.search(action) else work_type
    return 'implementation'


def selected_route(config, work_type, selected_host, identity=None):
    validate_delegation(config)
    require(work_type in TYPES, 'DELEGATION_TASK_TYPE_INVALID')
    require(selected_host in ('codex', 'claude'), 'DELEGATION_SELECTED_HOST_INVALID')
    rule = 'default:' + work_type
    route = config['routes'][work_type]
    if identity and identity in config['overrides']:
        route = config['overrides'][identity]
        rule = 'override:' + identity
    elif route != {'preferred': {'harness': 'selected', 'tier': DEFAULT_TIERS[work_type]},
                   'fallbacks': [{'harness': 'selected', 'model': None}]}:
        rule = 'yaml:' + work_type
    candidates = []
    for index, item in enumerate((route['preferred'], *route['fallbacks'])):
        harness = selected_host if item['harness'] == 'selected' else item['harness']
        model = config['models'][harness][item['tier']] if 'tier' in item else item['model']
        candidates.append({'harness': harness, 'requested_model': model,
                           'tier': item.get('tier'), 'rule': rule,
                           'choice': 'preferred' if index == 0 else 'fallback:' + str(index)})
    return candidates


def stronger_candidate(config, prior, selected_host):
    """One escalation to a stronger configured tier, when one exists."""
    tier = prior.get('tier')
    stronger = {'light': 'standard', 'standard': 'high',
                'documentation': 'high', 'review': 'high'}.get(tier)
    if not stronger:
        return None
    harness = prior['harness'] if prior['harness'] in ('codex', 'claude') else selected_host
    if config['models'][harness][stronger] == prior['requested_model']:
        return None
    return {'harness': harness, 'requested_model': config['models'][harness][stronger],
            'tier': stronger, 'rule': 'stronger-retry:' + tier + '->' + stronger,
            'choice': 'reassignment'}


def read_policy(root):
    from workflow import load_policy
    return load_policy(root)


def active_host(root):
    from workflow import active_host as host
    return host(root)


def ledger_path(root, feature):
    path = (root / feature / 'workflow/delegations.json').resolve()
    require(path.is_relative_to(root.resolve() / 'specs') and
            path.parent.parent == (root / feature).resolve(), 'DELEGATION_FEATURE_INVALID')
    return path


def active_task_ids(root, feature):
    path = ledger_path(root, feature)
    active = set()
    if path.exists():
        ledger = json.loads(path.read_text(encoding='utf-8'))
        active.update(attempt['identity'].rsplit('/', 1)[-1]
                      for attempt in ledger.get('attempts', [])
                      if attempt.get('status') in ('starting', 'running'))
    progress = root / feature / 'workflow/progress/state.json'
    if progress.is_file():
        state = json.loads(progress.read_text(encoding='utf-8'))
        active.update(task['id'] for task in state.get('tasks', [])
                      if task.get('status') == 'running')
    return active


def annotate_tasks(root, feature, config, selected_host=None):
    """Refresh pending task metadata without changing checkbox lines or active work."""
    validate_delegation(config)
    feature = feature_identity(root, feature)
    if not config['enabled']:
        return {'changed': False, 'annotated': 0, 'disabled': True}
    selected_host = selected_host or active_host(root)
    path = (root / feature / 'tasks.md').resolve()
    require(path.is_relative_to(root.resolve() / 'specs'), 'DELEGATION_FEATURE_INVALID')
    if not path.is_file():
        return {'changed': False, 'annotated': 0, 'missing_tasks': True}
    raw = path.read_bytes()
    bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
    lines = raw.decode('utf-8-sig').splitlines(keepends=True)
    running = active_task_ids(root, feature)
    default_newline = '\r\n' if any(line.endswith('\r\n') for line in lines) else '\n'
    output = []
    annotated = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        body = line.rstrip('\r\n')
        ending = line[len(body):]
        joined = INLINE_MARKER.search(body) if TASK_LINE.match(body) else None
        if joined:
            # Repair a marker an earlier release appended to a final task line
            # that had no newline. That release also added the newline after the
            # marker, so at end of file the original unterminated ending returns.
            old_marker = '  ' + joined[1]
            marker_ending = ending if index < len(lines) else ''
            body, ending = body[:joined.start()], default_newline
        elif index < len(lines) and MARKER.match(lines[index].rstrip('\r\n')):
            old_marker = lines[index].rstrip('\r\n')
            marker_ending = lines[index][len(old_marker):]
            index += 1
        else:
            old_marker, marker_ending = None, ending
        match = TASK_LINE.match(body)
        if not match:
            output.append(line)
            continue
        task_id = match[3]
        if match[2].lower() == 'x' or task_id in running:
            output.append(body + ending)
            if old_marker is not None:
                output.append(old_marker + marker_ending)
            continue
        work_type = task_type(match[1])
        route = selected_route(config, work_type, selected_host, feature + '/' + task_id)[0]
        metadata = {'task_id': task_id, 'task_type': work_type,
                    'preferred_harness': route['harness'],
                    'preferred_model': route['requested_model'], 'rule': route['rule']}
        # A final task line without a newline gains one before its marker; the
        # marker then ends the file the same way the task line did.
        output.append(body + (ending or default_newline))
        output.append('  <!-- sanduq-delegation ' + json.dumps(metadata, sort_keys=True) + ' -->' +
                      marker_ending)
        annotated += 1
    content = ''.join(output)
    original = ''.join(lines)
    if content != original:
        temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        temp.write_bytes(bom + content.encode('utf-8'))
        os.replace(temp, path)
    return {'changed': content != original, 'annotated': annotated, 'running_unchanged': sorted(running)}


SKILL_FILES = ('delegate.mjs', 'SKILL.md', 'contracts/result-schema-v2.md')
SKILL_ROOTS = ('.agents/skills', '.claude/skills', '.codex/skills')
# The driver contract this workflow depends on. A copy is reusable only when the
# driver itself reports these capabilities; files that merely exist prove nothing.
DRIVER_CONTRACT = 'delegate-task.driver.v1'
REQUIRED_CONTRACT = {
    'result_schema': 'delegate-task.result.v2',
    'commands': {'start', 'collect', 'doctor', 'contract'},
    'start_flags': {'--harness', '--task', '--cwd', '--model', '--sandbox', '--timeout',
                    '--constraint', '--allow-commit'},
    'collect_flags': {'--json'},
    'env': {'DELEGATE_RUNS_DIR'},
    'meta_fields': {'run_id', 'harness', 'model', 'constraint', 'permission', 'allow_commit'},
    'result_fields': {'run_id', 'harness', 'status', 'status_reason', 'status_provenance', 'summary',
                      'requested_model', 'actual_model', 'model_observed', 'tokens',
                      'dirty_paths_changed', 'head_changed', 'index_changed', 'coverage_complete',
                      'artifacts'},
}
INSTALL_LOCK_TIMEOUT = 180.0


def local_skill_paths(root, host):
    agent = '.agents' if host == 'codex' else '.claude'
    return [root / agent / 'skills/delegate-task',
            global_root() / agent / 'skills/delegate-task',
            global_root() / ('.codex' if host == 'codex' else '.claude') / 'skills/delegate-task']


def global_root():
    return Path.home()


def is_junction(path):
    """True for a Windows directory junction, which ``is_symlink`` does not report.

    ``Path.is_junction`` only exists from Python 3.12; earlier versions read the
    reparse tag directly.
    """
    path = Path(path)
    if hasattr(path, 'is_junction'):
        return path.is_junction()
    if os.name != 'nt':
        return False
    try:
        return os.lstat(path).st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
    except (OSError, AttributeError):
        return False


def is_link(path):
    """A symlink or a Windows junction: an entry that points at a folder elsewhere."""
    return Path(path).is_symlink() or is_junction(path)


def driver_compatibility(node, driver):
    """Return None when the driver reports the required contract, else the reason."""
    try:
        result = subprocess.run([node, str(driver), 'contract'], capture_output=True, text=True,
                                encoding='utf-8', timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 'contract query failed: ' + str(exc)[:200]
    if result.returncode:
        return 'driver predates the contract command (exit ' + str(result.returncode) + ')'
    try:
        contract = json.loads(result.stdout)
    except ValueError:
        return 'contract output is not JSON'
    if not isinstance(contract, dict) or contract.get('contract') != DRIVER_CONTRACT:
        found = contract.get('contract') if isinstance(contract, dict) else None
        return 'contract ' + str(found) + ' is not ' + DRIVER_CONTRACT
    if contract.get('result_schema') != REQUIRED_CONTRACT['result_schema']:
        return ('result schema ' + str(contract.get('result_schema')) + ' is not ' +
                REQUIRED_CONTRACT['result_schema'])
    for key, required in REQUIRED_CONTRACT.items():
        if key == 'result_schema':
            continue
        missing = sorted(required - set(contract.get(key) or ()))
        if missing:
            return key + ' missing ' + ', '.join(missing)
    if (contract.get('exit_codes') or {}).get('collect_still_running') != 3:
        return 'collect does not report a running run with exit code 3'
    return None


def check_copy(folder, node):
    """Classify one installed copy as None (usable), 'broken' or an incompatibility reason."""
    driver = folder / 'delegate.mjs'
    if not all((folder / name).is_file() for name in SKILL_FILES):
        return 'broken', None
    if subprocess.run([node, '--check', str(driver)], capture_output=True).returncode:
        return 'broken', None
    reason = driver_compatibility(node, driver)
    return ('incompatible', reason) if reason else (None, None)


def inspect_skill(root, host):
    """Find the first usable project or global copy; report why others were rejected."""
    override = os.environ.get('SANDUQ_DELEGATE_DRIVER')
    candidates = ([Path(override).parent] if override else []) + local_skill_paths(root, host)
    plugin = os.environ.get('CLAUDE_PLUGIN_ROOT')
    if plugin:
        candidates.append(Path(plugin) / 'skills/delegate-task')
    broken, incompatible = [], []
    node = shutil.which('node')
    for folder in dict.fromkeys(candidates):
        if not folder.exists():
            continue
        if node is None:
            return {'ok': False, 'error': 'NODE_MISSING'}
        problem, reason = check_copy(folder, node)
        if problem == 'broken':
            broken.append(str(folder))
            continue
        if problem:
            incompatible.append({'path': str(folder), 'reason': reason})
            continue
        return {'ok': True, 'driver': str((folder / 'delegate.mjs').resolve()),
                'scope': 'project' if folder.is_relative_to(root) else 'global'}
    error = ('DELEGATE_SKILL_BROKEN' if broken else
             'DELEGATE_SKILL_INCOMPATIBLE' if incompatible else 'DELEGATE_SKILL_MISSING')
    return {'ok': False, 'error': error, 'broken': broken, 'incompatible': incompatible}


def bundled_skill():
    folder = Path(__file__).resolve().parents[1] / 'assets/delegate-task'
    if folder.is_dir():
        return folder
    # Canonical source checkout: packaged releases carry the asset instead.
    source = Path(__file__).resolve().parents[3] / 'skills/agent-tools/skills/delegate-task'
    return source if source.is_dir() else None


def backup_root(root, scope):
    """Backups live outside every skill discovery root, so no stale SKILL.md is found."""
    base = root if scope == 'project' else global_root()
    folder = (base / '.specify/workflow/backups/delegate-task' if scope == 'project' else
              base / '.sanduq/backups/delegate-task')
    resolved = folder.resolve()
    require(resolved.is_relative_to(base.resolve()) and
            not any(resolved.is_relative_to((base / skills).resolve()) for skills in SKILL_ROOTS),
            'DELEGATE_SKILL_BACKUP_PATH_INVALID')
    return folder


def move_aside(item, backups):
    """Move one directory entry, never its tree file by file, into a fresh backup slot."""
    backups.mkdir(parents=True, exist_ok=True)
    slot = backups / (item.name + '.' + uuid.uuid4().hex)
    try:
        item.rename(slot)
    except OSError as exc:
        # A single rename keeps every customised file together; never fall back
        # to a recursive copy-and-delete that could stop halfway.
        raise DelegationError('DELEGATE_SKILL_BACKUP_FAILED: ' + str(exc)) from exc
    return slot


def install_lock_path(root, scope):
    base = root / '.specify/workflow/runtime' if scope == 'project' else global_root() / '.sanduq/runtime'
    return base / 'delegate-skill-install.lock'


def legacy_backups(root):
    """Sibling backups earlier builds left inside skill discovery roots, by scope."""
    found = {'project': [], 'global': []}
    for scope, base in (('project', root), ('global', global_root())):
        for skills in SKILL_ROOTS:
            folder = base / skills
            if folder.is_dir():
                found[scope] += sorted(folder.glob('delegate-task.sanduq-backup-*'))
    return found


def move_legacy_backups(root, legacy):
    """Move each legacy backup to its own scope's backup root, never across scopes."""
    moved = []
    for scope, items in legacy.items():
        if not items:
            continue
        backups = backup_root(root, scope)
        if scope == 'project':
            from workflow import ensure_local_excludes
            ensure_local_excludes(root)
        for item in items:
            moved.append({'from': str(item), 'to': str(move_aside(item, backups))})
    return moved


def rejected_copies(status):
    """Normalise inspect_skill rejections to path/reason records."""
    return ([{'path': path, 'reason': 'broken: required files missing or driver fails node --check'}
             for path in status.get('broken') or []] + list(status.get('incompatible') or []))


def install_skill(root, host, scope, force_scope=False, upgrade_owner=None):
    """Reuse any usable copy; otherwise install the bundled skill at ``scope``.

    Installation, legacy backup moves and backup rollback run under a lock per
    scope, so concurrent dispatchers never interleave; a waiter re-inspects and
    reuses the copy the first one installed. ``force_scope`` refreshes the copy
    at ``scope`` even when a usable one exists. While an upgrade or install
    owns the project's managed files, only that upgrade or install may change a
    skill; everyone else is refused inside the project lock, which it drains.
    """
    require(scope in ('project', 'global'), 'DELEGATION_SCOPE_INVALID')
    legacy = legacy_backups(root)
    with contextlib.ExitStack() as stack:
        stack.enter_context(file_lock(install_lock_path(root, 'project'), INSTALL_LOCK_TIMEOUT,
                                      'DELEGATE_SKILL_INSTALL_BUSY'))
        require_no_maintenance(root, (os.getpid(), upgrade_owner))
        if scope == 'global' or legacy['global']:
            stack.enter_context(file_lock(install_lock_path(root, 'global'), INSTALL_LOCK_TIMEOUT,
                                          'DELEGATE_SKILL_INSTALL_BUSY'))
        return install_skill_locked(root, host, scope, force_scope)


def install_skill_locked(root, host, scope, force_scope):
    agent = '.agents' if host == 'codex' else '.claude'
    target_root = root if scope == 'project' else global_root()
    target = target_root / agent / 'skills/delegate-task'
    existing = inspect_skill(root, host)
    if existing.get('error') == 'NODE_MISSING':
        return existing
    # Earlier builds left sibling backups inside discovery roots; they leave
    # even when a usable copy is reused, so no stale SKILL.md stays visible.
    moved = move_legacy_backups(root, legacy_backups(root))
    notices = ['DELEGATE_SKILL_LEGACY_BACKUP_MOVED: ' + item['from'] + ' -> ' + item['to']
               for item in moved]
    if existing['ok'] and not force_scope:
        return {**existing, 'installed': False, 'legacy_backups_moved': moved, 'notices': notices}
    node = shutil.which('node')
    require(node is not None, 'NODE_MISSING')
    source = bundled_skill()
    require(source is not None and all((source / name).is_file() for name in SKILL_FILES),
            'DELEGATE_SKILL_PACKAGE_MISSING')
    target.parent.mkdir(parents=True, exist_ok=True)
    require(target.parent.resolve().is_relative_to(target_root.resolve()),
            'DELEGATE_SKILL_TARGET_OUTSIDE_SCOPE')
    if scope == 'project':
        from workflow import ensure_local_excludes
        ensure_local_excludes(root)
    backups = backup_root(root, scope)
    backups.mkdir(parents=True, exist_ok=True)
    # Build and verify the new copy outside the discovery root first, so a
    # failed or interrupted install never leaves a partial skill behind.
    staging = backups / ('.staging-' + uuid.uuid4().hex)
    try:
        shutil.copytree(source, staging, ignore=shutil.ignore_patterns('test', 'runs', 'node_modules'))
        problem, reason = check_copy(staging, node)
        require(problem is None, 'DELEGATE_SKILL_INSTALL_FAILED: ' + str(reason or problem))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    rejected = {item['path']: item['reason'] for item in rejected_copies(existing)}
    # A dangling junction neither exists nor is a symlink, but it is still the
    # user's entry: move the link itself aside so a failure can put it back.
    dangling = is_link(target) and not target.exists()
    backup = move_aside(target, backups) if target.exists() or is_link(target) else None
    placed = False
    try:
        staging.rename(target)
        placed = True
        require(all((target / name).is_file() for name in SKILL_FILES), 'DELEGATE_SKILL_INSTALL_FAILED')
    except Exception:
        # Only the copy this call put in place is removed. Anything still at the
        # target after a failed rename belongs to someone else and stays.
        if placed and not is_link(target) and target.exists():
            require(target.resolve().is_relative_to(target_root.resolve()),
                    'DELEGATE_SKILL_ROLLBACK_OUTSIDE_SCOPE')
            shutil.rmtree(target)
        shutil.rmtree(staging, ignore_errors=True)
        if backup is not None and not os.path.lexists(target):
            backup.rename(target)
        raise
    replaced = None
    if backup is not None:
        replaced = [{'path': str(target), 'backup': str(backup),
                     'reason': rejected.get(str(target), 'dangling link' if dangling else
                                            'replaced at the configured scope')}]
        notices.append('DELEGATE_SKILL_REPLACED: ' + str(target) + ' (' + replaced[0]['reason'] +
                       ') was moved to ' + str(backup) + '; carry any local customisation '
                       'into the new copy by hand')
    return {'ok': True, 'driver': str((target / 'delegate.mjs').resolve()), 'scope': scope,
            'installed': True, 'backup': str(backup) if backup else None,
            'replaced': replaced, 'rejected': rejected_copies(existing) or None,
            'legacy_backups_moved': moved, 'notices': notices}


def owned_scope(root, host, driver):
    """The scope whose Sanduq install location holds ``driver``, else None.

    Only a real folder at the project or global location Sanduq installs to is
    Sanduq's to refresh. A driver override, a plugin copy, another discovery
    root or a symlinked or junctioned folder belongs to someone else.
    """
    agent = '.agents' if host == 'codex' else '.claude'
    folder = Path(driver).resolve().parent
    for scope, base in (('project', root), ('global', global_root())):
        location = base / agent / 'skills/delegate-task'
        if not is_link(location) and location.is_dir() and location.resolve() == folder:
            return scope
    return None


def health_error(status):
    """The failure code, with the failing copy and next action when doctor names them."""
    error = status.get('error', 'DELEGATE_SKILL_UNAVAILABLE')
    return error + ': ' + status['path'] + ': ' + status['action'] if status.get('action') else error


def doctor(root, host, install=False, scope='project', upgrade_owner=None):
    node = shutil.which('node')
    if not node:
        return {'ok': False, 'error': 'NODE_MISSING'}
    probe = subprocess.run([node, '--version'], capture_output=True, text=True)
    version = re.search(r'v?(\d+)', probe.stdout)
    if probe.returncode or not version or int(version[1]) < 18:
        return {'ok': False, 'error': 'NODE_18_REQUIRED'}
    status = (install_skill(root, host, scope, upgrade_owner=upgrade_owner) if install
              else inspect_skill(root, host))
    if not status['ok']:
        return status
    result = subprocess.run([node, status['driver'], 'doctor'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8')
    refresh = owned_scope(root, host, status['driver'])
    if result.returncode and install and not status.get('installed') and refresh:
        # Refresh the copy that failed, where it is. Installing at the
        # configured scope instead would leave the failing copy first in the
        # search order, and every later dispatch would replace the other one.
        first = status
        status = install_skill(root, host, refresh, force_scope=True, upgrade_owner=upgrade_owner)
        status['notices'] = (first.get('notices') or []) + (status.get('notices') or [])
        result = subprocess.run([node, status['driver'], 'doctor'], cwd=root,
                                capture_output=True, text=True, encoding='utf-8')
    if result.returncode:
        owned = owned_scope(root, host, status['driver']) is not None
        action = ('the copy was refreshed from the bundle and still fails; inspect the diagnostic'
                  if status.get('installed') else
                  'run "python .specify/extensions/workflow/scripts/delegation.py install" to refresh it'
                  if owned else
                  'Sanduq does not own this copy (a driver override, plugin, symlinked folder or '
                  'another discovery root) and will not replace it; repair it, or remove it so a '
                  'Sanduq install is used')
        return {**status, 'ok': False, 'error': 'DELEGATE_SKILL_DOCTOR_FAILED',
                'path': str(Path(status['driver']).resolve().parent), 'owned': owned,
                'action': action, 'diagnostic': result.stderr.strip() or result.stdout.strip()}
    available = {}
    cli_errors = {}
    for harness in ('codex', 'claude'):
        line = next((line for line in result.stdout.splitlines()
                     if re.match(r'^' + harness + r'\s', line)), '')
        if not line or 'NOT FOUND on PATH' in line:
            cli_errors[harness] = 'AGENT_CLI_MISSING'
        elif 'UNDECODABLE SHIM' in line or 'BROKEN:' in line:
            cli_errors[harness] = 'AGENT_CLI_BROKEN'
        available[harness] = harness not in cli_errors
    return {**status, 'node': probe.stdout.strip(), 'harnesses': available,
            'cli_errors': cli_errors, 'diagnostic': result.stdout.strip()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('doctor', 'install', 'annotate', 'route'):
        command = sub.add_parser(action)
        if action in ('annotate', 'route'):
            command.add_argument('--feature', required=True)
        if action == 'route':
            command.add_argument('--id', required=True)
            command.add_argument('--type', choices=TYPES, required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        policy = read_policy(root)
        config = policy['delegation']
        host = active_host(root)
        if args.action in ('doctor', 'install'):
            result = doctor(root, host, args.action == 'install', config['install_scope'])
        elif args.action == 'annotate':
            result = annotate_tasks(root, args.feature, config, host)
        else:
            # The same specs/<name> identity the dispatcher and overrides use.
            require(re.fullmatch(r'T\d{3,}|stage:[a-z_]+', args.id), 'DELEGATION_IDENTITY_INVALID')
            identity = feature_identity(root, args.feature) + '/' + args.id
            result = {'enabled': config['enabled'], 'identity': identity, 'type': args.type,
                      'candidates': selected_route(config, args.type, host, identity) if config['enabled'] else []}
        print(json.dumps(result, indent=2))
        return 0 if result.get('ok', True) else 1
    except (DelegationError, OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
