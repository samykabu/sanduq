import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';

export function alive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return true; // unknown ownership is not dead
  try { process.kill(pid, 0); return true; } catch (e) { return e.code !== 'ESRCH'; }
}

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
      const record = { pid: process.pid, active_child: null };
      try { fs.writeFileSync(owner, JSON.stringify(record), { flag: 'wx', encoding: 'utf8' }); }
      catch { continue; }
      // Another recovery may have removed an empty directory before publication.
      // Multiple owner files are ambiguous: nobody is authorised to execute.
      if (fs.readdirSync(dir).length !== 1) return null;
      const release = () => {
        try { fs.unlinkSync(owner); fs.rmdirSync(dir); } catch { /* preserve others */ }
      };
      release.child = pid => {
        record.active_child = pid;
        fs.writeFileSync(owner, JSON.stringify(record), 'utf8');
      };
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
      // Native Windows cannot prove an orphaned descendant tree dead merely
      // because its root pid has gone. Leave that owner for explicit resolution.
      if (process.platform === 'win32' || alive(previous.active_child)) return null;
      try { process.kill(-previous.active_child, 0); return null; }
      catch (e) { if (e.code !== 'ESRCH') return null; }
    }
    try { fs.unlinkSync(path.join(dir, owners[0])); fs.rmdirSync(dir); }
    catch { return null; }
  }
  return null;
}
