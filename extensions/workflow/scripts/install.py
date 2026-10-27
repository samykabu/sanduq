#!/usr/bin/env python3
"""Install the policy-selected Sanduq packages through public Spec Kit commands.

Dry-run by default. Apply records a local backup and rolls back on failure.
No shell interpolation, catalog-name resolution, or generated-command patching.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import ntpath
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from urllib.parse import quote
import yaml
from packaging.version import InvalidVersion, Version
from packaging.specifiers import SpecifierSet
from workflow import load_policy, read, write, require, inside, registry, doctor, locked, WorkflowError, RANGES, ensure_local_excludes, package_digest, active_host, github_repository, sanduq_ci, git, now, explain
from reconcile import reconcile
from delegate_dispatch import maintenance_preflight
from delegation import is_junction, is_link
from hosts import (ALIASES, HOST_SKILLS, CODEX_HOOK_APPROVAL, ROLE_FILES, ROLES, alias_wanted, aliases_enabled,
                   installed_hosts, register_hosts, skill_errors, skill_report)
try:
    import sanduq_gh
except ModuleNotFoundError:  # the source tree; package.py copies it into scripts/
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'shared'))
    import sanduq_gh

PACKAGE = Path(__file__).resolve().parents[1]
DIRECTORIES = ('.specify/extensions', '.specify/presets')
FILES = ('.specify/extensions.yml', '.specify/workflow.yml', '.specify/integration.json', '.specify/init-options.json', '.specify/workflow/integration-backup.json',
         '.specify/workflow/install-lock.json',
         '.specify/workflow/install-receipt.json',
         '.github/workflows/sanduq-workflow-gates.yml', '.github/workflows/documentation-gates.yml',
         # Host files the guard hook and role agents are merged into (hosts.apply_host_files).
         '.claude/settings.json', '.codex/hooks.json', '.codex/config.toml',
         *(pattern.format(role) for pattern in ROLE_FILES.values() for role in ROLES))


# Raw delegate-task run artifacts and dependencies are not skill content. They
# can hold secrets a harness printed and change while a run is live.
SKILL_RAW_DATA = ('runs', 'node_modules')


def skill_files(folder):
    """The delegate-task folder's own files, pruning raw run data and dependencies."""
    found = []
    for directory, dirs, names in os.walk(folder):
        here = Path(directory)
        if here == folder:
            dirs[:] = [d for d in dirs if d not in SKILL_RAW_DATA]
        # Never descend into a symlinked or junctioned folder; keep it as an
        # entry so the link rule below still applies inside the skill.
        links = [d for d in dirs if is_link(here / d)]
        dirs[:] = [d for d in dirs if d not in links]
        found += [here / d for d in links]
        found += [here / n for n in names]
    return found


def managed_files(root):
    files = set()
    # A symlinked or junctioned delegate-task folder is a user-managed install.
    # It is kept as one link, never followed, so rollback restores the link itself.
    skill_links = set()
    for folder in DIRECTORIES:
        path = inside(root, folder)
        if path.exists(): files.update(p for p in path.rglob('*') if p.is_file() or p.is_symlink())
    for folder in ('.agents/skills', '.claude/skills', '.claude/commands'):
        path = inside(root, folder)
        if path.exists():
            for item in path.glob('speckit*'):
                files.update([item] if item.is_file() or item.is_symlink() else (p for p in item.rglob('*') if p.is_file() or p.is_symlink()))
            # Not glob('delegate-task'): Python 3.11 matches a literal name with exists(), which drops a dangling link.
            for item in [path / 'delegate-task'] if os.path.lexists(path / 'delegate-task') else []:
                if is_link(item):
                    skill_links.add(item)
                elif item.is_dir():
                    files.update(skill_files(item))
                else:
                    files.add(item)
    # Delegation decisions are tracked feature history, not generated report
    # state. Include them in rollback snapshots without rewriting them.
    files.update((root / 'specs').glob('*/workflow/delegations.json'))
    files.update(root / f for f in FILES if (root / f).is_file())
    require(all(p.resolve().is_relative_to(root) and not (is_link(p) and p.is_dir()) for p in files), 'MANAGED_PATH_SYMLINK_UNSUPPORTED')
    # A link's own location must be inside the project; its target need not be.
    require(all(p.parent.resolve().is_relative_to(root) for p in skill_links), 'MANAGED_PATH_SYMLINK_UNSUPPORTED')
    result = {p.relative_to(root).as_posix(): {'symlink': str(p.readlink())} if p.is_symlink() else p.read_bytes() for p in files}
    # A skill link is always a folder link, even while its target is missing:
    # asking the target would restore a dangling link as a file link on Windows.
    # A junction is recorded as one, so rollback never turns it into a symlink.
    result.update({p.relative_to(root).as_posix(): {'symlink': str(p.readlink()), 'directory': True,
                                                    **({'junction': True} if is_junction(p) else {})}
                   for p in skill_links})
    return result


def remove_link(path):
    """Remove a symlink or junction itself; Windows removes a directory link with rmdir."""
    try:
        path.unlink()
    except (IsADirectoryError, PermissionError):
        if not is_link(path):
            raise
        os.rmdir(path)


# os.readlink reports a drive-letter junction target as \\?\C:\...; the
# reparse data stores it as \??\C:\.... A volume path (\\?\Volume{...}\) keeps
# its prefix, since without it the path means something else.
EXTENDED_PATH_PREFIX = '\\\\?\\'
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
FSCTL_SET_REPARSE_POINT = 0x000900A4


def junction_target(value):
    value = str(value)
    rest = value[len(EXTENDED_PATH_PREFIX):]
    drive = value.startswith(EXTENDED_PATH_PREFIX) and len(rest) >= 3 and rest[1:3] == ':\\'
    return rest if drive else value


def mount_point_data(target):
    """The REPARSE_DATA_BUFFER of a junction to ``target``, byte for byte.

    This is the record ``mklink /J`` writes. Nothing in it is parsed by a shell,
    and the target need not exist, so a dangling junction comes back exactly.
    """
    import struct
    substitute = '\\??\\' + (target[len(EXTENDED_PATH_PREFIX):]
                             if target.startswith(EXTENDED_PATH_PREFIX) else target)
    names = (substitute + '\0' + target + '\0').encode('utf-16-le')
    substitute_bytes, print_bytes = len(substitute) * 2, len(target) * 2
    body = struct.pack('<HHHH', 0, substitute_bytes, substitute_bytes + 2, print_bytes) + names
    return struct.pack('<LHH', IO_REPARSE_TAG_MOUNT_POINT, len(body), 0) + body


