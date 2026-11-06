# SPDX-License-Identifier: MIT
"""Versioned, project-declared exact check inputs. No process execution or Node dependency."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sys
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

UTF8_ENV = {'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'}
_ENV_LOCK = threading.RLock()


def execution_environment():
    return {**os.environ, **UTF8_ENV}


@contextmanager
def utf8_environment():
    """Adapt the existing capped runner's inherited environment, restoring it on every exit."""
    with _ENV_LOCK:
        previous = {name: os.environ.get(name) for name in UTF8_ENV}
        os.environ.update(UTF8_ENV)
        try:
            yield
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


class InputIdentityError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode('utf-8')).hexdigest()


def path_at(root, label):
    if (not isinstance(label, str) or not label or '\\' in label or ':' in label
            or any(c in label for c in '\0\n\r') or PurePosixPath(label).is_absolute()
            or PurePosixPath(label).as_posix() != label
            or any(p.casefold() in ('..', '.git') for p in label.split('/'))):
        raise InputIdentityError('INPUT_PATH_INVALID: ' + str(label))
    root = Path(root).resolve()
    target = root / label
    for part in (target, *target.parents):
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise InputIdentityError('INPUT_LINK_UNSUPPORTED: ' + label)
    if not target.resolve().is_relative_to(root):
        raise InputIdentityError('INPUT_PATH_OUTSIDE_ROOT: ' + label)
    return target


def file_digest(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            hasher.update(block)
    return hasher.hexdigest()


def executable_identity(root, command):
    if not isinstance(command, list) or not command or not all(isinstance(a, str) for a in command) or not command[0]:
        raise InputIdentityError('INPUT_ARGV_INVALID')
    local = Path(root) / command[0]
    selected = os.path.abspath(local) if local.is_file() else shutil.which(command[0])
    if not selected or not Path(selected).is_file():
        raise InputIdentityError('VERIFICATION_EXECUTABLE_MISSING: ' + command[0])
    selected = os.path.abspath(selected)
    target = Path(selected).resolve()
    return {'invocation': selected, 'path': str(target), 'sha256': file_digest(target)}


def command_input(root, command):
    """Validate interpreter input without importing or executing project code."""
    executable = executable_identity(root, command)
    name = Path(executable['invocation']).stem.lower()
    python = name.startswith('python') or name == 'py'
    node = name in ('node', 'nodejs')
    powershell = name in ('pwsh', 'powershell')
    if not (python or node or powershell):
        return None
    index = 1
    while index < len(command):
        argument = command[index]
        if ((argument in ('-c', '-m') and python)
                or (argument in ('-e', '--eval', '-p', '--print') and node)
                or (argument.lower() in ('-command', '-encodedcommand') and powershell)):
            if index + 1 >= len(command) or not command[index + 1].strip():
                break
            return None
        if node and argument == '--test':
            return None  # Node's built-in discovery is an intentional execution mode.
        if (argument.lower() == '-file' and powershell) or argument == '--':
            index += 1
            if index >= len(command):
                break
            argument = command[index]
        elif argument.startswith('-'):
            index += 2 if argument in ('-W', '-X', '--check-hash-based-pycs') and python else 1
            continue
        script = Path(argument)
        script = script if script.is_absolute() else Path(root) / script
        if not script.is_file():
            raise InputIdentityError('Checker script missing: ' + argument)
        return argument
    raise InputIdentityError('Interpreter script/module argument missing: ' + command[0])


def environment_identity(root, command, names):
    if not isinstance(names, list) or not all(isinstance(n, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', n) for n in names):
        raise InputIdentityError('INPUT_ENVIRONMENT_INVALID')
    # Only identities are persisted, never environment values (including PATH).
    effective = execution_environment()
    return {'python': sys.version, 'platform': platform.platform(),
            'cwd': str(Path(root).resolve()), 'executable': executable_identity(root, command),
            'variables': {name: digest({'value': effective.get(name)})
                          for name in sorted(set(names) | {'PATH'} | set(UTF8_ENV))}}


def global_identity(root, excluded=()):
    """Legacy checks retain whole-project freshness; generated proof paths are excluded."""
    root = Path(root).resolve()
    listed = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                            cwd=root, capture_output=True)
    labels = ([p.decode('utf-8') for p in listed.stdout.split(b'\0') if p] if listed.returncode == 0
              else [p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()])
    result = {}
    for label in sorted(set(labels)):
        if ('__pycache__' in Path(label).parts or '.git' in Path(label).parts
                or any(label == e or label.startswith(e + '/') for e in excluded)):
            continue
        path = path_at(root, label)
        result[label] = file_digest(path) if path.is_file() else None
    return result


def manifest_identity(root, definition, command, manifest):
    """Completeness is an explicit project assertion; unresolved dependencies refuse reuse.

    Files include checker code, config, transitive sources, fixtures and lockfiles.
    Directories bind both membership and every member's bytes, including ignored files.
    Environment lists nonsecret names; secret-dependent checks use unresolved instead.
    """
    keys = {'schema_version', 'complete', 'files', 'directories', 'environment', 'unresolved'}
    if (not isinstance(manifest, dict) or set(manifest) != keys
            or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1
            or manifest.get('complete') is not True):
        raise InputIdentityError('INPUT_MANIFEST_UNKNOWN_OR_INCOMPLETE')
    for key in ('files', 'directories', 'environment', 'unresolved'):
        values = manifest[key]
        if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values) or len(values) != len(set(values)):
            raise InputIdentityError('INPUT_MANIFEST_INVALID: ' + key)
    if manifest['unresolved'] or not manifest['files']:
        raise InputIdentityError('INPUT_DEPENDENCIES_UNKNOWN_OR_EMPTY')
    files, directories = {}, {}
    for label in manifest['files']:
        path = path_at(root, label)
        if not path.is_file():
            raise InputIdentityError('INPUT_FILE_MISSING: ' + label)
        files[label] = file_digest(path)
    for label in manifest['directories']:
        directory = path_at(root, label)
        if not directory.is_dir():
            raise InputIdentityError('INPUT_DIRECTORY_MISSING: ' + label)
        members = {}
        for child in sorted(directory.rglob('*')):
            name = child.relative_to(Path(root).resolve()).as_posix()
            path_at(root, name)
            if child.is_file():
                members[name] = file_digest(child)
            elif child.is_dir():
                members[name + '/'] = None
            else:
                raise InputIdentityError('INPUT_NONREGULAR: ' + name)
        directories[label] = members
    covered = set(files) | {p for members in directories.values() for p in members}
    script = command_input(root, command)
    if script:
        target = (Path(root) / script).resolve()
        if not target.is_relative_to(Path(root).resolve()) or target.relative_to(Path(root).resolve()).as_posix() not in covered:
            raise InputIdentityError('INPUT_UNDECLARED_CHECKER: ' + script)
    for argument in command[1:]:
        label = argument.split('=', 1)[-1] if argument.startswith('-') and '=' in argument else argument
        if label and (Path(root) / label).is_file():
            target = (Path(root) / label).resolve()
            if not target.is_relative_to(Path(root).resolve()) or target.relative_to(Path(root).resolve()).as_posix() not in covered:
                raise InputIdentityError('INPUT_UNDECLARED_COMMAND_FILE: ' + label)
    return {'schema_version': 1, 'complete': True, 'definition': digest(definition),
            'command': command, 'files': files, 'directories': directories,
            'environment': environment_identity(root, command, manifest['environment'])}
