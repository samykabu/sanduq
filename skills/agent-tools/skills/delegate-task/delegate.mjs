#!/usr/bin/env node
// delegate.mjs - delegate one task to an external agent CLI harness, in the
// background, and return a normalised result.
//
// Behaviour is defined by three contracts in contracts/:
//   status-precedence.md   how a terminal status is decided (and why exit code matters)
//   git-fields.md          what the git baseline measures, and what it cannot see
//   result-schema-v2.md    the result shape, backward read, journal, single-writer rule
//
// Harnesses spawn with shell:false (resolved to a real .exe or node+script), so
// task text never reaches a shell.

import { spawn, spawnSync, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
import { StringDecoder } from 'node:string_decoder';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RUNS = process.env.DELEGATE_RUNS_DIR || path.join(HERE, 'runs');
const WIN = process.platform === 'win32';

const SCHEMA = 'delegate-task.result.v2';
const VERSION_PROBE_MS = 10_000;
const GIT_PROBE_MS = 10_000;
const START_ACK_MS = 15_000;
const HEARTBEAT_MS = 5_000;
const STALE_MS = 60_000;          // no heartbeat this long => the supervisor is gone
const CLAIM_STALE_MS = 30_000;    // a finalisation claim older than this may be stolen
const ABORT_GRACE_MS = 3_000;     // how long a signal handler waits for the child to die
// Declared after positiveIntEnv below; see MAX_LOG_BYTES.
const MAX_LINE_CHARS = 1_000_000;
const STATUSES = new Set(['successful', 'failed', 'abandoned']);

// An unparseable cap must not silently mean "unlimited": NaN fails every
// comparison, so `written > NaN` is always false and nothing is ever capped.
function positiveIntEnv(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined) return fallback;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) {
    console.error(`delegate: ${name}="${raw}" is not a positive whole number; using ${fallback}`);
    return fallback;
  }
  return Math.floor(n);
}
const MAX_LOG_BYTES = positiveIntEnv('DELEGATE_MAX_LOG_BYTES', 32 * 1024 * 1024);
const LOG_TAIL_BYTES = positiveIntEnv('DELEGATE_LOG_TAIL_BYTES', 512 * 1024);

/* ---------- executable resolution ---------- */

function which(name) {
  const exts = WIN
    ? (process.env.PATHEXT || '.COM;.EXE;.BAT;.CMD').split(';').map((e) => e.trim().toLowerCase()).filter(Boolean).concat([''])
    : [''];
  for (const d of (process.env.PATH || process.env.Path || '').split(path.delimiter).filter(Boolean)) {
    const dir = d.replace(/^"(.*)"$/, '$1');
    for (const e of exts) {
      const p = path.join(dir, name + e);
      try { if (fs.statSync(p).isFile()) return p; } catch { /* keep looking */ }
    }
  }
  return null;
}

// npm's Windows .cmd shims can't be spawned without a shell. Read the shim and
// point at what it actually launches. A shim we cannot decode is 'undecodable',
// not 'missing' - the binary is right there, and "not found on PATH" would send
// the operator off to reinstall something already installed.
//
// DELEGATE_BIN_<HARNESS> overrides the lookup with an explicit path. That serves
// an install outside PATH, and it is what lets the suite drive a fake harness
// end to end through start/collect.
function resolveBin(name, harnessId) {
  const override = harnessId ? process.env[`DELEGATE_BIN_${harnessId.toUpperCase()}`] : undefined;
  if (override) {
    if (!fs.existsSync(override)) return { state: 'missing', file: null, args: [], path: override };
    return override.toLowerCase().endsWith('.js') || override.toLowerCase().endsWith('.mjs')
      ? { state: 'ok', file: process.execPath, args: [override], path: override }
      : { state: 'ok', file: override, args: [], path: override };
  }
  const p = which(name);
  if (!p) return { state: 'missing', file: null, args: [], path: null };
  const low = p.toLowerCase();
  if (!low.endsWith('.cmd') && !low.endsWith('.bat')) return { state: 'ok', file: p, args: [], path: p };
  let txt;
  try { txt = fs.readFileSync(p, 'utf8'); } catch { return { state: 'undecodable', file: null, args: [], path: p }; }
  // Anchor on node_modules so the shim's own `IF EXIST "%dp0%\node.exe"` misses.
  const m = txt.match(/"%dp0%\\((?:node_modules|\.\.)[^"]*\.(exe|js))"/i);
  if (!m) return { state: 'undecodable', file: null, args: [], path: p };
  const target = path.join(path.dirname(p), m[1]);
  if (!fs.existsSync(target)) return { state: 'undecodable', file: null, args: [], path: p };
  return target.toLowerCase().endsWith('.js')
    ? { state: 'ok', file: process.execPath, args: [target], path: p }
    : { state: 'ok', file: target, args: [], path: p };
}

/* ---------- bounded exec ---------- */

function boundedExec(file, args, { cwd, timeout, env } = {}) {
  try {
    const out = execFileSync(file, args, {
      cwd, encoding: 'utf8', timeout: timeout || VERSION_PROBE_MS,
      killSignal: 'SIGKILL', stdio: ['ignore', 'pipe', 'pipe'],
      maxBuffer: 64 * 1024 * 1024, env: env || process.env, windowsHide: true,
    });
    return { ok: true, out: out || '', err: null };
  } catch (e) {
    return { ok: false, out: String(e.stdout || ''), err: e };
  }
}

/* ---------- git baseline (contract 3b) ---------- */

const GIT_UNKNOWN = {
  git_visible_after: null, dirty_paths_changed: null,
  head_changed: null, index_changed: null, coverage_complete: false,
};

function git(cwd, args) {
  const r = boundedExec('git', ['-C', cwd, ...args], { timeout: GIT_PROBE_MS });
  return r.ok ? r.out : null;
}

// `git status --porcelain=v1 -z`: NUL-separated records; a rename/copy record is
// followed by an extra NUL-separated origin path, which must be consumed.
function parsePorcelainZ(raw) {
  if (raw == null) return null;
  const parts = raw.split('\0');
  const out = [];
  for (let i = 0; i < parts.length; i++) {
    const rec = parts[i];
    if (!rec) continue;
    const xy = rec.slice(0, 2);
    const p = rec.slice(3);
    let orig = null;
    if (xy[0] === 'R' || xy[0] === 'C') { orig = parts[++i] ?? null; }
    out.push({ xy, path: p, orig });
  }
  return out;
}

const porcelainKey = (r) => `${r.xy} ${r.path}${r.orig ? ` <- ${r.orig}` : ''}`;

// A path we cannot hash is not covered, and saying so is the whole point of the
// coverage flag. A directory in the dirty set is a submodule or an unreadable
// tree: its porcelain line never changes when its contents do, so treating it as
// covered would manufacture exactly the false assurance this design forbids.
function fingerprintPaths(root, paths) {
  const prints = new Map();
  let complete = true;
  for (const rel of paths) {
    const abs = path.join(root, rel);
    let file;
    try {
      const st = fs.lstatSync(abs);
      if (st.isSymbolicLink()) {
        file = `link:${crypto.createHash('sha256').update(fs.readlinkSync(abs)).digest('hex')}`;
      } else if (st.isDirectory()) {
        file = 'DIR-UNCOVERED';
        complete = false;
      } else if (!st.isFile()) {
        file = 'SPECIAL-UNCOVERED';
        complete = false;
      } else {
        file = crypto.createHash('sha256').update(fs.readFileSync(abs)).digest('hex');
      }
    } catch (e) {
      if (e && e.code === 'ENOENT') { file = 'ABSENT'; }
      else { file = 'UNREADABLE'; complete = false; }
    }
    const idx = git(root, ['ls-files', '-s', '-z', '--', rel]);
    prints.set(rel, { file, index: idx == null ? null : idx });
  }
  return { prints, complete };
}

// A path is not an identity: `.git` can be replaced or re-initialised in place,
// and comparing root strings would call two unrelated repositories the same one.
function repoIdentity(cwd, head) {
  const gitDir = (git(cwd, ['rev-parse', '--absolute-git-dir']) || '').trim();
  if (!gitDir) return null;
  const roots = head ? (git(cwd, ['rev-list', '--max-parents=0', 'HEAD']) || '').trim() : '';
  const rootCommit = roots ? roots.split(/\r?\n/).filter(Boolean).pop() : null;
  // Two parts, compared differently: the git-dir is stable for the life of a
  // repository, while the root commit only exists once there IS one. A first
  // commit legitimately adds a root commit to the same repository, so it must
  // not read as a different one.
  return { gitDir: path.resolve(gitDir), rootCommit };
}

// true = same repository, false = definitely different, null = cannot tell.
// An unborn repository has no objects at all, so a path whose `.git` was moved
// away and re-initialised is indistinguishable from the original. That is
// reported as unknown rather than certified as the same one.
function sameRepository(a, b) {
  if (!a || !b) return null;
  if (a.gitDir !== b.gitDir) return false;
  if (a.rootCommit && b.rootCommit) return a.rootCommit === b.rootCommit;
  if (!a.rootCommit && b.rootCommit) return true;   // the first commit: same repo, now non-empty
  if (!a.rootCommit && !b.rootCommit) return null;   // both unborn: unidentifiable
  return false;                                      // had history, now has none
}

const repoIdString = (id) => (id ? `${id.gitDir}|${id.rootCommit || 'unborn'}` : null);

function parseRepoId(s) {
  if (!s) return null;
  const i = s.lastIndexOf('|');
  if (i < 0) return { gitDir: s, rootCommit: null };
  const rc = s.slice(i + 1);
  return { gitDir: s.slice(0, i), rootCommit: rc === 'unborn' ? null : rc };
}

function gitCapture(cwd) {
  const root = (git(cwd, ['rev-parse', '--show-toplevel']) || '').trim();
  if (!root) return { root: null, id: null, head: null, index: null, porcelain: null, prints: new Map(), complete: false, unborn: false };
  const headRaw = git(cwd, ['rev-parse', 'HEAD']);
  const head = headRaw === null ? null : (headRaw.trim() || null);
  // An initialised repository with no commit yet: HEAD is unborn, which is a
  // KNOWN state, not an unknown one. Conflating the two hides a first commit.
  const unborn = head === null && git(cwd, ['rev-parse', '--is-inside-work-tree']) !== null;
  const indexRaw = git(cwd, ['diff', '--cached', '--raw', '-z']);
  const index = indexRaw == null ? null : crypto.createHash('sha256').update(indexRaw).digest('hex');
  const porcelain = parsePorcelainZ(
    git(cwd, ['-c', 'status.relativePaths=false', 'status', '--porcelain=v1', '-z']),
  );
  const id = repoIdentity(cwd, head);
  if (porcelain == null) return { root, id, head, index, porcelain: null, prints: new Map(), complete: false, unborn };
  const fp = fingerprintPaths(root, porcelain.map((r) => r.path));
  return { root, id, head, index, porcelain, prints: fp.prints, complete: fp.complete, unborn };
}

function headMovement(before, after) {
  if (before.unborn && after.head) return true;          // the first commit
  if (before.head && after.head) return before.head !== after.head;
  if (before.unborn && after.unborn) return false;        // still no commits
  return null;                                            // genuinely unknown
}

