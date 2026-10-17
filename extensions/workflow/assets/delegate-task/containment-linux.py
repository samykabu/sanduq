"""Private Linux subreaper. Input is JSON over stdin, never shell source."""
import ctypes
import errno
import json
import os
import signal
import subprocess
import sys
import time


def event(obj):
    try:
        print(json.dumps(obj), flush=True)
    except BrokenPipeError:
        pass


def run(req):
    proof = dict(nonce=req['nonce'], state='unresolved', mechanism='linux_subreaper',
                 started=False, root_pid=None, exit_code=None, signal=None,
                 timed_out=False, owner_lost=False, launch_error=None, reaped=0)
    stopping = False

    def abort(*_):
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, abort)
    libc = ctypes.CDLL(None, use_errno=True)
    # Become the nearest living ancestor for double-forked/setsid descendants.
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        proof.update(state='closed', launch_error='SUBREAPER_UNAVAILABLE')
        return proof
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        proof.update(state='closed', launch_error='OWNER_WATCH_UNAVAILABLE')
        return proof
    if os.getppid() != req['owner_pid']:
        proof.update(state='closed', owner_lost=True)
        return proof
    # Verify the kernel child-enumeration interface before launching anything.
    children_file = '/proc/self/task/%s/children' % os.getpid()
    try:
        with open(children_file, encoding='ascii') as f:
            f.read()
    except OSError:
        proof.update(state='closed', launch_error='CHILD_ENUMERATION_UNAVAILABLE')
        return proof
    with open(req['stdout'], 'ab', buffering=0) as out, open(req['stderr'], 'ab', buffering=0) as err:
        try:
            child = subprocess.Popen([req['file']] + req['args'], cwd=req['cwd'], env=req['env'],
                                     stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                     start_new_session=True, close_fds=True)
        except OSError as exc:
            proof.update(state='closed', launch_error=errno.errorcode.get(exc.errno, 'SPAWN_FAILED'))
            return proof
        proof.update(started=True, root_pid=child.pid)
        event(dict(type='started', root_pid=child.pid))
        began = time.monotonic()
        cleanup_until = None
        while True:
            # Reap only our own children. ECHILD is the closure proof: any live
            # descendant would still have a chain to a direct subreaper child.
            empty = False
            while True:
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    empty = True
                    break
                if pid == 0:
                    break
                proof['reaped'] += 1
                if pid == child.pid:
                    code = os.waitstatus_to_exitcode(status)
                    child.returncode = code
                    proof['exit_code'] = code if code >= 0 else None
                    proof['signal'] = signal.Signals(-code).name if code < 0 else None
            if empty:
                proof['state'] = 'closed'
                return proof
            if os.getppid() != req['owner_pid']:
                proof['owner_lost'] = True
                stopping = True
            if time.monotonic() - began >= req['timeout_s']:
                proof['timed_out'] = True
                stopping = True
            if os.path.exists(req['cancel']):
                stopping = True
            if stopping:
                if cleanup_until is None:
                    cleanup_until = time.monotonic() + 10
                # Kill direct children before reaping them, so their PIDs cannot
                # be reused between enumeration and kill. Orphans are adopted and
                # handled on the next iteration, including new process groups.
                with open(children_file, encoding='ascii') as f:
                    children = [int(v) for v in f.read().split()]
                for pid in children:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if time.monotonic() > cleanup_until:
                    return proof  # unable to prove closure; lock stays unresolved
            time.sleep(0.01)


if __name__ == '__main__':
    request = json.loads(sys.stdin.read(4 * 1024 * 1024))
    try:
        result = run(request)
    except Exception:
        result = dict(nonce=request['nonce'], state='unresolved', mechanism='linux_subreaper',
                      started=True, launch_error='CONTAINMENT_HELPER_FAILED')
    # Persist before writing to the pipe: the supervisor may already be gone.
    with open(request['proof'], 'x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False)
        f.write('\n')
    event(dict(type='finished'))
