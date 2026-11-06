import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { containmentProof } from './process-tools.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
function helper() {
  if (process.platform === 'win32') return {
    file: path.join(process.env.SystemRoot || 'C:\\Windows', 'System32/WindowsPowerShell/v1.0/powershell.exe'),
    args: ['-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', path.join(HERE, 'containment-windows.ps1')],
  };
  if (process.platform === 'linux') {
    const configured = process.env.DELEGATE_CONTAINMENT_PYTHON;
    const candidates = configured === undefined ? ['/usr/bin/python3', '/usr/local/bin/python3'] : [configured];
    const file = candidates.find(p => p && path.isAbsolute(p) && fs.existsSync(p) && fs.statSync(p).isFile());
    if (!file) throw new Error('Linux containment requires a real Python 3 binary (DELEGATE_CONTAINMENT_PYTHON)');
    return { file: fs.realpathSync(file), args: ['-I', '-u', path.join(HERE, 'containment-linux.py')] };
  }
  throw new Error('native check containment is supported on Windows and Linux only; no check launched');
}

// The child is a private owner helper. User argv/env travel as JSON on stdin;
// there is no user command shell or interpolation. Logs go straight to files.
export async function runContained(request, { ownership, startedFile, cancelFile, onCancelReady }) {
  const h = helper();
  const binding = { proof: request.proof, nonce: request.nonce };
  ownership.child('launching', binding);
  const child = spawn(h.file, h.args, { shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  let spawnError = null, protocol = '', started = false, closed = false, timedOut = false;
  let startupTimer, runTimer, drainTimer;
  const cancel = () => {
    try { fs.writeFileSync(cancelFile, '', { flag: 'wx', encoding: 'utf8', mode: 0o600 }); } catch { /* already requested */ }
  };
  const result = await new Promise(resolve => {
    const finish = () => {
      if (closed) return;
      closed = true;
      clearTimeout(startupTimer); clearTimeout(runTimer); clearTimeout(drainTimer);
      child.stdin.destroy(); child.stdout.destroy(); child.stderr.destroy(); child.unref();
      resolve({ proof: containmentProof(binding), helper_pid: child.pid, spawn_error: spawnError, timed_out: timedOut });
    };
    const requestStop = () => { cancel(); drainTimer ??= setTimeout(finish, 15000); };
    onCancelReady(requestStop);
    startupTimer = setTimeout(requestStop, 30000);
    child.on('error', e => { spawnError = e.code || 'HELPER_SPAWN_FAILED'; });
    child.stdin.on('error', () => {});
    child.stderr.on('data', () => {}); // helper diagnostics never echo request data
    child.stdout.on('data', bytes => {
      protocol += bytes.toString('utf8');
      if (protocol.length > 65536) { requestStop(); protocol = ''; return; }
      let nl;
      while ((nl = protocol.indexOf('\n')) >= 0) {
        const line = protocol.slice(0, nl); protocol = protocol.slice(nl + 1);
        let e; try { e = JSON.parse(line); } catch { continue; }
        if (e.type === 'started' && !started) {
          started = true; clearTimeout(startupTimer);
          // Native helper owns the actual runtime deadline. This guard only
          // bounds a broken helper after that deadline, without shortening it.
          runTimer = setTimeout(() => { timedOut = true; requestStop(); }, request.timeout_s * 1000);
        }
      }
    });
    child.on('spawn', () => {
      try {
        ownership.child(child.pid, binding);
        fs.writeFileSync(startedFile, JSON.stringify({ pid: child.pid, containment: binding, started_at: new Date().toISOString() }) + '\n', { flag: 'wx', encoding: 'utf8', mode: 0o600 });
        child.stdin.end(JSON.stringify(request));
      } catch { requestStop(); child.stdin.end(); }
    });
    child.on('close', finish);
  });
  // A failed OS spawn never launched the helper or user program. Every other
  // missing proof is unresolved, including a helper hard kill.
  if (spawnError && !child.pid) {
    fs.writeFileSync(request.proof, JSON.stringify({ nonce: request.nonce, state: 'closed', mechanism: process.platform === 'win32' ? 'windows_job' : 'linux_subreaper', started: false, launch_error: spawnError }) + '\n', { flag: 'wx', encoding: 'utf8', mode: 0o600 });
    result.proof = containmentProof(binding);
  }
  return result;
}
