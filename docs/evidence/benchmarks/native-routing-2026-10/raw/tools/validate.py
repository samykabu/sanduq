"""Post-run validity check for one T07 run. No model call. Exit 0 valid, 1 INVALID, 2 cannot check.

usage: python validate.py <run> [--clone DIR]
  <run>    a1, b2, fx-codex, ...; the clone is runs/<run> unless --clone is given (e.g. a pilot clone).
  Without --clone the verdict is also written into logs/rows/<run>.json ("validity"), which report.py shows.

The arm and host come from the clone's setup commit ("T07 arm policy: <arm> (host <host>)", setup-run.sh).
The expected route of each task is recomputed from that commit's .specify/ with the installed Workflow's
own loader and selected_route (tools/checkroute.py first_route), i.e. what checkroute predicted at setup
(logs/route-<run>.json), for every task work type rather than only T001/T002 implementation.

A run is INVALID when
  (a) .specify/workflow.yml differs from the setup commit (committed or not);
  (b) a task (T###) attempt's route_kind differs from the route predicted at setup (not checked for the
      in-session arm, whose claims record no route);
  (c) external arm: any adopted / in-session / DELEGATION_TASK_SUBSTITUTED attempt, or no external task
      attempt;
  (d) fixture arm: not at least one external and one native task attempt (a one-task plan fails here);
  (e) native arm: no native task attempt (a documentation/qa_collect task routed external by design is
      fine; any task off its predicted route is caught by (b));
  and, for every delegation arm, when the ledger has no task attempt at all.
"""
import argparse
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from checkroute import first_route, loader  # noqa: E402

BASE = Path('<sandbox>')
TASK = re.compile(r'/(T\d{3,})$')


def git(clone, *args, binary=False):
    return subprocess.run(['git', '-C', str(clone), *args], check=True, capture_output=True,
                          **({} if binary else {'text': True, 'encoding': 'utf-8'})).stdout


def route_kind(attempt):
    return attempt.get('route_kind') or ('in-session' if attempt.get('adopted') else 'unknown')


def check(clone):
    setup = git(clone, 'log', '--format=%H%x09%s', '--grep=^T07 arm policy', '-1').strip()
    if not setup:
        raise ValueError(f'no "T07 arm policy" setup commit in {clone}')
    sha, subject = setup.split('\t', 1)
    arm, host = re.match(r'T07 arm policy: (\w+) \(host (\w+)\)', subject).groups()
    reasons = []

    if git(clone, 'diff', sha, '--', '.specify/workflow.yml').strip():  # (a)
        reasons.append(f'workflow.yml edited after the setup commit {sha[:7]}')

    attempts, tasks_md = [], {}
    for ledger in sorted(clone.glob('specs/*/workflow/delegations.json')):
        feature = ledger.parent.parent
        attempts += json.loads(ledger.read_text(encoding='utf-8'))['attempts']
        if (feature / 'tasks.md').exists():
            for line in (feature / 'tasks.md').read_text(encoding='utf-8').splitlines():
                m = re.match(r'^\s*- \[[ xX]\]\s+(T\d{3,})\b', line)
                if m:
                    tasks_md[f'specs/{feature.name}/{m.group(1)}'] = line
    tasks = [a for a in attempts if TASK.search(a.get('identity', ''))]

    with tempfile.TemporaryDirectory() as tmp:  # the setup commit's policy and installed Workflow
        tarfile.open(fileobj=io.BytesIO(git(clone, 'archive', sha, '.specify', binary=True))).extractall(tmp, filter='data')
        config, setup_host, delegation = loader(tmp)
        predicted = {}
        for a in tasks:
            ident = a['identity']
            work_type = a.get('task_type')
            if work_type not in delegation.TYPES:  # adopted attempts record no work type: classify the task line
                work_type = delegation.task_type(tasks_md.get(ident, ''), True)
            predicted[ident] = first_route(config, setup_host, delegation, work_type, ident)

    if arm != 'insession':
        for a in tasks:  # (b)
            if route_kind(a) != predicted[a['identity']]:
                reasons.append(f"{a['identity'].rsplit('/', 1)[1]} ran {route_kind(a)}, setup predicted "
                               f"{predicted[a['identity']]}")
        if not tasks:
            reasons.append('no task attempt in the ledger')
    kinds = [route_kind(a) for a in tasks]
    if arm == 'external':  # (c)
        bad = [a for a in attempts if a.get('adopted') or route_kind(a) == 'in-session' or
               str(a.get('route_reason', '')).startswith('external-substituted') or
               'DELEGATION_TASK_SUBSTITUTED' in json.dumps(a)]
        if bad:
            reasons.append('adopted/in-session/substituted attempts: ' +
                           ', '.join(sorted({a['identity'].rsplit('/', 1)[1] for a in bad})))
        if 'external' not in kinds:
            reasons.append('no external task attempt')
    if arm == 'fixture' and not ('external' in kinds and 'native' in kinds):  # (d)
        reasons.append(f'fixture needs one external and one native task attempt; has {sorted(set(kinds)) or "none"} '
                       f'over {len({a["identity"] for a in tasks})} task(s)')
    if arm == 'native' and 'native' not in kinds:  # (e); off-route tasks are caught by (b)
        reasons.append('native arm has no native task attempt')
    return {'valid': not reasons, 'arm': arm, 'host': host, 'setup_commit': sha[:12],
            'task_attempts': len(tasks), 'task_route_kinds': dict(sorted({k: kinds.count(k) for k in kinds}.items())),
            'reasons': list(dict.fromkeys(reasons))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run')
    parser.add_argument('--clone', type=Path)
    args = parser.parse_args()
    clone = args.clone or BASE / 'runs' / args.run
    try:
        verdict = check(clone)
    except (OSError, subprocess.CalledProcessError, KeyError, ValueError, AttributeError) as exc:
        print(f'CANNOT CHECK {args.run}: {exc}', file=sys.stderr)
        sys.exit(2)
    row = BASE / 'logs/rows' / (args.run + '.json')
    if not args.clone and row.exists():
        data = json.loads(row.read_text(encoding='utf-8'))
        data['validity'] = verdict
        row.write_text(json.dumps(data, indent=1), encoding='utf-8')
    print(('VALID ' if verdict['valid'] else 'INVALID ') + args.run + ' (' + verdict['arm'] + ', ' + verdict['host'] +
          f", {verdict['task_attempts']} task attempts {verdict['task_route_kinds']})" +
          ''.join('\n  - ' + r for r in verdict['reasons']))
    sys.exit(0 if verdict['valid'] else 1)


if __name__ == '__main__':
    main()