def set_mount_point(path, target):
    """Turn the empty folder ``path`` into a junction to ``target``."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    kernel.DeviceIoControl.restype = wintypes.BOOL
    kernel.DeviceIoControl.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                       wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                       wintypes.LPVOID)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    generic_write, open_existing = 0x40000000, 3
    backup_semantics, open_reparse_point = 0x02000000, 0x00200000
    handle = kernel.CreateFileW(str(path), generic_write, 0, None, open_existing,
                                backup_semantics | open_reparse_point, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        data = mount_point_data(target)
        buffer = ctypes.create_string_buffer(data, len(data))
        returned = wintypes.DWORD()
        if not kernel.DeviceIoControl(handle, FSCTL_SET_REPARSE_POINT, buffer, len(data),
                                      None, 0, ctypes.byref(returned), None):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def create_junction(path, target):
    """Create a Windows directory junction at ``path`` pointing at ``target``.

    It writes the junction's reparse data directly, so the target is kept
    exactly, whether or not it exists, and never reaches a shell that would
    expand %NAME% or other metacharacters in it. The target is never touched.
    """
    require(os.name == 'nt', 'ROLLBACK_JUNCTION_UNSUPPORTED: junctions exist only on Windows')
    target = junction_target(target)
    # A junction names a local volume: a drive path or a \\?\Volume{...}\ path.
    require((ntpath.isabs(target) and not target.startswith('\\\\')) or target.startswith(EXTENDED_PATH_PREFIX),
            'ROLLBACK_JUNCTION_FAILED: ' + str(path) + ' -> ' + target + ': not a local absolute path')
    os.mkdir(path)
    try:
        set_mount_point(path, target)
    except Exception as error:
        os.rmdir(path)
        raise WorkflowError('ROLLBACK_JUNCTION_FAILED: ' + str(path) + ' -> ' + target + ': ' + str(error)) from error
    require(is_junction(path) and junction_target(os.readlink(path)) == target,
            'ROLLBACK_JUNCTION_FAILED: ' + str(path) + ' does not point at ' + target)


def clear_emptied_folder(path):
    """Remove a real folder that rollback has already emptied of managed files."""
    if not path.is_dir() or is_link(path):
        return
    for item in sorted(path.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        item.rmdir()
    path.rmdir()


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


BACKUP_KINDS = ('installs', 'upgrades', 'hosts')
KEEP_BACKUP_ZIPS = 3
# Written after the snapshot and removed after success or a completed rollback; a hard kill leaves it, and doctor
# then reports INSTALL_INTERRUPTED with the restore command (AHMED-09).
IN_PROGRESS = '.specify/workflow/runtime/install-in-progress.json'


def mark_in_progress(root, kind, backup):
    write(root / IN_PROGRESS, {'kind': kind, 'backup': str(backup), 'pid': os.getpid(), 'started_at': now()})


def clear_in_progress(root):
    (root / IN_PROGRESS).unlink(missing_ok=True)


def restore_backup(root, backup):
    """`install.py --restore <backup>`: put back the managed files that folder's before.zip holds."""
    root, backup = root.resolve(), Path(backup).resolve()
    manifest = read(backup / 'before.json') if (backup / 'before.json').is_file() else None
    require(isinstance(manifest, dict) and (backup / 'before.zip').is_file(),
            'RESTORE_BACKUP_INVALID: ' + str(backup) + ' holds no before.json and before.zip pair')
    with zipfile.ZipFile(backup / 'before.zip') as archive:  # links keep their before.json record; files their bytes
        files = {name: entry if 'sha256' not in entry else archive.read(name) for name, entry in manifest.items()}
    with locked(root / '.specify/workflow/runtime/dispatch.lock'), locked(root / '.specify/workflow/runtime/install.lock'):
        restore(root, files, managed_files(root))
        clear_in_progress(root)
    return {'restored': True, 'backup': str(backup), 'files': len(files)}


def backup_zips(root):
    """Every install, upgrade and host-switch ``before.zip``, newest first."""
    base = root / '.specify/workflow/backups'
    found = [p for kind in BACKUP_KINDS for p in (base / kind).glob('*/before.zip') if p.is_file()]
    return sorted(found, key=lambda p: p.stat().st_mtime_ns, reverse=True)


def backup_usage(root):
    """Count and bytes of the kept backup zips, for doctor and the apply result."""
    zips = backup_zips(root)
    return {'zips': len(zips), 'bytes': sum(p.stat().st_size for p in zips)}


def prune_backups(root, keep=KEEP_BACKUP_ZIPS):
    """After a successful apply, delete all but the newest ``keep`` zips.

    before.json, result.json and alias backups stay. Never raises: the apply already succeeded.
    """
    try:
        for path in backup_zips(root)[keep:]:
            path.unlink(missing_ok=True)
        return backup_usage(root)
    except OSError as exc:
        return {'error': 'BACKUP_PRUNE_FAILED: ' + str(exc)}


def restore(root, files, expected):
    current = managed_files(root)
    require(current == expected, 'ROLLBACK_CONFLICT: managed files changed; backup retained for review')
    # A folder link comes back only where rollback leaves nothing behind: an
    # unmanaged file there (such as a new copy's run data) is never deleted.
    for name, content in files.items():
        folder = root / name
        if isinstance(content, dict) and content.get('directory') and folder.is_dir() and not is_link(folder):
            leftovers = [p for p in folder.rglob('*') if not p.is_dir() and p.relative_to(root).as_posix() not in current]
            require(not leftovers, 'ROLLBACK_CONFLICT: unmanaged files in ' + name + '; backup retained for review')
    # Only exact managed files within the already-validated project are touched.
    # Preserve empty directories instead of recursively deleting computed paths.
    def lexical(name):
        path = root / name
        require(path.parent.resolve().is_relative_to(root), 'ROLLBACK_PATH_OUTSIDE_PROJECT')
        return path  # Do not resolve a symlink and accidentally unlink its target.
    # Make every junction first, beside the runtime files, so one that cannot be
    # made stops the rollback before anything changes. A junction is never
    # brought back as a symlink.
    staged = {}
    try:
        for name, content in files.items():
            if isinstance(content, dict) and content.get('junction'):
                lexical(name)
                runtime = root / '.specify/workflow/runtime'; runtime.mkdir(parents=True, exist_ok=True)
                staged[name] = runtime / ('junction-restore-' + uuid.uuid4().hex)
                create_junction(staged[name], content['symlink'])
    except Exception as error:
        for link in staged.values():
            if os.path.lexists(link): os.rmdir(link)  # A junction or a half-made empty folder.
        raise WorkflowError('ROLLBACK_JUNCTION_FAILED: nothing was restored; backup retained for review: ' +
                            str(error)) from error
    try:
        for name in current.keys() - files.keys():
            path = lexical(name)
            remove_link(path) if is_link(path) else path.unlink()
        for name, content in sorted(files.items(), key=lambda item: isinstance(item[1], dict)):
            path = lexical(name); path.parent.mkdir(parents=True, exist_ok=True)
            if is_link(path): remove_link(path)
            if isinstance(content, dict):
                if content.get('directory'): clear_emptied_folder(path)
                if path.exists(): path.unlink()
                if content.get('junction'):
                    staged.pop(name).rename(path)  # Moves the junction itself, never its target.
                else:
                    path.symlink_to(content['symlink'], target_is_directory=bool(content.get('directory')))
            else: path.write_bytes(content)
    finally:
        for link in staged.values():
            if os.path.lexists(link): os.rmdir(link)  # A junction or a half-made empty folder.


def delegation_preflight(root):
    """Refuse while a delegation attempt is live; dispatchers already see this lock.

    delegate_dispatch is imported with this module, never lazily here: a first
    import would write bytecode into the managed scripts folder mid-transaction.
    """
    try:
        maintenance_preflight(root)
    except ValueError as exc:
        raise WorkflowError(str(exc)) from exc


