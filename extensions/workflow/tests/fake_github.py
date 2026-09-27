"""A fake GitHub REST client for CI evidence tests: recorded or built responses, no network."""
import io
import json
import zipfile
from pathlib import Path

RECORDED = Path(__file__).resolve().parent / 'fixtures/ci-runs'
WORKFLOW = 'Bootstrap verification'
CHECK = 'Bootstrap required lanes'


class FakeGitHub:
    """`api(endpoint)` and `download(endpoint)` answered from a dict; every call is logged."""

    def __init__(self, responses=None, downloads=None):
        self.responses = dict(responses or {})
        self.downloads = dict(downloads or {})
        self.calls = []

    def api(self, endpoint):
        self.calls.append(endpoint)
        if endpoint not in self.responses:
            if '/artifacts?' in endpoint:  # a name filter that matches nothing is an empty list, as on GitHub
                return {'total_count': 0, 'artifacts': []}
            import ci_evidence
            raise ci_evidence.EvidenceError('GitHub API ' + endpoint + ': HTTP 404')
        return json.loads(json.dumps(self.responses[endpoint]))

    def download(self, endpoint):
        self.calls.append(endpoint)
        if endpoint not in self.downloads:
            import ci_evidence
            raise ci_evidence.EvidenceError('GitHub API ' + endpoint + ': HTTP 404')
        return self.downloads[endpoint]

    def add_run(self, repository, run, jobs, artifacts, archive, commit):
        base = f'repos/{repository}/actions/runs/{run["id"]}'
        name = f'bootstrap-plan-{run["id"]}-{run["run_attempt"]}'
        self.responses[base] = run
        self.responses[f'{base}/attempts/{run["run_attempt"]}'] = run
        self.responses[f'{base}/attempts/{run["run_attempt"]}/jobs?per_page=100'] = jobs
        self.responses[f'{base}/artifacts?per_page=100&name={name}'] = artifacts
        for item in artifacts.get('artifacts', []):
            if archive is not None:
                self.downloads[f'repos/{repository}/actions/artifacts/{item["id"]}/zip'] = archive
        if commit:
            self.responses[f'repos/{repository}/git/commits/{commit["sha"]}'] = commit
        return self


def recorded(run_id):
    """The recorded responses of one real Bunyan verification run."""
    folder = RECORDED / str(run_id)
    load = lambda name: json.loads((folder / name).read_text(encoding='utf-8'))  # noqa: E731
    run = load('run.json')
    client = FakeGitHub().add_run(run['repository']['full_name'], run, load('jobs.json'), load('artifacts.json'),
                                  (folder / 'artifact.zip').read_bytes(), load('commit.json'))
    if (folder / 'pulls.json').is_file():
        client.responses[f'repos/{run["repository"]["full_name"]}/commits/{run["head_sha"]}/pulls'] = load('pulls.json')
    return client


def plan_zip(plan):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr('verification-plan.json', json.dumps(plan, indent=2))
    return buffer.getvalue()


def fake_run(repository, run_id, head, tree, key, lanes, *, attempt=1, event='pull_request', pull_request=11,
             tier='pr', conclusion='success', status='completed', check_conclusion='success', plan_overrides=None,
             artifact=True, client=None):
    """Responses for one verification run whose plan artifact follows the A9a contract."""
    plan = {'schemaVersion': 1, 'keyVersion': 'bunyan-source-key/1', 'repository': repository, 'workflow': WORKFLOW,
            'event': event, 'pullRequest': pull_request if event == 'pull_request' else None, 'runId': run_id,
            'runAttempt': attempt, 'headSha': head, 'headTreeSha': tree, 'sourceKey': key, 'tier': tier,
            'lanes': sorted(set(lanes)), 'legs': ['unit']}
    plan.update(plan_overrides or {})
    run = {'id': run_id, 'name': WORKFLOW, 'run_attempt': attempt, 'event': event, 'status': status,
           'conclusion': conclusion, 'head_sha': head, 'repository': {'full_name': repository},
           'pull_requests': [{'number': pull_request}] if event == 'pull_request' else []}
    jobs = {'jobs': [{'name': 'Plan the tier and lanes', 'conclusion': 'success'},
                     {'name': CHECK, 'conclusion': check_conclusion}]}
    name = f'bootstrap-plan-{run_id}-{attempt}'
    artifacts = {'artifacts': [{'id': run_id + 7, 'name': name, 'expired': False,
                                'workflow_run': {'id': run_id, 'head_sha': head}}] if artifact else []}
    return (client or FakeGitHub()).add_run(repository, run, jobs, artifacts, plan_zip(plan),
                                            {'sha': head, 'tree': {'sha': tree}})