function gitCompare(before, cwd) {
  if (!before || !before.root || before.porcelain == null) return { ...GIT_UNKNOWN };
  const after = gitCapture(cwd);
  if (!after.root || after.porcelain == null) return { ...GIT_UNKNOWN };
  // If the path now resolves to a DIFFERENT repository, the two snapshots are
  // not comparable and anything derived from them would be fiction. Compare
  // identity, not the root path - `.git` can be replaced in place.
  const same = sameRepository(before.id, after.id);
  if (path.resolve(after.root) !== path.resolve(before.root) || same === false) {
    return { ...GIT_UNKNOWN, git_visible_after: after.porcelain.map(porcelainKey) };
  }
  // same === null: the path still looks like the same repository but we cannot
  // prove it (both ends unborn). Compare anyway - the porcelain and fingerprints
  // are still the best evidence available - but never call the coverage complete.
  const identityKnown = same === true;
  const beforeKeys = new Set(before.porcelain.map(porcelainKey));
  const afterKeys = new Set(after.porcelain.map(porcelainKey));
  const changed = new Set();
  for (const r of after.porcelain) if (!beforeKeys.has(porcelainKey(r))) changed.add(r.path);
  for (const r of before.porcelain) if (!afterKeys.has(porcelainKey(r))) changed.add(r.path);
  // Re-fingerprint exactly the baseline paths: an edit to a file that was already
  // dirty never changes its porcelain line, so only content catches it.
  const re = fingerprintPaths(before.root, [...before.prints.keys()]);
  for (const [rel, print] of before.prints) {
    const now = re.prints.get(rel);
    if (!now) continue;
    const known = !String(print.file).endsWith('UNCOVERED') && print.file !== 'UNREADABLE'
      && !String(now.file).endsWith('UNCOVERED') && now.file !== 'UNREADABLE';
    if (known && now.file !== print.file) changed.add(rel);
    if (print.index !== null && now.index !== null && print.index !== now.index) changed.add(rel);
  }
  return {
    git_visible_after: after.porcelain.map(porcelainKey),
    dirty_paths_changed: [...changed].sort(),
    head_changed: headMovement(before, after),
    index_changed: before.index !== null && after.index !== null ? before.index !== after.index : null,
    coverage_complete: before.complete && after.complete && re.complete && identityKnown,
  };
}

// Three-valued on purpose. Proof of a write settles it even when coverage is
// partial; only when nothing is proven AND coverage is incomplete is the answer
// genuinely unknown. Collapsing that last case to false is the false assurance a
// tripwire must never give.
function readOnlyVerdict(g) {
  if (g.dirty_paths_changed === null) return null;
  if (g.dirty_paths_changed.length > 0 || g.head_changed === true || g.index_changed === true) return true;
  if (!g.coverage_complete) return null;
  return false;
}

