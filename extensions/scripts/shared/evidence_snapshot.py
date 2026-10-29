# SPDX-License-Identifier: MIT
"""Capture exact bytes using retained Git objects or immutable file proofs."""
from __future__ import annotations

import hashlib
import json
import re
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath

from check_inputs import path_at, file_digest, InputIdentityError

SCHEMA = 'sanduq.evidence.snapshot.v1'
MAX_BYTES = 16777216
# v1 descriptors remain unchanged. Limits count every label, even shared proofs;
# validation retains only one 64 KiB chunk; resolution returns at most 64 MiB.
MAX_RECORDS = 256
MAX_TOTAL_BYTES = 67108864
CHUNK_BYTES = 65536
OID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')


def git(root, *args):
    result = subprocess.run(['git', *args], cwd=root, capture_output=True)
    if result.returncode:
        raise InputIdentityError('EVIDENCE_GIT_UNAVAILABLE: ' + result.stderr.decode('utf-8', errors='replace')[:300])
    return result.stdout


def repository(root):
    common = Path(git(root, 'rev-parse', '--git-common-dir').decode('utf-8').strip())
    return str((Path(root) / common).resolve())


def _blob_metadata(root, commit, label):
    path_at(root, label)
    if not isinstance(commit, str) or not OID.fullmatch(commit) or '\n' in label or '\r' in label:
        raise InputIdentityError('EVIDENCE_IMMUTABLE_COMMIT_REQUIRED')
    if git(root, 'cat-file', '-t', commit).strip() != b'commit':
        raise InputIdentityError('EVIDENCE_COMMIT_REQUIRED')
    oid = git(root, 'rev-parse', '--verify', f'{commit}:{label}').decode('ascii').strip()
    if not OID.fullmatch(oid) or git(root, 'cat-file', '-t', oid).strip() != b'blob':
        raise InputIdentityError('EVIDENCE_BLOB_REQUIRED')
    size = int(git(root, 'cat-file', '-s', oid).strip())
    if not 0 <= size <= MAX_BYTES:
        raise InputIdentityError('EVIDENCE_BLOB_TOO_LARGE')
    return oid, size


def _consume(stream, size, collect, oid=None):
    """Read at most the preflight size plus one byte, hashing without aggregation."""
    sha = hashlib.sha256()
    identity = hashlib.new('sha1' if len(oid) == 40 else 'sha256') if oid else None
    if identity:
        identity.update(b'blob ' + str(size).encode('ascii') + b'\0')
    chunks = [] if collect else None
    count = 0
    while True:
        chunk = stream.read(min(CHUNK_BYTES, size - count + 1))
        if not chunk:
            break
        count += len(chunk)
        if count > size:
            raise InputIdentityError('EVIDENCE_CONTENT_SIZE_MISMATCH')
        sha.update(chunk)
        if identity:
            identity.update(chunk)
        if collect:
            chunks.append(chunk)
    if count != size:
        raise InputIdentityError('EVIDENCE_CONTENT_SIZE_MISMATCH')
    if identity and identity.hexdigest() != oid:
        raise InputIdentityError('EVIDENCE_BLOB_IDENTITY_MISMATCH')
    return (b''.join(chunks) if collect else None), sha.hexdigest()


def _blob_content(root, oid, size, collect):
    # stderr goes to a temporary file so a failed Git process cannot block stdout
    # consumption. Payload stdout is always bounded by the metadata preflight.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(['git', 'cat-file', 'blob', oid], cwd=root,
                                   stdout=subprocess.PIPE, stderr=errors)
        try:
            with process.stdout:
                result = _consume(process.stdout, size, collect, oid)
            if process.wait():
                errors.seek(0)
                raise InputIdentityError('EVIDENCE_GIT_UNAVAILABLE: ' + errors.read(300).decode('utf-8', errors='replace'))
            return result
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


def blob(root, commit, label):
    oid, size = _blob_metadata(root, commit, label)
    data, _ = _blob_content(root, oid, size, True)
    return oid, data


def _file_size(path, error):
    try:
        info = path.stat()
    except FileNotFoundError as exc:
        raise InputIdentityError(error) from exc
    if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= MAX_BYTES:
        raise InputIdentityError(error)
    return info.st_size


def _file_content(path, size, collect):
    with path.open('rb') as stream:
        return _consume(stream, size, collect)


def _payload_budget(total, size):
    total += size
    if total > MAX_TOTAL_BYTES:
        raise InputIdentityError('EVIDENCE_PAYLOAD_TOO_LARGE')
    return total


