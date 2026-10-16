import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';

export function alive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return true; // unknown ownership is not dead
  try { process.kill(pid, 0); return true; } catch (e) { return e.code !== 'ESRCH'; }
}

export function containmentProof(binding) {
  if (!binding || typeof binding.proof !== 'string' || typeof binding.nonce !== 'string') return null;
  try {
    if (fs.statSync(binding.proof).size > 4096) return null;
    const proof = JSON.parse(fs.readFileSync(binding.proof, 'utf8'));
    return proof.nonce === binding.nonce && ['windows_job', 'linux_subreaper'].includes(proof.mechanism) ? proof : null;
  } catch { return null; }
}
export const containmentClosed = binding => containmentProof(binding)?.state === 'closed';

// Only call for a child created by this process, never a pid read from a lock.
export function killOwnedTree(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return;
  if (process.platform === 'win32') {
    const exe = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'taskkill.exe');
    spawnSync(exe, ['/pid', String(pid), '/T', '/F'], { shell: false, windowsHide: true, stdio: 'ignore' });
  } else {
    try { process.kill(-pid, 'SIGKILL'); } catch { /* owned group already gone */ }
  }
}

// A lock directory keeps the immutable owner filename through recovery. Removal
// targets that filename only; rmdir cannot remove a directory with a new owner.
// Unknown/incomplete ownership blocks conservatively; age never proves death.
export function acquireBatchLock(dir) {
  const token = `${process.pid}-${crypto.randomUUID()}`;
  for (let i = 0; i < 4; i++) {
    try {
      fs.mkdirSync(dir);
      const owner = path.join(dir, token);
      const record = { pid: process.pid, active_child: null, containment: null };
      try { fs.writeFileSync(owner, JSON.stringify(record), { flag: 'wx', encoding: 'utf8' }); }
      catch { continue; }
      // Another recovery may have removed an empty directory before publication.
      // Multiple owner files are ambiguous: nobody is authorised to execute.
      if (fs.readdirSync(dir).length !== 1) return null;
      const release = () => {
        if (record.active_child !== null) return; // unresolved ownership is durable
        try { fs.unlinkSync(owner); fs.rmdirSync(dir); } catch { /* preserve others */ }
      };
      release.child = (pid, binding = null) => {
        if (pid !== null && record.active_child !== null && !(record.active_child === 'launching' && record.containment?.nonce === binding?.nonce)) throw new Error('prior containment is unresolved');
        if (pid === null && record.containment && !containmentClosed(record.containment)) throw new Error('containment closure is unproven');
        record.active_child = pid;
        record.containment = binding;
        fs.writeFileSync(owner, JSON.stringify(record), 'utf8');
      };
      release.hasActive = () => record.active_child !== null;
      return release;
    } catch (e) {
      if (e.code !== 'EEXIST') throw e;
    }
    const owners = fs.readdirSync(dir);
    if (owners.length !== 1 || !/^\d+-[a-f0-9-]+$/.test(owners[0])) return null;
    if (alive(Number(owners[0].split('-')[0]))) return null;
    let previous;
    try {
      const file = path.join(dir, owners[0]);
      if (fs.statSync(file).size > 4096) return null;
      previous = JSON.parse(fs.readFileSync(file, 'utf8'));
    }
    catch { return null; }
    if (previous.active_child !== null) {
      // A dead root or helper alone says nothing about detached descendants.
      // Recovery never kills recorded processes and requires native closure.
      if (alive(previous.active_child) || !containmentClosed(previous.containment)) return null;
    }
    try { fs.unlinkSync(path.join(dir, owners[0])); fs.rmdirSync(dir); }
    catch { return null; }
  }
  return null;
}
