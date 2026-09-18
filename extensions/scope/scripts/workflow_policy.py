"""Optional managed-project policy; unmanaged Scope retains its previous contract."""
from pathlib import Path
import hashlib
import json


def load(root):
    path = Path(root) / '.specify/workflow.yml'
    if not path.exists():
        return None
    import yaml
    data = yaml.safe_load(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('Unsupported workflow policy; run workflow doctor before Scope.')
    return data


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
    if state.get('schema_version') != 1 or state.get('issue') != f'{repo}#{issue}': return None
    if state.get('feature') != feature.relative_to(root).as_posix() or state.get('repo_path') != str(root): return None
    if active.get('stage') not in stages or not active.get('token') or active.get('mode') != 'revalidate': return None
    return {'feature': feature.relative_to(root).as_posix(), 'stage': active['stage'], 'state': state}
