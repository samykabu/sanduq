"""Optional managed-project policy; unmanaged Scope retains its previous contract."""
from pathlib import Path
import copy
import hashlib
import json


_PARSED = {}  # resolved path -> (file text, parsed policy)
_MODULES = {}  # Workflow script file name -> module, imported once per process


def load(root):
    path = Path(root) / '.specify/workflow.yml'
    try:
        text = path.read_text(encoding='utf-8-sig')
    except FileNotFoundError:
        return None
    # Keyed by the text, not the mtime: reading is cheap, parsing is not, and a same-size rewrite inside one
    # mtime tick must not return the old policy.
    key = str(path.resolve())
    cached = _PARSED.get(key)
    if cached is None or cached[0] != text:
        import yaml
        cached = _PARSED[key] = (text, yaml.load(text, Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader)))
    # A copy, so no caller can change the cached policy.
    data = copy.deepcopy(cached[1])
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('Unsupported workflow policy; run workflow doctor before Scope.')
    return data


def setting(root, section, key, default=None):
    """One optional policy value; no policy, section or key gives `default`."""
    value = ((load(root) or {}).get(section) or {}).get(key)
    return default if value is None else value


def keep_together(root, analysis):
    policy = load(root)
    if not policy:
        return None
    band = policy.get('scope', {}).get('keep_together')
    estimate = analysis.get('effort_estimate', {})
    if band and (not isinstance(band, dict) or any(type(band.get(k)) not in (int, float) or band[k] < 0 for k in ('target', 'tolerance'))):
        raise ValueError('Invalid scope keep-together band; run workflow doctor.')
    if not band or estimate.get('unit') != band.get('unit'):
        return None
    value = estimate.get('value')
    if type(value) not in (int, float) or not band.get('unit') or band.get('inclusive') is not True:
        return None
    if band['target'] - band['tolerance'] <= value <= band['target'] + band['tolerance']:
        return {'source': '.specify/workflow.yml', 'band': band, 'estimate': estimate,
                'sha256': hashlib.sha256(json.dumps(band, sort_keys=True).encode()).hexdigest()}
    return None


def paths(root):
    root = Path(root).resolve()
    policy = load(root)
    scope = (policy or {}).get('scope', {})
    folder = scope.get('artifact_directory', '.specify/scope/github' if policy else 'Design/UI-Spec/github')
    plan = scope.get('plan_file', 'docs/workflow/implementation-plan.html' if policy else 'Design/UI-Spec/implementation-plan.html')
    resolved = [(root / p).resolve() for p in (folder, plan)]
    if not all(p.is_relative_to(root) for p in resolved):
        raise ValueError('Scope artifact paths must remain inside the project.')
    return resolved


def statuses(root):
    mapping = (load(root) or {}).get('scope', {}).get('statuses', {})
    if not isinstance(mapping, dict) or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in mapping.items()) or len(set(mapping.values())) != len(mapping):
        raise ValueError('Scope status mappings must be unique nonempty names.')
    return mapping


def board_mode(root):
    """Workflow's `project_sync.mode` (REQ-22) read by Workflow itself; `full` without a managed policy."""
    policy = load(root)
    return _required_workflow().project_sync_mode(policy) if policy else 'full'


def board_writes(root, status):
    """Whether Scope moves the board to the logical `status`: every status in full mode (or unmanaged), in minimal
    only those of the phases minimal writes, none in off."""
    policy = load(root)
    if not policy:
        return True
    workflow = _required_workflow()
    return workflow.project_sync_mode(policy) == 'full' or any(
        workflow.sync_phase_written(policy, phase) for phase, logical in workflow.PHASE_DEFAULTS.items() if logical == status)


def _required_workflow():
    workflow = _workflow_module()
    if workflow is None:
        raise ValueError('SCOPE_WORKFLOW_UNAVAILABLE: the workflow extension cannot be loaded to read project_sync.mode.')
    return workflow


def _workflow_module():
    """Workflow's own `workflow.py`, imported from the scripts folder this one sits in, so the
    checkpoint-identity gate is shared with Workflow itself rather than copied. None when it cannot be
    imported, which refuses the claim."""
    if 'workflow.py' not in _MODULES:
        try:
            _scripts_on_path()
            import workflow
        except Exception:
            workflow = None
        _MODULES['workflow.py'] = workflow
    return _MODULES['workflow.py']


def _scripts_on_path():
    """Workflow's scripts folder (this folder's parent) on sys.path, once."""
    import sys
    scripts = str(Path(__file__).resolve().parents[1])
    if scripts not in sys.path:
        sys.path.insert(0, scripts)


