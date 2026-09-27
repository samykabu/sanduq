#!/usr/bin/env python3
"""A CI verification run read as evidence (workflow 1.6.0, B4).

The consumer contract is Bunyan's `docs/development/verification-plan-contract.md`
(its validator twin is `eng/ci/plan-evidence.mjs`): every verification run
uploads the artifact `<prefix>-<run_id>-<run_attempt>` holding one
`verification-plan.json` that names the run, its head commit and tree, the
canonical source key of that tree (`source_key.py`), the tier and the lanes.

Everything is read through the GitHub REST API. `collect` does the reading
through an injectable client (`GhClient` shells out to `gh api`; tests pass a
fake with recorded responses) and `validate` is pure, so every rule is tested
without a network.
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import zipfile

from source_key import KEY_VERSION

PLAN_FILE = 'verification-plan.json'
DEFAULT_ARTIFACT_PREFIX = 'bootstrap-plan'
SHA = re.compile(r'^[0-9a-f]{40}$')
KEY = re.compile(r'^[0-9a-f]{64}$')


class EvidenceError(ValueError):
    """The GitHub API could not be read."""


def artifact_name(run_id, attempt, prefix=DEFAULT_ARTIFACT_PREFIX):
    return f'{prefix}-{run_id}-{attempt}'


class GhClient:
    """GitHub REST access through the `gh` CLI (its own authentication, REST budget)."""

    def _run(self, endpoint):
        result = subprocess.run(['gh', 'api', endpoint, '-H', 'Accept: application/vnd.github+json',
                                 '-H', 'X-GitHub-Api-Version: 2022-11-28'], capture_output=True)
        if result.returncode != 0:
            raise EvidenceError('GitHub API ' + endpoint + ': ' +
                                result.stderr.decode('utf-8', 'replace').strip()[:500])
        return result.stdout

    def api(self, endpoint):
        return json.loads(self._run(endpoint).decode('utf-8'))

    def download(self, endpoint):
        return self._run(endpoint)


def read_plan(archive):
    """The parsed `verification-plan.json` of an artifact zip, or None when unreadable."""
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            return json.loads(bundle.read(PLAN_FILE).decode('utf-8'))
    except (zipfile.BadZipFile, KeyError, ValueError, UnicodeDecodeError):
        return None


def collect(client, repository, run_id, attempt=None, prefix=DEFAULT_ARTIFACT_PREFIX):
    """Read the run attempt, its jobs, its plan artifact and the plan head's tree."""
    base = f'repos/{repository}/actions/runs/{run_id}'
    latest = client.api(base)
    number = attempt or latest.get('run_attempt')
    run = latest if str(number) == str(latest.get('run_attempt')) else client.api(f'{base}/attempts/{number}')
    jobs = client.api(f'{base}/attempts/{number}/jobs?per_page=100').get('jobs') or []
    name = artifact_name(run_id, number, prefix)
    artifacts = client.api(f'{base}/artifacts?per_page=100&name={name}').get('artifacts') or []
    plan, head_tree = None, None
    found = [item for item in artifacts if item.get('name') == name and not item.get('expired')]
    if len(found) == 1:
        plan = read_plan(client.download(f'repos/{repository}/actions/artifacts/{found[0]["id"]}/zip'))
    if isinstance(plan, dict) and isinstance(plan.get('headSha'), str) and SHA.match(plan['headSha']):
        head_tree = (client.api(f'repos/{repository}/git/commits/{plan["headSha"]}').get('tree') or {}).get('sha')
    return {'run': run, 'jobs': jobs, 'artifacts': artifacts, 'plan': plan, 'head_tree': head_tree,
            'attempt': number, 'artifact': name}


def _sorted_unique(values):
    return (isinstance(values, list) and all(isinstance(item, str) and item for item in values)
            and all(values[index - 1] < values[index] for index in range(1, len(values))))