// Compare the delegate's claim against the DETECTED DELTA only - never against
// git_visible_after, which contains baseline dirt and would turn a pre-existing
// dirty file into an accusation that the delegate lied.
function claimMismatch(claimed, delta, coverageComplete) {
  if (!coverageComplete || delta === null || claimed == null) return null;
  // The envelope asks for a comma-separated list, and git permits commas in
  // filenames. When the delta contains one the grammar is ambiguous, so the
  // honest answer is "cannot tell", not a false accusation.
  if (delta.some((p) => p.includes(','))) return null;
  const norm = (s) => String(s).trim().replace(/^"(.*)"$/, '$1').replace(/\\/g, '/').replace(/^\.\//, '');
  const claimSet = new Set(
    String(claimed).split(',').map(norm).filter((s) => s && s.toLowerCase() !== 'none'),
  );
  const deltaSet = new Set(delta.map(norm));
  if (claimSet.size !== deltaSet.size) return true;
  for (const c of claimSet) if (!deltaSet.has(c)) return true;
  return false;
}

/* ---------- task envelope ---------- */

const BEGIN = '<' + '<<DELEGATION_RESULT>>' + '>';
const END = '<' + '<<END_DELEGATION_RESULT>>' + '>';
const RESULT_RE = new RegExp(BEGIN + '([\\s\\S]*?)' + END);

// Policy, not enforcement. The runner cannot stop a bypassed delegate from doing
// any of this; it can only measure afterwards (see contracts/git-fields.md).
function policyLines({ allowCommit, extra }) {
  const rules = [
    'Complete the objective end to end. Do not stop to ask for confirmation.',
    'Stay inside the working directory unless the objective says otherwise.',
    allowCommit
      ? 'You may commit, but only work you have verified.'
      : 'Do NOT run `git add` or `git commit`. Leave your changes in the working tree; the operator reviews and commits.',
    "If the project has test, lint or build commands, run them and fix what they surface - don't just report it.",
    'If you cannot finish, stop and report status "abandoned" with the reason.',
    ...(extra || []),
  ];
  return rules.map((r) => `- ${r}`).join('\n');
}

function resultBlockSpec() {
  return `Your final message MUST end with this block, exactly once, markers verbatim:

${BEGIN}
status: successful | failed | abandoned
summary: <2-4 sentences on what you actually did, in past tense>
files_changed: <comma-separated paths, or none>
${END}

Use "successful" only if the objective is fully met. Use "failed" if you
attempted it and it did not work. Use "abandoned" if you stopped early -
blocked, out of scope, missing credentials, or ran out of room.`;
}

function envelope({ task, cwd, deliverable, constraints, allowCommit }) {
  return `# Delegated task

You are executing a single task on behalf of another agent. You cannot ask
questions while this run is in progress, so make reasonable assumptions and say
what you assumed. A follow-up turn may continue this same session, so leave your
reasoning where the next turn can pick it up.

## Objective
${task}

## Working directory
${cwd}

## Constraints
${policyLines({ allowCommit, extra: constraints })}

## Deliverable
${deliverable || 'Apply the change directly in the working tree, then report what you did.'}

## Required final output
${resultBlockSpec()}`;
}

// A resumed dispatch repeats every non-negotiable rule AND the parent's original
// constraints and deliverable. A parent session may be stale or adversarial, and
// policy is not inherited - it is restated. Dropping the parent's scope
// exclusions here would be the exact failure Amendment 4 exists to prevent.
function deltaEnvelope({ task, cwd, deliverable, constraints, allowCommit, parent }) {
  return `# Delegated task - continuation

You are continuing the session you ran earlier (delegate run ${parent}). Apply only
the change below. Everything you already did stands unless this contradicts it.

## Objective
${task}

## Working directory
${cwd}

## Constraints (these apply to this turn too - they are not inherited, they are restated)
${policyLines({ allowCommit, extra: constraints })}

## Deliverable
${deliverable || 'Apply the change directly in the working tree, then report what you did.'}

## Required final output
${resultBlockSpec()}`;
}

function parseEnvelope(text) {
  if (!text) return null;
  const m = String(text).match(RESULT_RE);
  if (!m) return null;
  const out = {};
  for (const line of m[1].split(/\r?\n/)) {
    const kv = line.match(/^\s*(status|summary|files_changed)\s*:\s*(.*)$/i);
    if (kv && !(kv[1].toLowerCase() in out)) out[kv[1].toLowerCase()] = kv[2].trim();
  }
  if (out.status) {
    const s = out.status.toLowerCase().replace(/[^a-z]/g, '');
    out.status = STATUSES.has(s) ? s : null;
  }
  if (out.files_changed != null) {
    const v = out.files_changed.trim();
    out.files_changed = (!v || v.toLowerCase() === 'none') ? null : v;
  }
  return Object.keys(out).length ? out : null;
}

/* ---------- token normalisation ---------- */

function tokens(o = {}) {
  const n = (v) => (Number.isFinite(v) ? v : 0);
  const t = {
    input_total: n(o.input_total), input_fresh: n(o.input_fresh),
    cache_read: n(o.cache_read), cache_write: n(o.cache_write),
    output_total: n(o.output_total), reasoning: n(o.reasoning),
    fidelity: o.fidelity || 'exact',
  };
  t.total = t.input_total + t.output_total;
  return t;
}

const hasUsage = (u) => Boolean(u && typeof u === 'object' && Object.keys(u).length > 0);

// A bounded window of the most recent complete records.
//
// Extracted so the eviction policy can be tested directly rather than only
// through end-to-end side effects - three separate mutations of an inlined
// version survived a full suite because their damage was invisible from outside.
//
// The budget is counted in BYTES, not JavaScript characters: a UTF-16 length
// under-measures multibyte telemetry by up to 3x, so a "512 KB" window would
// silently hold far more.
export function makeRetention(limitBytes) {
  let lines = [];
  let head = 0;
  let bytes = 0;
  let dropped = 0;
  return {
    add(line) {
      lines.push(line);
      bytes += Buffer.byteLength(line, 'utf8') + 1;
      // One record is always kept, even if it alone exceeds the budget: the last
      // record is usually the terminal event, and dropping it to honour a byte
      // bound would defeat the purpose of retaining anything at all.
      while (bytes > limitBytes && lines.length - head > 1) {
        bytes -= Buffer.byteLength(lines[head], 'utf8') + 1;
        lines[head] = null;
        head++;
        dropped++;
      }
      // Compact, or the backing array keeps every evicted slot alive for the
      // life of a high-volume run.
      if (head > 1024) { lines = lines.slice(head); head = 0; }
    },
    lines: () => lines.slice(head).filter((l) => l !== null),
    reset() { lines = []; head = 0; bytes = 0; },
    get dropped() { return dropped; },
    set dropped(v) { dropped = v; },
    // Test seams: the backing array must stay bounded, and the byte accounting
    // must be observable without inferring it from an end-to-end result.
    _size: () => lines.length,
    _bytes: () => bytes,
  };
}

const jsonl = (text) => {
  const out = [];
  for (const line of String(text).split(/\r?\n/)) {
    const s = line.trim();
    if (s.startsWith('{')) { try { out.push(JSON.parse(s)); } catch { /* partial line */ } }
  }
  return out;
};

/* ---------- harness adapters ---------- */
// readOnly describes what --sandbox actually requests of that CLI:
//   enforced        the CLI sandboxes the filesystem itself
//   plan            a documented read-only/plan mode
//   tools-allowlist only read-shaped tools are exposed
// session_capture:  streaming (id appears mid-run) | terminal (only at the end)
//
// Every adapter must report complete:false when no TERMINAL event arrived. A
// stream that stops mid-run is abandoned, not successful - see gotcha 1 and its
// mirror image, which this refactor exists to fix.

const HARNESSES = {
  claude: {
    bin: 'claude', label: 'Claude Code', tier: 'verified',
    readOnly: 'plan', resume: 'verified', session_capture: 'terminal',
    reports: { cost: true, model: true },
    versionArgs: ['--version'],
    args: ({ task, model, perm, resume }) => [
      '-p', task, '--output-format', 'json',
      ...(model ? ['--model', model] : []),
      ...(resume ? ['--resume', resume] : []),
      ...(perm === 'bypass' ? ['--dangerously-skip-permissions'] : ['--permission-mode', 'plan']),
    ],
    mode: (perm) => (perm === 'bypass' ? '--dangerously-skip-permissions' : '--permission-mode plan'),
    session: (e) => e.session_id ?? e.sessionId ?? (e.session && (e.session.id ?? e.session.session_id)) ?? null,
    parse: (out) => {
      const ev = jsonl(out);
      // A terminal record, not merely "the last JSON object on stdout": any
      // stray object would otherwise be read as a complete successful run.
      // Strictly the terminal record. `is_error` and `subtype` also appear on
      // other objects, so accepting them as discriminators let an arbitrary
      // JSON line read as a complete, successful run.
      const r = ev.filter((e) => e.type === 'result').pop();
      if (!r) {
        return {
          status: 'abandoned', reason: 'no result record on stdout', complete: false,
          text: '', usage_raw: null, tokens: tokens({ fidelity: 'unavailable' }),
        };
      }
      const u = r.usage || {};
      const fresh = u.input_tokens || 0;
      const cw = u.cache_creation_input_tokens || 0;
      const cr = u.cache_read_input_tokens || 0;
      let status = 'successful', reason = '';
      if (r.subtype === 'error_max_turns') { status = 'abandoned'; reason = 'hit max turns'; }
      else if (r.is_error || (r.subtype && r.subtype !== 'success')) {
        status = 'failed'; reason = r.api_error_status || r.subtype || 'error';
      }
      return {
        status, reason, complete: true, text: r.result || '',
        model: Object.keys(r.modelUsage || {})[0] || null,
        cost_usd: typeof r.total_cost_usd === 'number' ? r.total_cost_usd : null,
        session: r.session_id || null,
        usage_raw: hasUsage(u) ? u : null,
        // Claude's three input fields are DISJOINT - sum them for the true total.
        tokens: tokens({
          input_total: fresh + cw + cr, input_fresh: fresh, cache_read: cr, cache_write: cw,
          output_total: u.output_tokens || 0,
          reasoning: (u.output_tokens_details && u.output_tokens_details.thinking_tokens) || 0,
          fidelity: hasUsage(u) ? 'exact' : 'unavailable',
        }),
      };
    },
  },

  codex: {
    bin: 'codex', label: 'OpenAI Codex', tier: 'verified',
    readOnly: 'enforced', resume: 'verified', session_capture: 'streaming',
    // codex's JSONL carries neither a cost nor a model field anywhere.
    reports: { cost: false, model: false },
    versionArgs: ['--version'],
    args: ({ task, model, perm, resume }) => [
      'exec',
      ...(resume ? ['resume', resume] : []),
      '--json', '--skip-git-repo-check',
      ...(model ? ['-m', model] : []),
      ...(perm === 'bypass' ? ['--dangerously-bypass-approvals-and-sandbox'] : ['-s', 'read-only']),
      task,
    ],
    mode: (perm) => (perm === 'bypass' ? '--dangerously-bypass-approvals-and-sandbox' : '-s read-only'),
    session: (e) => e.thread_id ?? e.threadId ?? (e.thread && (e.thread.thread_id ?? e.thread.id)) ?? null,
    parse: (out) => {
      const ev = jsonl(out);
      // usage on turn.completed is cumulative for the session - take the last.
      const done = ev.filter((e) => e.type === 'turn.completed').pop();
      const failed = ev.filter((e) => e.type === 'turn.failed').pop();
      const msg = ev.filter((e) => e.item && e.item.type === 'agent_message').pop();
      const u = (done && done.usage) || {};
      const inTotal = u.input_tokens || 0;
      const cr = u.cached_input_tokens || 0;
      let status = 'successful', reason = '';
      if (failed) { status = 'failed'; reason = (failed.error && failed.error.message) || 'turn.failed'; }
      else if (!done) { status = 'abandoned'; reason = 'no turn.completed event'; }
      return {
        status, reason, complete: Boolean(done || failed),
        text: (msg && msg.item.text) || '', model: null, cost_usd: null,
        usage_raw: hasUsage(u) ? u : null,
        // Codex input_tokens INCLUDES cached_input_tokens - subtract for fresh.
        tokens: tokens({
          input_total: inTotal, input_fresh: Math.max(0, inTotal - cr),
          cache_read: cr, cache_write: u.cache_write_input_tokens || 0,
          output_total: u.output_tokens || 0, reasoning: u.reasoning_output_tokens || 0,
          fidelity: hasUsage(u) ? 'exact' : 'unavailable',
        }),
      };
    },
  },

  opencode: {
    bin: 'opencode', label: 'OpenCode', tier: 'verified',
    readOnly: 'plan', resume: 'verified', session_capture: 'streaming',
    reports: { cost: true, model: false },
    versionArgs: ['--version'],
    args: ({ task, model, perm, resume }) => [
      'run', '--format', 'json',
      ...(resume ? ['--session', resume] : []),
      ...(model ? ['-m', model] : []),
      // --auto auto-approves so a headless run doesn't block on a prompt nobody
      // can answer. Never on the plan agent: it would approve the very asks that
      // make plan mode read-only.
      ...(perm === 'bypass' ? ['--auto'] : ['--agent', 'plan']),
      task,
    ],
    mode: (perm) => (perm === 'bypass' ? '--auto (build)' : '--agent plan'),
    session: (e) => e.sessionID ?? e.session_id ?? null,
    parse: (out) => {
      const ev = jsonl(out);
      // One step_finish PER STEP - these must be summed, not last-wins.
      const steps = ev.filter((e) => e.type === 'step_finish');
      const acc = { i: 0, o: 0, r: 0, cr: 0, cw: 0, cost: 0 };
      let sawTokens = false;
      for (const s of steps) {
        const t = (s.part && s.part.tokens) || {};
        if (hasUsage(t)) sawTokens = true;
        acc.i += t.input || 0; acc.o += t.output || 0; acc.r += t.reasoning || 0;
        acc.cr += (t.cache && t.cache.read) || 0; acc.cw += (t.cache && t.cache.write) || 0;
        acc.cost += (s.part && s.part.cost) || 0;
      }
      const text = ev.filter((e) => e.type === 'text').map((e) => (e.part && e.part.text) || '').join('');
      const last = steps.length ? steps[steps.length - 1].part.reason : null;
      // A `step_finish` is emitted per step, INCLUDING intermediate tool steps.
      // Treating any of them as terminal turned a stream cut mid-run into a
      // published verdict - the exact false-success class this driver exists to
      // prevent. Only a terminal reason ends a turn.
      const TERMINAL = new Set(['stop', 'length', 'error', 'aborted', 'cancelled']);
      const terminal = last !== null && TERMINAL.has(last);
      let status = 'successful', reason = last && last !== 'stop' ? last : '';
      if (!steps.length) { status = 'abandoned'; reason = 'no step_finish event'; }
      else if (!terminal) { status = 'abandoned'; reason = `stream ended after a non-terminal step (reason: ${last})`; }
      else if (last !== 'stop') { status = last === 'length' ? 'abandoned' : 'failed'; }
      return {
        status, reason, complete: terminal, text, model: null,
        cost_usd: acc.cost || null,
        usage_raw: steps.length ? { steps: steps.length, summed: acc } : null,
        tokens: tokens({
          input_total: acc.i + acc.cr + acc.cw, input_fresh: acc.i,
          cache_read: acc.cr, cache_write: acc.cw,
          output_total: acc.o, reasoning: acc.r,
          fidelity: sawTokens ? 'exact' : 'unavailable',
        }),
      };
    },
  },

  copilot: {
    bin: 'copilot', label: 'GitHub Copilot CLI', tier: 'experimental',
    readOnly: 'plan', resume: 'experimental', session_capture: 'terminal',
    reports: { cost: false, model: false },
    note: 'reports premium-request counts, never token counts',
    versionArgs: ['--version'],
    args: ({ task, model, perm, resume }) => [
      '-p', task, '--output-format', 'json', '--no-color', '--log-level', 'none',
      ...(model ? ['--model', model] : []),
      ...(resume ? [`--resume=${resume}`] : []),
      ...(perm === 'bypass' ? ['--allow-all-tools'] : ['--mode', 'plan']),
    ],
    mode: (perm) => (perm === 'bypass' ? '--allow-all-tools' : '--mode plan'),
    session: (e) => (e.type === 'result' ? (e.sessionId || null) : null),
    parse: (out) => {
      const ev = jsonl(out);
      const res = ev.filter((e) => e.type === 'result').pop();
      const err = ev.filter((e) => e.type === 'session.error').pop();
      const text = ev.filter((e) => e.type === 'assistant.message')
        .map((e) => (e.data && (e.data.text || e.data.content)) || '').join('\n');
      if (!res && !err) {
        return {
          status: 'abandoned', reason: 'no result event', complete: false,
          text, usage_raw: null, tokens: tokens({ fidelity: 'unavailable' }),
        };
      }
      let status = res && res.exitCode === 0 ? 'successful' : 'failed';
      let reason = '';
      if (err) {
        reason = (err.data && (err.data.message || err.data.errorType)) || 'session error';
        status = (err.data && err.data.errorType) === 'quota' ? 'abandoned' : 'failed';
      }
      return {
        status, reason, complete: true, text, model: null, cost_usd: null,
        session: (res && res.sessionId) || null,
        usage_raw: (res && res.usage) || null,
        // No token fields exist anywhere in Copilot's event stream.
        tokens: tokens({ fidelity: 'unavailable' }),
      };
    },
  },

  pi: {
    bin: 'pi', label: 'Pi', tier: 'experimental',
    readOnly: 'tools-allowlist', resume: 'experimental', session_capture: 'streaming',
    reports: { cost: false, model: false },
    note: 'auth is file-based in ~/.pi/agent/auth.json; sessions persist under ~/.pi/agent/sessions/<cwd-slug>/',
    versionArgs: ['--version'],
    // --no-session is deliberately NOT passed: without a session there is nothing
    // to resume. Pi therefore writes a session into its own store, which this
    // driver's `prune` does not clean. See SKILL.md.
    args: ({ task, model, perm, resume }) => [
      '--print', '--mode', 'json',
      ...(model ? ['--model', model] : []),
      ...(resume ? ['--session', resume] : []),
      ...(perm === 'bypass' ? ['--approve'] : ['--no-approve', '--tools', 'read,grep,find,ls']),
      task,
    ],
    mode: (perm) => (perm === 'bypass' ? '--approve' : '--no-approve --tools read,grep,find,ls'),
    session: (e) => (e.type === 'session' && typeof e.id === 'string' ? e.id : null),
    parse: (out, err) => {
      const ev = jsonl(out);
      // A terminal assistant turn, not "any object that happens to carry usage":
      // an intermediate message_start would otherwise turn a truncated stream
      // into a successful run.
      const terminal = ev.filter((e) => e.type === 'message_end' || e.type === 'result').pop();
      const text = ev.filter((e) => e.type === 'assistant' || e.type === 'text' || e.type === 'message_end')
        .map((e) => {
          if (typeof e.text === 'string') return e.text;
          const c = (e.message && e.message.content) ?? e.content;
          if (typeof c === 'string') return c;
          if (Array.isArray(c)) return c.map((x) => (x && x.text) || '').join('');
          return '';
        }).join('');
      if (!terminal) {
        const firstErr = String(err || '').split(/\r?\n/).find((l) => l.trim());
        return {
          status: 'abandoned', reason: firstErr || 'no message_end event', complete: false,
          text, usage_raw: null, tokens: tokens({ fidelity: 'unavailable' }),
        };
      }
      const usage = ev.map((e) => e.usage || e.tokens || (e.message && e.message.usage))
        .filter(Boolean).pop() || {};
      const fresh = usage.input_tokens != null ? usage.input_tokens : (usage.input || 0);
      const cr = usage.cache_read_input_tokens || usage.cacheRead || 0;
      const cw = usage.cache_creation_input_tokens || usage.cacheWrite || 0;
      const known = hasUsage(usage);
      const stopped = terminal.message && terminal.message.stopReason;
      return {
        status: stopped && stopped === 'error' ? 'failed' : 'successful',
        reason: stopped && stopped === 'error' ? 'assistant stopReason: error' : '',
        complete: true, text, model: null, cost_usd: null,
        usage_raw: known ? usage : null,
        tokens: tokens({
          input_total: fresh + cr + cw, input_fresh: fresh, cache_read: cr, cache_write: cw,
          output_total: usage.output_tokens != null ? usage.output_tokens : (usage.output || 0),
          reasoning: usage.reasoning || 0,
          fidelity: known ? 'partial' : 'unavailable',
        }),
      };
    },
  },
};

/* ---------- status precedence (contract 3a) ---------- */

export function resolveStatus({
  timedOut, spawnError, signal, exitCode, parse, self,
  headMoved, indexMoved, allowCommit,
}) {
  // Every true observation is recorded, matched or not: a timeout that happened
  // AFTER success telemetry must keep both facts, and an integrity signal must
  // never vanish because an earlier rule won.
  const ev = [];
  if (timedOut) ev.push('watchdog fired');
  if (spawnError) ev.push(`spawn error: ${spawnError}`);
  ev.push(`harness telemetry: ${parse ? parse.status : 'none'}${parse && parse.reason ? ` (${parse.reason})` : ''}`);
  ev.push(`exit_code: ${exitCode === null || exitCode === undefined ? 'null' : exitCode}`);
  ev.push(`signal: ${signal || 'none'}`);
  ev.push(`self_report: ${self && self.status ? self.status : 'absent'}`);
  if (parse && parse.complete === false) ev.push('telemetry: incomplete (no terminal event)');
  if (parse && parse.parseError) ev.push('adapter threw while parsing');
  if (headMoved === true) ev.push(`HEAD moved during the run window${allowCommit ? ' (--allow-commit)' : ''}`);
  if (indexMoved === true) ev.push(`the staged set changed during the run window${allowCommit ? ' (--allow-commit)' : ''}`);

  const done = (status, primary, reason) => ({
    status, reason: reason || '', provenance: { primary, evidence: ev },
  });

  if (timedOut) return done('abandoned', 'timeout', 'timed out');
  if (spawnError) return done('failed', 'spawn_error', spawnError);
  if (signal) return done('failed', 'signal', `killed by ${signal}`);
  // Rule 4 - the D1 repair. Before this, exit code was passed to every adapter
  // and read by none, so a success-shaped event plus exit 1 published successful.
  if (Number.isInteger(exitCode) && exitCode !== 0) {
    return done('failed', 'exit_code', `harness exited ${exitCode}`);
  }
  if (parse && parse.parseError) return done('failed', 'parse_error', parse.reason);
  if (parse && parse.complete === false) {
    return done('abandoned', 'telemetry_incomplete', parse.reason || 'incomplete telemetry');
  }
  // The ladder must be TOTAL: an adapter that returns something outside the
  // three-status vocabulary is a defect in the adapter, not a new status.
  if (!parse || !STATUSES.has(parse.status)) {
    return done('failed', 'parse_error',
      `adapter returned an invalid status: ${JSON.stringify(parse ? parse.status : undefined)}`);
  }
  if (parse.status !== 'successful') return done(parse.status, 'harness_telemetry', parse.reason);
  if (self && self.status && self.status !== 'successful') {
    return done(self.status, 'self_report', 'self-reported by delegate');
  }
  if (!allowCommit && (headMoved === true || indexMoved === true)) {
    const what = headMoved === true ? 'HEAD moved' : 'the staged set changed';
    return done('failed', headMoved === true ? 'head_moved' : 'index_moved',
      `${what} during the run window - review required (pass --allow-commit if this was expected)`);
  }
  return done('successful', 'harness_telemetry', '');
}

/* ---------- run state, journal, single-writer ---------- */

// Run ids come from the command line. Without validation, `status ../elsewhere`
// resolves outside RUNS and reads - or finalises, or launches from - a directory
// the operator never pointed us at.
const RUN_ID_RE = /^[a-z][a-z0-9]*-\d{14}-[0-9a-f]{6}$/;

function runDir(id) {
  if (typeof id !== 'string' || !RUN_ID_RE.test(id)) {
    die(`invalid run id "${id}" (expected <harness>-<timestamp>-<hex>)`);
  }
  const dir = path.join(RUNS, id);
  // Belt and braces: even a grammar-passing id must land directly under RUNS.
  if (path.dirname(path.resolve(dir)) !== path.resolve(RUNS)) {
    die(`run id "${id}" does not resolve inside the runs directory`);
  }
  return dir;
}
const readJson = (p) => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return null; } };

