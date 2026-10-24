"""Assessed accepted-Scope recovery. No claim, approval, migration or downstream re-stamp."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import wf_core as core
from wf_core import (WorkflowError, require, read, digest, canonical_path, _no_link_below,
                     git, run_git, locked, now, checkpoint_policy_digest)
from wf_fingerprints import fingerprint_files, source_fingerprints_of, source_fingerprints
from wf_receipts import required_inputs, validate_evidence_snapshots, scope_proof_authority
from sanduq_hash import portable_content, text_attributes
import evidence_snapshot
import lifecycle

PLAN = 'sanduq.scope-revalidation-plan.v1'
ASSESSMENT = 'sanduq.scope-revalidation.v1'
CONTEXT = {'.github/memory/project-memory.md', 'UIUX-Deviations.md'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


@contextmanager
def fresh_reads():
    """Recovery's final reread must not reuse the CLI operation's earlier observations."""
    previous, bytecode = core._OPERATION, sys.dont_write_bytecode
    core._OPERATION, sys.dont_write_bytecode = None, True
    try:
        yield
    finally:
        core._OPERATION, sys.dont_write_bytecode = previous, bytecode


def path_at(root, label):
    name = canonical_path(root, label)
    require(_no_link_below(root, name.split('/')), 'SCOPE_RECOVERY_UNSAFE_PATH: ' + label)
    return root / name


def raw(root, label, optional=False):
    path = path_at(root, label)
    if optional and not path.exists():
        return None
    require(path.is_file(), 'SCOPE_RECOVERY_INPUT_MISSING: ' + label)
    return path.read_bytes()


def blob(root, revision, label):
    result = run_git(root, 'show', revision + ':' + label)
    require(result.returncode == 0, 'SCOPE_RECOVERY_HISTORY_MISSING: ' + revision + ':' + label)
    return result.stdout


def proof_blob(root, anchor, name, expected, attr):
    """Original proof bytes. Stage output is committed after its receipt's head, so look later in
    reachable history, accepting only bytes that reproduce the recorded fingerprint under the
    original attributes (or exact storage). Never a current file or a guessed hash."""
    found = run_git(root, 'show', anchor + ':' + name)
    if found.returncode == 0:
        return found.stdout, anchor
    matches = {}
    for rev in git(root, 'rev-list', 'HEAD', '--', name).splitlines():
        shown = run_git(root, 'show', rev + ':' + name)
        if (shown.returncode == 0 and run_git(root, 'merge-base', '--is-ancestor', anchor, rev).returncode == 0
                and expected in (sha(portable_content(name, shown.stdout, attr)), sha(shown.stdout))):
            matches.setdefault(shown.stdout, rev)
    require(len(matches) == 1, 'SCOPE_RECOVERY_HISTORY_MISSING: ' + anchor + ':' + name)
    return next(iter(matches.items()))


def historical_attributes(root, revision, paths):
    # Local/global attribute overrides have no immutable historical provenance.
    info = Path(git(root, 'rev-parse', '--git-path', 'info/attributes'))
    if not info.is_absolute():
        info = root / info
    require(not info.exists() or not info.read_bytes().strip(), 'SCOPE_RECOVERY_ATTRIBUTE_HISTORY_UNKNOWN: info/attributes')
    configured = run_git(root, 'config', '--path', '--get', 'core.attributesFile', text=True).stdout.strip()
    default = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'git/attributes'
    require(not configured and not default.exists(), 'SCOPE_RECOVERY_ATTRIBUTE_HISTORY_UNKNOWN: global attributes')
    result = run_git(root, '-c', 'core.attributesFile=' + os.devnull, 'check-attr',
                     '--source=' + revision, '-z', '--stdin', 'text',
                     input=('\0'.join(paths) + '\0').encode(),
                     env={**os.environ, 'GIT_ATTR_NOSYSTEM': '1'})
    require(result.returncode == 0, 'SCOPE_RECOVERY_ATTRIBUTE_HISTORY_UNAVAILABLE: ' + result.stderr.decode('utf-8', 'replace'))
    fields = result.stdout.decode().split('\0')
    return {fields[i]: fields[i + 2] for i in range(0, len(fields) - 1, 3)}


def history(run, state, receipt):
    """An immutable reachable checkpoint carrying this exact acceptance, not a guessed old hash."""
    label = run.relative + '/workflow/checkpoint.json'
    revisions = git(run.root, 'rev-list', 'HEAD', '--', label).splitlines()
    anchors = []
    for rev in revisions:
        shown = run_git(run.root, 'show', rev + ':' + label)
        if shown.returncode:
            continue
        try:
            previous = json.loads(shown.stdout)
        except ValueError:
            continue
        if (all(previous.get(k) == state.get(k) for k in ('run_id', 'branch', 'feature', 'issue'))
                and previous.get('receipts', {}).get('scope') == receipt):
            # The first commit containing this acceptance fixes the historical attribute context.
            candidates = []
            for parent in git(run.root, 'rev-list', '--parents', '-n', '1', rev).split()[1:]:
                old = run_git(run.root, 'show', parent + ':' + label)
                try:
                    same = not old.returncode and json.loads(old.stdout).get('receipts', {}).get('scope') == receipt
                except ValueError:
                    same = False
                if same:
                    candidates.append(parent)
            if not candidates:
                anchors.append((rev, previous))
    require(len(anchors) == 1, 'SCOPE_RECOVERY_HISTORY_MISSING_OR_AMBIGUOUS: expected one original accepted checkpoint')
    return anchors[0]


def provider(run, receipt, original):
    source = Path(__file__).resolve().parents[2] / 'scope/scripts/scope.py'
    require(source.is_file(), 'SCOPE_RECOVERY_PROVIDER_UNAVAILABLE: install the compatible Scope package beside Workflow')
    spec = importlib.util.spec_from_file_location('sanduq_scope_recovery_provider', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    required = 'validate_binding' if receipt is None else 'revalidate_accepted'
    require(hasattr(module.Scope, required), 'SCOPE_RECOVERY_PROVIDER_INCOMPATIBLE: Scope 1.11.1 required')
    try:
        app = module.Scope(run.root)
        return app.validate_binding(original) if receipt is None else app.revalidate_accepted(run.relative, receipt, original)
    except module.ScopeError as exc:
        raise WorkflowError(str(exc)) from exc


def native_parent_children(root, anchor, feature, original, bound):
    """Children of the retained parent approval, from the native parent proof under its recorded fingerprint."""
    label = feature + '/scope/approved-parent-context/publication-result.json'
    require(len(bound.get(label, ())) == 1, 'SCOPE_RECOVERY_APPROVAL_HISTORY_REQUIRED: unbound ' + label)
    attr = historical_attributes(root, anchor, [label])[label]
    data, _ = proof_blob(root, anchor, label, next(iter(bound[label])), attr)
    try:
        nodes = json.loads(data)['nodes']
        parent, issue = original['parent'], original['issue']
        children = sorted(n for n in nodes.values() if n != parent)
        require(json.loads(data)['issue'] == parent and parent in nodes.values() and issue in children
                and len(children) == original['approval'].get('child_count'), 'x')
    except (ValueError, KeyError, TypeError, AttributeError, WorkflowError) as exc:
        raise WorkflowError('SCOPE_RECOVERY_APPROVAL_HISTORY_REQUIRED: ' + label) from exc
    return children


def historical_scope_authority(root, anchor, receipt, original, feature=None, bound=None):
    """Recover omitted fields only from this acceptance's immutable native gate evidence."""
    if not original.get('approval') or (original.get('parent') and 'parent_children' not in original):
        # Older bindings omitted provenance. Only an already accepted, immutable gate proof can supply it.
        proofs = []
        for label in receipt.get('evidence', []):
            attr = historical_attributes(root, anchor, [label])[label]
            data, _ = proof_blob(root, anchor, canonical_path(root, label), receipt['fingerprints'][label], attr)
            require(sha(portable_content(label, data, attr)) == receipt['fingerprints'][label],
                    'SCOPE_RECOVERY_HISTORY_UNPROVEN: ' + label)
            try:
                proof = json.loads(data)
            except ValueError:
                continue
            if isinstance(proof, dict) and all(k in proof for k in ('issue', 'score', 'prompt', 'fingerprint', 'dependencies')):
                proofs.append(scope_proof_authority(proof, original))
        if (not proofs and original.get('approval') and original.get('parent')
                and 'parent_children' not in original and bound is not None):
            # The gate proof predates the binding's family fields; the accepted parent proof supplies them.
            proofs.append(scope_proof_authority(
                {**{k: original[k] for k in ('issue', 'score', 'fingerprint', 'dependencies')},
                 'prompt': original.get('published_prompt', original['prompt']),
                 'parent_children': native_parent_children(root, anchor, feature, original, bound)}, original))
        require(proofs and all(p == proofs[0] for p in proofs), 'SCOPE_RECOVERY_APPROVAL_HISTORY_REQUIRED')
        original = proofs[0]
    return original


