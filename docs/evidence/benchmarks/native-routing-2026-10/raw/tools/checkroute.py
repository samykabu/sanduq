"""Print the route the installed Workflow resolves for a clone's policy. No model call.

usage: python checkroute.py <clone> [--feature specs/<name>]
Loads .specify/workflow.yml through the installed Workflow's own loader (full validation) and calls its
delegation.selected_route for tasks T001 and T002 (implementation; and under "by_type" the first
candidate's route_kind for every task work type), and the discovery stage (Plan).
Delegation off prints the reason selected_route would give (`native-unsupported:delegation-disabled`):
a claim records no route at all in that case. tools/validate.py uses first_route() on the setup commit.
"""
import argparse
import json
import sys
from pathlib import Path

TASK_TYPES = ('implementation', 'qa_author', 'qa_collect', 'documentation', 'review')


def loader(root):
    sys.path.insert(0, str(Path(root) / '.specify/extensions/workflow/scripts'))
    from wf_policy import load_policy
    from wf_health import active_host
    import delegation
    return load_policy(Path(root))['delegation'], active_host(Path(root)), delegation


def first_route(config, host, delegation, work_type, identity):
    """route_kind of the first candidate (what a claim records), `native` for review under SEC-01."""
    try:
        return delegation.selected_route(config, work_type, host, identity)[0]['route_kind']
    except delegation.DelegationError as exc:
        if str(exc).startswith('DELEGATION_REVIEW_ROUTE_UNSAFE'):
            return 'native'
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('clone', type=Path)
    parser.add_argument('--feature', default='specs/999-dry-run')
    args = parser.parse_args()
    root = args.clone.resolve()
    config, host, delegation = loader(root)
    out = {'clone': str(root), 'host': host, 'enabled': config['enabled'],
           'native_allowed': config.get('native_allowed'), 'overrides': sorted(config['overrides'])}
    for label, work_type, ident in (('T001', 'implementation', args.feature + '/T001'),
                                    ('T002', 'implementation', args.feature + '/T002'),
                                    ('stage:plan', 'discovery', None)):
        candidates = delegation.selected_route(config, work_type, host, ident)
        out[label] = [{k: c[k] for k in ('route_kind', 'route_reason', 'harness', 'requested_model')}
                      for c in candidates]
    out['by_type'] = {t: {task: first_route(config, host, delegation, t, args.feature + '/' + task)
                          for task in ('T001', 'T002')} for t in TASK_TYPES}
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
