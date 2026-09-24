"""Portable UTF-8 text hashing; SQL and explicitly binary files remain byte exact.

Byte-sensitive content is never rewritten. A tracked byte-sensitive file whose
working tree differs from the index only by Git's own checkout conversion
(core.autocrlf, eol attributes) is read as its committed blob, which is what a
clean CI checkout holds, so fingerprints do not depend on how the file was
checked out. Any real edit still hashes the working-tree bytes.
"""
import hashlib
import subprocess
from pathlib import Path


def _git(root, args, data=b''):
    result = subprocess.run(['git', *args], cwd=root, input=data, capture_output=True)
    if result.returncode:
        raise ValueError('Cannot read Git index for fingerprints: ' + result.stderr.decode('utf-8', 'replace'))
    return result.stdout


def text_attributes(root, paths):
    paths = sorted(set(paths))
    if not paths:
        return {}
    result = subprocess.run(['git', 'check-attr', '-z', '--stdin', 'text'], cwd=root,
                            input='\0'.join(paths).encode('utf-8') + b'\0', capture_output=True)
    if result.returncode:
        raise ValueError('Cannot inspect Git text attributes: ' + result.stderr.decode('utf-8', 'replace'))
    values = result.stdout.decode('utf-8').split('\0')
    return {values[i]: values[i + 2] for i in range(0, len(values) - 1, 3)}


def byte_sensitive(path, content, text_attribute=None):
    # SQL can contain byte-sensitive definitions; never normalize it implicitly.
    # -text also takes precedence over a familiar filename extension.
    if Path(path).suffix.lower() == '.sql' or text_attribute == 'unset' or b'\0' in content:
        return True
    try:
        content.decode('utf-8')
    except UnicodeDecodeError:
        return True
    return False


def portable_content(path, content, text_attribute=None):
    if byte_sensitive(path, content, text_attribute):
        return content
    # Do not normalize lone CR: it can be meaningful data, not checkout conversion.
    return content.replace(b'\r\n', b'\n')


def _blob_id(content, length):
    digest = hashlib.sha1 if length == 40 else hashlib.sha256
    return digest(b'blob %d\0' % len(content) + content).hexdigest()


def committed_blobs(root, contents):
    """Return index blob bytes for tracked paths that only differ by checkout conversion.

    `contents` maps root-relative POSIX paths to working-tree bytes. Git is asked
    a fixed number of times, whatever the inventory size: one index listing, one
    batched clean-conversion hash and one batched blob read.
    """
    if not contents:
        return {}
    index = {}
    for entry in _git(root, ['ls-files', '--stage', '-z']).split(b'\0'):
        meta, _, name = entry.partition(b'\t')
        fields = meta.split()
        # Only ordinary stage-0 files: never symlinks, submodules or conflicts.
        if len(fields) == 3 and fields[2] == b'0' and fields[0] in (b'100644', b'100755'):
            index[name.decode('utf-8', 'surrogateescape')] = fields[1].decode('ascii')
    # Bytes already equal to the index blob need no conversion check (the usual
    # clean CI checkout). --stdin-paths is line based and unquotes a leading
    # quote, so such names keep their working-tree bytes.
    pending = sorted(p for p, content in contents.items() if p in index and '\n' not in p
                     and not p.startswith('"') and _blob_id(content, len(index[p])) != index[p])
    if not pending:
        return {}
    # Attributes and hash-object --stdin-paths resolve paths from the top level.
    top, prefix = (_git(root, ['rev-parse', '--show-toplevel', '--show-prefix'])
                   .decode('utf-8', 'surrogateescape').split('\n')[:2])
    cleaned = _git(Path(top), ['hash-object', '--stdin-paths'],
                   ''.join(prefix + p + '\n' for p in pending).encode('utf-8', 'surrogateescape')).split()
    same = [p for p, oid in zip(pending, cleaned) if oid.decode('ascii') == index[p]]
    if not same:
        return {}
    output = _git(root, ['cat-file', '--batch'], ''.join(index[p] + '\n' for p in same).encode('ascii'))
    result, offset = {}, 0
    for path in same:
        end = output.index(b'\n', offset)
        header = output[offset:end].split()
        if len(header) != 3 or header[1] != b'blob':
            raise ValueError('Cannot read committed blob for ' + path)
        size = int(header[2])
        result[path] = output[end + 1:end + 1 + size]
        offset = end + 1 + size + 1
    return result


def portable_files(root, paths):
    """Read root-relative paths as checkout-independent bytes; None marks a missing file."""
    root = Path(root)
    paths = sorted(set(paths))
    attributes = text_attributes(root, paths)
    raw = {p: (root / p).read_bytes() if (root / p).is_file() else None for p in paths}
    sensitive = {p: c for p, c in raw.items() if c is not None and byte_sensitive(p, c, attributes.get(p))}
    committed = committed_blobs(root, sensitive)
    return {p: None if c is None else committed.get(p, portable_content(p, c, attributes.get(p)))
            for p, c in raw.items()}


EOL_DRIFT = {(b'i/lf', b'w/crlf'), (b'i/crlf', b'w/lf')}


def eol_drift(root):
    """Tracked byte-sensitive files whose working-tree line endings differ from the index."""
    try:
        listing = _git(root, ['ls-files', '--eol', '-z'])
    except (ValueError, OSError):
        return []
    found = []
    for entry in listing.split(b'\0'):
        meta, separator, name = entry.partition(b'\t')
        fields = meta.split()
        if not separator or len(fields) < 2 or (fields[0], fields[1]) not in EOL_DRIFT:
            continue
        attributes = {field.removeprefix(b'attr/') for field in fields[2:]}
        name = name.decode('utf-8', 'surrogateescape')
        if Path(name).suffix.lower() == '.sql' or b'-text' in attributes:
            found.append(name)
    return sorted(found)
