"""Write one T07 arm's delegation settings into a clone's .specify/workflow.yml.

usage: python policy.py <clone> <arm> [--issue N]
  arm  insession  delegation off: the host session does the work itself
       native     delegation on, native-first (no native_allowed key, no override)
       external   delegation on, native_allowed false for implementation, qa_author, qa_collect and
                  documentation: every task external (review stays native under the SEC-01 interim;
                  discovery and coordination stages stay native-first)
       fixture    delegation on, native-first, plus an override that sends T001 of issue N's feature
                  external on the host's own standard model (route_reason native-unsupported:model-pin)

Only the delegation block changes; delegation is operational policy (wf_core.OPERATIONAL_POLICY), so it
never invalidates a receipt. The feature path for the override is derived exactly as
wf_identity.issue_identity derives it, from the issue title on GitHub.
"""
import argparse
import json
import re
import subprocess
import unicodedata
from pathlib import Path

import yaml

REPO = 'samykabu/sanduq-sandbox-ph04'
ARMS = ('insession', 'native', 'external', 'fixture')
EXTERNAL_TYPES = ('implementation', 'qa_author', 'qa_collect', 'documentation')


def feature_for(issue):
    title = json.loads(subprocess.run(['gh', 'api', f'repos/{REPO}/issues/{issue}'], check=True,
                                      capture_output=True, text=True, encoding='utf-8').stdout)['title']
    # Same rule as wf_identity.issue_identity (Workflow 1.25.0; unchanged in 2.0.1, checked by the #93 folder).
    slug = re.sub(r'[^\w]+', '-', unicodedata.normalize('NFKC', title).casefold(),
                  flags=re.UNICODE).strip('-_')[:56].strip('-_') or 'issue'
    return f'specs/{issue}-{slug}'


def host_of(clone):
    integration = json.loads((clone / '.specify/integration.json').read_text(encoding='utf-8-sig'))
    return integration.get('default_integration') or integration.get('integration')


def apply(policy, arm, host, feature=None):
    d = policy['delegation']
    d['enabled'] = arm != 'insession'
    d.pop('native_allowed', None)
    d['overrides'] = {}
    if arm == 'external':
        d['native_allowed'] = dict.fromkeys(EXTERNAL_TYPES, False)
    if arm == 'fixture':
        model = d['models'][host]['standard']  # same model the native worker is pinned to
        d['overrides'] = {feature + '/T001': {'preferred': {'harness': 'selected', 'model': model}, 'fallbacks': []}}
    return policy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('clone', type=Path)
    parser.add_argument('arm', choices=ARMS)
    parser.add_argument('--issue', type=int)
    parser.add_argument('--feature', help='specs/<name>; skips the GitHub title lookup (dry runs)')
    args = parser.parse_args()
    if args.arm == 'fixture' and not (args.issue or args.feature):
        parser.error('fixture needs --issue (or --feature)')
    path = args.clone / '.specify/workflow.yml'
    policy = yaml.safe_load(path.read_text(encoding='utf-8-sig'))
    feature = args.feature or (feature_for(args.issue) if args.arm == 'fixture' else None)
    apply(policy, args.arm, host_of(args.clone), feature)
    path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding='utf-8', newline='\n')
    print(json.dumps({'arm': args.arm, 'host': host_of(args.clone), 'feature': feature,
                      'delegation': {k: policy['delegation'].get(k) for k in ('enabled', 'native_allowed', 'overrides')}}))


if __name__ == '__main__':
    main()