def validate(evidence, repository, run_id, check, workflow=None, attempt=None, local=None, prefix=DEFAULT_ARTIFACT_PREFIX):
    """The failed contract checks for one run as accepted evidence (empty when it holds).

    `check` is the job whose success certifies the run (`ci.gate.verification_check`);
    `local` is `{tree, key}` recomputed from the local repository for the plan's head.
    """
    errors = []
    run, plan = evidence.get('run'), evidence.get('plan')
    if not isinstance(run, dict):
        return ['The run could not be read.']
    if str(run.get('id')) != str(run_id):
        errors.append(f'The API returned run {run.get("id")}, not {run_id}.')
    if attempt is not None and str(run.get('run_attempt')) != str(attempt):
        errors.append(f'The API returned attempt {run.get("run_attempt")}, not {attempt}.')
    if workflow and run.get('name') != workflow:
        errors.append(f'Run {run.get("id")} is "{run.get("name")}", not {workflow}.')
    if run.get('conclusion') == 'cancelled' or run.get('status') == 'cancelled':
        errors.append(f'Run {run.get("id")} attempt {run.get("run_attempt")} was cancelled.')
    if run.get('status') != 'completed':
        errors.append(f'Run {run.get("id")} attempt {run.get("run_attempt")} has not completed ({run.get("status")}).')
    required = [job for job in evidence.get('jobs') or [] if job.get('name') == check]
    if len(required) != 1 or required[0].get('conclusion') != 'success':
        seen = ', '.join(str(job.get('conclusion')) for job in required) or 'missing'
        errors.append(f'The {check} check of run {run.get("id")} attempt {run.get("run_attempt")} '
                      f'did not conclude success ({seen}).')
    name = artifact_name(run.get('id'), run.get('run_attempt'), prefix)
    found = [item for item in evidence.get('artifacts') or [] if item.get('name') == name]
    if len(found) != 1:
        errors.append(f'Run {run.get("id")} has {len(found) or "no"} artifact(s) named {name}.')
    elif found[0].get('expired'):
        errors.append(f'Artifact {name} has expired.')
    elif (found[0].get('workflow_run') or {}).get('id') not in (None, run.get('id')):
        errors.append(f'Artifact {name} belongs to run {found[0]["workflow_run"]["id"]}.')
    if not isinstance(plan, dict):
        errors.append(f'{PLAN_FILE} in {name} is missing or unreadable.')
        return errors

    def field(key, actual, wanted):
        if actual != wanted:
            errors.append(f'{key} is {json.dumps(actual)}, expected {json.dumps(wanted)}.')

    field('schemaVersion', plan.get('schemaVersion'), 1)
    field('keyVersion', plan.get('keyVersion'), KEY_VERSION)
    field('repository', plan.get('repository'), repository)
    if (run.get('repository') or {}).get('full_name'):
        field('repository (run)', plan.get('repository'), run['repository']['full_name'])
    field('workflow', plan.get('workflow'), run.get('name'))
    field('event', plan.get('event'), run.get('event'))
    field('runId', plan.get('runId'), int(run.get('id') or 0))
    field('runAttempt', plan.get('runAttempt'), int(run.get('run_attempt') or 0))
    head = plan.get('headSha')
    if not (isinstance(head, str) and SHA.match(head)):
        errors.append(f'headSha {json.dumps(head)} is not a 40-hex commit.')
    else:
        field('headSha', head, run.get('head_sha'))
    if plan.get('event') == 'pull_request':
        numbers = [item.get('number') for item in run.get('pull_requests') or []]
        if type(plan.get('pullRequest')) is not int or plan['pullRequest'] not in numbers:
            errors.append(f'pullRequest {json.dumps(plan.get("pullRequest"))} is not a pull request of run '
                          f'{run.get("id")} ({", ".join(map(str, numbers)) or "none"}).')
    else:
        field('pullRequest', plan.get('pullRequest'), None)
    tree = plan.get('headTreeSha')
    if not (isinstance(tree, str) and SHA.match(tree)):
        errors.append(f'headTreeSha {json.dumps(tree)} is not a 40-hex tree.')
    elif tree != evidence.get('head_tree'):
        errors.append(f'headTreeSha {tree} is not the tree of {head} ({evidence.get("head_tree") or "unknown"}).')
    if not (isinstance(plan.get('sourceKey'), str) and KEY.match(plan['sourceKey'])):
        errors.append(f'sourceKey {json.dumps(plan.get("sourceKey"))} is not a 64-hex key.')
    if local is not None:
        if local.get('tree') != tree:
            errors.append(f'The local tree of {head} is {local.get("tree")}, not {tree}.')
        if local.get('key') != plan.get('sourceKey'):
            errors.append(f'sourceKey {plan.get("sourceKey")} does not match the key {local.get("key")} '
                          f'recomputed from the tree of {head}.')
    if not (isinstance(plan.get('tier'), str) and plan['tier']):
        errors.append(f'tier {json.dumps(plan.get("tier"))} is not a tier.')
    for key in ('lanes', 'legs'):
        if not _sorted_unique(plan.get(key)):
            errors.append(f'{key} is not a sorted list of unique ids.')
    return errors
