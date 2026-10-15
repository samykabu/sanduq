"""Per-feature lock file {"pid","host","started_at"}.

Stale recovery happens only when the owner ran on this host and its pid is dead. A lock whose owner is alive,
or on another host, is never stolen. An unreadable lock (a writer died between create and write) is stale
after 10 seconds.

Recovery is serialised by a second, short-lived lock `<lock>.recover`, created with O_EXCL. Whoever holds it
re-reads the owner and re-checks that it is still stale before unlinking, so a contender that observed a dead owner
earlier can never delete a live lock that another contender acquired in between. A recovery lock left by a crashed
recoverer expires after 10 seconds. Only one process recovers at a time; the others keep retrying.
"""
import json
import os
import secrets
import socket
import time
from pathlib import Path

from .util import iso, utcnow


class LockBusy(Exception):
    pass


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.GetLastError() == 5  # access denied means the process exists
        try:
            code = ctypes.c_ulong()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class Lock:
    def __init__(self, path, retries=3, delay=0.2):
        self.path, self.retries, self.delay = Path(path), retries, delay
        self.token = secrets.token_hex(8)

    def _stale(self):
        try:
            owner = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(owner, dict):
                raise ValueError
        except FileNotFoundError:
            return False
        except (OSError, ValueError):
            try:
                return time.time() - self.path.stat().st_mtime > 10
            except OSError:
                return False
        return owner.get('host') == socket.gethostname() and not pid_alive(owner.get('pid'))

    def _try(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'pid': os.getpid(), 'host': socket.gethostname(), 'started_at': iso(utcnow()),
                       'token': self.token}, stream)
        return True

    def _recover(self):
        """Remove a stale lock under the recovery lock. Returns True when this call removed it."""
        guard = self.path.with_name(self.path.name + '.recover')
        fd = None
        for _ in range(2):
            try:
                fd = os.open(str(guard), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                try:
                    if time.time() - guard.stat().st_mtime <= 10:
                        return False
                    os.unlink(guard)  # its recoverer died; take the guard on the second pass
                except OSError:
                    return False
            except OSError:
                return False
        if fd is None:
            return False
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'pid': os.getpid(), 'host': socket.gethostname()}, stream)
            if not self._stale():  # re-check now that no other recoverer can act
                return False
            os.unlink(self.path)
            return True
        except OSError:
            return False
        finally:
            try:
                os.unlink(guard)
            except OSError:
                pass

    def acquire(self):
        for attempt in range(self.retries + 1):
            if self._try():
                return self
            if self._stale() and self._recover() and self._try():
                return self
            if attempt < self.retries:
                time.sleep(self.delay)
        raise LockBusy(str(self.path))

    def release(self):
        try:
            owner = json.loads(self.path.read_text(encoding='utf-8'))
            if owner.get('token') == self.token:
                os.unlink(self.path)
        except (OSError, ValueError):
            pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False