def memory_archive_preflight(root):
    """Refuse while a Memory archive run is active: the apply changes Memory's hooks, which its approval binds.

    Memory records the active run in <git common dir>/sanduq-memory/active.json (archive.py active_id).
    """
    if not (root / '.specify/extensions/memory/scripts/archive.py').is_file():
        return
    common = Path(git(root, 'rev-parse', '--git-common-dir'))
    active = read((common if common.is_absolute() else root / common).resolve() / 'sanduq-memory/active.json', {})
    run_id = active.get('run_id') if isinstance(active, dict) else active
    require(not run_id, f'MEMORY_ARCHIVE_ACTIVE: archive run {run_id} is not finished; resume or roll it back with '
                        f'"/speckit.memory.session --run {run_id}" (or see "python .specify/extensions/memory/scripts/'
                        'archive.py status"), then run this again')


def command(root, args, log):
    result = subprocess.run(args, cwd=root, input='y\n', capture_output=True, text=True, encoding='utf-8')
    log.append({'args': args, 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
    require(result.returncode == 0, 'INSTALL_COMMAND_FAILED: ' + ' '.join(args) + ': ' + failure_message(result))


def failure_message(result):
    """A failed command's own message: the last paragraph of stderr, else stdout, unwrapped (Spec Kit's Rich console
    wraps at 80 columns); for a failed installer run, the `error` of its JSON result."""
    for text in (result.stderr, result.stdout):
        paragraphs = [p for p in re.split(r'\n\s*\n', (text or '').strip()) if p.strip()]
        if paragraphs:
            last = ' '.join(paragraphs[-1].split())
            try:
                last = json.loads(last).get('error') or last
            except (ValueError, AttributeError):
                pass
            return str(last)[-500:]
    return 'no output, exit code ' + str(result.returncode)


def speckit_version(root):
    """The installed Spec Kit CLI version from `specify --version` ("specify 1.0.11"), or None when unknown."""
    try:
        done = subprocess.run(['specify', '--version'], cwd=root, capture_output=True, text=True, encoding='utf-8',
                              timeout=30)
        return str(Version(re.search(r'specify\s+(\S+)', done.stdout or '').group(1)))
    except (OSError, subprocess.TimeoutExpired, AttributeError, InvalidVersion):
        return None


def check_speckit_requirement(root, name, version, spec, asked):
    """Spec Kit refuses a package whose `requires.speckit_version` excludes it only mid-apply; refuse in preview."""
    current = speckit_version(root) if spec else None
    if current is None:
        return  # nothing to check, or Spec Kit's version is unknown: Spec Kit still checks on add
    require(SpecifierSet(spec).contains(Version(current), prereleases=True),
            f'OPTIONAL_PACKAGE_SPECKIT_INCOMPATIBLE: {name} {version} requires spec-kit {spec}; installed {current}. '
            'Upgrade Spec Kit' + (f' or run without --with {name}.' if asked else '.'))


def preservation(root, name):
    folder = root / '.specify/extensions' / name
    if not folder.exists(): return {}
    # These are consumer configuration/evidence, never package implementation.
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file()
            and (p.name in ('config.json', '.env') or p.name.endswith('-config.yml') or 'state' in p.relative_to(folder).parts)}


def rendered(asset, policy):
    """The shipped CI template rendered for this project's recorded selection."""
    try:
        return sanduq_ci.render(asset.read_bytes(), policy.get('ci') or sanduq_ci.default_ci())
    except sanduq_ci.CIPolicyError as exc:
        raise WorkflowError('CI_RENDER_FAILED: ' + asset.name + ': ' + str(exc)) from exc


def required_gate_checks(root):
    """Read active branch rules before removing a previously installed gate job."""
    repo = github_repository(root)

    def api(endpoint, missing_ok=False):
        try:
            data = sanduq_gh.api(endpoint, cwd=root, timeout=60)
        except sanduq_gh.GhError as exc:
            if exc.timeout:
                raise WorkflowError('CI_BRANCH_RULE_INSPECTION_FAILED: gh api ' + endpoint + ' timed out after 60 s') from exc
            if missing_ok and ('HTTP 404' in exc.stderr or 'Not Found' in exc.stderr):
                return None
            raise WorkflowError('CI_BRANCH_RULE_INSPECTION_FAILED: ' + exc.stderr.strip()[:400]) from exc
        except ValueError as exc:
            raise WorkflowError('CI_BRANCH_RULE_RESPONSE_INVALID') from exc
        require(data is not None, 'CI_BRANCH_RULE_RESPONSE_INVALID')  # an empty body
        return data

    branch = api('repos/' + repo)['default_branch']
    endpoint = 'repos/' + repo + '/rules/branches/' + quote(branch, safe='')
    rules = api(endpoint)
    require(isinstance(rules, list), 'CI_BRANCH_RULE_RESPONSE_INVALID')
    names = []
    for rule in rules:
        if rule.get('type') == 'required_status_checks':
            for check in rule.get('parameters', {}).get('required_status_checks', []):
                names.append(check.get('context') if isinstance(check, dict) else check)
    protection = api('repos/' + repo + '/branches/' + quote(branch, safe='') +
                     '/protection/required_status_checks', missing_ok=True)
    if protection:
        names.extend(protection.get('contexts', []))
        names.extend(check.get('context') for check in protection.get('checks', []))
    return sorted({name for name in names if isinstance(name, str)
                   and ('workflow-evidence' in name or 'Sanduq workflow gates' in name)})


# The lines Assure's AU8 added to documentation-gates.yml; keep equal to assure_init.HEAD_CHECKOUT.
ASSURE_HEAD_CHECKOUT = (b"          # The recorded states describe the PR head, not GitHub's merge commit.\n"
                        b"          ref: ${{ github.event.pull_request.head.sha }}\n")


def ci_matches_managed(content, asset, receipt):
    # Git may convert this managed YAML between LF and CRLF after installation.
    normalized = content.replace(b'\r\n', b'\n')
    if normalized == asset.replace(b'\r\n', b'\n'):
        return True
    # Older receipts hash raw bytes. Check both checkout forms of the existing
    # file so an updated asset can replace its unedited predecessor as well.
    variants = (content, normalized, normalized.replace(b'\n', b'\r\n'))
    return receipt.get('ci_sha256') in {hashlib.sha256(value).hexdigest() for value in variants}


ALIAS_AGENTS = ('.agents', '.claude')
# The host whose Spec Kit integration renders each alias folder.
ALIAS_HOSTS = {'.agents': 'codex', '.claude': 'claude'}
# Local state that never feeds a Spec Kit render and may be large or locked.
RENDER_SKIP = ('.specify/workflow/backups', '.specify/workflow/runtime')


def alias_source_path(package_root, name):
    """A package ships SKILL.md; a source checkout stores it as SKILL.ext.md (see package.py)."""
    path = package_root / 'skills' / name / 'SKILL.md'
    return path if path.is_file() else path.with_name('SKILL.ext.md')


def alias_targets(root, package_root, enabled=True, unwanted=False):
    """(name, source, accepted hashes, destination) for every alias Sanduq manages here.

    ``enabled`` is the --with-aliases choice; ``unwanted`` yields the aliases it excludes instead.
    """
    registered = registry(root)
    for name, accepted_file in ALIASES.items():
        source = alias_source_path(package_root, name).read_bytes()
        accepted = read(package_root / 'assets' / accepted_file, [])
        for agent in ALIAS_AGENTS:
            skills = root / agent / 'skills'
            if not skills.is_dir(): continue
            destination = skills / name / 'SKILL.md'
            if alias_wanted(name, destination, enabled, registered) != unwanted:
                yield name, source, accepted, destination


def content_hash(content):
    """SHA-256 of the whole file with CRLF normalised to LF, as git may check it out either way."""
    return hashlib.sha256(content.replace(b'\r\n', b'\n')).hexdigest()


def alias_recognised(content, source, accepted, previous):
    """True when ``content`` (the whole file) is Sanduq's own alias content.

    That is: absent, the packaged alias, an accepted legacy alias hash, or the
    hash the last install recorded in install-lock.json. Frontmatter alone
    never decides: a body edited under unchanged frontmatter has another hash.
    """
    if content is None:
        return True
    value = content_hash(content)
    return value == content_hash(source) or value in accepted or value == previous


def spec_kit_render(root, host, runner=command):
    """Hashes of the alias files Spec Kit generates for ``host`` from this project's current sources.

    The project's ``.specify`` folder is copied into an empty temporary project
    and the public ``specify integration use <host>`` command renders every
    enabled extension's skills there, exactly as it does in the project. The
    project itself is never touched. Any failure yields no hashes, so nothing
    is then recognised as generated.
    """
    if host not in installed_hosts(root):
        return {}
    skip = {(root / path).resolve() for path in RENDER_SKIP}

    def ignore(directory, names):
        here = Path(directory).resolve()
        return [name for name in names if here / name in skip]
    temp = Path(tempfile.mkdtemp(prefix='sanduq-alias-render-'))
    try:
        shutil.copytree(root / '.specify', temp / '.specify', symlinks=True, ignore=ignore)
        runner(temp, ['specify', 'integration', 'use', host], [])
        found = {}
        for name in ALIASES:
            path = temp / HOST_SKILLS[host] / name / 'SKILL.md'
            if path.is_file():
                found[name] = content_hash(path.read_bytes())
        return found
    except (OSError, WorkflowError, subprocess.SubprocessError, shutil.Error):
        return {}
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def review_aliases(root, package_root, runner=command, enabled=True):
    """Judge every existing alias file before anything changes.

    Returns ``{'generated': {key: hash}, 'unrecognized': {key: hash}}``. An
    alias Sanduq recognises as its own is in neither. ``generated`` holds files
    whose full content is exactly what Spec Kit renders for that command from
    the current sources (for example the upstream Bridge executor a bare
    ``specify integration use`` wrote). ``unrecognized`` holds everything
    else: a local edit. Spec Kit runs only when some alias is not recognised.
    """
    previous = read(root / '.specify/workflow/install-lock.json', {}).get('aliases', {})
    renders, review = {}, {'generated': {}, 'unrecognized': {}}
    for name, source, accepted, destination in alias_targets(root, package_root, enabled):
        key = destination.relative_to(root).as_posix()
        content = destination.read_bytes() if destination.is_file() else None
        if alias_recognised(content, source, accepted, previous.get(key)):
            continue
        value = content_hash(content)
        host = ALIAS_HOSTS[key.split('/', 1)[0]]
        if host not in renders:
            renders[host] = spec_kit_render(root, host, runner)
        review['generated' if renders[host].get(name) == value else 'unrecognized'][key] = value
    return review


def local_edit_error(key):
    return ('ALIAS_HAS_LOCAL_EDITS: ' + key + '; migrate this customization into Sanduq, or rerun with '
            '--replace-unrecognized-aliases to back it up and replace it')


def alias_edit_errors(root, package_root, runner=command, review=None):
    """Aliases a user has edited, found before anything is changed."""
    review = review_aliases(root, package_root, runner) if review is None else review
    return [local_edit_error(key) for key in sorted(review['unrecognized'])]


def install_aliases(root, package_root, baseline=None, generated=None, replace_unrecognized=False, backup=None,
                    replaced=None, enabled=True, remove_unwanted=False):
    """Write the managed aliases into every host skill folder.

    ``baseline`` is the transaction's snapshot. Spec Kit regenerates an alias
    from upstream sources whenever it registers extensions for a host, so the
    content judged is what the file held before the transaction: whatever our
    own ``specify`` call wrote over it (or created) during this transaction is
    replaced whenever that earlier content is. The earlier content is replaced
    silently only when it is Sanduq's own alias content or its hash is in
    ``generated`` (Spec Kit's own render, from ``review_aliases`` before the
    transaction). Anything else is a local edit and is refused, unless
    ``replace_unrecognized`` is set: the file is then copied into ``backup``
    first and recorded in ``replaced``.

    ``enabled`` is the --with-aliases choice. With ``remove_unwanted`` (--without-aliases) an
    alias it excludes is deleted when it holds Sanduq's own content; anything else stays.
    """
    previous = read(root / '.specify/workflow/install-lock.json', {}).get('aliases', {})
    generated = generated or {}
    inventory = {}
    if remove_unwanted:
        for name, source, accepted, destination in alias_targets(root, package_root, enabled, unwanted=True):
            if destination.is_file() and not destination.is_symlink() and alias_recognised(
                    destination.read_bytes(), source, accepted, previous.get(destination.relative_to(root).as_posix())):
                destination.unlink()
                if not any(destination.parent.iterdir()): destination.parent.rmdir()
    for name, source, accepted, destination in alias_targets(root, package_root, enabled):
        key = destination.relative_to(root).as_posix()
        content = destination.read_bytes() if destination.exists() else None
        if baseline is not None:
            original = baseline.get(key)
            content = original if isinstance(original, bytes) else None if original is None else content
        if not alias_recognised(content, source, accepted, previous.get(key)) and \
                generated.get(key) != content_hash(content):
            require(replace_unrecognized and backup is not None, local_edit_error(key))
            saved = Path(backup) / 'unrecognized-aliases' / key
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(content)
            if replaced is not None:
                replaced.append({'path': key, 'backup': str(saved)})
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink(): destination.unlink()  # Never patch its upstream command target.
        destination.write_bytes(source)
        inventory[key] = content_hash(source)
    return inventory


def workflow_version():
    """Version of the workflow package this installer belongs to."""
    doc = yaml.safe_load((PACKAGE / 'extension.yml').read_text(encoding='utf-8-sig'))
    return str(doc['extension']['version'])


def check_workflow_requirement(name, doc, version=None):
    """Enforce a sibling's `requires.extensions` entry naming `workflow`.

    Spec Kit only validates that `requires` is a mapping; it never enforces
    `requires.extensions`, so the workflow installer does it for the packages
    it installs or finds installed (e.g. scope 1.5.0 needs workflow >= 1.8.0)."""
    version = version or workflow_version()
    for item in ((doc or {}).get('requires') or {}).get('extensions') or []:
        if item.get('id') != 'workflow' or item.get('required', True) is False: continue
        spec = str(item.get('version') or '')
        require(Version(version) in SpecifierSet(spec),
                f'WORKFLOW_VERSION_UNSUPPORTED: {name} requires workflow {spec}; this installer is workflow {version}')


# Progress wiring (policy `progress:` in workflow.yml). Spec Kit renders the extension's five events into these host
# files on every extension command, so the installer re-applies the policy after its last Spec Kit call.
PROGRESS_SCRIPT = '.specify/extensions/progress/scripts/progress.py'
PROGRESS_HOST_FILES = {'claude': '.claude/settings.json', 'codex': '.codex/config.toml'}
SPECKIT_PROGRESS = 'speckit.progress.hook'
NATIVE_TAG = '--managed-by=progress-report'  # the tag `progress hooks install` puts on its entries
TOML_BLOCK = re.compile(r'\[\[hooks\.(\w+)\]\]\n(?:(?!\[\[hooks\.\w+\]\]).)*?speckit_marker = true\n*', re.DOTALL)


def progress_policy(policy, wiring='speckit'):
    """The `progress:` keys; without `hook_wiring`, ``wiring`` (install() passes the project's current one), every
    tool on PostToolUse."""
    section = policy.get('progress') if isinstance(policy.get('progress'), dict) else {}
    return {'hook_wiring': section.get('hook_wiring') or wiring, 'post_tool_matcher': section.get('post_tool_matcher') or ''}


def _is_speckit_progress(handler):
    return isinstance(handler, dict) and SPECKIT_PROGRESS in str(handler.get('command', ''))


def edit_speckit_progress_json(path, remove=False, matcher=''):
    """Claude settings.json: drop the Spec Kit Progress entries (native wiring), or move the PostToolUse one into its
    own group with `matcher`. Returns how many entries were touched."""
    raw = path.read_text(encoding='utf-8-sig') if path.is_file() else ''
    data = json.loads(raw) if raw.strip() else {}
    hooks = data.get('hooks') if isinstance(data.get('hooks'), dict) else {}
    touched = 0
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list) or (not remove and event != 'PostToolUse'):
            continue
        kept, ours = [], []
        for group in groups:
            inner = group.get('hooks') if isinstance(group, dict) else None
            if not isinstance(inner, list) or not any(_is_speckit_progress(h) for h in inner):
                kept.append(group); continue
            ours += [h for h in inner if _is_speckit_progress(h)]
            rest = [h for h in inner if not _is_speckit_progress(h)]
            if rest: kept.append({**group, 'hooks': rest})
        touched += len(ours)
        if ours and not remove: kept.append({'matcher': matcher, 'hooks': ours})
        if kept: hooks[event] = kept
        else: del hooks[event]
    if touched:
        path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    return touched


