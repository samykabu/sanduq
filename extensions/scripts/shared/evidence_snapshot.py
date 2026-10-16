"""Capture exact bytes using retained Git objects or immutable file proofs."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import uuid
from pathlib import Path

from check_inputs import path_at, file_digest, InputIdentityError

SCHEMA = 'sanduq.evidence.snapshot.v1'
MAX_BYTES = 16777216
OID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')


def git(root, *args):
    result = subprocess.run(['git', *args], cwd=root, capture_output=True)
    if result.returncode:
        raise InputIdentityError('EVIDENCE_GIT_UNAVAILABLE: ' + result.stderr.decode('utf-8', errors='replace')[:300])
    return result.stdout


def repository(root):
    common = Path(git(root, 'rev-parse', '--git-common-dir').decode('utf-8').strip())
    return str((Path(root) / common).resolve())


def blob(root, commit, label):
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
    data = git(root, 'cat-file', 'blob', oid)
    algorithm = 'sha1' if len(oid) == 40 else 'sha256'
    if len(data) != size or hashlib.new(algorithm, b'blob ' + str(size).encode('ascii') + b'\0' + data).hexdigest() != oid:
        raise InputIdentityError('EVIDENCE_BLOB_IDENTITY_MISMATCH')
    return oid, data


def capture(root, labels, output):
    root = Path(root).resolve()
    destination = path_at(root, output)
    if destination.exists() or not labels or len(set(labels)) != len(labels) or output in labels:
        raise InputIdentityError('EVIDENCE_CAPTURE_NEW_OUTPUT_AND_UNIQUE_INPUTS_REQUIRED')
    head = git(root, 'rev-parse', 'HEAD').decode('ascii').strip()
    repo = repository(root)
    retention = 'refs/sanduq/evidence/' + uuid.uuid4().hex
    records = []
    for label in labels:
        path = path_at(root, label)
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise InputIdentityError('EVIDENCE_INPUT_MISSING_OR_TOO_LARGE: ' + label)
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        try:
            oid, committed = blob(root, head, label)
        except InputIdentityError:
            oid, committed = None, None
        if committed == data:
            records.append({'kind': 'git', 'repository': repo, 'commit': head, 'path': label,
                            'blob': oid, 'sha256': sha, 'retention': retention})
        else:
            proof = destination.parent / (destination.name + '.objects') / sha
            path_at(root, proof.relative_to(root).as_posix())
            proof.parent.mkdir(parents=True, exist_ok=True)
            if not proof.exists():
                with proof.open('xb') as stream:
                    stream.write(data)
            if file_digest(proof) != sha:
                raise InputIdentityError('EVIDENCE_FILE_PROOF_TAMPERED')
            records.append({'kind': 'file', 'path': label, 'proof': proof.relative_to(root).as_posix(), 'sha256': sha})
    if any(r['kind'] == 'git' for r in records):
        git(root, 'update-ref', retention, head, '0' * len(head))
    snapshot = {'schema': SCHEMA, 'records': records}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(snapshot, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    # Admission uses the same resolver as later reads.
    resolve(root, output)
    return {'snapshot': output, 'sha256': file_digest(destination),
            'git_records': sum(r['kind'] == 'git' for r in records),
            'file_records': sum(r['kind'] == 'file' for r in records)}


def resolve(root, snapshot_path):
    path = path_at(root, snapshot_path)
    if path.stat().st_size > MAX_BYTES:
        raise InputIdentityError('EVIDENCE_SNAPSHOT_TOO_LARGE')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or set(value) != {'schema', 'records'} or value['schema'] != SCHEMA or not isinstance(value['records'], list) or not value['records']:
        raise InputIdentityError('EVIDENCE_SNAPSHOT_INVALID')
    result = {}
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
        if label in result:
            raise InputIdentityError('EVIDENCE_DUPLICATE_PATH')
        if kind == 'git':
            ref = record['retention']
            if record['repository'] != repository(root) or not isinstance(ref, str) or not re.fullmatch(r'refs/sanduq/evidence/[0-9a-f]{32}', ref):
                raise InputIdentityError('EVIDENCE_REPOSITORY_OR_RETENTION_MISMATCH')
            if git(root, 'rev-parse', '--verify', ref).decode('ascii').strip() != record['commit']:
                raise InputIdentityError('EVIDENCE_RETENTION_MISSING')
            oid, data = blob(root, record['commit'], label)
            if oid != record['blob']:
                raise InputIdentityError('EVIDENCE_BLOB_MISMATCH')
        else:
            proof = path_at(root, record['proof'])
            if not proof.is_file() or proof.stat().st_size > MAX_BYTES:
                raise InputIdentityError('EVIDENCE_PROOF_MISSING_OR_TOO_LARGE')
            data = proof.read_bytes()
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise InputIdentityError('EVIDENCE_CONTENT_MISMATCH')
        result[label] = data
    return result