function writeJson(p, o) {
  const tmp = `${p}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(o, null, 2));
  fs.renameSync(tmp, p);
}

function journal(dir, obj) {
  try {
    fs.appendFileSync(path.join(dir, 'journal.jsonl'),
      `${JSON.stringify({ t: new Date().toISOString(), ...obj })}\n`, 'utf8');
  } catch { /* a journal write must never take the run down */ }
}

function readJournal(dir) {
  try {
    return fs.readFileSync(path.join(dir, 'journal.jsonl'), 'utf8')
      .split(/\r?\n/).filter((l) => l.trim().startsWith('{'))
      .map((l) => { try { return JSON.parse(l); } catch { return null; } })
      .filter(Boolean);
  } catch { return []; }
}

// Single-writer rule with recovery. A claim records its owner; a claim whose
// owner is dead, or which is older than CLAIM_STALE_MS, is stolen rather than
// bricking the run forever. Returns null ONLY when another LIVE writer holds a
// fresh claim - callers must treat that as "retry", never as a result.
function finalizeOnce(dir, build) {
  const resultPath = path.join(dir, 'result.json');
  const claimPath = `${resultPath}.claim`;

  // Ownership is taken ONLY by an exclusive create (`wx`), which the OS makes
  // atomic.
  //
  // Recovery is the hard part. Unlinking a stale claim is NOT a compare-and-swap:
  // the claim inspected need not be the claim deleted, so two contenders can both
  // proceed (an ABA race). Instead a stealer RENAMES the claim to a unique name -
  // rename of a given source succeeds for exactly one caller, the losers get
  // ENOENT - and then re-verifies the owner it actually captured. If the captured
  // owner turns out to be alive, the claim is put back untouched.
  //
  // Age alone NEVER revokes a claim whose owner process is alive: a legitimate
  // finaliser doing slow git work would otherwise be robbed mid-build.
  let owned = false;
  for (let attempt = 0; attempt < 4 && !owned; attempt++) {
    const existing = readJson(resultPath);
    if (existing) return existing;
    try {
      const fd = fs.openSync(claimPath, 'wx');
      fs.writeSync(fd, JSON.stringify({ pid: process.pid, t: Date.now() }));
      fs.closeSync(fd);
      owned = true;
      break;
    } catch { /* someone holds it - decide whether it is still theirs */ }

    const claim = readJson(claimPath);
    const ownerAlive = claim && Number.isInteger(claim.pid) && alive(claim.pid);
    if (ownerAlive) return null;                       // a LIVE owner: caller must retry
    // A verifiably dead owner cannot be mid-build, so it is stealable at once -
    // age is irrelevant. The stale window applies only when the claim carries no
    // usable pid, where liveness cannot be checked at all.
    const unusable = !claim || !Number.isInteger(claim.pid);
    const age = claim && Number.isFinite(claim.t) ? Date.now() - claim.t : Infinity;
    if (unusable && age <= CLAIM_STALE_MS) return null;

    const captured = `${claimPath}.${process.pid}.${crypto.randomBytes(3).toString('hex')}`;
    try { fs.renameSync(claimPath, captured); }
    catch { continue; }                                // another contender captured it first
    const takenFrom = readJson(captured);
    if (takenFrom && Number.isInteger(takenFrom.pid) && alive(takenFrom.pid)) {
      // ABA: between inspecting and capturing, a live claimant replaced it.
      try { fs.renameSync(captured, claimPath); } catch { /* it will age out */ }
      return null;
    }
    try { fs.unlinkSync(captured); } catch { /* ignore */ }
  }
  if (!owned) return null;

  const result = build();
  writeJson(resultPath, result);
  journal(dir, { state: 'terminal', status: result.status, primary: result.status_provenance.primary });
  return result;
}

function alive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try { process.kill(pid, 0); return true; } catch (e) { return e.code === 'EPERM'; }
}

function killTree(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return;
  if (WIN) spawnSync('taskkill', ['/pid', String(pid), '/T', '/F'], { stdio: 'ignore' });
  else {
    try { process.kill(-pid, 'SIGKILL'); }
    catch { try { process.kill(pid, 'SIGKILL'); } catch { /* gone */ } }
  }
}

function hardenDir(dir) {
  // POSIX only: 0700 keeps another local account out of prompts and logs.
  // Windows inherits the parent ACL; chmod there is a near no-op, so doctor says so.
  if (!WIN) { try { fs.chmodSync(dir, 0o700); } catch { /* best effort */ } }
}

/* ---------- v1 backward read (contract 3c) ---------- */

function normaliseResult(raw) {
  if (!raw) return null;
  if (raw.schema === SCHEMA) return raw;
  // Only a result with NO schema key is v1. A result carrying some OTHER schema
  // came from a different (probably newer) driver; relabelling it v1 would
  // invent a legacy interpretation for data we do not understand.
  if (raw.schema !== undefined) {
    return { ...raw, unsupported_schema: true };
  }
  return {
    schema: 'delegate-task.result.v1', legacy: true,
    run_id: raw.run_id, parent_run_id: null,
    harness: raw.harness, harness_label: raw.harness_label, harness_version: null, tier: raw.tier,
    status: raw.status, status_reason: raw.status_reason || '',
    status_provenance: { primary: 'legacy', evidence: ['v1 run: provenance not recorded'] },
    summary: raw.summary,
    files_claimed: raw.files_changed ?? null,
    git_visible_after: null, dirty_paths_changed: null, files_mismatch: null,
    head_changed: null, index_changed: null, coverage_complete: false, read_only_violation: null,
    permission_requested: raw.permission || null, permission_mode_applied: null,
    containment_evidence: null,
    tokens: raw.tokens, usage_raw: null, cost_usd: raw.cost_usd ?? null,
    session_id: null, session_capture: null, envelope: null,
    exit_code: raw.exit_code, signal: null, duration_ms: raw.duration_ms, truncated_output: false,
    task: raw.task, cwd: raw.cwd, model: raw.model || null,
    started_at: raw.started_at, ended_at: raw.ended_at,
    artifacts: raw.artifacts || null,
  };
}

function journalPid(j, state) {
  const e = j.filter((x) => x.state === state).pop();
  return e && Number.isInteger(e.pid) ? e.pid : null;
}

function stateOf(id) {
  const dir = runDir(id);
  const meta = readJson(path.join(dir, 'meta.json'));
  if (!meta) return null;
  const res = normaliseResult(readJson(path.join(dir, 'result.json')));
  if (res) return { state: 'done', meta, res, dir };

  const j = readJournal(dir);
  const lastBeat = j.filter((e) => e.state === 'heartbeat' || e.state === 'supervisor_started').pop();
  const beatMs = lastBeat ? Date.parse(lastBeat.t) : NaN;
  // An unparseable timestamp, or one meaningfully in the FUTURE, is not evidence
  // of liveness - clamping a future stamp to "age 0" would let a bad clock keep
  // a dead run looking alive indefinitely.
  const rawAge = Number.isFinite(beatMs) ? Date.now() - beatMs : NaN;
  const beatAge = Number.isFinite(rawAge) && rawAge > -HEARTBEAT_MS ? Math.max(0, rawAge) : Infinity;
  const supAlive = alive(meta.supervisor_pid);
  const childPid = journalPid(j, 'child_started');

  if (!j.some((e) => e.state === 'supervisor_started')) {
    if (beatAge > START_ACK_MS) return { state: 'lost', meta, res: null, dir, childPid, why: 'supervisor never acknowledged start' };
    return { state: 'starting', meta, res: null, dir, childPid };
  }
  // A stale heartbeat from a supervisor that is STILL ALIVE is not death. The
  // git baseline runs many separately-bounded probes before the child starts, so
  // a large dirty tree can legitimately outlast the heartbeat window. Refusing
  // to publish is the safe failure; fabricating a terminal result is not.
  if (supAlive && beatAge > STALE_MS) {
    return {
      state: 'stalled', meta, res: null, dir, childPid,
      why: `the supervisor (pid ${meta.supervisor_pid}) is alive but has not heartbeat for ${Math.round(beatAge / 1000)}s`,
    };
  }
  if (supAlive) return { state: 'running', meta, res: null, dir, childPid };

  // The supervisor is gone. NEVER finalise while its child is still alive: on
  // POSIX the child leads its own process group and outlives the supervisor, and
  // a terminal result written now would be a snapshot of a run still in motion.
  if (alive(childPid)) {
    return {
      state: 'adrift', meta, res: null, dir, childPid,
      why: `the supervisor is gone but the harness (pid ${childPid}) is still running`,
    };
  }
  return { state: 'lost', meta, res: null, dir, childPid, why: 'supervisor process is gone' };
}

/* ---------- result assembly ---------- */

function buildResult({
  meta, dir, parse, statusRes, self, gitCmp, roVerdict, sessionId,
  exitCode, signal, t0, truncated, launched, repoRoot, repoId, recordsDropped,
}) {
  const h = HARNESSES[meta.harness];
  const delta = gitCmp.dirty_paths_changed;
  const claimed = self && self.files_changed ? self.files_changed : null;
  const fallback = String((parse && parse.text) || '').replace(RESULT_RE, '').trim().split(/\n\s*\n/).pop();
  const summary = (self && self.summary) || fallback || '(no summary produced)';
  return {
    schema: SCHEMA,
    run_id: meta.run_id, parent_run_id: meta.parent_run_id || null,
    harness: meta.harness, harness_label: meta.harness_label,
    harness_version: meta.harness_version || null, tier: meta.tier,

    status: statusRes.status,
    status_reason: statusRes.reason || (parse && parse.reason) || '',
    status_provenance: statusRes.provenance,
    summary: String(summary).slice(0, 4000),

    files_claimed: claimed,
    git_visible_after: gitCmp.git_visible_after,
    dirty_paths_changed: delta,
    files_mismatch: claimMismatch(claimed, delta, gitCmp.coverage_complete),
    head_changed: gitCmp.head_changed,
    index_changed: gitCmp.index_changed,
    coverage_complete: gitCmp.coverage_complete,
    read_only_violation: meta.permission === 'sandbox' ? roVerdict : null,

    permission_requested: meta.permission,
    // Nothing was "applied" if the harness never launched; saying otherwise
    // claims a containment posture that was never requested of anything.
    permission_mode_applied: launched ? `${meta.harness}: ${h.mode(meta.permission)}` : null,
    containment_evidence: launched
      ? containmentEvidence(meta.permission, roVerdict, gitCmp)
      : 'the harness never launched',

    tokens: (parse && parse.tokens) || tokens({ fidelity: 'unavailable' }),
    usage_raw: (parse && parse.usage_raw) || null,
    cost_usd: parse && parse.cost_usd != null ? parse.cost_usd : null,
    // Distinguishes "this harness never says" from "we failed to parse it".
    cost_reported: Boolean(h.reports && h.reports.cost),
    model_reported: Boolean(h.reports && h.reports.model),
    // `model` is retained for v2 readers and may fall back to the request.
    // These fields let consumers tell an observed model from that fallback.
    requested_model: meta.model || null,
    actual_model: (parse && parse.model) || null,
    model_observed: Boolean(parse && parse.model),

    session_id: sessionId || null,
    session_capture: h.session_capture,
    // --raw skips the envelope, so there is no self-report to refine a clean exit
    // and no files_claimed. Record that rather than letting it look like an
    // enveloped run whose delegate simply said nothing.
    envelope: meta.raw ? 'raw' : (meta.parent_run_id ? 'delta' : 'standard'),
    clean_env: Boolean(meta.clean_env),
    kept_env_names: meta.clean_env ? (meta.kept_env_names || []) : null,

    exit_code: exitCode, signal: signal || null,
    duration_ms: Date.now() - t0,
    truncated_output: Boolean(truncated),
    // Post-cap records the retention window could not hold. Non-zero means the
    // delegate's own words may be missing even though the status is sound.
    records_dropped: recordsDropped || 0,

    task: meta.task, cwd: meta.cwd, model: (parse && parse.model) || meta.model || null,
    repo_root: repoRoot || null, repo_id: repoIdString(repoId),
    started_at: meta.started_at, ended_at: new Date().toISOString(),
    artifacts: {
      dir,
      stdout: path.join(dir, 'stdout.log'),
      stderr: path.join(dir, 'stderr.log'),
      journal: path.join(dir, 'journal.jsonl'),
    },
  };
}

function containmentEvidence(perm, verdict, g) {
  if (perm !== 'sandbox') return 'not requested - run was write-capable';
  if (verdict === true) return `violation signal: ${(g.dirty_paths_changed || []).length} path(s) changed in the run window (attribution not established)`;
  if (verdict === false) return 'no covered final-state delta detected (cannot see ignored, reverted, or out-of-repo writes)';
  return 'unknown - git could not report, or fingerprint coverage was incomplete';
}

/* ---------- commands ---------- */

// The terminal result for a start whose supervisor never acknowledged. Exit 5
// follows it. Consumers (the Sanduq dispatcher) read `permission_mode_applied:
// null` and `containment_evidence: 'the harness never launched'`, together with
// a journal holding no supervisor event, as proof that no agent ran.
function finalizeStartFailure({ meta, dir, why, t0 }) {
  return finalizeOnce(dir, () => buildResult({
    meta, dir, parse: null, launched: false,
    statusRes: resolveStatus({ spawnError: why, exitCode: null, parse: null, self: null }),
    self: null, gitCmp: { ...GIT_UNKNOWN }, roVerdict: null, sessionId: null,
    exitCode: null, signal: null, t0, truncated: false,
  }));
}

async function cmdStart(o) {
  const t0 = Date.now();
  const h = HARNESSES[o.harness];
  if (!h) die(`unknown harness "${o.harness}". Known: ${Object.keys(HARNESSES).join(', ')}`);
  if (!o.task) die('--task (or --task-file) is required');

  // Argument validation BEFORE binary resolution, so a bad flag reports the bad
  // flag rather than "not installed" on a machine lacking that CLI.
  if (!Number.isFinite(o.timeout) || o.timeout <= 0 || o.timeout * 1000 > 2_147_483_647) {
    die(`--timeout must be a positive number of seconds under ${Math.floor(2_147_483_647 / 1000)} (got "${o.timeoutRaw}")`);
  }
  try {
    if (!fs.statSync(o.cwd).isDirectory()) die(`--cwd is not a directory: ${o.cwd}`);
  } catch { die(`--cwd does not exist: ${o.cwd}`); }

  const bin = resolveBin(h.bin, o.harness);
  if (bin.state === 'missing') die(`${h.label}: "${h.bin}" not found on PATH`);
  if (bin.state === 'undecodable') {
    die(`${h.label}: found ${bin.path} but could not resolve what it launches. ` +
        'It is installed; this driver only decodes npm-shaped .cmd shims.');
  }

  const probe = probeVersion(h, bin);
  if (probe.state === 'broken') {
    die(`${h.label} is installed but "${h.bin} ${h.versionArgs.join(' ')}" failed: ${probe.detail}`);
  }

  let parent = null, resumeSession = null, inherited = null;
  if (o.resume) {
    const s = stateOf(o.resume) || die(`no such run to resume: ${o.resume}`);
    if (!s.res) die(`run ${o.resume} has not finished; nothing to resume from`);
    if (s.meta.harness !== o.harness) {
      die(`run ${o.resume} used ${s.meta.harness}; --harness ${o.harness} cannot resume it`);
    }
    if (!s.res.session_id) {
      die(`run ${o.resume} produced no session id (${h.label} capture is "${h.session_capture}") - cannot resume`);
    }
    if (path.resolve(s.meta.cwd) !== path.resolve(o.cwd)) {
      die(`run ${o.resume} ran in ${s.meta.cwd}; refusing to resume it in a different directory`);
    }
    if (s.res.harness_version && probe.version && s.res.harness_version !== probe.version) {
      die(`run ${o.resume} used ${h.label} ${s.res.harness_version}; this machine has ${probe.version}. ` +
          'A session is not portable across CLI versions - dispatch a fresh run.');
    }
    const parentModel = s.meta.model || null;
    if (o.model && parentModel && o.model !== parentModel) {
      die(`run ${o.resume} used model ${parentModel}; --model ${o.model} would change it mid-session`);
    }
    // Identity, not path: `.git` can be replaced or re-initialised in place, and
    // a resumed session would then be applied to a different repository.
    const nowRepo = gitCapture(o.cwd);
    if (s.res.repo_id && nowRepo.id && !sameRepository(parseRepoId(s.res.repo_id), nowRepo.id)) {
      die(`run ${o.resume} ran in a different repository (${s.res.repo_root || 'unknown'}); ` +
          'this path now resolves to another one');
    }
    parent = o.resume;
    resumeSession = s.res.session_id;
    // The parent's scope exclusions and deliverable are part of the policy that
    // must be restated, not silently dropped (Amendment 4).
    inherited = { deliverable: s.meta.deliverable || null, constraints: s.meta.constraint || [] };
  }

  fs.mkdirSync(RUNS, { recursive: true });
  hardenDir(RUNS);
  const stamp = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14);
  const id = `${o.harness}-${stamp}-${crypto.randomBytes(3).toString('hex')}`;
  const dir = runDir(id);
  fs.mkdirSync(dir, { recursive: true });
  hardenDir(dir);
  journal(dir, { state: 'created' });

  const deliverable = o.deliverable || (inherited && inherited.deliverable) || null;
  const constraints = [
    ...(inherited ? inherited.constraints : []),
    ...o.constraint.filter((c) => !(inherited && inherited.constraints.includes(c))),
  ];
  const built = { task: o.task, cwd: o.cwd, deliverable, constraints, allowCommit: o.allowCommit };
  const prompt = o.raw ? o.task : (parent ? deltaEnvelope({ ...built, parent }) : envelope(built));
  fs.writeFileSync(path.join(dir, 'prompt.txt'), prompt);

  const keptEnvNames = o.cleanEnv ? envKeepList(o.keepEnv).filter((k) => process.env[k] !== undefined) : null;
  const meta = {
    run_id: id, parent_run_id: parent, resume_session: resumeSession,
    harness: o.harness, harness_label: h.label, harness_version: probe.version, tier: h.tier,
    task: o.task, cwd: o.cwd, model: o.model || null,
    deliverable, constraint: constraints,
    permission: o.perm, allow_commit: o.allowCommit, raw: o.raw,
    timeout_ms: Math.round(o.timeout * 1000),
    clean_env: o.cleanEnv, keep_env: o.keepEnv, kept_env_names: keptEnvNames,
    started_at: new Date().toISOString(), nonce: crypto.randomBytes(4).toString('hex'),
    supervisor_pid: null,
  };
  writeJson(path.join(dir, 'meta.json'), meta);

  const child = spawn(process.execPath, [fileURLToPath(import.meta.url), '__supervise', id],
    { detached: true, stdio: 'ignore', windowsHide: true, env: process.env });

  let spawnFailed = null;
  child.on('error', (e) => { spawnFailed = e.message; });
  child.unref();

  meta.supervisor_pid = child.pid || null;
  writeJson(path.join(dir, 'meta.json'), meta);

  // Await, never block: a synchronous wait would starve the 'error' listener
  // above and we would learn nothing about a spawn that failed outright.
  const deadline = Date.now() + START_ACK_MS;
  let acked = false;
  while (Date.now() < deadline) {
    if (spawnFailed) break;
    if (readJournal(dir).some((e) => e.state === 'supervisor_started')) { acked = true; break; }
    await new Promise((r) => setTimeout(r, 120));
  }
  if (!acked) {
    const why = spawnFailed || `supervisor did not acknowledge start within ${START_ACK_MS / 1000}s`;
    finalizeStartFailure({ meta, dir, why, t0 });
    killTree(child.pid);
    die(`supervisor failed to start: ${why}`, 5);
  }

  console.log(JSON.stringify({
    run_id: id, harness: o.harness, state: 'running', run_dir: dir,
    ...(parent ? { parent_run_id: parent, resumed_session: resumeSession } : {}),
  }, null, 2));
}