def edit_speckit_progress_toml(path, remove=False, matcher=''):
    """Codex config.toml: the same two edits on the `[[hooks.<Event>]]` blocks Spec Kit wrote (one block per handler)."""
    text = path.read_text(encoding='utf-8') if path.is_file() else ''
    touched = 0

    def rewrite(match):
        nonlocal touched
        block = match.group(0)
        if SPECKIT_PROGRESS not in block:
            return block
        if remove:
            touched += 1; return ''
        if match.group(1) != 'PostToolUse':
            return block
        touched += 1
        return re.sub(r'(?m)^matcher = .*$', 'matcher = ' + json.dumps(matcher), block, count=1)
    updated = TOML_BLOCK.sub(rewrite, text)
    if touched:
        path.write_text(updated, encoding='utf-8')
    return touched


SLOW_DISPATCHER_HINT = ("Progress hooks cost about 1.4 s per tool call through Spec Kit's dispatcher in this project; "
                        'set progress.hook_wiring: native in .specify/workflow.yml (about 0.13 s).')


def dispatcher_cost(root, host, probed):
    """The Spec Kit dispatcher entry Progress runs through on ``host``: its interpreter, and whether that interpreter
    imports specify_cli (the dispatcher then loads specify_cli.events on every tool call, about 1.4 s, not 0.2 s)."""
    path = root / PROGRESS_HOST_FILES[host]
    text = path.read_text(encoding='utf-8-sig') if path.is_file() else ''
    if host == 'claude':
        groups = (json.loads(text) if text.strip() else {}).get('hooks') or {}
        commands = [h.get('command', '') for event in groups.values() if isinstance(event, list) for g in event
                    if isinstance(g, dict) for h in g.get('hooks') or [] if _is_speckit_progress(h)]
    else:  # a TOML basic string is valid JSON for the escapes Spec Kit writes
        commands = [json.loads(value) for value in re.findall(r'(?m)^\s*command\s*=\s*(".*")\s*$', text) if SPECKIT_PROGRESS in value]
    if not commands:
        return None
    try:
        interpreter = shlex.split(commands[0])[0]  # Spec Kit POSIX-quotes the interpreter (events._shell_quote)
    except (ValueError, IndexError):
        return {'path': '.specify/events.py', 'interpreter': None, 'imports_specify_cli': None}
    if interpreter not in probed:
        try:
            probed[interpreter] = subprocess.run([interpreter, '-c', 'import specify_cli.events'], cwd=str(root),
                                                 capture_output=True, timeout=5).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            probed[interpreter] = None  # unknown: the probe could not run
    return {'path': '.specify/events.py', 'interpreter': interpreter, 'imports_specify_cli': probed[interpreter]}


