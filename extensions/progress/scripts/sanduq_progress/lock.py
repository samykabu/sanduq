"""Per-feature lock held by the operating system.

The lock file is opened and an exclusive, non-blocking OS lock is taken on it (msvcrt.locking on Windows,
fcntl.flock elsewhere) and held for the lifetime of the Lock. The OS drops the lock when the owning process dies, so
there is no stale-lock recovery and nothing a contender can delete using stale evidence. The file content
{"pid","host","started_at","token"} is diagnostic only and is never used to decide ownership. The file is left in place
on release (removing it would let a contender lock an unlinked inode).
"""
import json
import os
import time
from pathlib import Path

from .util import iso, refuse_link, utcnow

# On Windows a locked byte range cannot be read by other handles, so the lock byte sits far beyond the metadata.
_WIN_LOCK_OFFSET = 1 << 30


def _hostname():
    return os.environ.get('COMPUTERNAME') or (os.uname().nodename if hasattr(os, 'uname') else '')


class LockBusy(Exception):
    pass


def _os_lock(fd):
    """Take an exclusive non-blocking lock on fd. Returns False when another holder has it."""
    try:
        if os.name == 'nt':
            import msvcrt
            os.lseek(fd, _WIN_LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _os_unlock(fd):
    try:
        if os.name == 'nt':
            import msvcrt
            os.lseek(fd, _WIN_LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


class Lock:
    def __init__(self, path, retries=3, delay=0.2):
        self.path, self.retries, self.delay = Path(path), retries, delay
        self.token = None
        self.fd = None

    def _try(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        refuse_link(self.path)
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT)
        if not _os_lock(fd):
            os.close(fd)
            return False
        self.fd = fd
        try:  # diagnostics only
            self.token = os.urandom(8).hex()
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, json.dumps({'pid': os.getpid(), 'host': _hostname(), 'started_at': iso(utcnow()),
                                     'token': self.token}).encode('utf-8'))
        except OSError:
            pass
        return True

    def acquire(self):
        if self.fd is not None:
            return self
        for attempt in range(self.retries + 1):
            if self._try():
                return self
            if attempt < self.retries:
                time.sleep(self.delay)
        raise LockBusy(str(self.path))

    def release(self):
        if self.fd is None:
            return
        fd, self.fd = self.fd, None
        _os_unlock(fd)
        try:
            os.close(fd)
        except OSError:
            pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False