function probeVersion(h, bin) {
  if (!bin || bin.state !== 'ok') return { state: bin ? bin.state : 'missing', version: null, detail: null };
  const r = boundedExec(bin.file, [...bin.args, ...h.versionArgs], { timeout: VERSION_PROBE_MS });
  if (!r.ok) {
    const e = r.err || {};
    const detail = e.code === 'ETIMEDOUT'
      ? `probe timed out after ${VERSION_PROBE_MS}ms`
      : (String(e.stderr || e.message || 'non-zero exit').trim().split('\n')[0]);
    return { state: 'broken', version: null, detail };
  }
  const v = (r.out || '').trim().split('\n')[0].trim();
  return { state: 'ok', version: v || 'unknown', detail: null };
}

const ENV_BASE = ['PATH', 'Path', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'LANG', 'LC_ALL', 'LC_CTYPE',
  'TERM', 'TMPDIR', 'TEMP', 'TMP', 'SystemRoot', 'SystemDrive', 'USERPROFILE', 'APPDATA',
  'LOCALAPPDATA', 'PATHEXT', 'COMSPEC'];

const envKeepList = (extra) => [...ENV_BASE, ...(extra || [])];

function buildEnv(meta) {
  if (!meta.clean_env) return process.env;
  const out = {};
  for (const k of envKeepList(meta.keep_env)) if (process.env[k] !== undefined) out[k] = process.env[k];
  return out;
}