def progress_accepts(script, flag):
    done = subprocess.run([sys.executable, str(script), 'hooks', '--help'], capture_output=True, text=True, encoding='utf-8')
    return flag in (done.stdout or '')


def wire_progress(root, policy, hosts):
    """Apply `progress.hook_wiring` and `progress.post_tool_matcher` to each installed host after Spec Kit rendered its
    entries; the returned record goes into install-lock.json. Native wiring removes the Spec Kit entries and lets
    `progress hooks install --host <host>` write entries that run scripts/hook.py directly."""
    wanted = progress_policy(policy)
    record = {**wanted, 'hosts': {}}
    probed = {}
    script = root / PROGRESS_SCRIPT
    if not script.is_file():
        return record
    for host in hosts:
        path = root / PROGRESS_HOST_FILES[host]
        edit = edit_speckit_progress_json if host == 'claude' else edit_speckit_progress_toml
        entry = {'file': PROGRESS_HOST_FILES[host]}
        if wanted['hook_wiring'] == 'native':
            entry['speckit_entries_removed'] = edit(path, remove=True)
            args = [sys.executable, str(script), '--root', str(root), 'hooks', 'install', '--host', host]
            if wanted['post_tool_matcher']:
                entry['matcher_applied'] = progress_accepts(script, '--post-tool-matcher')
                if entry['matcher_applied']: args += ['--post-tool-matcher', wanted['post_tool_matcher']]
                else: entry['note'] = 'post_tool_matcher not applied: the installed Progress has no --post-tool-matcher (agent-tools 1.5.0 or later)'
            done = subprocess.run(args, cwd=str(root), capture_output=True, text=True, encoding='utf-8')
            require(done.returncode == 0, 'PROGRESS_HOOKS_INSTALL_FAILED: ' + (done.stdout + done.stderr).strip())
            entry['file'] = '.claude/settings.json' if host == 'claude' else '.codex/hooks.json'
            entry['result'] = done.stdout.strip()
        else:
            native = root / ('.claude/settings.json' if host == 'claude' else '.codex/hooks.json')
            if native.is_file() and NATIVE_TAG in native.read_text(encoding='utf-8-sig'):
                # Back from native wiring: drop hook.py's entries; Spec Kit re-rendered its own (install() re-adds progress).
                done = subprocess.run([sys.executable, str(script), '--root', str(root), 'hooks', 'uninstall', '--host', host],
                                      cwd=str(root), capture_output=True, text=True, encoding='utf-8')
                require(done.returncode == 0, 'PROGRESS_HOOKS_UNINSTALL_FAILED: ' + (done.stdout + done.stderr).strip())
                entry['native_entries_removed'] = done.stdout.strip()
            if wanted['post_tool_matcher']:
                entry['matcher_applied'] = edit(path, matcher=wanted['post_tool_matcher']) > 0
            entry['dispatcher'] = dispatcher_cost(root, host, probed)
            if (entry['dispatcher'] or {}).get('imports_specify_cli'):
                record['hint'] = SLOW_DISPATCHER_HINT
        entry['cost_class'] = ('native' if wanted['hook_wiring'] == 'native' else
                               'dispatcher-specify-cli' if (entry.get('dispatcher') or {}).get('imports_specify_cli') else
                               'dispatcher')
        record['hosts'][host] = entry
    return record


