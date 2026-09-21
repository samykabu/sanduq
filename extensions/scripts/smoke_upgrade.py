#!/usr/bin/env python3
"""Exercise an actual published PR 4.0.2 -> staged 4.1.0 upgrade and failure rollback."""
import hashlib
import json
import subprocess
import sys
import zipfile
import yaml
from pathlib import Path
from smoke_install import smoke


def main():
    initial = smoke('codex')
    workspace = Path(initial['workspace']); root = workspace / 'project'
    source = workspace / 'packages/workflow'
    sys.path.insert(0, str(root / '.specify/extensions/workflow/scripts'))
    import install as installer
    from reconcile import reconcile
    from workflow import WorkflowError, registry
    downloads = workspace / 'published'; downloads.mkdir()
    subprocess.run(['gh','release','download','pr-v4.0.2','--repo','samykabu/sanduq','--pattern','pr.zip','--dir',str(downloads)],check=True)
    with zipfile.ZipFile(downloads/'pr.zip') as archive:
        require_safe = all((downloads / name).resolve().is_relative_to(downloads.resolve()) for name in archive.namelist())
        if not require_safe: raise RuntimeError('Unsafe archive path')
        archive.extractall(downloads)
    legacy = next(downloads.rglob('extension.yml')).parent
    reconcile(root,apply=True,restore=True)
    installer.command(root,['specify','extension','add','--dev',str(legacy),'--force'],[])
    reconcile(root,apply=True)
    config = root / '.specify/extensions/pr/config.json'
    config.write_text('{"custom_project_setting":"preserve-me"}\n',encoding='utf-8')
    assert registry(root)['pr']['version'] == '4.0.2'
    before = installer.managed_files(root)
    def fail_after_real_upgrade(repo,args,log):
        installer.command(repo,args,log)
        if args[:3] == ['specify','extension','add']:
            raise WorkflowError('Injected interruption after successful native extension upgrade')
    try:
        installer.install(root,apply=True,packages=workspace/'packages',package_root=source,runner=fail_after_real_upgrade)
        raise AssertionError('Expected injected failure')
    except WorkflowError as error:
        assert 'INSTALL_ROLLED_BACK' in str(error), error
    assert installer.managed_files(root) == before, 'Rollback did not restore all managed file bytes'
    assert registry(root)['pr']['version'] == '4.0.2'
    result = installer.install(root,apply=True,packages=workspace/'packages',package_root=source)
    assert registry(root)['pr']['version'] == '4.1.0'
    assert json.loads(config.read_text()) == {'custom_project_setting':'preserve-me'}
    assert json.loads((root/'.specify/workflow/install-receipt.json').read_text())['applied']
    # A synthetic future workflow package tests the outer transaction without publishing it.
    from upgrade import upgrade
    manifest = source / 'extension.yml'
    metadata = yaml.safe_load(manifest.read_text(encoding='utf-8'))
    current_version = str(metadata['extension']['version'])
    major, minor, patch = map(int, current_version.split('.'))
    future_version = f'{major}.{minor}.{patch + 1}'
    metadata['extension']['version'] = future_version
    manifest.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding='utf-8')
    workflow_before = installer.managed_files(root)
    def fail_after_integration(repo, args, log):
        installer.command(repo, args, log)
        if args[0] == sys.executable:
            raise WorkflowError('Injected interruption after new workflow integration install')
    try:
        upgrade(root, future_version, apply=True, packages=workspace / 'packages', runner=fail_after_integration)
        raise AssertionError('Expected outer upgrade failure')
    except WorkflowError as error:
        assert 'WORKFLOW_UPGRADE_ROLLED_BACK' in str(error), error
    assert installer.managed_files(root) == workflow_before, 'Outer workflow rollback changed managed state'
    assert registry(root)['workflow']['version'] == current_version
    workflow_result = upgrade(root, future_version, apply=True, packages=workspace / 'packages')
    assert registry(root)['workflow']['version'] == future_version
    for relative in ('scripts/progress.py', 'skills/workflow/references/execution.md'):
        assert (root / '.specify/extensions/workflow' / relative).read_bytes() == (source / relative).read_bytes()
    assert json.loads(config.read_text()) == {'custom_project_setting':'preserve-me'}
    receipt = {'ok':True,'from':'pr 4.0.2 (downloaded published asset)','to':'pr 4.1.0 (staged)',
               'published_archive_sha256':hashlib.sha256((downloads/'pr.zip').read_bytes()).hexdigest(),
               'verified':['real native CLI upgrade','injected post-upgrade failure','byte-exact managed rollback',
                           'retry succeeds','custom config retained','policy and preset registration retained',
                           f'workflow {current_version} to synthetic staged {future_version} self-upgrade',
                           'outer rollback after successful integration install', 'self-upgrade retry succeeds'],
               'workflow_upgrade_backup': workflow_result['backup'],
               'workspace':str(workspace),'upgrade_backup':result['backup']}
    (workspace/'upgrade-result.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__': main()
