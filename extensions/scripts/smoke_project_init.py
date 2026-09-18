#!/usr/bin/env python3
"""Exercise real Project Init scripts against a local fake GitHub board, without remote writes."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'extensions/workflow/scripts'))
from workflow import default_policy, project_errors, write


def smoke(shell):
    parent = ROOT / 'dist/project-init-tests'; parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=shell + '-', dir=parent)).resolve()
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    shutil.copytree(ROOT / 'extensions/project', root / '.specify/extensions/project', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT / 'extensions/workflow/scripts', root / '.specify/extensions/workflow/scripts', ignore=shutil.ignore_patterns('__pycache__'))
    names = dict(zip(('Backlog', 'Feature Specification', 'Need Clarifications', 'Ready', 'In progress', 'In review', 'Done'),
                     ('Inbox', 'Discovery', 'Questions', 'Planned', 'Building', 'Reviewing', 'Complete')))
    policy = default_policy(False, False); policy['scope'] = {'statuses': names}
    (root / '.specify/workflow.yml').write_text(yaml.safe_dump(policy), encoding='utf-8')
    hooks = 'hooks:\n  after_specify:\n  - extension: project\n    command: speckit.project.sync\n    optional: true\n    enabled: false\n'
    (root / '.specify/extensions.yml').write_text(hooks, encoding='utf-8')
    fixture = {'project': {'id': 'PVT_fixture', 'url': 'https://github.com/orgs/acme/projects/1'},
               'fields': {'fields': [{'id': 'STATUS_fixture', 'name': 'Status',
                                     'options': [{'id': 'OPT_' + str(i), 'name': name} for i, name in enumerate(names.values())]}]}}
    write(root / 'board.json', fixture)
    env = dict(os.environ, SANDUQ_PROJECT_FIXTURE=str(root / 'board.json'))
    if shell == 'pwsh':
        script = root / '.specify/extensions/project/scripts/powershell/project-init.ps1'
        wrapper = root / 'run.ps1'
        quoted = str(script).replace("'", "''")
        wrapper.write_text("""$ErrorActionPreference = 'Stop'
function global:gh {
    $global:LASTEXITCODE = 0
    $data = Get-Content -LiteralPath $env:SANDUQ_PROJECT_FIXTURE -Raw | ConvertFrom-Json
    if ($args[0] -eq 'auth') { 'Authenticated fixture project scope'; return }
    if ($args[0] -eq 'project' -and $args[1] -eq 'view') { $data.project | ConvertTo-Json -Depth 12 -Compress; return }
    if ($args[0] -eq 'project' -and $args[1] -eq 'field-list') { $data.fields | ConvertTo-Json -Depth 12 -Compress; return }
    throw 'Unexpected or mutating GitHub operation in Project Init fixture'
}
""" + f"& '{quoted}' -Owner acme -Number 1 -OwnerType org -NonInteractive -Json\n", encoding='utf-8')
        args = ['pwsh', '-NoProfile', '-File', str(wrapper)]
    else:
        fakebin = root / 'fakebin'; fakebin.mkdir()
        executable = fakebin / 'gh'
        executable.write_text("""#!/usr/bin/env python3
import json, os, sys
with open(os.environ['SANDUQ_PROJECT_FIXTURE'], encoding='utf-8') as stream: data = json.load(stream)
args = sys.argv[1:]
if args[:2] == ['auth', 'status']: print('Authenticated fixture project scope')
elif args[:2] == ['project', 'view']: print(json.dumps(data['project']))
elif args[:2] == ['project', 'field-list']: print(json.dumps(data['fields']))
else: raise SystemExit('Unexpected or mutating GitHub operation in Project Init fixture')
""", encoding='utf-8')
        executable.chmod(0o755)
        env['PATH'] = str(fakebin) + os.pathsep + env.get('PATH', '')
        args = ['bash', str(root / '.specify/extensions/project/scripts/bash/project-init.sh'),
                '--owner', 'acme', '--number', '1', '--owner-type', 'org', '--non-interactive', '--json']
    result = subprocess.run(args, cwd=root, env=env, input='', capture_output=True, text=True, encoding='utf-8')
    (root / 'execution.log').write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
    if result.returncode: raise RuntimeError(f'Project Init failed; inspect {root / "execution.log"}')
    config = json.loads((root / '.specify/extensions/project/config.json').read_text(encoding='utf-8-sig'))
    assert config['phaseToStatus']['open'] == 'Discovery', config
    assert config['phaseToStatus']['analysis'] == 'Planned', config
    assert config['statusOptions']['Questions'], 'Unmapped Scope-only board option was lost'
    assert config['hookMode'] == 'required', config
    assert (root / '.specify/extensions.yml').read_text(encoding='utf-8') == hooks, 'Managed hook journal would be invalidated'
    assert not project_errors(root, policy), project_errors(root, policy)
    evidence = {'ok': True, 'shell': shell, 'workspace': str(root),
                'verified': 'real init script, custom board names, all Scope options, required sync, unchanged managed hooks; fake GitHub only'}
    write(root / 'result.json', evidence)
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shell', choices=('pwsh', 'bash'), required=True)
    smoke(parser.parse_args().shell)