async function cmdSupervise(id) {
  const dir = runDir(id);
  const meta = readJson(path.join(dir, 'meta.json'));
  if (!meta) process.exit(1);
  journal(dir, { state: 'supervisor_started', pid: process.pid, nonce: meta.nonce });

  const h = HARNESSES[meta.harness];
  const bin = resolveBin(h.bin, meta.harness);
  const t0 = Date.now();

  const gitBefore = gitCapture(meta.cwd);
  journal(dir, { state: 'git_baseline', root: gitBefore.root, dirty: gitBefore.porcelain ? gitBefore.porcelain.length : null });

  const finish = (extra) => finalizeOnce(dir, () => {
    const gitCmp = gitCompare(gitBefore, meta.cwd);
    return buildResult({ meta, dir, gitCmp, roVerdict: readOnlyVerdict(gitCmp), t0, repoRoot: gitBefore.root, repoId: gitBefore.id, ...extra });
  });

  // The binary was resolvable at start; if it vanished between then and now, that
  // race gets a terminal result rather than a null dereference.
  if (bin.state !== 'ok') {
    finish({
      parse: null, self: null, sessionId: null, exitCode: null, signal: null,
      truncated: false, launched: false,
      statusRes: resolveStatus({ spawnError: `${h.bin} disappeared between start and dispatch (${bin.state})`, exitCode: null, parse: null, self: null }),
    });
    process.exit(5);
  }

  const prompt = fs.readFileSync(path.join(dir, 'prompt.txt'), 'utf8');
  const args = [...bin.args, ...h.args({
    task: prompt, model: meta.model, perm: meta.permission, resume: meta.resume_session || null,
  })];

  const outPath = path.join(dir, 'stdout.log');
  const errPath = path.join(dir, 'stderr.log');
  const outFd = fs.openSync(outPath, 'a');
  const errFd = fs.openSync(errPath, 'a');

  // stdin 'ignore' matters: codex blocks reading stdin when it is not a TTY.
  // stdout/stderr are piped rather than redirected so session ids can be captured
  // while the run is live and output can be bounded.
  const child = spawn(bin.file, args, {
    cwd: meta.cwd, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true,
    detached: !WIN, env: buildEnv(meta),
  });

  let spawnError = null;
  let sessionId = meta.resume_session || null;
  const streams = {
    out: { fd: outFd, written: 0, capped: false, tail: [], tailBytes: 0 },
    err: { fd: errFd, written: 0, capped: false, tail: [], tailBytes: 0 },
  };
  const dec = { out: new StringDecoder('utf8'), err: new StringDecoder('utf8') };
  let lineBuf = '';
  // Declared before capWrite: crossing the cap part-way through an already
  // discarded record has to count that record, and the two events can happen in
  // either order.
  let discarding = false;
  let discardCounted = false;

  // Capping bounds the FILE, not the telemetry: once capped we keep a rolling
  // tail in memory and append it before parsing, so a terminal event arriving
  // after the cap does not silently become "telemetry_incomplete".
  const capWrite = (s, chunk) => {
    if (!s.capped && s.written + chunk.length <= MAX_LOG_BYTES) {
      s.written += chunk.length;
      try { fs.writeSync(s.fd, chunk); } catch { /* ignore */ }
      return;
    }
    if (!s.capped) {
      s.capped = true;
      // The newline matters: the file may end mid-record, and without it the
      // truncated text would run into the first retained record and destroy it.
      try { fs.writeSync(s.fd, `\n[delegate: output capped at ${MAX_LOG_BYTES} bytes; complete records after this point are appended below]\n`); } catch { /* ignore */ }
      journal(dir, { state: 'output_capped', bytes: s.written });
      // An over-limit record already being discarded when the cap crosses is now
      // genuinely lost - its head is in the truncated file and its tail is thrown
      // away. Counting only at discard-start would report zero here.
      if (s === streams.out && discarding && !discardCounted) {
        discardCounted = true;
        retained.dropped++;
      }
    }
    s.tail.push(chunk); s.tailBytes += chunk.length;
    while (s.tailBytes > LOG_TAIL_BYTES && s.tail.length > 0) s.tailBytes -= s.tail.shift().length;
    // A single chunk larger than the whole tail budget would otherwise defeat the
    // bound; keep its last LOG_TAIL_BYTES rather than all of it or none of it.
    if (!s.tail.length && chunk.length > LOG_TAIL_BYTES) {
      const keep = chunk.subarray(chunk.length - LOG_TAIL_BYTES);
      s.tail.push(keep); s.tailBytes = keep.length;
    } else if (!s.tail.length) {
      s.tail.push(chunk); s.tailBytes = chunk.length;
    }
  };

  // Retained COMPLETE lines, bounded independently of the raw byte tail. A byte
  // suffix cannot parse a record whose opening brace was evicted, so an oversized
  // terminal event would be destroyed by the cap and a finished run would publish
  // `telemetry_incomplete`. The scanner already sees whole lines as they arrive,
  // so keeping those is what makes the cap lossless for telemetry.
  // Retention starts ONLY once the raw log is capped. capWrite never writes a
  // partial chunk, so every byte is either already in the file or not written at
  // all - retaining from process start would replay records the file already
  // holds, and an additive adapter (OpenCode sums every step_finish) would count
  // them twice.
  //
  // `head` indexes the live window instead of Array.shift(), which is linear per
  // eviction; the budget is counted in BYTES, matching what the name promises.
  const retained = makeRetention(LOG_TAIL_BYTES);
  const retain = (line) => retained.add(line);
  const retainedLines = () => retained.lines();

  // A record longer than MAX_LINE_CHARS is refused as an anti-DoS bound. Real
  // pipe delivery splits such a record across many reads, so the buffer guard
  // below fires repeatedly BEFORE any newline arrives - counting there, or at the
  // final unparseable suffix, would either over-count or never fire at all.
  // `discarding` makes the drop exactly one event and swallows the remainder.

  const scan = (text) => {
    lineBuf += text;
    let nl;
    while ((nl = lineBuf.indexOf('\n')) !== -1) {
      const line = lineBuf.slice(0, nl);
      lineBuf = lineBuf.slice(nl + 1);
      if (discarding) { discarding = false; discardCounted = false; continue; }  // tail of a dropped record
      const s = line.trim();
      if (!s.startsWith('{')) continue;
      if (s.length > MAX_LINE_CHARS) { if (streams.out.capped) retained.dropped++; continue; }
      let e; try { e = JSON.parse(s); } catch { continue; }
      if (streams.out.capped) retain(s);
      const sid = h.session(e);
      if (sid && sid !== sessionId) {
        sessionId = sid;
        journal(dir, { state: 'session', session_id: sid });
      }
    }
    // Mid-record and already over the bound: start discarding, and count the loss
    // once. Only when the log is capped is the record actually lost - otherwise
    // it is still complete in stdout.log and the adapter will parse it there.
    if (lineBuf.length > MAX_LINE_CHARS) {
      if (!discarding) {
        discarding = true;
        // The two counting sites are mutually exclusive by construction: this one
        // requires the cap to have already crossed, the one in capWrite requires
        // it not to have. discardCounted keeps that invariant explicit rather
        // than implicit, so a later edit cannot quietly produce a double count.
        if (streams.out.capped) { retained.dropped++; discardCounted = true; }
      }
      lineBuf = '';
    }
  };

  child.stdout.on('data', (c) => { capWrite(streams.out, c); scan(dec.out.write(c)); });
  child.stderr.on('data', (c) => { capWrite(streams.err, c); });
  child.on('error', (e) => { spawnError = e.message; });
  // Journal the child only once the OS confirms it started; Node reports spawn
  // failure asynchronously, so recording it earlier claims a child that may
  // never exist - and recovery reads this to decide whether a run is adrift.
  child.on('spawn', () => journal(dir, { state: 'child_started', pid: child.pid || null }));

  const flushTails = () => {
    // stdout gets the retained COMPLETE lines - they parse by construction.
    // stderr has no telemetry to preserve, so its raw byte tail is fine.
    const keep = streams.out.capped ? retainedLines() : [];
    if (keep.length) {
      try { fs.writeSync(streams.out.fd, `${keep.join('\n')}\n`); } catch { /* ignore */ }
      retained.reset();
    }
    streams.out.tail = []; streams.out.tailBytes = 0;
    if (streams.err.capped && streams.err.tail.length) {
      try { for (const c of streams.err.tail) fs.writeSync(streams.err.fd, c); } catch { /* ignore */ }
      streams.err.tail = []; streams.err.tailBytes = 0;
    }
  };

  const beat = setInterval(() => journal(dir, { state: 'heartbeat' }), HEARTBEAT_MS);
  beat.unref?.();

  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; killTree(child.pid); }, meta.timeout_ms);

  // The supervisor's own death must still produce a result. Registration is a
  // no-op for SIGTERM/SIGHUP on native Windows; the heartbeat/staleness path in
  // stateOf covers what no handler can.
  let aborting = false;
  for (const sig of ['SIGTERM', 'SIGINT', 'SIGHUP']) {
    process.on(sig, () => {
      if (aborting) return;
      aborting = true;
      clearTimeout(timer); clearInterval(beat);
      killTree(child.pid);

      // Shutdown must be ASYNCHRONOUS. A synchronous wait here starves the very
      // stdout/exit callbacks that drain the child, so the "preserved evidence"
      // would be missing whatever was still buffered.
      let settled = false;
      const snapshot = (exited) => {
        if (settled) return;
        settled = true;
        flushTails();
        const parsed = safeParse(h, outPath, errPath, null);
        finalizeOnce(dir, () => {
          const gitCmp = gitCompare(gitBefore, meta.cwd);
          return buildResult({
            meta, dir, gitCmp, roVerdict: readOnlyVerdict(gitCmp), t0, launched: true,
            parse: parsed, self: parseEnvelope(parsed.text), sessionId,
            repoRoot: gitBefore.root, repoId: gitBefore.id,
            exitCode: null, signal: null, truncated: streams.out.capped || streams.err.capped,
            recordsDropped: retained.dropped,
            statusRes: {
              status: 'abandoned',
              reason: `the relay was killed by ${sig}; the harness was terminated with it`,
              provenance: {
                primary: 'relay_aborted',
                evidence: [`signal: ${sig}`, `session_id: ${sessionId || 'none'}`,
                  exited ? 'the harness exited before the snapshot'
                    : 'the harness did not exit within the grace window'],
              },
            },
          });
        });
        process.exit(128 + 15);
      };
      // Whichever comes first: the child closing its streams, or the grace window.
      child.once('close', () => setImmediate(() => snapshot(true)));
      setTimeout(() => snapshot(false), ABORT_GRACE_MS).unref?.();
    });
  }

  // Wait for 'close', not 'exit'. 'exit' fires when the process ends, while its
  // stdio may still hold buffered output; closing the log descriptors then can
  // drop the terminal JSONL record and turn a finished run into
  // telemetry_incomplete. 'close' fires only once the streams are drained.
  const { code, signal } = await new Promise((res) => {
    child.on('close', (c, s) => res({ code: c, signal: s }));
    child.on('error', () => res({ code: null, signal: null }));
  });
  clearTimeout(timer); clearInterval(beat);
  if (lineBuf.trim()) scan('\n');
  flushTails();
  try { fs.closeSync(outFd); fs.closeSync(errFd); } catch { /* ignore */ }

  const parsed = safeParse(h, outPath, errPath, code);
  const self = parseEnvelope(parsed.text);
  const gitCmp = gitCompare(gitBefore, meta.cwd);

  const statusRes = resolveStatus({
    timedOut, spawnError, signal: timedOut ? null : signal,
    exitCode: timedOut ? null : code, parse: parsed, self,
    headMoved: gitCmp.head_changed, indexMoved: gitCmp.index_changed,
    allowCommit: meta.allow_commit,
  });

  // Written exactly once, inside the claim. Patching the file afterwards - as an
  // earlier build did to add repo_root - reopens the window the claim exists to
  // close, and can overwrite a signal handler's or a collector's verdict.
  finalizeOnce(dir, () => buildResult({
    meta, dir, parse: parsed, statusRes, self, gitCmp, launched: !spawnError,
    roVerdict: readOnlyVerdict(gitCmp), sessionId, repoRoot: gitBefore.root, repoId: gitBefore.id,
    exitCode: code, signal, t0, truncated: streams.out.capped || streams.err.capped,
    recordsDropped: retained.dropped,
  }));
}