def writer_guards(run, state):
    import delegation
    core.require_not_delegated_context('Scope recovery')
    delegation.require_no_maintenance(run.root)
    require(not state.get('active'), 'ACTIVE_CLAIM_MUST_BE_RESOLVED_BEFORE_SCOPE_RECOVERY')
    require(read(run.root / '.specify/superpowers-handoff.json', {}).get('status') not in ('executing', 'blocked'),
            'LEGACY_EXECUTOR_OWNS_FEATURE')
    for checkpoint in sorted((run.root / 'specs').glob('*/workflow/checkpoint.json')):
        path_at(run.root, checkpoint.relative_to(run.root).as_posix())
        require(not read(checkpoint, {}).get('active'), 'OTHER_FEATURE_STAGE_ACTIVE: ' + str(checkpoint))
    ledger = read(run.feature / 'workflow/delegations.json', {})
    require(isinstance(ledger, dict) and isinstance(ledger.get('attempts', []), list), 'DELEGATION_LEDGER_INVALID')
    require(not any(a.get('status') in ('starting', 'running') for a in ledger.get('attempts', [])),
            'DELEGATION_ATTEMPTS_ACTIVE')
    require(delegation.ledger_trust_state(run.root, run.relative) != 'untrusted', 'DELEGATION_LEDGER_UNTRUSTED')