def capture(root, labels, output):
    root = Path(root).resolve()
    destination = path_at(root, output)
    if len(labels) > MAX_RECORDS:
        raise InputIdentityError('EVIDENCE_TOO_MANY_RECORDS')
    if destination.exists() or not labels or len(set(labels)) != len(labels) or output in labels:
        raise InputIdentityError('EVIDENCE_CAPTURE_NEW_OUTPUT_AND_UNIQUE_INPUTS_REQUIRED')
    # Preflight every source before reading payload or creating any proof/ref.
    sources, total = [], 0
    for label in labels:
        path = path_at(root, label)
        size = _file_size(path, 'EVIDENCE_INPUT_MISSING_OR_TOO_LARGE: ' + label)
        total = _payload_budget(total, size)
        sources.append((label, path, size))
    head = git(root, 'rev-parse', 'HEAD').decode('ascii').strip()
    repo = repository(root)
    retention = 'refs/sanduq/evidence/' + uuid.uuid4().hex
    records = []
    for label, path, size in sources:
        data, sha = _file_content(path, size, True)
        try:
            oid, committed_size = _blob_metadata(root, head, label)
            _, committed_sha = _blob_content(root, oid, committed_size, False)
        except InputIdentityError:
            oid, committed_sha = None, None
        if committed_sha == sha:
            records.append({'kind': 'git', 'repository': repo, 'commit': head, 'path': label,
                            'blob': oid, 'sha256': sha, 'retention': retention})
        else:
            proof = destination.parent / (destination.name + '.objects') / sha
            path_at(root, proof.relative_to(root).as_posix())
            proof.parent.mkdir(parents=True, exist_ok=True)
            if not proof.exists():
                with proof.open('xb') as stream:
                    stream.write(data)
            proof_size = _file_size(proof, 'EVIDENCE_PROOF_MISSING_OR_TOO_LARGE')
            if _file_content(proof, proof_size, False)[1] != sha:
                raise InputIdentityError('EVIDENCE_FILE_PROOF_TAMPERED')
            records.append({'kind': 'file', 'path': label, 'proof': proof.relative_to(root).as_posix(), 'sha256': sha})
    if any(r['kind'] == 'git' for r in records):
        git(root, 'update-ref', retention, head, '0' * len(head))
    snapshot = {'schema': SCHEMA, 'records': records}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(snapshot, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    # Admission verifies streaming; it never needs a dictionary of payload bytes.
    validate(root, output)
    return {'snapshot': output, 'sha256': file_digest(destination),
            'git_records': sum(r['kind'] == 'git' for r in records),
            'file_records': sum(r['kind'] == 'file' for r in records)}


def _snapshot_plan(root, snapshot_path):
    path = path_at(root, snapshot_path)
    if path.stat().st_size > MAX_BYTES:
        raise InputIdentityError('EVIDENCE_SNAPSHOT_TOO_LARGE')
    with path.open('rb') as stream:
        encoded = stream.read(MAX_BYTES + 1)
    if len(encoded) > MAX_BYTES:
        raise InputIdentityError('EVIDENCE_SNAPSHOT_TOO_LARGE')
    value = json.loads(encoded.decode('utf-8'))
    if not isinstance(value, dict) or set(value) != {'schema', 'records'} or value['schema'] != SCHEMA or not isinstance(value['records'], list) or not value['records']:
        raise InputIdentityError('EVIDENCE_SNAPSHOT_INVALID')
    if len(value['records']) > MAX_RECORDS:
        raise InputIdentityError('EVIDENCE_TOO_MANY_RECORDS')
    plan, seen, total = [], set(), 0
    for record in value['records']:
        if not isinstance(record, dict):
            raise InputIdentityError('EVIDENCE_RECORD_INVALID')
        kind = record.get('kind')
        fields = ({'kind', 'repository', 'commit', 'path', 'blob', 'sha256', 'retention'} if kind == 'git'
                  else {'kind', 'path', 'proof', 'sha256'} if kind == 'file' else set())
        if not fields or set(record) != fields or not isinstance(record['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', record['sha256']):
            raise InputIdentityError('EVIDENCE_RECORD_INVALID')
        label = record['path']
        path_at(root, label)
        if label in seen:
            raise InputIdentityError('EVIDENCE_DUPLICATE_PATH')
        seen.add(label)
        if kind == 'git':
            ref = record['retention']
            # v1's absolute repository path is provenance, not a portable identity.
            # Recovery in the current repository requires the exact retained ref (or,
            # since refs are never pushed, a commit that is an ancestor of HEAD, as in
            # a fresh CI checkout), then the blob, Git object content hash and SHA-256
            # below. Never rewrite the descriptor (and so never invalidate receipts).
            repo = record['repository']
            if (not isinstance(repo, str) or any(c in repo for c in '\0\n\r')
                    or not (PurePosixPath(repo).is_absolute() or PureWindowsPath(repo).is_absolute())
                    or not isinstance(ref, str) or not re.fullmatch(r'refs/sanduq/evidence/[0-9a-f]{32}', ref)):
                raise InputIdentityError('EVIDENCE_REPOSITORY_OR_RETENTION_MISMATCH')
            commit = record['commit']
            retained = subprocess.run(['git', 'rev-parse', '--verify', '--quiet', ref], cwd=root, capture_output=True)
            if retained.stdout.decode('ascii').strip() != commit and not (
                    isinstance(commit, str) and OID.fullmatch(commit) and subprocess.run(
                        ['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=root, capture_output=True).returncode == 0):
                raise InputIdentityError('EVIDENCE_RETENTION_MISSING')
            oid, size = _blob_metadata(root, record['commit'], label)
            if oid != record['blob']:
                raise InputIdentityError('EVIDENCE_BLOB_MISMATCH')
            source = oid
        else:
            proof = path_at(root, record['proof'])
            size = _file_size(proof, 'EVIDENCE_PROOF_MISSING_OR_TOO_LARGE')
            source = proof
        total = _payload_budget(total, size)
        plan.append((record, source, size))
    return plan


def _resolve(root, snapshot_path, collect):
    # Metadata for ALL records is checked before the first payload read. Shared
    # proofs count once per label, because resolve returns bytes for every label.
    plan = _snapshot_plan(root, snapshot_path)
    result = {} if collect else None
    for record, source, size in plan:
        data, sha = (_blob_content(root, source, size, collect) if record['kind'] == 'git'
                     else _file_content(source, size, collect))
        if sha != record['sha256']:
            raise InputIdentityError('EVIDENCE_CONTENT_MISMATCH')
        if collect:
            result[record['path']] = data
    return result


def validate(root, snapshot_path):
    """Verify every exact proof within the resolve budgets, without retaining payload."""
    return _resolve(root, snapshot_path, False)


def resolve(root, snapshot_path):
    """Return exact bytes for all labels after aggregate metadata admission."""
    return _resolve(root, snapshot_path, True)