function safeParse(h, outPath, errPath, code) {
  let stdout = '', stderr = '';
  try { stdout = fs.readFileSync(outPath, 'utf8'); } catch { /* ignore */ }
  try { stderr = fs.readFileSync(errPath, 'utf8'); } catch { /* ignore */ }
  try {
    const p = h.parse(stdout, stderr, code);
    return { parseError: false, ...p };
  } catch (e) {
    return {
      parseError: true, status: 'failed', reason: `parse error: ${e.message}`,
      complete: false, text: '', usage_raw: null, tokens: tokens({ fidelity: 'unavailable' }),
    };
  }
}

function synthesizeLost(s) {
  // No handler could run (SIGKILL, crash, native-Windows hard kill). Build a
  // terminal result from the journal, the logs and a git snapshot.
  const { meta, dir } = s;
  const h = HARNESSES[meta.harness];
  const j = readJournal(dir);
  const sid = (j.filter((e) => e.state === 'session').pop() || {}).session_id || meta.resume_session || null;
  const parsed = safeParse(h, path.join(dir, 'stdout.log'), path.join(dir, 'stderr.log'), null);
  // A synthesised result has no run-start baseline, so only the after-state is
  // knowable. Everything comparative must be null - reporting head_changed:false
  // here would be an assurance nothing measured.
  const after = gitCapture(meta.cwd);
  const blind = { ...GIT_UNKNOWN, git_visible_after: after.porcelain ? after.porcelain.map(porcelainKey) : null };
  return finalizeOnce(dir, () => buildResult({
    meta, dir, parse: parsed, self: parseEnvelope(parsed.text), gitCmp: blind,
    roVerdict: null, sessionId: sid, exitCode: null, signal: null, launched: j.some((e) => e.state === 'child_started'),
    t0: Date.parse(meta.started_at) || Date.now(), truncated: false,
    statusRes: {
      status: 'abandoned',
      reason: s.why || 'supervisor disappeared without writing a result',
      provenance: {
        primary: 'supervisor_lost',
        evidence: [s.why || 'supervisor gone', `journal states: ${j.map((e) => e.state).join(' > ')}`,
          `session_id: ${sid || 'none'}`, 'git delta unavailable: no run-start baseline survived'],
      },
    },
  }));
}

function cmdStatus(id) {
  const s = stateOf(id) || die(`no such run: ${id}`);
  console.log(JSON.stringify({
    run_id: id, state: s.state, harness: s.meta.harness,
    status: s.res ? s.res.status : null,
    provenance: s.res ? s.res.status_provenance.primary : null,
    session_id: s.res ? s.res.session_id : null,
    child_pid: s.childPid ?? null,
    elapsed_s: Math.round((Date.now() - new Date(s.meta.started_at)) / 1000),
    ...(s.why ? { why: s.why } : {}),
  }, null, 2));
}

async function cmdCollect(id, o) {
  let s = stateOf(id) || die(`no such run: ${id}`);
  const deadline = Date.now() + (o.wait ? o.wait * 1000 : 0);
  while (['running', 'starting', 'adrift', 'stalled'].includes(s.state) && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 2000));
    s = stateOf(id);
  }
  if (s.state === 'running' || s.state === 'starting') die(`run ${id} still executing (use --wait <seconds>)`, 3);
  if (s.state === 'adrift') {
    die(`run ${id}: ${s.why}. Refusing to publish a result while the harness is still writing. ` +
        `Wait for it, or kill pid ${s.childPid} and collect again.`, 6);
  }
  if (s.state === 'stalled') {
    die(`run ${id}: ${s.why}. Refusing to publish a competing result while it may still finish. ` +
        `Inspect ${path.join(s.dir, 'journal.jsonl')}, or kill it and collect again.`, 6);
  }
  if (s.state === 'lost') {
    const res = synthesizeLost(s);
    if (!res) die(`run ${id}: another process is finalising this run; retry in a moment`, 7);
    s = { ...s, state: 'done', res: normaliseResult(res) };
  }
  if (!s.res) die(`run ${id}: no result could be read`, 7);
  if (s.res.unsupported_schema) {
    die(`run ${id} was written by a different driver (schema "${s.res.schema}"); this build cannot read it`, 8);
  }
  if (o.json) { console.log(JSON.stringify(s.res, null, 2)); return; }
  printResult(s.res);
}

function printResult(r) {
  const t = r.tokens || {};
  const L = [];
  L.push(`Delegation ${r.run_id}${r.parent_run_id ? `  (resumed from ${r.parent_run_id})` : ''}`);
  L.push(`Harness      ${r.harness_label}${r.harness_version ? ` ${r.harness_version}` : ''}` +
         `${r.tier === 'experimental' ? '  (EXPERIMENTAL)' : ''}` +
         `  model=${r.model || (r.model_reported === false ? 'not reported by this harness' : 'harness default')}`);
  if (r.legacy) L.push('Schema       v1 run - git measurement, provenance and session were not recorded');
  L.push(`Status       ${String(r.status).toUpperCase()}${r.status_reason ? `  - ${r.status_reason}` : ''}`);
  L.push(`Because      ${r.status_provenance.primary}`);
  if (r.envelope === 'raw') L.push('             (--raw: no envelope, so no self-report and no claimed files)');
  if (r.records_dropped) {
    L.push(`             (${r.records_dropped} record(s) dropped past the output cap - the summary may be incomplete)`);
  }
  L.push(`Duration     ${(r.duration_ms / 1000).toFixed(1)}s   exit=${r.exit_code === null ? 'n/a' : r.exit_code}` +
         `${r.signal ? `  signal=${r.signal}` : ''}${r.truncated_output ? '  [output capped]' : ''}`);
  L.push('');
  L.push('Summary');
  L.push(String(r.summary).split('\n').map((l) => `  ${l}`).join('\n'));
  L.push('');

  L.push('Changes');
  if (r.dirty_paths_changed === null) {
    L.push('  measured   git could not report - inspect the working tree directly');
  } else if (r.dirty_paths_changed.length === 0) {
    L.push('  measured   no git-visible change in the run window');
  } else {
    L.push(`  measured   ${r.dirty_paths_changed.join(', ')}`);
  }
  L.push(`  claimed    ${r.files_claimed || 'none'}`);
  if (r.files_mismatch === true) L.push('  ⚠ claim and measurement disagree');
  if (r.files_mismatch === null && r.files_claimed != null) {
    L.push('  (claim not checked - coverage incomplete or the delta contains an ambiguous path)');
  }
  if (r.head_changed === true) L.push('  ⚠ HEAD MOVED during the run window - review before trusting this tree');
  if (r.index_changed === true) L.push('  ⚠ the staged set changed during the run window');
  if (!r.coverage_complete && r.dirty_paths_changed !== null) L.push('  (fingerprint coverage incomplete)');

  L.push('');
  L.push(`Permission   requested=${r.permission_requested}  applied=${r.permission_mode_applied || 'n/a (never launched)'}`);
  if (r.permission_requested === 'sandbox') {
    L.push(`  read_only_violation: ${r.read_only_violation === null ? 'unknown' : r.read_only_violation}`);
    L.push(`  ${r.containment_evidence}`);
  }
  if (r.clean_env) L.push(`  clean-env: kept ${(r.kept_env_names || []).length} variable(s) - names only, never values`);

  L.push('');
  L.push(`Tokens (${t.fidelity})`);
  L.push(`  input   total ${t.input_total}  (fresh ${t.input_fresh}, cache read ${t.cache_read}, cache write ${t.cache_write})`);
  L.push(`  output  total ${t.output_total}  (reasoning ${t.reasoning})`);
  L.push(`  TOTAL   ${t.total}`);
  // A bare null reads like a parsing bug. Say which it is.
  L.push(r.cost_usd != null
    ? `  cost    $${r.cost_usd.toFixed(4)}`
    : `  cost    ${r.cost_reported === false ? 'not reported by this harness' : 'unknown'}`);
  if (t.fidelity === 'unavailable') L.push('  (zeroes mean UNKNOWN, not free)');

  if (r.session_id) L.push(`\nSession      ${r.session_id}   resume with: --resume ${r.run_id}`);
  L.push(`\nLogs         ${r.artifacts ? r.artifacts.dir : '(none)'}`);
  console.log(L.join('\n'));
}