def _plan(run):
    from wf_health import package_digest, resolve_commands
    from wf_policy import state_tier, tier
    from decisions import fresh_ledger, verify_ledger
    state = run.load()
    writer_guards(run, state)
    require(state['policy_digest'] == checkpoint_policy_digest(state, run.policy), 'SCOPE_RECOVERY_POLICY_CHANGED')
    require(state['dependency_digest'] == package_digest(run.root), 'SCOPE_RECOVERY_DEPENDENCY_CHANGED: migrate separately')
    require(state['commands'] == resolve_commands(run.root, run.policy, state_tier(state)), 'SCOPE_RECOVERY_COMMANDS_CHANGED')
    receipt = state['receipts'].get('scope')
    require(isinstance(receipt, dict) and receipt.get('stage') == 'scope' and receipt.get('outcome') == 'passed'
            and not receipt.get('stale'), 'SCOPE_RECOVERY_ACCEPTED_RECEIPT_REQUIRED')
    run._check_receipt('scope', {k: v for k, v in receipt.items() if k not in core.RUNTIME_RECEIPT_FIELDS},
                       run.tier_of(state))
    labels = set(receipt.get('fingerprints', {}))
    require(labels and set(receipt.get('inputs', []) + receipt.get('evidence', [])) <= labels,
            'SCOPE_RECOVERY_INVENTORY_INCOMPLETE')
    require(set(required_inputs(run.root, run.relative, 'scope', run.tier_of(state))) <= labels,
            'SCOPE_RECOVERY_INVENTORY_INCOMPLETE')
    canonical = [canonical_path(run.root, name) for name in labels]
    require(len(set(canonical)) == len(canonical), 'SCOPE_RECOVERY_AMBIGUOUS_LABELS')
    audits = receipt.get('scope_revalidations', [])
    historical_receipt = audits[0]['previous_receipt'] if audits else receipt
    anchor, previous = history(run, state, historical_receipt)
    source_label = run.relative + '/scope-source.json'
    original_bytes = blob(run.root, anchor, source_label)
    require(raw(run.root, source_label) == original_bytes, 'SCOPE_RECOVERY_AUTHORITY_CHANGED: scope-source.json')
    original = json.loads(original_bytes)
    require(str(original.get('repo')) + '#' + str(original.get('issue')) == state['issue'], 'SCOPE_RECOVERY_BINDING_MISMATCH')
    # scope-source must itself be bound by an accepted receipt, not an untrusted sibling file.
    bound = {r.get('fingerprints', {}).get(source_label) for r in previous['receipts'].values()}
    source_attr = historical_attributes(run.root, anchor, [source_label])[source_label]
    require(sha(portable_content(source_label, original_bytes, source_attr)) in bound,
            'SCOPE_RECOVERY_AUTHORITY_HISTORY_UNBOUND')
    bound_hashes = {}
    for item in list(previous['receipts'].values()) + [r for r in state['receipts'].values()
                                                       if r.get('outcome') == 'passed' and not r.get('stale')]:
        for name, value in item.get('fingerprints', {}).items():
            bound_hashes.setdefault(name, set()).add(value)
    original = historical_scope_authority(run.root, anchor, historical_receipt, original, run.relative, bound_hashes)
    live = provider(run, receipt, original)
    score = receipt.get('effort_score', state.get('effort_score', original.get('score')))
    require(score == original.get('score'), 'SCOPE_RECOVERY_EFFORT_CHANGED')
    if state.get('profile'):
        require(state['profile'].get('score') == score and state_tier(state) == tier(run.policy, score),
                'SCOPE_RECOVERY_TIER_CHANGED')
    decision = run.relative + '/workflow/decisions.json'
    require(decision in labels, 'SCOPE_RECOVERY_DECISION_HISTORY_REQUIRED')
    ledger = fresh_ledger(run.root, run.relative)
    verify_ledger(run.root, run.relative, ledger)
    stored_ledger = read(path_at(run.root, decision))
    require(ledger == stored_ledger, 'SCOPE_RECOVERY_DECISIONS_CHANGED: reconcile separately')

    inventory, snapshots = {}, {}
    for audit in audits:
        for label, expected in audit['assessment_evidence'].items():
            data = raw(run.root, label)
            require(sha(data) == expected, 'SCOPE_RECOVERY_ASSESSMENT_EVIDENCE_CHANGED: ' + label)
            inventory[label] = expected
    for stage, item in state['receipts'].items():
        validate_evidence_snapshots(run.root, item)
        source_fingerprints_of(run.root, item, run.relative)  # never hide a storage failure
        inventory.update({p: sha(raw(run.root, p)) for p in set(item.get('fingerprints', {})) | set(item.get('evidence', []))})
        if item.get('source_inventory'):
            label = run.relative + '/' + item['source_inventory']['path']
            inventory[label] = sha(raw(run.root, label))
        for snapshot in item.get('evidence_snapshots', []):
            resolved = evidence_snapshot.resolve(run.root, snapshot)
            descriptor = read(path_at(run.root, snapshot))
            for entry in descriptor['records']:
                if entry['kind'] == 'file':
                    inventory[entry['proof']] = sha(raw(run.root, entry['proof']))
            if stage == 'scope':
                for label, data in resolved.items():
                    require(label not in snapshots or snapshots[label] == data, 'SCOPE_RECOVERY_HISTORY_AMBIGUOUS: ' + label)
                    snapshots[label] = data

    old_attrs = historical_attributes(run.root, anchor, sorted(canonical))
    current_attrs = text_attributes(run.root, sorted(canonical))
    current = fingerprint_files(run.root, labels, feature=run.relative, like=receipt['fingerprints'])
    paths, blockers = [], []
    for label in sorted(labels):
        name = canonical_path(run.root, label)
        before, proof_commit = snapshots.get(name), anchor
        if before is None:
            before, proof_commit = proof_blob(run.root, anchor, name, historical_receipt['fingerprints'][label],
                                              old_attrs.get(name))
        # Historical context and raw bytes must independently reproduce the accepted hash.
        old_hash = sha(portable_content(name, before, old_attrs.get(name)))
        interpretation = 'historical-attributes'
        if old_hash != historical_receipt['fingerprints'][label] and sha(before) == historical_receipt['fingerprints'][label]:
            old_hash, interpretation = sha(before), 'exact-retained-storage'
        require(old_hash == historical_receipt['fingerprints'][label], 'SCOPE_RECOVERY_HISTORY_UNPROVEN: ' + label)
        after = raw(run.root, label)
        assessed = next((p for audit in reversed(audits) for p in audit['plan']['paths']
                         if p['path'] == label), None)
        if (assessed and assessed['after_raw_sha256'] == sha(after)
                and current[label] == receipt['fingerprints'][label] == assessed['after_fingerprint']):
            continue
        if current[label] == receipt['fingerprints'][label] and before == after:
            continue
        if audits:
            # shortcut: one assessed transition, require new historical admission before another.
            blockers.append('SCOPE_RECOVERY_NEW_HISTORY_REQUIRED: ' + label)
            paths.append({'path': label, 'classification': 'blocked',
                          'before_raw_sha256': sha(before), 'after_raw_sha256': sha(after),
                          'before_fingerprint': old_hash, 'after_fingerprint': current[label],
                          'before_attribute': old_attrs.get(name), 'after_attribute': current_attrs.get(name),
                          'before_interpretation': interpretation,
                          'history': {'commit': anchor, 'path': name, 'snapshot': name in snapshots,
                                  **({'proof_commit': proof_commit} if proof_commit != anchor else {})}})
            continue
        if before == after and (old_attrs.get(name) != current_attrs.get(name) or interpretation == 'exact-retained-storage'):
            classification = 'unchanged-bytes-context-transition'
        elif name in CONTEXT and before != after:
            classification = 'context-edit'
        else:
            classification = 'blocked'
            blockers.append('SCOPE_RECOVERY_SUBSTANTIVE_CHANGE: ' + label)
        paths.append({'path': label, 'classification': classification,
                      'before_raw_sha256': sha(before), 'after_raw_sha256': sha(after),
                      'before_fingerprint': old_hash, 'after_fingerprint': current[label],
                      'before_attribute': old_attrs.get(name), 'after_attribute': current_attrs.get(name),
                      'before_interpretation': interpretation,
                      'history': {'commit': anchor, 'path': name, 'snapshot': name in snapshots,
                                  **({'proof_commit': proof_commit} if proof_commit != anchor else {})}})

    config = ['.specify/workflow.yml', '.specify/extensions/.registry', '.specify/extensions/project/config.json',
              '.specify/scope/plan-pending.json', '.specify/scope/prerequisite-overrides.json',
              '.specify/superpowers-handoff.json', run.relative + '/workflow/decisions.json',
              run.relative + '/workflow/delegations.json', run.relative + '/scope-source.json',
              run.relative + '/workflow/lifecycle.jsonl']
    inventory.update({name: sha(data) if (data := raw(run.root, name, optional=True)) is not None else None for name in config})
    for name in live.get('local_paths', []):
        data = raw(run.root, name, optional=True)
        inventory[name] = sha(data) if data is not None else None
    # Pin all attribute sources, provider catalogues and actual candidate runtime bytes.
    for directory in (run.root / '.specify/scope', run.root / '.specify/extensions', run.root / '.specify/presets'):
        if directory.exists():
            for path in sorted(directory.rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix in ('.py', '.json', '.yml'):
                    label = path.relative_to(run.root).as_posix()
                    inventory[label] = sha(raw(run.root, label))
    attribute_paths = git(run.root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0')
    for label in filter(None, attribute_paths):
        if label.rsplit('/', 1)[-1] == '.gitattributes':
            inventory[label] = sha(raw(run.root, label))
    runtime = {}
    for directory in (Path(__file__).parent, Path(__file__).parents[2] / 'scope/scripts'):
        runtime.update({str(path.relative_to(directory.parent.parent)): sha(path.read_bytes()) for path in sorted(directory.glob('*.py'))})
    index = Path(git(run.root, 'rev-parse', '--git-path', 'index'))
    if not index.is_absolute():
        index = run.root / index
    downstream = {}
    source_now = None
    for stage, item in state['receipts'].items():
        if stage == 'scope':
            continue
        values = item.get('fingerprints', {})
        observed = fingerprint_files(run.root, values, feature=run.relative, like=values)
        changed = sorted(p for p in values if observed[p] != values[p])
        if stage in core.SOURCE_STAGES:
            if source_now is None:
                source_now = source_fingerprints(run.root)
                for label in source_now:
                    data = raw(run.root, label, optional=True)
                    inventory[label] = sha(data) if data is not None else None
            old = source_fingerprints_of(run.root, item, run.relative)
            changed = sorted(set(changed) | {p for p in set(old) | set(source_now) if old.get(p) != source_now.get(p)})
        if changed or item.get('stale'):
            downstream[stage] = {'changed_paths': changed, 'marked_stale': item.get('stale')}
    result = {'schema': PLAN, 'feature': run.relative, 'through': 'scope',
              'identity': {k: state.get(k) for k in ('repo_identity', 'branch', 'issue', 'run_id', 'head', 'generation', 'profile')},
              'head': git(run.root, 'rev-parse', 'HEAD'), 'history_anchor': anchor,
              'checkpoint_sha256': sha(run.path.read_bytes()), 'receipts_sha256': digest(state['receipts']),
              'index_sha256': sha(index.read_bytes()) if index.exists() else None,
              'git_configuration_sha256': sha(run_git(run.root, 'config', '--null', '--show-origin', '--list').stdout),
              'policy': run.policy, 'commands': state['commands'], 'runtime': runtime,
              'provider': live, 'decisions': ledger, 'inventory': inventory,
              'current_attributes': text_attributes(run.root, sorted(inventory)), 'paths': paths,
              'schema_transition': {'from': state['schema_version'], 'to': core.CHECKPOINT_SCHEMA,
                                    'drops_repo_path': 'repo_path' in state},
              'retained_receipts': {s: digest(r) for s, r in state['receipts'].items() if s != 'scope'},
              'remaining_drift': downstream,
              'blockers': blockers, 'can_apply': not blockers, 'noop': not paths}
    # No gate hooks, tests or source snapshot creation during preview.
    result['plan_id'] = digest(result)
    return result


def plan(run):
    with fresh_reads():
        run.policy = __import__('wf_policy').load_policy(run.root)
        return _plan(run)


def exact(value, fields, error):
    require(isinstance(value, dict) and set(value) == set(fields), error)


def assess(run, found, assessment):
    exact(assessment, ('schema', 'plan_id', 'reason', 'actor', 'schema_transition', 'stages'), 'SCOPE_RECOVERY_ASSESSMENT_INVALID')
    require(assessment['schema'] == ASSESSMENT and assessment['plan_id'] == found['plan_id'], 'SCOPE_RECOVERY_PLAN_STALE')
    require(all(isinstance(assessment[k], str) and assessment[k].strip() for k in ('actor', 'reason')), 'SCOPE_RECOVERY_ASSESSMENT_INVALID')
    require(assessment['schema_transition'] == found['schema_transition'], 'SCOPE_RECOVERY_SCHEMA_TRANSITION_UNASSESSED')
    exact(assessment['stages'], ('scope',), 'SCOPE_RECOVERY_ASSESSMENT_INVALID')
    entry = assessment['stages']['scope']
    exact(entry, ('summary', 'evidence', 'assessments'), 'SCOPE_RECOVERY_ASSESSMENT_INVALID')
    require(isinstance(entry['summary'], str) and entry['summary'].strip(), 'SCOPE_RECOVERY_ASSESSMENT_INVALID')
    require(isinstance(entry['assessments'], list), 'SCOPE_RECOVERY_ASSESSMENT_INVALID')
    expected = {p['path']: p for p in found['paths']}
    seen, proofs = set(), {}
    for item in entry['assessments']:
        exact(item, ('path', 'classification', 'conclusion', 'rationale'), 'SCOPE_RECOVERY_ASSESSMENT_INVALID')
        name = item['path']
        require(isinstance(name, str) and name in expected and name not in seen, 'SCOPE_RECOVERY_ASSESSMENT_PATHS')
        seen.add(name)
        require(item['classification'] == expected[name]['classification'] and item['conclusion'] == 'scope-unchanged'
                and isinstance(item['rationale'], str) and item['rationale'].strip(), 'SCOPE_RECOVERY_ASSESSMENT_INVALID')
    require(seen == set(expected), 'SCOPE_RECOVERY_ASSESSMENT_PATHS')
    evidence = entry['evidence']
    require(isinstance(evidence, list) and evidence and all(isinstance(p, str) for p in evidence)
            and len(set(evidence)) == len(evidence), 'SCOPE_RECOVERY_EVIDENCE_REQUIRED')
    for name in evidence:
        require(name.startswith(run.relative + '/evidence/') and name not in found['inventory'], 'SCOPE_RECOVERY_EVIDENCE_UNBOUND')
        data = raw(run.root, name)
        proof = json.loads(data)
        exact(proof, ('schema', 'plan_id', 'scope_unchanged', 'findings'), 'SCOPE_RECOVERY_EVIDENCE_UNBOUND')
        require(proof['schema'] == ASSESSMENT and proof['plan_id'] == found['plan_id'] and proof['scope_unchanged'] is True
                and proof['findings'] == entry['assessments'], 'SCOPE_RECOVERY_EVIDENCE_UNBOUND')
        proofs[name] = sha(data)
    return proofs


def apply(run, assessment):
    from delegate_dispatch import ledger_lock
    core.require_not_delegated_context('Scope recovery')
    # No-op and rejected preflight never create lock files or directories.
    found = plan(run)
    proofs = assess(run, found, assessment)
    require(found['can_apply'], 'SCOPE_RECOVERY_BLOCKED: ' + '; '.join(found['blockers']))
    if found['noop']:
        return {'revalidated': [], 'noop': True, 'plan_id': found['plan_id']}
    runtime = run.root / '.specify/workflow/runtime'
    scope_lock = path_at(run.root, '.specify/scope/mutation.lock')
    for name in ('dispatch.lock', 'decision-' + digest(run.relative) + '.lock',
                 'delegation-' + digest(run.relative) + '.lock', digest(run.relative) + '.lock'):
        path_at(run.root, '.specify/workflow/runtime/' + name)
    with locked(runtime / 'dispatch.lock'), locked(run.lock), locked(scope_lock), ledger_lock(run.root, run.relative), \
            locked(runtime / ('decision-' + digest(run.relative) + '.lock')):
        current = plan(run)
        require(current == found and assess(run, current, assessment) == proofs, 'SCOPE_RECOVERY_PLAN_STALE')
        state = run.load()
        old = copy.deepcopy(state['receipts']['scope'])
        replacement = copy.deepcopy(old)
        for item in found['paths']:
            replacement['fingerprints'][item['path']] = item['after_fingerprint']
        record = {'kind': 'scope-revalidation', 'plan': found, 'assessment': copy.deepcopy(assessment),
                  'assessment_evidence': proofs, 'previous_receipt': old, 'at': now()}
        replacement.setdefault('scope_revalidations', []).append(record)
        state['receipts']['scope'] = replacement
        # Last fresh provider/evidence/identity read, with every relevant writer lock still held.
        require(plan(run) == found and assess(run, found, assessment) == proofs, 'SCOPE_RECOVERY_PLAN_STALE')
        writer_guards(run, run.load())
        lifecycle.queue(state, 'scope', 'revalidate-upstream', episode_id='scope-revalidation:' + found['plan_id'],
                        reason=assessment['reason'])
        try:
            run.save(state, evaluate_next=False)  # canonical atomic save/outbox, with the assessed v1->v2 transition
        except (OSError, ValueError) as exc:
            durable = read(run.path, {})
            if durable.get('receipts', {}).get('scope') == replacement:
                return {'revalidated': ['scope'], 'committed': True, 'lifecycle_pending': True, 'error': str(exc)}
            raise
        return {'revalidated': ['scope'], 'committed': True, 'lifecycle_pending': False,
                'retained_receipts': found['retained_receipts'],
                'note': 'Later stages retain their own freshness requirements.'}
