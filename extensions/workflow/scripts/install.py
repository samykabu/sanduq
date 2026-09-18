#!/usr/bin/env python3
"""Install the policy-selected Sanduq packages through public Spec Kit commands.

Dry-run by default. Apply records a local backup and rolls back on failure.
No shell interpolation, catalog-name resolution, or generated-command patching.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path
import yaml
from packaging.version import Version
from packaging.specifiers import SpecifierSet
from workflow import load_policy, read, write, require, inside, registry, doctor, locked, WorkflowError, RANGES, ensure_local_excludes, package_digest, active_host
from reconcile import reconcile

PACKAGE = Path(__file__).resolve().parents[1]
DIRECTORIES = ('.specify/extensions', '.specify/presets')
FILES = ('.specify/extensions.yml', '.specify/workflow.yml', '.specify/workflow/integration-backup.json',
         '.specify/workflow/install-lock.json',
         '.specify/workflow/install-receipt.json',
         '.github/workflows/sanduq-workflow-gates.yml', '.github/workflows/documentation-gates.yml')


def managed_files(root):
    files = set()
    for folder in DIRECTORIES:
        path = inside(root, folder)
        if path.exists(): files.update(p for p in path.rglob('*') if p.is_file() or p.is_symlink())
    for folder in ('.agents/skills', '.claude/skills', '.claude/commands'):
        path = inside(root, folder)
        if path.exists():
            for item in path.glob('speckit*'):
                files.update([item] if item.is_file() or item.is_symlink() else (p for p in item.rglob('*') if p.is_file() or p.is_symlink()))
    files.update(root / f for f in FILES if (root / f).is_file())
    require(all(p.resolve().is_relative_to(root) and not (p.is_symlink() and p.is_dir()) for p in files), 'MANAGED_PATH_SYMLINK_UNSUPPORTED')
    return {p.relative_to(root).as_posix(): {'symlink': str(p.readlink())} if p.is_symlink() else p.read_bytes() for p in files}


def snapshot(root, directory):
    files = managed_files(root)
    directory.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(directory / 'before.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            if isinstance(content, dict):
                info = zipfile.ZipInfo(name); info.create_system = 3; info.external_attr = 0o120777 << 16
                archive.writestr(info, content['symlink'])
            else: archive.writestr(name, content)
    write(directory / 'before.json', {p: v if isinstance(v, dict) else {'sha256': hashlib.sha256(v).hexdigest()} for p,v in files.items()})
    return files


def restore(root, files, expected):
    current = managed_files(root)
    require(current == expected, 'ROLLBACK_CONFLICT: managed files changed; backup retained for review')
    # Only exact managed files within the already-validated project are touched.
    # Preserve empty directories instead of recursively deleting computed paths.
    def lexical(name):
        path = root / name
        require(path.parent.resolve().is_relative_to(root), 'ROLLBACK_PATH_OUTSIDE_PROJECT')
        return path  # Do not resolve a symlink and accidentally unlink its target.
    for name in current.keys() - files.keys(): lexical(name).unlink()
    for name, content in sorted(files.items(), key=lambda item: isinstance(item[1], dict)):
        path = lexical(name); path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink(): path.unlink()
        if isinstance(content, dict):
            if path.exists(): path.unlink()
            path.symlink_to(content['symlink'])
        else: path.write_bytes(content)


def command(root, args, log):
    result = subprocess.run(args, cwd=root, input='y\n', capture_output=True, text=True, encoding='utf-8')
    log.append({'args': args, 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
    require(result.returncode == 0, 'INSTALL_COMMAND_FAILED: ' + ' '.join(args))


def preservation(root, name):
    folder = root / '.specify/extensions' / name
    if not folder.exists(): return {}
    # These are consumer configuration/evidence, never package implementation.
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file()
            and (p.name in ('config.json', '.env') or p.name.endswith('-config.yml') or 'state' in p.relative_to(folder).parts)}


def install(root, apply=False, packages=None, package_root=PACKAGE, runner=command, upgrade_owner=None):
    root = root.resolve(); policy = load_policy(root)
    lock = read(package_root / 'dependencies.json')
    require(lock and lock.get('repository') == 'https://github.com/samykabu/sanduq', 'INVALID_DEPENDENCY_LOCK')
    selected = dict(lock['required'])
    for process, enabled in policy['processes'].items():
        if enabled: selected.update(lock['selected'][process])
    existing = registry(root); operations = []; retained = []
    order = ('illustrate', 'project', 'scope', 'pr', 'assure', 'user-manual')
    for name in sorted(selected, key=lambda key: order.index(key)):
        version = selected[name]
        manifest = root / '.specify/extensions' / name / 'extension.yml'
        meta = (yaml.safe_load(manifest.read_text(encoding='utf-8-sig')) or {}).get('extension', {}) if manifest.exists() else {}
        if name in existing:
            require(meta.get('repository', '').rstrip('/') == lock['repository'], 'EXISTING_EXTENSION_SOURCE_CONFLICT: ' + name)
            if existing[name].get('version') == version and existing[name].get('enabled') is True: continue
            if Version(existing[name]['version']) > Version(version):
                require(Version(existing[name]['version']) in SpecifierSet(RANGES.get(name, '>=2.1.2,<3')), 'NEWER_DEPENDENCY_INCOMPATIBLE: ' + name)
                require(existing[name].get('enabled') is True, 'NEWER_DEPENDENCY_DISABLED: enable after compatibility review, never downgrade implicitly')
                retained.append({'extension':name,'version':existing[name]['version'],'tested_baseline':version,
                                 'note':'Newer compatible package retained; active runs still require reviewed migration.'})
                continue
        if packages:
            source = packages.resolve() / name
            candidate = yaml.safe_load((source / 'extension.yml').read_text(encoding='utf-8-sig'))['extension']
            require((candidate['id'], str(candidate['version']), candidate['repository']) == (name, version, lock['repository']), 'STAGED_PACKAGE_IDENTITY_MISMATCH: ' + name)
            args = ['specify', 'extension', 'add', '--dev', str(source), '--force']
        else:
            url = f"{lock['repository']}/releases/download/{name}-v{version}/{name}.zip"
            args = ['specify', 'extension', 'add', name, '--from', url, '--force']
        operations.append({'extension':name,'version':version,'args':args})
    preset_ops = []
    for name, priority in (('scope-gate','2'),('scope-brainstorm','2'),('workflow','1')):
        source = package_root / 'presets' / name
        require((source / 'preset.yml').is_file(), 'BUNDLED_PRESET_MISSING: build/install the workflow archive first')
        preset_ops.append({'name':name,'source':str(source),'priority':priority})
    result = {'applied':False,'extensions':operations,'retained_newer':retained,'presets':preset_ops,'processes':policy['processes']}
    if not apply: return result
    upgrade = read(root / '.specify/workflow/runtime/upgrade.lock', {})
    require(not upgrade or upgrade.get('pid') == upgrade_owner, 'WORKFLOW_UPGRADE_IN_PROGRESS')
    bridge = read(root / '.specify/superpowers-handoff.json', {})
    require(bridge.get('status') not in ('executing','blocked'), 'LEGACY_EXECUTOR_OWNS_FEATURE: reconcile its actual work before installation')
    # A package update cannot occur while an executor owns unfinished work.
    for path in (root / 'specs').glob('*/workflow/checkpoint.json'):
        require(not read(path, {}).get('active'), 'ACTIVE_STAGE_MUST_BE_RESOLVED: ' + str(path))
    with locked(root / '.specify/workflow/runtime/dispatch.lock'), locked(root / '.specify/workflow/runtime/install.lock'):
        upgrade = read(root / '.specify/workflow/runtime/upgrade.lock', {})
        require(not upgrade or upgrade.get('pid') == upgrade_owner, 'WORKFLOW_UPGRADE_IN_PROGRESS')
        for path in (root / 'specs').glob('*/workflow/checkpoint.json'):
            require(not read(path, {}).get('active'), 'ACTIVE_STAGE_MUST_BE_RESOLVED: ' + str(path))
        ensure_local_excludes(root)
        backup = root / '.specify/workflow/backups/installs' / uuid.uuid4().hex
        before = snapshot(root, backup); log = []
        try:
            if (root / '.specify/workflow/integration-backup.json').exists():
                reconcile(root, apply=True, restore=True)
            for operation in operations:
                preserved = preservation(root, operation['extension'])
                runner(root, operation['args'], log)
                folder = root / '.specify/extensions' / operation['extension']
                for name, content in preserved.items():
                    p = folder / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(content)
            for operation in preset_ops:
                if (root / '.specify/presets' / operation['name'] / 'preset.yml').exists():
                    runner(root, ['specify','preset','remove',operation['name']], log)
                runner(root, ['specify','preset','add','--dev',operation['source'],'--priority',operation['priority']], log)
            alias = package_root / 'skills/speckit-scope/SKILL.md'
            accepted = read(package_root / 'assets/legacy-alias-hashes.json', [])
            for agent in ('.agents', '.claude'):
                skills = root / agent / 'skills'
                if not skills.is_dir(): continue
                destination = skills / 'speckit-scope/SKILL.md'
                if destination.exists() and destination.read_bytes() != alias.read_bytes():
                    value = hashlib.sha256(destination.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
                    require(value in accepted, 'SCOPE_ALIAS_HAS_LOCAL_EDITS: migrate this customization into Sanduq before replacement')
                destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(alias.read_bytes())
            reconcile(root, apply=True)
            target = root / '.github/workflows/sanduq-workflow-gates.yml'
            asset = package_root / 'assets/github/workflow-gates.yml'
            if target.exists():
                old_inventory = read(root / '.specify/workflow/install-receipt.json', {})
                require(target.read_bytes() == asset.read_bytes() or old_inventory.get('ci_sha256') == hashlib.sha256(target.read_bytes()).hexdigest(), 'CI_WORKFLOW_HAS_LOCAL_EDITS')
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(asset.read_bytes())
            legacy = root / '.github/workflows/documentation-gates.yml'
            reference = root / '.specify/extensions/assure/assets/github/documentation-gates.yml'
            if legacy.exists():
                require(reference.exists() and legacy.read_bytes().replace(b'\r\n',b'\n') == reference.read_bytes().replace(b'\r\n',b'\n'), 'LEGACY_CI_HAS_LOCAL_EDITS: reconcile selected processes explicitly')
                legacy.unlink()  # exact backed-up legacy gate; policy-aware gate replaces it
            health = doctor(root, policy); require(health['ok'], '; '.join(health['errors']))
            installed = registry(root)
            inventory = {}
            for name in sorted(set(selected) | {'workflow'}):
                entry = installed.get(name, {})
                version = entry.get('version')
                inventory[name] = {key: entry.get(key) for key in ('version', 'enabled', 'manifest_hash', 'source')}
                inventory[name]['release_url'] = f"{lock['repository']}/releases/download/{name}-v{version}/{name}.zip"
                inventory[name]['distribution'] = 'local-development' if entry.get('source') == 'local' else 'release'
            write(root / '.specify/workflow/install-lock.json', {
                'schema_version': 1, 'host': active_host(root), 'processes': policy['processes'],
                'extensions': inventory, 'dependency_digest': package_digest(root),
                'presets': {name: {key: entry.get(key) for key in ('version', 'enabled', 'priority', 'manifest_hash')}
                            for name, entry in read(root / '.specify/presets/.registry', {}).get('presets', {}).items()},
                'tested_compatibility': {'spec_kit': lock.get('tested_spec_kit', {}), 'upstream_optional': lock.get('upstream_optional', {})},
            })
            receipt = {**result,'applied':True,'backup':str(backup),'commands':log,'ci_sha256':hashlib.sha256(asset.read_bytes()).hexdigest()}
            write(root / '.specify/workflow/install-receipt.json', receipt)
            write(backup / 'result.json', {'ok':True,'commands':log})
            return receipt
        except Exception as exc:
            failed = managed_files(root)
            write(backup / 'result.json', {'ok':False,'error':str(exc),'commands':log})
            restore(root, before, failed)
            raise WorkflowError('INSTALL_ROLLED_BACK: ' + str(exc) + '; backup: ' + str(backup)) from exc


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--packages', type=Path, help='Extracted, verified local package directory for offline development')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--upgrade-owner', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.root,args.apply,args.packages,upgrade_owner=args.upgrade_owner),indent=2))
    except (WorkflowError, ValueError, OSError, KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)})); sys.exit(1)