# Illustrate's opt-in self-check hook (`illustrate.hooks.self_check`). Illustrate owns the entry: its hook script's
# management CLI writes or removes one native entry per host and drops the Spec Kit dispatcher entry a 2.5.0 install
# rendered. Spec Kit never touches these unmarked entries, so this runs after the last Spec Kit call.
ILLUSTRATE_HOOK = '.specify/extensions/illustrate/hooks/self_check_hook.py'
ILLUSTRATE_HOOK_APPROVAL = ('Codex runs the Illustrate self-check only after you approve it: open Codex here, run /hooks '
                            'and approve the Illustrate hook (.codex/hooks.json).')


def wire_illustrate(root, policy, hosts):
    """Install the hook on every host when the key is true, uninstall it otherwise; the record goes into
    install-lock.json and the receipt."""
    section = policy.get('illustrate') if isinstance(policy.get('illustrate'), dict) else {}
    hooks = section.get('hooks') if isinstance(section.get('hooks'), dict) else {}
    action = 'install' if hooks.get('self_check') is True else 'uninstall'
    record = {'self_check': action == 'install', 'action': action, 'hosts': {}}
    script = root / ILLUSTRATE_HOOK
    if not script.is_file():
        require(action == 'uninstall', 'ILLUSTRATE_HOOK_SCRIPT_MISSING: ' + ILLUSTRATE_HOOK)
        record['skipped'] = 'hook script not installed'
        return record
    for host in (h for h in hosts if h in ('claude', 'codex')):
        done = subprocess.run([sys.executable, str(script), action, '--host', host, '--root', str(root), '--json'],
                              cwd=str(root), stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8')
        try:
            entry = json.loads(done.stdout) if done.returncode == 0 else None
        except ValueError:
            entry = None
        # An Illustrate older than the management CLI reads stdin and prints nothing; that is a failure too.
        require(isinstance(entry, dict), f'ILLUSTRATE_HOOK_{action.upper()}_FAILED: {host}: ' +
                ((done.stdout or '') + (done.stderr or '')).strip()[-400:])
        record['hosts'][host] = {key: entry.get(key) for key in ('file', 'added', 'removed', 'needs_approval')}
    return record


def preset_digest(folder):
    """sha256 over a bundled preset's files (paths and LF-normalised bytes), to tell a changed preset from the last apply's."""
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts):
        digest.update(path.relative_to(folder).as_posix().encode() + b'\0' + path.read_bytes().replace(b'\r\n', b'\n') + b'\0')
    return digest.hexdigest()


