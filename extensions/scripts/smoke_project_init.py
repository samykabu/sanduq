#!/usr/bin/env python3
"""Exercise the real Project Init script (or a one-release shell stub) against a local fake GitHub board,
without remote writes. The fake `gh` sits first on PATH on Linux, macOS and Windows."""
import argparse
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
import yaml

from package import package

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'extensions/workflow/scripts'))
from workflow import default_policy, project_errors, write

FAKE_GH = """import json, os, sys
with open(os.environ['SANDUQ_PROJECT_FIXTURE'], encoding='utf-8') as stream: data = json.load(stream)
args = sys.argv[1:]
if args[:2] == ['auth', 'status']: print("Logged in to github.com\\n  - Token scopes: 'project', 'repo'")
elif args[:2] == ['project', 'view']: print(json.dumps(data['project']))
elif args[:2] == ['project', 'field-list']: print(json.dumps(data['fields']))
else: raise SystemExit('Unexpected or mutating GitHub operation in Project Init fixture')
"""


def fake_gh(bindir, source):
    """A `gh` that runs `source` with this interpreter. On Windows, where a subprocess finds only .exe files,
    it is pip's console-script launcher with the script appended as a zip."""
    bindir.mkdir(exist_ok=True)
    if os.name != 'nt':
        (bindir / 'gh').write_text('#!' + sys.executable + '\n' + source, encoding='utf-8', newline='\n')
        (bindir / 'gh').chmod(0o755)
        return
    pip = importlib.util.find_spec('pip')
    launcher = pip and Path(pip.origin).parent / '_vendor/distlib/t64.exe'
    if not launcher or not launcher.is_file():
        raise RuntimeError('pip is needed to build the fake gh.exe')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('__main__.py', source)
    (bindir / 'gh.exe').write_bytes(launcher.read_bytes() + b'#!"' + sys.executable.encode() + b'"\r\n' + archive.getvalue())


def smoke(shell):
    parent = ROOT / 'dist/project-init-tests'; parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=shell + '-', dir=parent)).resolve()
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    # The installed layout: the package carries the shared helpers project_init.py imports.
    for extension in ('project', 'workflow'):
        with zipfile.ZipFile(package(extension, output=root / (extension + '.zip'))['archive']) as archive:
            archive.extractall(root / '.specify/extensions')
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
    fake_gh(root / 'fakebin', FAKE_GH)
    # The stubs run `python` from PATH: this interpreter's folder comes right after the fake gh.
    env['PATH'] = os.pathsep.join([str(root / 'fakebin'), str(Path(sys.executable).parent), env.get('PATH', '')])
    scripts = root / '.specify/extensions/project/scripts'
    flags = ['--owner', 'acme', '--number', '1', '--owner-type', 'org', '--json']
    if shell == 'pwsh':
        args = ['pwsh', '-NoProfile', '-File', str(scripts / 'powershell/project-init.ps1'),
                '-Owner', 'acme', '-Number', '1', '-OwnerType', 'org', '-NonInteractive', '-Json']
    elif shell == 'bash':
        args = ['bash', (scripts / 'bash/project-init.sh').as_posix(), *flags, '--non-interactive']
    else:
        args = [sys.executable, str(scripts / 'project_init.py'), *flags]
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
    parser.add_argument('--shell', choices=('python', 'pwsh', 'bash'), default='python',
                        help='python runs project_init.py; pwsh and bash run the one-release stubs')
    smoke(parser.parse_args().shell)