def bound_claim(root, repo, issue, stages):
    """Recognize the managed owner's existing-feature claim, never policy alone."""
    root = Path(root).resolve()
    if not load(root): return None
    def read(path):
        value = json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
        return value if isinstance(value, dict) else {}
    selected = read(root / '.specify/feature.json').get('feature_directory')
    if not isinstance(selected, str): return None
    feature = (root / selected).resolve()
    if not feature.is_relative_to(root / 'specs') or not (feature / 'spec.md').is_file(): return None
    source = read(feature / 'scope-source.json')
    state = read(feature / 'workflow/checkpoint.json')
    active = state.get('active') or {}
    if not isinstance(active, dict): return None
    if (source.get('repo'), source.get('issue')) != (repo, issue): return None
    if state.get('schema_version') not in (1, 2) or state.get('issue') != f'{repo}#{issue}': return None  # checkpoint v1 or v2
    # `repo_path`, when present, is a pre-1.8.0 checkpoint's absolute path
    # (machine- and clone-specific -- the same checkpoint-identity design bug
    # workflow.py's `Run.load()` fixes) and is never compared: the `issue`
    # check just above already binds this claim to the real, portable GitHub
    # repo string, not a local path.
    if state.get('feature') != feature.relative_to(root).as_posix(): return None
    # The issue match above is only as strong as
    # this repository's own origin, so the claim also passes the exact
    # identity gate `workflow.py` applies on load (`repo_identity` match, or a
    # legacy checkpoint's verifiable history, and the issue naming this
    # repository's GitHub remote). Anything else, or no workflow module to
    # ask, is not a claim.
    workflow = _workflow_module()
    if workflow is None: return None
    try:
        workflow.verify_checkpoint_identity(root, state, feature.relative_to(root).as_posix())
    except Exception:
        return None
    if active.get('stage') not in stages or not active.get('token') or active.get('mode') != 'revalidate': return None
    return {'feature': feature.relative_to(root).as_posix(), 'stage': active['stage'], 'state': state}


def fresh_claim(root, repo, issue, feature, token, session, stages=("scope", "specify")):
    """Explicit initial issue-bound caller, never the historical global feature pointer."""
    if not all((feature, token, session)):
        raise ValueError('SCOPE_WORKFLOW_BINDING_REQUIRED: feature, token and session are required together.')
    workflow = _workflow_module()
    if workflow is None:
        raise ValueError('SCOPE_WORKFLOW_UNAVAILABLE')
    run = workflow.Run(Path(root).resolve(), feature)
    try:
        state = run.load()  # repository, feature, issue remote and current branch checks
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    active = state.get('active') or {}
    if (state.get('issue') != f'{repo}#{issue}' or active.get('stage') not in stages
            # A Specify claim on a spec Scope rendered is `bind-only`: still the initial binding.
            or active.get('mode') not in ('initial', 'bind-only' if active.get('stage') == 'specify' else 'initial')
            or active.get('token') != token
            or active.get('session_id') != session or ((run.feature / 'scope-source.json').exists() and (active.get('stage') != 'specify' or
                workflow.read(run.feature / 'scope-source.json', {}).get('repo') != repo or
                workflow.read(run.feature / 'scope-source.json', {}).get('issue') != issue))
            or any(stage != 'scope' for stage in state.get('receipts', {}))):
        raise ValueError('SCOPE_WORKFLOW_BINDING_MISMATCH')
    # Fresh live decisions are reread, including immutable question and applied evidence checks.
    import os
    decisions = _decisions_module()
    previous = {key: os.environ.get(key) for key in
                ('SANDUQ_WORKFLOW_CLAIM_TOKEN', 'SANDUQ_WORKFLOW_SESSION_ID')}
    try:
        os.environ['SANDUQ_WORKFLOW_CLAIM_TOKEN'] = token
        os.environ['SANDUQ_WORKFLOW_SESSION_ID'] = session
        try:
            ledger = decisions.reconcile(run.root, run.relative, claim_token=token, session_id=session)
            decisions.verify_ledger(run.root, run.relative, ledger)
        except Exception as exc:
            raise ValueError(str(exc)) from exc
    finally:
        for key, value in previous.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value
    return {'feature': run.relative, 'stage': active['stage'],
            'decision_sha256': workflow.digest(ledger), 'state': state,
            'decision_evidence': {name: sha for item in ledger['decisions']
                                  for name, sha in item.get('application', {}).get('evidence', {}).items()}}


def _decisions_module():
    """Workflow's `decisions.py`, imported from the scripts folder this one sits in."""
    if 'decisions.py' not in _MODULES:
        _scripts_on_path()
        import decisions
        _MODULES['decisions.py'] = decisions
    return _MODULES['decisions.py']
