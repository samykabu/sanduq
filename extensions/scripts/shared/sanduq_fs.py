"""One file lock, one atomic JSON write and one bounded subprocess runner for Sanduq's runtimes (SAMY-01/02/09).

Stdlib only: each consumer loads it without Workflow or PyYAML. Callers pass their own error type (`error=`)
so their codes and exception classes stay unchanged.

The lock is an exclusive-create file holding `{pid, host, token, created}`. A lock whose recorded pid has
exited on this host is recovered automatically; a lock from another host, or a live pid, is never taken.
"""
import json
import os
import random
import socket
import subprocess
import time
import uuid
from contextlib import contextmanager


class LockError(Exception):
    pass


def process_alive(pid):
    """True unless this host proves ``pid`` has exited; unknown answers count as alive."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if os.name == 'nt':
        # os.kill(pid, 0) terminates the process on Windows, so ask the kernel.
        import ctypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no such process
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


# A lock file with no readable owner is only stale once it is this old: its
# creator writes the owner record immediately after the exclusive create.
LOCK_UNREADABLE_STALE_SECONDS = 60


def lock_owner(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def lock_is_stale(path, owner):
    """A lock is stale only when its recorded owner provably died on this host."""
    if owner is None or not isinstance(owner.get('pid'), int):
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            return False
        return age >= LOCK_UNREADABLE_STALE_SECONDS
    if owner.get('host') != socket.gethostname():
        return False
    return not process_alive(owner['pid'])


def recover_stale_lock(path):
    """Remove ``path`` only if it still holds the dead owner that was inspected.

    Unlinking after a check is not atomic: another stealer may already have
    replaced the lock with a live one. A single rename captures exactly one
    file; if the captured owner is not the dead one inspected, it goes back.
    """
    owner = lock_owner(path)
    if not lock_is_stale(path, owner):
        return False
    captured = path.with_name(path.name + '.stale-' + uuid.uuid4().hex)
    try:
        os.rename(path, captured)
    except OSError:
        return False
    if lock_owner(captured) == owner and lock_is_stale(captured, lock_owner(captured)):
        captured.unlink(missing_ok=True)
        return True
    try:
        # Put a live owner back without replacing any newer lock.
        os.link(captured, path)
        captured.unlink(missing_ok=True)
    except OSError:
        # A newer lock exists; the displaced owner detects the loss in
        # lock_held() and refuses to write.
        captured.unlink(missing_ok=True)
    return False


def lock_held(path, token):
    owner = lock_owner(path)
    return bool(owner and owner.get('token') == token)


def release_owned_lock(path, token, error=LockError, busy='LOCK_RELEASE_BUSY'):
    """Release our lock after transient Windows readers close their handles.

    Opening a lock file to inspect its owner can briefly prevent unlink on
    Windows. Recheck the token on every retry so a replacement lock is never
    removed by the former owner.
    """
    deadline = time.monotonic() + 5
    while True:
        owner = lock_owner(path)
        if owner is not None:
            if owner.get('token') != token:
                return
            try:
                path.unlink(missing_ok=True)
                return
            except PermissionError:
                pass
        elif not path.exists():
            return
        if time.monotonic() >= deadline:
            raise error(busy + ': could not release ' + str(path) +
                        '; check that no process still has the file open')
        time.sleep(0.02)


def describe_owner(path):
    """`pid P on host H for Ns (alive: yes|unknown)` for a held lock: what a busy message names."""
    owner = lock_owner(path) or {}
    pid, host = owner.get('pid'), owner.get('host')
    try:
        age = '%ds' % max(0, time.time() - path.stat().st_mtime)
    except OSError:
        age = 'an unknown time'
    alive = 'yes' if host == socket.gethostname() and process_alive(pid) else 'unknown'
    return 'pid %s on host %s for %s (alive: %s)' % (pid, host, age, alive)


def busy_message(path, busy):
    owner = lock_owner(path) or {}
    pid = owner.get('pid')
    check = ('"tasklist /FI \\"PID eq %s\\"" on Windows or "ps -p %s" elsewhere' % (pid, pid)
             if pid is not None else 'the process list')
    return (busy + ': retry the command once the process holding ' + str(path) + ' finishes: ' +
            describe_owner(path) + '. A lock whose owner has exited on this host is recovered automatically; '
            'if ' + check + ' shows no such process and the lock came from another host or an older version, '
            'delete ' + str(path) + ' and retry')


@contextmanager
def file_lock(path, timeout, busy, error=LockError, release_busy='LOCK_RELEASE_BUSY'):
    """Exclusive cross-process lock that recovers a dead owner's lock file.

    Yields the owner token; callers that write shared state call lock_held()
    before their final write so a displaced owner never overwrites a newer one.
    `timeout` 0 tries once (after recovering a dead owner) and then raises `error(busy_message(...))`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except (FileExistsError, PermissionError):
            if recover_stale_lock(path):
                continue
            if time.monotonic() >= deadline:
                raise error(busy_message(path, busy)) from None
            time.sleep(0.05)
    try:
        os.write(fd, json.dumps({'pid': os.getpid(), 'host': socket.gethostname(),
                                 'token': token, 'created': time.time()}).encode())
        os.close(fd)
        yield token
    finally:
        release_owned_lock(path, token, error, release_busy)


def replace_file(source, target, attempts=10):
    """`os.replace` with a short bounded retry: on Windows another process (an indexer, a scanner, a
    concurrent reader) can hold the target for a moment and the rename fails with PermissionError."""
    for attempt in range(attempts):
        try:
            return os.replace(source, target)
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.02 + 0.03 * random.random())


def write_json(path, value):
    """Atomic JSON write: a uuid temp name beside the target (concurrent writers never share one), then replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        replace_file(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def run_bounded(args, *, timeout, error_code, next_step, error=RuntimeError, **kwargs):
    """`subprocess.run` with a timeout; a timeout raises `error('<error_code>: ... ; <next_step>')`.

    `subprocess.run` kills the direct child on a timeout, so a caller holding a lock releases it on the way
    out. shortcut: grandchildren are not killed; callers that start process trees kill the tree themselves.
    """
    try:
        return subprocess.run(args, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired:
        raise error('%s: %s did not finish within %s s and was stopped; %s'
                    % (error_code, os.path.basename(str(args[0])), timeout, next_step)) from None