def install(root, apply=False, packages=None, package_root=PACKAGE, runner=command, upgrade_owner=None, preserve_ci=False,
            replace_unrecognized_aliases=False, with_optional=(), with_aliases=None):
    """``with_aliases``: True installs the short aliases, False removes Sanduq's own copies, None keeps
    the project's earlier choice (an install that left aliases keeps them)."""
    root = root.resolve(); policy = load_policy(root)
    aliases_on = aliases_enabled(root) if with_aliases is None else with_aliases
    lock = read(package_root / 'dependencies.json')
    require(lock and lock.get('repository') == 'https://github.com/samykabu/sanduq', 'INVALID_DEPENDENCY_LOCK')
    selected = dict(lock['required'])
    for process, enabled in policy['processes'].items():
        if enabled: selected.update(lock['selected'][process])
    existing = registry(root); operations = []; retained = []
    last_wiring = (read(root / '.specify/workflow/install-lock.json', {}).get('progress') or {}).get('hook_wiring')
    was_native = last_wiring == 'native'
    # IP21: without an explicit key, Progress keeps the wiring it has (Spec Kit's, if installed before the lock
    # recorded one); a project with no Progress wiring yet gets native wiring.
    progress = progress_policy(policy, last_wiring or ('speckit' if 'progress' in existing else 'native'))
    # Optional extensions (Progress) are installed only when asked for with --with, or kept in step when already installed.
    # They are never required, and the workflow works without them.
    offered = lock.get('optional') or {}
    unknown = sorted(set(with_optional) - set(offered))
    require(not unknown, 'UNKNOWN_OPTIONAL_EXTENSION: ' + ', '.join(unknown) + '; offered: ' + ', '.join(sorted(offered)))
    chosen = sorted(set(with_optional) | {name for name in offered if name in existing})
    selected.update({name: offered[name] for name in chosen})
    order = ('illustrate', 'project', 'scope', 'pr', 'assure', 'user-manual', 'progress')
    for name in sorted(selected, key=lambda key: order.index(key)):
        version = selected[name]
        manifest = root / '.specify/extensions' / name / 'extension.yml'
        installed_doc = (yaml.safe_load(manifest.read_text(encoding='utf-8-sig')) or {}) if manifest.exists() else {}
        meta = installed_doc.get('extension', {})
        check_workflow_requirement(name, installed_doc)
        if name in existing:
            require(meta.get('repository', '').rstrip('/') == lock['repository'], 'EXISTING_EXTENSION_SOURCE_CONFLICT: ' + name)
            # Leaving native Progress wiring needs Spec Kit to render the progress events again, so re-add it.
            rewire = name == 'progress' and was_native and progress['hook_wiring'] == 'speckit'
            if existing[name].get('version') == version and existing[name].get('enabled') is True and not rewire: continue
            if Version(existing[name]['version']) > Version(version):
                require(Version(existing[name]['version']) in SpecifierSet(RANGES.get(name, '>=2.1.2,<3')), 'NEWER_DEPENDENCY_INCOMPATIBLE: ' + name)
                require(existing[name].get('enabled') is True, 'NEWER_DEPENDENCY_DISABLED: enable after compatibility review, never downgrade implicitly')
                retained.append({'extension':name,'version':existing[name]['version'],'tested_baseline':version,
                                 'note':'Newer compatible package retained; active runs still require reviewed migration.'})
                continue
        if packages:
            source = packages.resolve() / name
            candidate_doc = yaml.safe_load((source / 'extension.yml').read_text(encoding='utf-8-sig'))
            check_workflow_requirement(name, candidate_doc)
            candidate = candidate_doc['extension']
            require((candidate['id'], str(candidate['version']), candidate['repository']) == (name, version, lock['repository']), 'STAGED_PACKAGE_IDENTITY_MISMATCH: ' + name)
            args = ['specify', 'extension', 'add', '--dev', str(source), '--force']
        else:
            url = f"{lock['repository']}/releases/download/{name}-v{version}/{name}.zip"
            args = ['specify', 'extension', 'add', name, '--from', url, '--force']
        if name in offered:  # an optional package may need a newer Spec Kit than Workflow's tested one
            spec = ((candidate_doc.get('requires') or {}).get('speckit_version') if packages
                    else (lock.get('optional_speckit') or {}).get(name))
            check_speckit_requirement(root, name, version, spec, name in with_optional)
        operations.append({'extension':name,'version':version,'args':args})
    preset_ops = []
    for name, priority in (('scope-gate','2'),('scope-brainstorm','2'),('workflow','1')):
        source = package_root / 'presets' / name
        require((source / 'preset.yml').is_file(), 'BUNDLED_PRESET_MISSING: build/install the workflow archive first')
        preset_ops.append({'name':name,'source':str(source),'priority':priority,'sha256':preset_digest(source)})
    # Re-add a preset only when it changed since the last apply. An extension update re-renders the commands a preset
    # replaces, so any extension operation still re-adds every preset.
    last = read(root / '.specify/workflow/install-lock.json', {}).get('presets') or {}
    skipped_presets = [] if operations else [
        op['name'] for op in preset_ops
        if (root / '.specify/presets' / op['name'] / 'preset.yml').is_file()
        and (last.get(op['name']) or {}).get('source_sha256') == op['sha256']
        and str((last.get(op['name']) or {}).get('priority')) == op['priority']]
    # Spec Kit registers extension skills only for the default integration, so
    # every other installed host is re-registered after the packages change.
    default_host, hosts = active_host(root), installed_hosts(root)
    result = {'applied':False,'extensions':operations,'retained_newer':retained,'presets':preset_ops,
              'skipped_presets':skipped_presets,'processes':policy['processes'],
              'optional_extensions': chosen,
              'hosts': {'default': default_host, 'installed': hosts,
                        're_register': [['specify', 'integration', 'use', host] for host in hosts if host != default_host] +
                                       ([['specify', 'integration', 'use', default_host]] if len(hosts) > 1 else [])},
              'gate': sanduq_ci.gate_config(policy['ci']),
              'preserve_ci_requested': preserve_ci, 'preserved_ci': None,
              'replace_unrecognized_aliases_requested': replace_unrecognized_aliases,
              'with_aliases': aliases_on,
              'progress': progress if 'progress' in chosen else None}
    if 'codex' in hosts:
        result['codex_hook_approval'] = CODEX_HOOK_APPROVAL
    if not apply:
        review = review_aliases(root, package_root, runner, enabled=aliases_on)
        result['aliases'] = {'generated_by_spec_kit': sorted(review['generated']),
                             'unrecognized': sorted(review['unrecognized']),
                             'blockers': [] if replace_unrecognized_aliases else alias_edit_errors(root, package_root, review=review)}
        return result
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
        # A rollback restores every delegation ledger, so no attempt may be live.
        delegation_preflight(root)
        memory_archive_preflight(root)
        # Judge every alias against the sources as they are now, before any
        # Spec Kit command changes them; a local edit stops here untouched.
        review = review_aliases(root, package_root, runner, enabled=aliases_on)
        if not replace_unrecognized_aliases:
            errors = alias_edit_errors(root, package_root, review=review)
            require(not errors, '; '.join(errors))
        ensure_local_excludes(root)
        backup = root / '.specify/workflow/backups/installs' / uuid.uuid4().hex
        before = snapshot(root, backup); log = []
        if upgrade_owner is None: mark_in_progress(root, 'install', backup)  # an upgrade owns the outer marker
        result['hook_metadata_refreshes'] = []
        try:
            if (root / '.specify/workflow/integration-backup.json').exists():
                restored_hooks = reconcile(root, apply=True, restore=True)
                result['hook_metadata_refreshes'] = [change for change in restored_hooks['changes']
                                                    if change.get('metadata_refresh')]
            for operation in operations:
                preserved = preservation(root, operation['extension'])
                runner(root, operation['args'], log)
                folder = root / '.specify/extensions' / operation['extension']
                for name, content in preserved.items():
                    p = folder / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(content)
            for operation in (op for op in preset_ops if op['name'] not in skipped_presets):
                if (root / '.specify/presets' / operation['name'] / 'preset.yml').exists():
                    runner(root, ['specify','preset','remove',operation['name']], log)
                runner(root, ['specify','preset','add','--dev',operation['source'],'--priority',operation['priority']], log)
            result['hosts']['re_registered'] = register_hosts(root, runner, log, default_host, hosts)
            replaced = []
            alias_hashes = install_aliases(root, package_root, baseline=before, generated=review['generated'],
                                           replace_unrecognized=replace_unrecognized_aliases, backup=backup,
                                           replaced=replaced, enabled=aliases_on,
                                           remove_unwanted=with_aliases is False)
            result['replaced_unrecognized_aliases'] = replaced
            # Reconcile also re-applies the host files: hidden hook-only skills, guard hook, roles.
            result['host_files'] = reconcile(root, apply=True).get('host_files')
            if 'progress' in chosen:
                result['progress'] = wire_progress(root, {'progress': progress}, hosts)
            result['illustrate'] = wire_illustrate(root, policy, hosts)
            if any(entry.get('needs_approval') for entry in result['illustrate']['hosts'].values()):
                result['illustrate_hook_approval'] = ILLUSTRATE_HOOK_APPROVAL
            host_errors = skill_errors(skill_report(root, hosts))
            # Nothing may rewrite an alias after it is written (Spec Kit ran above).
            host_errors += ['ALIAS_NOT_RESTORED: ' + key for key, value in alias_hashes.items()
                            if not (root / key).is_file() or hashlib.sha256(
                                (root / key).read_bytes().replace(b'\r\n', b'\n')).hexdigest() != value]
            require(not host_errors, '; '.join(host_errors))
            if policy['delegation']['enabled']:
                from delegation import doctor as delegation_doctor, health_error
                delegation_health = delegation_doctor(root, active_host(root), install=True,
                                                      scope=policy['delegation']['install_scope'],
                                                      upgrade_owner=upgrade_owner)
                require(delegation_health['ok'], health_error(delegation_health))
            target = root / '.github/workflows/sanduq-workflow-gates.yml'
            # The shipped asset is a template. What lands in the project is the
            # project's own CI selection rendered from it, never a copy.
            asset = rendered(package_root / 'assets/github/workflow-gates.yml', policy)
            gate_disabled = (sanduq_ci.gate_config(policy['ci'])['mode'] == 'disabled'
                             or policy['ci']['provider'] == 'none')
            require(not (gate_disabled and target.exists() and preserve_ci),
                    'CI_GATE_DISABLED_PRESERVED_FILE_CONFLICT: a preserved workflow would still run')
            if gate_disabled and target.exists():
                stale = required_gate_checks(root)
                require(not stale, 'CI_GATE_REQUIRED_BY_BRANCH_RULE: remove or update ' +
                        ', '.join(stale) + ' in GitHub branch rules before disabling the job')
            if target.exists() and preserve_ci:
                result['preserved_ci'] = {'path': target.relative_to(root).as_posix(),
                                          'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
            elif target.exists():
                old_inventory = read(root / '.specify/workflow/install-receipt.json', {})
                # The receipt is git-excluded, so a fresh clone also recognises an unedited render of the
                # template before the base-branch gate (SEC-03) by the copy the package keeps.
                previous = package_root / 'assets/github/previous/workflow-gates.yml'
                require(ci_matches_managed(target.read_bytes(), asset, old_inventory) or (
                    previous.is_file() and ci_matches_managed(target.read_bytes(), rendered(previous, policy), {})),
                    'CI_WORKFLOW_HAS_LOCAL_EDITS')
            if gate_disabled:
                if target.exists(): target.unlink()
            elif not result['preserved_ci']:
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(asset)
            legacy = root / '.github/workflows/documentation-gates.yml'
            reference = root / '.specify/extensions/assure/assets/github/documentation-gates.yml'
            if legacy.exists():
                # Unedited: a render of the Assure template now, of the one before this transaction updated
                # Assure, or of either without the head checkout AU8 added (assure_init.HEAD_CHECKOUT).
                earlier = before.get(reference.relative_to(root).as_posix())
                previous = reference.parent / 'previous' / reference.name  # the template before SEC-03
                templates = [t.replace(b'\r\n', b'\n') for t in (reference.read_bytes() if reference.exists() else None, earlier,
                                                                 previous.read_bytes() if previous.exists() else None)
                             if isinstance(t, bytes)]
                templates += [t.replace(ASSURE_HEAD_CHECKOUT, b'') for t in templates]
                try:
                    renders = [sanduq_ci.render(t, policy.get('ci') or sanduq_ci.default_ci()) for t in templates]
                except sanduq_ci.CIPolicyError as exc:
                    raise WorkflowError('CI_RENDER_FAILED: ' + reference.name + ': ' + str(exc)) from exc
                require(legacy.read_bytes().replace(b'\r\n',b'\n') in renders, 'LEGACY_CI_HAS_LOCAL_EDITS: reconcile selected processes explicitly')
                legacy.unlink()  # exact backed-up legacy gate; policy-aware gate replaces it
            # The receipt and lock that record the preserved file are written
            # only after this check, so hand the choice to the doctor directly.
            health = doctor(root, policy, preserved_ci=(result['preserved_ci'] or {}).get('path'))
            require(health['ok'], '; '.join(health['errors']))
            installed = registry(root)
            digests = {op['name']: op['sha256'] for op in preset_ops}
            inventory = {}
            for name in sorted(set(selected) | {'workflow'}):
                entry = installed.get(name, {})
                version = entry.get('version')
                inventory[name] = {key: entry.get(key) for key in ('version', 'enabled', 'manifest_hash', 'source')}
                inventory[name]['release_url'] = f"{lock['repository']}/releases/download/{name}-v{version}/{name}.zip"
                inventory[name]['distribution'] = 'local-development' if entry.get('source') == 'local' else 'release'
            write(root / '.specify/workflow/install-lock.json', {
                'schema_version': 1, 'host': active_host(root), 'processes': policy['processes'],
                'optional_extensions': chosen, 'extensions': inventory, 'dependency_digest': package_digest(root),
                'aliases': alias_hashes, 'with_aliases': aliases_on,
                'progress': result['progress'],
                'illustrate': result['illustrate'],
                # Tracked, unlike the receipt, so fresh clones and worktrees
                # still treat a preserved CI file as project-owned.
                'preserved_ci': {'path': result['preserved_ci']['path']} if result['preserved_ci'] else None,
                'presets': {name: {**{key: entry.get(key) for key in ('version', 'enabled', 'priority', 'manifest_hash')},
                                   **({'source_sha256': digests[name]} if name in digests else {})}
                            for name, entry in read(root / '.specify/presets/.registry', {}).get('presets', {}).items()},
                'tested_compatibility': {'spec_kit': lock.get('tested_spec_kit', {}), 'upstream_optional': lock.get('upstream_optional', {})},
            })
            receipt = {**result,'applied':True,'backup':str(backup),'commands':log,
                       'ci_sha256':hashlib.sha256(asset.replace(b'\r\n', b'\n')).hexdigest()}
            write(root / '.specify/workflow/install-receipt.json', receipt)
            write(backup / 'result.json', {'ok':True,'commands':log,
                                         'hook_metadata_refreshes':result['hook_metadata_refreshes']})
            if upgrade_owner is None:  # an upgrade prunes once its own outer transaction succeeds
                receipt['backups'] = prune_backups(root)
                clear_in_progress(root)
            return receipt
        except BaseException as exc:  # Ctrl-C and SystemExit restore too, then re-raise as they are (AHMED-09)
            failed = managed_files(root)
            write(backup / 'result.json', {'ok':False,'error':str(exc) or type(exc).__name__,'commands':log,
                                         'hook_metadata_refreshes':result['hook_metadata_refreshes']})
            restore(root, before, failed)
            if upgrade_owner is None: clear_in_progress(root)
            if not isinstance(exc, Exception): raise
            raise WorkflowError('INSTALL_ROLLED_BACK: ' + str(exc) + '; backup: ' + str(backup)) from exc


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--packages', type=Path, help='Extracted, verified local package directory for offline development')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--preserve-ci', action='store_true', help='Keep the existing project workflow-gates CI file byte-for-byte')
    parser.add_argument('--replace-unrecognized-aliases', action='store_true',
                        help='Back up, then replace, a managed alias file whose content Sanduq does not recognise')
    parser.add_argument('--with', dest='with_optional', action='append', default=[], metavar='EXTENSION',
                        help='Also install an optional extension offered in dependencies.json (for example: progress)')
    aliases = parser.add_mutually_exclusive_group()
    aliases.add_argument('--with-aliases', dest='with_aliases', action='store_const', const=True, default=None,
                         help='Install the short speckit-scope and speckit-superpowers-bridge skills (off by default)')
    aliases.add_argument('--without-aliases', dest='with_aliases', action='store_const', const=False,
                         help='Remove the short alias skills an earlier install left (Sanduq content only)')
    parser.add_argument('--upgrade-owner', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--restore', type=Path, metavar='BACKUP',
                        help='Put back the managed files an interrupted install, upgrade or host switch backed up to this folder')
    args = parser.parse_args()
    try:
        if args.restore:
            print(json.dumps(restore_backup(args.root, args.restore), indent=2)); sys.exit(0)
        result = install(args.root,args.apply,args.packages,upgrade_owner=args.upgrade_owner,preserve_ci=args.preserve_ci,
                         replace_unrecognized_aliases=args.replace_unrecognized_aliases,with_optional=args.with_optional,
                         with_aliases=args.with_aliases)
        print(json.dumps(result,indent=2))
        for key in ('codex_hook_approval', 'illustrate_hook_approval'):
            if result.get(key): print(result[key], file=sys.stderr)
        if (result.get('progress') or {}).get('hint'): print(result['progress']['hint'], file=sys.stderr)
    except (WorkflowError, ValueError, OSError, KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc), **explain(str(exc))})); sys.exit(1)
