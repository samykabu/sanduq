"""Build a lifecycle fixture once per test class and copy the tree for every later test (round 4, W22/X25).

`reuse(test, build, reopen)` runs `build()` in `test.root` the first time a class reaches it from a given starting
tree, then saves a copy of the tree. A later test of the same class that starts from the same bytes gets that copy
instead and `reopen()` is returned. Each test still owns a fresh tree: nothing is shared or mutated in place.

Only a deterministic `build` may use it: one that depends on nothing but the class and the starting tree (no
patches, clocks or random values a test could observe).
"""
import atexit
import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path

_HOLDER = []
_SAVED = {}


def _folder():
    if not _HOLDER:
        holder = tempfile.TemporaryDirectory(prefix='sanduq-snapshots-')
        atexit.register(holder.cleanup)
        _HOLDER.append(Path(holder.name))
    return _HOLDER[0]


def tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(root).rglob('*') if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()


def _writable(function, path, _):
    os.chmod(path, stat.S_IWRITE)  # git writes its objects read-only on Windows
    function(path)


def _clear(root):
    for child in Path(root).iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, onerror=_writable)
        else:
            os.chmod(child, stat.S_IWRITE)
            child.unlink()


def reuse(test, build, reopen, key=()):
    root = Path(test.root)
    slot = (type(test).__module__, type(test).__qualname__, key, tree_digest(root))
    saved = _SAVED.get(slot)
    if saved is not None:
        _clear(root)
        shutil.copytree(saved, root, dirs_exist_ok=True, symlinks=True)
        return reopen()
    result = build()
    target = _folder() / str(len(_SAVED))
    shutil.copytree(root, target, symlinks=True)
    _SAVED[slot] = target
    return result
