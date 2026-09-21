#!/usr/bin/env python3
"""Exercise public Spec Kit install/reinstall in a fresh local fixture, without GitHub writes."""
import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from package import package, ROOT


def smoke(host, superspec_source=None):
    folder = ROOT / 'dist/install-tests'; folder.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=host + '-', dir=folder)).resolve()
    assert workspace.is_relative_to(folder.resolve())
    project = workspace / 'project'; project.mkdir()
    commands = []
    def run(args, expected=0):
        result = subprocess.run(args, cwd=project, input='y\n', text=True, encoding='utf-8', capture_output=True)
        commands.append({'args': args, 'exit_code': result.returncode})
        (workspace / f'{len(commands):02d}.log').write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
        if result.returncode != expected:
            raise RuntimeError(f'{args} failed ({result.returncode}); inspect {workspace}')
        return result.stdout
    run(['specify','init','--here','--non-interactive','--ignore-agent-tools','--integration',host] + (['--integration-options=--skills'] if host == 'codex' else []))
    for name in ('illustrate','project','scope','pr','assure','user-manual','workflow'):
        result = package(name, output=workspace / 'archives' / (name + '.zip'))
        with zipfile.ZipFile(result['archive']) as archive: archive.extractall(workspace / 'packages')
        if name == 'workflow': run(['specify','extension','add','--dev',str(workspace / 'packages' / name)])
    if superspec_source:
        run(['specify','extension','add','--dev',str(superspec_source.resolve())])
    runtime = str(project / '.specify/extensions/workflow/scripts/workflow.py')
    installer = str(project / '.specify/extensions/workflow/scripts/install.py')
    # Initialization selections are independent of installed optional packages.
    for qa, manual in (('off','off'),('on','off'),('off','on'),('on','on')):
        run([sys.executable,runtime,'init','--qa',qa,'--manual',manual,'--replace'])
        run([sys.executable,installer,'--packages',str(workspace / 'packages'),'--apply'])
        result = json.loads(run([sys.executable,runtime,'doctor']))
        assert result['ok'], result
    agent = '.agents' if host == 'codex' else '.claude'
    required = ['speckit-specify','speckit-plan','speckit-tasks','speckit-taskstoissues','speckit-implement']
    if superspec_source: required += ['speckit-superspec-brainstorm','speckit-superspec-tasks','speckit-superspec-execute']
    snapshots = {}
    for name in required:
        path = project / agent / 'skills' / name / 'SKILL.md'
        text = path.read_text(encoding='utf-8')
        assert text.count('<!-- sanduq-workflow-managed:v1 -->') == 1, name
        assert len(text) > 2500, 'Lost upstream command body: ' + name
        snapshots[name] = text
    protocol = '.specify/extensions/workflow/skills/workflow/references/execution.md'
    execution_names = ['speckit-implement']
    if superspec_source:
        execution_names.append('speckit-superspec-execute')
    for name in execution_names:
        assert protocol in snapshots[name], 'Missing execution protocol: ' + name
    installed_workflow = project / '.specify/extensions/workflow'
    execution_files = ('skills/workflow/references/execution.md', 'scripts/progress.py')
    execution_snapshots = {}
    for relative in execution_files:
        installed = (installed_workflow / relative).read_bytes()
        assert installed == (workspace / 'packages/workflow' / relative).read_bytes(), relative
        execution_snapshots[relative] = installed
    tasks = project / 'specs/001-smoke/tasks.md'
    tasks.parent.mkdir(parents=True)
    tasks.write_text('- [ ] T001 Verify installed report\n', encoding='utf-8')
    report = tasks.parent / 'workflow/progress'
    progress = str(installed_workflow / 'scripts/progress.py')
    run([sys.executable,progress,'init','--tasks',str(tasks),'--output',str(report)])
    run([sys.executable,progress,'task','--output',str(report),'--id','T001',
         '--status','running','--agent','smoke-worker','--note','Reinstall must retain this work'])
    report_before = (report / 'state.json').read_bytes()
    assert 'smoke-worker' in (report / 'index.html').read_text(encoding='utf-8')
    # Public reinstall must preserve composition and selected policy.
    before_policy = (project / '.specify/workflow.yml').read_bytes()
    run(['specify','extension','add','--dev',str(workspace / 'packages/workflow'),'--force'])
    for name, previous in snapshots.items():
        assert (project / agent / 'skills' / name / 'SKILL.md').read_text(encoding='utf-8') == previous
    assert (project / '.specify/workflow.yml').read_bytes() == before_policy
    for relative, previous in execution_snapshots.items():
        assert (installed_workflow / relative).read_bytes() == previous, relative
    assert (report / 'state.json').read_bytes() == report_before
    run([sys.executable,progress,'task','--output',str(report),'--id','T001','--status','done'])
    assert json.loads((report / 'state.json').read_text(encoding='utf-8'))['tasks'][0]['status'] == 'done'
    result = {'host':host,'superspec':bool(superspec_source),'ok':True,'workspace':str(workspace),'commands':commands,
              'verified':'installation, executor composition, bundled execution protocol, installed report CLI and state preservation, four policy choices, reconciliation, doctor and same-version reinstall; no semantic agent execution or live GitHub acceptance'}
    (workspace / 'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=('codex','claude'), required=True)
    parser.add_argument('--superspec-source', type=Path)
    args = parser.parse_args()
    result = smoke(args.host,args.superspec_source)
    print(json.dumps({k:v for k,v in result.items() if k != 'commands'},indent=2))