function cmdList() {
  if (!fs.existsSync(RUNS)) return console.log('(no runs yet)');
  const rows = fs.readdirSync(RUNS).map(stateOf).filter(Boolean)
    .sort((a, b) => a.meta.started_at.localeCompare(b.meta.started_at));
  if (!rows.length) return console.log('(no runs yet)');
  for (const s of rows) {
    const r = s.res;
    console.log([
      s.meta.run_id.padEnd(32),
      s.state.padEnd(9),
      String(r ? r.status : '-').padEnd(11),
      String(r && r.status_provenance ? r.status_provenance.primary : '-').padEnd(20),
      String(r && r.tokens ? r.tokens.total : '-').padStart(9),
      r && r.legacy ? ' (v1)' : '     ',
      ' ' + s.meta.task.replace(/\s+/g, ' ').slice(0, 44),
    ].join(' '));
  }
}

function cmdDoctor() {
  console.log('harness   tier          version                     read-only        resume        launches as');
  for (const [id, h] of Object.entries(HARNESSES)) {
    const b = resolveBin(h.bin, id);
    const p = probeVersion(h, b);
    const how = b.state === 'ok' ? (b.args.length ? `node ${path.basename(b.args[0])}` : path.basename(b.file))
      : b.state === 'undecodable' ? `UNDECODABLE SHIM (${b.path})` : 'NOT FOUND on PATH';
    const ver = p.state === 'ok' ? p.version : p.state === 'broken' ? `BROKEN: ${p.detail}` : '-';
    const verCell = String(ver).length > 26 ? `${String(ver).slice(0, 25)}…` : String(ver);
    console.log(
      `${id.padEnd(10)}${h.tier.padEnd(14)}${verCell.padEnd(28)}` +
      `${h.readOnly.padEnd(17)}${h.resume.padEnd(14)}${how}`,
    );
    if (h.note) console.log(`${' '.repeat(10)}note: ${h.note}`);
    if (p.state === 'broken') console.log(`${' '.repeat(10)}${h.bin} is installed but its version probe failed - the CLI may still work; re-run doctor`);
  }
  console.log(`\nruns dir: ${RUNS}`);
  console.log('  Run artifacts hold the full prompt, the harness\'s raw output and your task text.');
  console.log('  Treat them as sensitive: they can contain secrets the harness printed.');
  console.log(WIN
    ? '  Windows: directory permissions are inherited; this driver cannot restrict them.'
    : '  POSIX: the runs directory is chmod 0700.');
  console.log(`  Each stream is capped at ${MAX_LOG_BYTES} bytes (DELEGATE_MAX_LOG_BYTES), keeping a rolling tail.`);
  console.log('  Clean up with: delegate.mjs prune --keep 20 --yes');
}

function cmdPrune(o) {
  if (!fs.existsSync(RUNS)) return console.log('(no runs yet)');
  const all = fs.readdirSync(RUNS).map(stateOf).filter(Boolean)
    .sort((a, b) => b.meta.started_at.localeCompare(a.meta.started_at));
  const cutoff = o.olderThan ? Date.now() - o.olderThan * 86_400_000 : null;
  // adrift = a child is STILL WRITING; stalled = the supervisor may yet finish.
  const live = new Set(['running', 'starting', 'adrift', 'stalled']);
  const doomed = all.filter((s, i) => {
    if (live.has(s.state)) return false;
    if (o.keep != null && i < o.keep) return false;
    if (cutoff != null && new Date(s.meta.started_at).getTime() >= cutoff) return false;
    if (o.keep == null && cutoff == null) return false;
    return true;
  });
  const skipped = all.filter((s) => live.has(s.state));
  if (skipped.length) console.log(`keeping ${skipped.length} live run(s): ${skipped.map((s) => s.meta.run_id).join(', ')}`);
  if (!doomed.length) return console.log('nothing to prune');
  for (const s of doomed) console.log(`${o.yes ? 'removing' : 'would remove'}  ${s.meta.run_id}`);
  if (!o.yes) return console.log(`\n${doomed.length} run(s). Re-run with --yes to delete.`);
  for (const s of doomed) fs.rmSync(s.dir, { recursive: true, force: true });
  console.log(`\nremoved ${doomed.length} run(s)`);
}

/* ---------- cli ---------- */

function die(msg, code = 2) { console.error(`delegate: ${msg}`); process.exit(code); }

function parseArgs(argv) {
  const o = {
    harness: null, task: null, cwd: process.cwd(), model: null, perm: 'bypass',
    timeout: 1800, timeoutRaw: '1800', wait: 0, waitRaw: '0', json: false, raw: false,
    deliverable: null, constraint: [], allowCommit: false, resume: null,
    cleanEnv: false, keepEnv: [], keep: null, olderThan: null, yes: false,
  };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    // Every value-taking flag reports a missing value as a normal CLI error
    // instead of letting `undefined` leak into a path or an env lookup.
    const next = () => {
      const v = argv[++i];
      if (v === undefined) die(`${a} needs a value`);
      return v;
    };
    if (a === '--harness' || a === '-H') o.harness = next();
    else if (a === '--task' || a === '-t') o.task = next();
    else if (a === '--task-file') {
      const f = next();
      try { o.task = fs.readFileSync(f, 'utf8'); } catch { die(`--task-file not readable: ${f}`); }
    } else if (a === '--cwd') o.cwd = path.resolve(next());
    else if (a === '--model' || a === '-m') o.model = next();
    else if (a === '--sandbox') o.perm = 'sandbox';
    else if (a === '--bypass') o.perm = 'bypass';
    else if (a === '--timeout') { o.timeoutRaw = next(); o.timeout = Number(o.timeoutRaw); }
    else if (a === '--wait') { o.waitRaw = next(); o.wait = Number(o.waitRaw); }
    else if (a === '--deliverable') o.deliverable = next();
    else if (a === '--constraint') o.constraint.push(next());
    else if (a === '--allow-commit') o.allowCommit = true;
    else if (a === '--resume') o.resume = next();
    else if (a === '--clean-env') o.cleanEnv = true;
    else if (a === '--keep-env') o.keepEnv.push(next());
    else if (a === '--keep') o.keep = Number(next());
    else if (a === '--older-than') o.olderThan = Number(next());
    else if (a === '--yes') o.yes = true;
    else if (a === '--json') o.json = true;
    else if (a === '--raw') o.raw = true;
    else if (a.startsWith('-')) die(`unknown flag ${a}`);
    else rest.push(a);
  }
  if (!Number.isFinite(o.wait) || o.wait < 0) die(`--wait must be a non-negative number of seconds (got "${o.waitRaw}")`);
  if (o.keep !== null && (!Number.isInteger(o.keep) || o.keep < 0)) die('--keep must be a non-negative integer');
  if (o.olderThan !== null && (!Number.isFinite(o.olderThan) || o.olderThan < 0)) die('--older-than must be a non-negative number of days');
  if (o.raw && o.resume) die('--raw and --resume are incompatible: a resumed dispatch must carry its policy rules');
  return [o, rest];
}

// Machine-readable capability contract. A consumer that depends on these flags,
// fields and exit codes queries `delegate.mjs contract` rather than inferring
// compatibility from files that merely exist. Bump `contract` on any removal.
const DRIVER_CONTRACT = Object.freeze({
  contract: 'delegate-task.driver.v1',
  result_schema: SCHEMA,
  commands: ['start', 'collect', 'status', 'list', 'doctor', 'prune', 'contract'],
  start_flags: ['--harness', '--task', '--cwd', '--model', '--sandbox', '--timeout',
    '--deliverable', '--constraint', '--resume', '--allow-commit'],
  collect_flags: ['--wait', '--json'],
  env: ['DELEGATE_RUNS_DIR'],
  meta_fields: ['run_id', 'harness', 'model', 'constraint', 'permission', 'allow_commit'],
  result_fields: ['schema', 'run_id', 'harness', 'status', 'status_reason', 'status_provenance',
    'summary', 'requested_model', 'actual_model', 'model_observed', 'model_reported', 'tokens',
    'dirty_paths_changed', 'head_changed', 'index_changed', 'coverage_complete', 'artifacts'],
  exit_codes: { usage_or_start_refused: 2, collect_still_running: 3, supervisor_start_failed: 5 },
});

function cmdContract() { console.log(JSON.stringify(DRIVER_CONTRACT, null, 2)); }

const HELP = `delegate.mjs - run one task on an external agent CLI, in the background

  start    --harness <id> --task <text> [--cwd DIR] [--model M] [--sandbox]
           [--timeout SEC] [--deliverable TEXT] [--constraint TEXT]...
           [--resume <run_id>] [--allow-commit] [--clean-env] [--keep-env NAME]... [--raw]
  collect  <run_id> [--wait SEC] [--json]
  status   <run_id>
  list
  doctor
  prune    [--keep N] [--older-than DAYS] [--yes]
  contract print the machine-readable flags, fields and exit codes consumers rely on

Harnesses: ${Object.keys(HARNESSES).join(', ')}
Permissions default to full bypass; --sandbox requests each CLI's read-only mode.
DELEGATE_BIN_<HARNESS> overrides where a harness binary is found.
Contracts: contracts/status-precedence.md, git-fields.md, result-schema-v2.md`;

// Exported for test/run.mjs. The CLI only runs when this file is the entry point,
// so importing it for a unit test does not execute a command.
export {
  HARNESSES, DRIVER_CONTRACT, tokens, parseEnvelope, parsePorcelainZ, claimMismatch,
  readOnlyVerdict, normaliseResult, resolveBin, envelope, deltaEnvelope, policyLines,
  gitCapture, gitCompare, headMovement, finalizeOnce, finalizeStartFailure, positiveIntEnv,
};

// Node loads the entry module by its real path, so a skill folder reached
// through a symlink must compare real paths or every command silently no-ops.
function samePath(a, b) {
  try { return fs.realpathSync(a) === fs.realpathSync(b); } catch { return path.resolve(a) === path.resolve(b); }
}
const isMain = process.argv[1] && samePath(process.argv[1], fileURLToPath(import.meta.url));

if (isMain) {
  const cmd = process.argv[2];
  const [opts, rest] = parseArgs(process.argv.slice(3));

  if (cmd === 'start') await cmdStart(opts);
  else if (cmd === '__supervise') await cmdSupervise(process.argv[3]);
  else if (cmd === 'collect') await cmdCollect(rest[0] || die('collect needs a run_id'), opts);
  else if (cmd === 'status') cmdStatus(rest[0] || die('status needs a run_id'));
  else if (cmd === 'list') cmdList();
  else if (cmd === 'doctor') cmdDoctor();
  else if (cmd === 'contract') cmdContract();
  else if (cmd === 'prune') cmdPrune(opts);
  else { console.log(HELP); process.exit(cmd ? 2 : 0); }
}
