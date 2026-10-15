"""Per-feature lock file {"pid","host","started_at"}.

Stale recovery happens only when the owner ran on this host and its pid is dead. A lock whose owner is alive,
or on another host, is never stolen. An unreadable lock (a writer died between create and write) is stale
after 10 seconds. Recovery is atomic rename-away, but two recoverers racing can still hand a lock to both;
the window is a few microseconds and the protected data is append-only or rebuildable.
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

    def acquire(self):
        for attempt in range(self.retries + 1):
            if self._try():
                return self
            if self._stale():
                away = self.path.with_name(self.path.name + f'.stale-{os.getpid()}')
                try:
                    os.replace(self.path, away)
                    os.unlink(away)
                except OSError:
                    pass
                if self._try():
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
