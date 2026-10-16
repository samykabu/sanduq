import fs from 'node:fs';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';

function canonical(v) {
  if (Array.isArray(v)) return v.map(canonical);
  if (v && typeof v === 'object') return Object.fromEntries(Object.keys(v).sort().map(k => [k, canonical(v[k])]));
  return v;
}
function directoryIdentity(dir) {
  const real = fs.realpathSync(dir), s = fs.statSync(real, { bigint: true });
  let git = null;
  try {
    const lines = execFileSync('git', ['rev-parse', '--show-toplevel', '--absolute-git-dir'], {
      cwd: real, encoding: 'utf8', timeout: 3000, maxBuffer: 16384, windowsHide: true, shell: false, stdio: ['ignore', 'pipe', 'pipe'],
    }).trim().split(/\r?\n/);
    const gitDir = fs.realpathSync(lines[1]), gs = fs.statSync(gitDir, { bigint: true });
    git = { root: fs.realpathSync(lines[0]), git_dir: gitDir, dev: String(gs.dev), ino: String(gs.ino) };
  } catch { /* non-repository identity uses the real directory and its file id */ }
  return { path: real, dev: String(s.dev), ino: String(s.ino), git };
}
export function batchManifest(plan) {
  const normalized = {
    batch_id: plan.batch_id,
    cwd: fs.realpathSync(plan.cwd),
    env: plan.env || {},
    interpreters: { node: fs.realpathSync(process.execPath), ...(plan.interpreters || {}) },
    checks: plan.checks.map(c => ({ name: c.name, argv: c.argv, cwd: fs.realpathSync(c.cwd || plan.cwd), timeout_s: c.timeout_s, env: c.env || {} })),
  };
  const directories = [...new Set([normalized.cwd, ...normalized.checks.map(c => c.cwd)])].sort();
  const identity = { manifest: normalized, worktrees: directories.map(directoryIdentity) };
  return { schema: 'delegate-task.check-manifest.v1', sha256: crypto.createHash('sha256').update(JSON.stringify(canonical(identity)), 'utf8').digest('hex') };
}
