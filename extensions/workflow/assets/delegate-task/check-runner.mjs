#!/usr/bin/env node
// Native, sequential check batches. No agent CLI, command strings or shell.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { acquireBatchLock, containmentClosed, containmentProof, alive } from './process-tools.mjs';
import { runContained } from './containment.mjs';
import { excerptFile, redact, clipChars } from './bounded.mjs';
import { batchManifest } from './check-identity.mjs';
import { encodeReceipt, counts, validateMaxBytes, DEFAULT_MAX_BYTES } from './check-receipt.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MAX_PLAN = 1024 * 1024;
const ID = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$/;
const ATTEMPT_ID = /^attempt-\d+-[a-f0-9]{12}$/;
const attemptNames = batch => fs.readdirSync(batch).filter(n => ATTEMPT_ID.test(n)).sort();
const read = (p) => JSON.parse(fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, ''));
const write = (p, o) => fs.writeFileSync(p, JSON.stringify(o, null, 2) + '\n', { encoding: 'utf8', flag: 'wx', mode: 0o600 });
function boundedRead(p, max = MAX_PLAN) {
  if (fs.statSync(p).size > max) throw new Error('JSON metadata exceeds size limit');
  return read(p);
}
function seconds(n) { return Number.isFinite(n) && n > 0 && n * 1000 <= 2147483647; }
function envObject(o) {
  if (o === undefined) return {};
  if (!o || typeof o !== 'object' || Array.isArray(o) || Object.entries(o).some(([k, v]) => !k || /[=\0]/.test(k) || typeof v !== 'string' || v.includes('\0'))) throw new Error('env must contain explicit string values');
  return o;
}
export function validatePlan(p, { probePython = true } = {}) {
  if (!p || typeof p.batch_id !== 'string' || !ID.test(p.batch_id)) throw new Error('batch_id must be a safe identifier');
  if (!path.isAbsolute(p.cwd || '') || !fs.statSync(p.cwd).isDirectory()) throw new Error('cwd must be an existing absolute directory');
  if (!Array.isArray(p.checks) || !p.checks.length || p.checks.length > 100) throw new Error('checks must contain 1..100 named argv arrays');
  envObject(p.env);
  const names = new Set();
  let pythonChecked = false;
  for (const c of p.checks) {
    if (!c || typeof c.name !== 'string' || !c.name.trim() || c.name.length > 128 || names.has(c.name)) throw new Error('check names must be nonempty and unique (128 characters maximum)');
    names.add(c.name);
    if (!Array.isArray(c.argv) || !c.argv.length || c.argv.length > 256 || c.argv.some(a => typeof a !== 'string' || a.includes('\0') || a.length > 65536) || !c.argv[0].trim()) throw new Error('check argv executable must be nonempty; arguments must be strings');
    if (!seconds(c.timeout_s)) throw new Error('check timeout_s must be explicit, positive and within the Node timer range');
    if (c.cwd !== undefined && (!path.isAbsolute(c.cwd) || !fs.statSync(c.cwd).isDirectory())) throw new Error('check cwd must be an existing absolute directory');
    envObject(c.env);
    for (const arg of c.argv) {
      if (arg === '{{python}}') {
        const py = p.interpreters?.python;
        if (typeof py !== 'string' || !path.isAbsolute(py) || !fs.statSync(py).isFile() || /\.(cmd|bat|ps1|py)$/i.test(py)) throw new Error('{{python}} requires an explicit real Python executable path');
        if (probePython && !pythonChecked) {
          if (/[/\\]WindowsApps[/\\]/i.test(py)) throw new Error('Python app aliases are unsupported; select a real Python installation');
          try {
            const probe = execFileSync(py, ['-I', '-c', 'import sys; print("check-runner-python")'], { timeout: 10000, maxBuffer: 4096, encoding: 'utf8', windowsHide: true, shell: false, stdio: ['ignore', 'pipe', 'pipe'] });
            if (probe.trim() !== 'check-runner-python') throw new Error('unexpected interpreter response');
          } catch { throw new Error('explicit Python executable failed isolated interpreter probe'); }
          pythonChecked = true;
        }
      }
    }
  }
  return p;
}
function secretValues(p) {
  // Safe even before plan validation. Inspect only string values in env maps;
  // malformed plans and overlapping/overridden credentials remain redacted.
  const strings = o => o && typeof o === 'object' && !Array.isArray(o) ? Object.values(o).filter(v => typeof v === 'string' && v) : [];
  const inherited = Object.entries(process.env).filter(([k, v]) => v && /token|secret|passw|key|credential|auth/i.test(k)).map(([, v]) => v);
  return [...inherited, ...strings(p?.env), ...(Array.isArray(p?.checks) ? p.checks.flatMap(c => strings(c?.env)) : [])];
}
function executable(name, cwd, env) {
  const win = process.platform === 'win32';
  const dirs = /[/\\]/.test(name) ? [''] : (env.PATH || env.Path || '').split(path.delimiter);
  const exts = win && !path.extname(name) ? ['.exe', '.com', '.cmd', '.bat', ''] : [''];
  for (const d of dirs) for (const ext of exts) {
    const f = path.resolve(cwd, d.replace(/^"(.*)"$/, '$1'), name + ext);
    try {
      if (!fs.statSync(f).isFile()) continue;
      if (win && !/\.(exe|com)$/i.test(f)) throw new Error('unsupported Windows shim/script; provide its real executable and script as separate argv entries');
      return f;
    } catch (e) { if (e.message.startsWith('unsupported')) throw e; }
  }
  throw new Error('executable not found');
}
async function execute(c, p, dir, index, ownership) {
  const prefix = String(index + 1).padStart(3, '0');
  const paths = { stdout: path.join(dir, `${prefix}.stdout.log`), stderr: path.join(dir, `${prefix}.stderr.log`) };
  for (const file of Object.values(paths)) fs.closeSync(fs.openSync(file, 'wx', 0o600));
  const r = { name: c.name, status: 'pending', exit_code: null, signal: null, launch_error: null, error: null, timed_out: false, started_at: new Date().toISOString(), artifacts: paths, bytes: { stdout: 0, stderr: 0 } };
  const t0 = Date.now();
  let cancel = () => {}, aborted = false;
  const abort = () => { aborted = true; cancel(); };
  for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(sig, abort);
  try {
    const env = { ...process.env, ...p.env, ...c.env };
    const cwd = c.cwd || p.cwd;
    const argv = c.argv.map(a => a === '{{node}}' ? process.execPath : a === '{{python}}' ? p.interpreters.python : a);
    const file = executable(argv[0], cwd, env);
    const proof = path.join(dir, `${prefix}.containment.json`), cancelFile = path.join(dir, `${prefix}.cancel`);
    const contained = await runContained({ file, args: argv.slice(1), cwd, env, timeout_s: c.timeout_s,
      owner_pid: process.pid, stdout: paths.stdout, stderr: paths.stderr, proof,
      nonce: crypto.randomBytes(16).toString('hex'), cancel: cancelFile }, {
      ownership, startedFile: path.join(dir, `${prefix}.started.json`), cancelFile,
      onCancelReady: fn => { cancel = fn; if (aborted) cancel(); },
    });
    r.containment = contained.proof || { state: 'unresolved', mechanism: null };
    r.exit_code = contained.proof?.exit_code ?? null;
    r.signal = contained.proof?.signal ?? null;
    r.launch_error = contained.proof?.launch_error || contained.spawn_error;
    r.timed_out = Boolean(contained.timed_out || contained.proof?.timed_out);
    for (const key of ['stdout', 'stderr']) r.bytes[key] = fs.statSync(paths[key]).size;
    if (r.containment.state === 'closed') ownership.child(null);
    else r.error = 'owned descendant containment is unresolved; further execution is blocked';
    r.status = r.containment.state !== 'closed' ? 'containment_unresolved' : aborted ? 'abandoned' : r.timed_out ? 'timeout' : r.launch_error ? 'launch_failed' : r.exit_code === 0 && !r.signal ? 'passed' : 'failed';
  } catch (e) {
    r.launch_error = e.message;
    if (ownership.hasActive()) { cancel(); r.status = 'containment_unresolved'; r.containment = { state: 'unresolved', mechanism: null }; }
    else r.status = 'launch_failed';
  }
  finally {
    for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.removeListener(sig, abort);
  }
  r.ended_at = new Date().toISOString(); r.duration_ms = Date.now() - t0;
  return r;
}
function publicAttempt(r, secrets, outputBytes) {
  return {
    ...r,
    checks: r.checks.map(c => ({ ...c,
      name: clipChars(redact(c.name, secrets), 128).text,
      launch_error: c.launch_error ? clipChars(redact(c.launch_error, secrets), 512).text : null,
      error: c.error ? redact(c.error, secrets) : null,
      output: Object.fromEntries(Object.entries(c.artifacts || {}).map(([k, f]) => [k, excerptFile(f, { head: Math.ceil(outputBytes / 2), tail: Math.floor(outputBytes / 2), secrets })])),
    })),
  };
}
export async function runBatch(p, root, { retryOf = null } = {}) {
  validatePlan(p, { probePython: false });
  const batch = path.join(root, 'checks', p.batch_id);
  fs.mkdirSync(batch, { recursive: true, mode: 0o700 });
  const unlock = acquireBatchLock(path.join(batch, 'execution.lock'));
  if (!unlock) return { busy: true, batch_id: p.batch_id };
  try {
    const prior = attemptNames(batch), latest = prior.at(-1) || null;
    if (retryOf !== null && (!ATTEMPT_ID.test(retryOf) || retryOf !== latest)) throw new Error('--retry-of must match the latest existing attempt; no checks were executed');
    const identity = batchManifest(p), manifestPath = path.join(batch, 'manifest.json');
    if (fs.existsSync(manifestPath)) {
      if (boundedRead(manifestPath).sha256 !== identity.sha256) throw new Error('batch manifest/worktree identity changed; use a new batch_id');
    } else {
      if (prior.length) throw new Error('historical batch has no bound manifest/worktree identity; use a new batch_id (collection remains available)');
      write(manifestPath, identity);
    }
    if (latest && !retryOf) {
      const receipt = collectBatch(root, p.batch_id, latest, 1).attempts[0];
      return { ...receipt, refused: 'retry_required', requires_explicit_retry: true, execution_performed: false, latest_attempt_id: latest };
    }
    if (latest && retryOf) {
      const previousDir = path.join(batch, latest);
      if (!fs.existsSync(path.join(previousDir, 'result.json'))) {
        const previous = boundedRead(path.join(previousDir, 'attempt.json'));
        if (alive(previous.owner_pid)) throw new Error('previous attempt owner is live or unknown; retry refused');
        // The execution lock carries launch intent and active-child guards. A
        // missing lock on an unfinished launched attempt cannot prove containment.
        for (const name of fs.readdirSync(previousDir).filter(n => n.endsWith('.started.json'))) {
          const started = boundedRead(path.join(previousDir, name));
          if (alive(started.pid) || !containmentClosed(started.containment)) throw new Error('unfinished launched attempt requires explicit child/ownership resolution; retry refused');
        }
      }
    }
    validatePlan(p);
    const nextTime = Math.max(Date.now(), latest ? Number(latest.split('-')[1]) + 1 : 0);
    const attempt = `attempt-${nextTime}-${crypto.randomBytes(6).toString('hex')}`;
    const dir = path.join(batch, attempt);
    fs.mkdirSync(dir, { mode: 0o700 });
    write(path.join(dir, 'plan.json'), p);
    const result = { schema: 'delegate-task.check-batch.v1', batch_id: p.batch_id, attempt_id: attempt, retry_of: retryOf, manifest_sha256: identity.sha256, owner_pid: process.pid, started_at: new Date().toISOString(), status: 'running', checks: [] };
    // Immutable checkpoints preserve earlier exits if the owner is hard-killed.
    write(path.join(dir, 'attempt.json'), { ...result, checks: p.checks.map(c => ({ name: c.name, status: 'pending', exit_code: null })) });
    for (let i = 0; i < p.checks.length; i++) {
      const r = await execute(p.checks[i], p, dir, i, unlock);
      result.checks.push(r);
      write(path.join(dir, `${String(i + 1).padStart(3, '0')}.result.json`), r);
      if (r.status === 'abandoned' || r.status === 'containment_unresolved') {
        result.checks.push(...p.checks.slice(i + 1).map(c => ({ name: c.name, status: 'skipped', exit_code: null, error: r.status === 'containment_unresolved' ? 'prior check containment is unresolved' : 'batch interrupted before launch' })));
        break;
      }
    }
    result.status = result.checks.length === p.checks.length && result.checks.every(c => c.status === 'passed') ? 'successful' : 'failed';
    result.status_provenance = { primary: result.checks.some(c => c.status === 'containment_unresolved') ? 'containment_unresolved' : 'check_results' };
    result.ended_at = new Date().toISOString();
    write(path.join(dir, 'result.json'), result);
    return publicAttempt(result, secretValues(p), 1024);
  } finally { unlock(); }
}
function readAttempt(dir) {
  let r;
  try { r = boundedRead(path.join(dir, 'result.json')); }
  catch (e) {
    if (e.code !== 'ENOENT') throw e;
    r = boundedRead(path.join(dir, 'attempt.json'));
    r.status = 'incomplete';
    r.checks = r.checks.map((c, i) => {
      try { return boundedRead(path.join(dir, `${String(i + 1).padStart(3, '0')}.result.json`)); }
      catch (e) {
        if (e.code !== 'ENOENT') throw e;
        try {
          const started = boundedRead(path.join(dir, `${String(i + 1).padStart(3, '0')}.started.json`));
          return { ...c, status: Number.isInteger(r.owner_pid) && alive(r.owner_pid) ? 'running' : 'interrupted', child_pid: started.pid, started_at: started.started_at, containment: containmentProof(started.containment) || { state: 'unresolved' } };
        } catch (e) { if (e.code !== 'ENOENT') throw e; return c; }
      }
    });
  }
  return { ...r, total_checks: r.checks.length, check_status_counts: counts(r.checks), checks: r.checks.map((c, i) => ({ ...c, check_index: i })) };
}
export function collectBatch(root, batchId, attemptId = null, limit = 10, outputBytes = 1024, checkIndex = null) {
  if (!ID.test(batchId || '') || (attemptId && !/^attempt-\d+-[a-f0-9]{12}$/.test(attemptId))) throw new Error('invalid batch/attempt identifier');
  const batch = path.join(root, 'checks', batchId);
  const attempts = attemptNames(batch);
  if (attemptId && !attempts.includes(attemptId)) throw new Error('attempt not found');
  const selected = attemptId ? [attemptId] : attempts.slice(-limit);
  const selectedMetadata = new Map(); // at most 20 bounded metadata objects
  const statusCounts = {}, omittedCounts = {}, checkCounts = {};
  let totalChecks = 0, latestStatus = null;
  for (const a of attempts) {
    const stored = readAttempt(path.join(batch, a));
    const status = stored.status;
    if (selected.includes(a)) selectedMetadata.set(a, stored);
    if (a === attempts.at(-1)) latestStatus = status;
    totalChecks += stored.checks.length;
    for (const [key, value] of Object.entries(counts(stored.checks))) checkCounts[key] = (checkCounts[key] || 0) + value;
    statusCounts[status] = (statusCounts[status] || 0) + 1;
    if (!selected.includes(a)) omittedCounts[status] = (omittedCounts[status] || 0) + 1;
  }
  return { schema: 'delegate-task.check-collection.v1', batch_id: batchId, total_attempts: attempts.length, omitted_attempts: attempts.length - selected.length, truncated: attempts.length > selected.length,
    status_counts: statusCounts, omitted_status_counts: omittedCounts,
    status: statusCounts.failed ? 'failed' : statusCounts.incomplete ? 'incomplete' : statusCounts.successful ? 'successful' : null,
    status_provenance: { primary: 'attempt_history' }, latest_attempt_id: attempts.at(-1) || null, latest_status: latestStatus,
    total_checks: totalChecks, check_status_counts: checkCounts,
    selection: { attempt: attemptId, limit: attemptId ? 1 : limit, check_index: checkIndex },
    attempts: selected.map(a => {
      const dir = path.join(batch, a);
      const p = boundedRead(path.join(dir, 'plan.json'));
      let r = selectedMetadata.get(a);
      r = { ...r, checks: r.checks.filter(c => checkIndex === null || c.check_index === checkIndex) };
      if (checkIndex !== null && !r.checks.length) throw new Error('--check-index does not exist in selected attempt');
      return publicAttempt(r, secretValues(p), outputBytes);
    }),
  };
}
async function main(args) {
  let diagnosticsSecrets = secretValues(null);
  try {
  const cmd = args.shift(), opts = {};
  while (args.length) {
    const k = args.shift();
    if (!['--plan', '--batch', '--attempt', '--limit', '--output-bytes', '--max-bytes', '--retry-of', '--cursor', '--check-index'].includes(k) || !args.length) throw new Error('usage: check-runner.mjs run --plan FILE [--retry-of ATTEMPT] [--max-bytes N] | collect --batch ID [--attempt ID] [--limit N] [--output-bytes N] [--max-bytes N] [--cursor TOKEN] [--check-index N]');
    opts[k] = args.shift();
  }
  const root = process.env.DELEGATE_RUNS_DIR;
  if (!root || !path.isAbsolute(root)) throw new Error('DELEGATE_RUNS_DIR must be an explicit absolute ignored artifact directory');
  const maxBytes = validateMaxBytes(Number(opts['--max-bytes'] ?? DEFAULT_MAX_BYTES));
  if (cmd === 'run' && opts['--plan']) {
    if (['--batch', '--attempt', '--limit', '--output-bytes', '--cursor', '--check-index'].some(k => k in opts)) throw new Error('collection flags are not valid for run');
    const plan = boundedRead(opts['--plan']);
    diagnosticsSecrets = secretValues(plan);
    const result = await runBatch(plan, root, { retryOf: opts['--retry-of'] ?? null });
    process.stdout.write(encodeReceipt(result, maxBytes));
    process.exitCode = result.busy ? 3 : result.requires_explicit_retry ? 4 : result.status === 'successful' ? 0 : 1;
  } else if (cmd === 'collect' && opts['--batch']) {
    if ('--retry-of' in opts || '--plan' in opts) throw new Error('execution flags are not valid for collect');
    const limit = Number(opts['--limit'] ?? 10), bytes = Number(opts['--output-bytes'] ?? 1024);
    if (!Number.isInteger(limit) || limit < 1 || limit > 20 || !Number.isInteger(bytes) || bytes < 0 || bytes > 4096) throw new Error('invalid projection limits');
    const checkIndex = opts['--check-index'] === undefined ? null : Number(opts['--check-index']);
    if (checkIndex !== null && (!opts['--attempt'] || !Number.isInteger(checkIndex) || checkIndex < 0 || checkIndex > 99)) throw new Error('--check-index requires --attempt and an integer 0..99');
    process.stdout.write(encodeReceipt(collectBatch(root, opts['--batch'], opts['--attempt'], limit, bytes, checkIndex), maxBytes, opts['--cursor'] || null));
  } else throw new Error('expected run --plan FILE or collect --batch ID');
  } catch (e) {
    // Never print a raw JSON parse error (it may quote a secret from malformed
    // input). Other diagnostics use both explicit and inherited credentials.
    const message = e instanceof SyntaxError ? 'invalid UTF-8 JSON metadata' : e.message;
    console.error(`check-runner: ${redact(message, diagnosticsSecrets)}`);
    process.exitCode = 2;
  }
}
if (process.argv[1] && fs.realpathSync(process.argv[1]) === fs.realpathSync(fileURLToPath(import.meta.url))) {
  await main(process.argv.slice(2));
}
