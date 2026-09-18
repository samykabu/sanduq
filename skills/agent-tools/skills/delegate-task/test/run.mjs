#!/usr/bin/env node
// Characterization + contract suite for delegate.mjs.
//
//   node test/run.mjs      (from this skill's directory)
//
// Two kinds of case live here:
//
//   CONTRACT   asserts a rule from contracts/. Breaking one is a contract break.
//   REPAIR-Dn  pins a defect that v1 shipped. The comment records what v1 DID,
//              so the test explains itself without needing the old source.
//
// Node built-ins only. No network, no harness CLI is launched: the harness end of
// every case is a captured or synthesised event stream.

import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn, spawnSync, execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { StringDecoder } from 'node:string_decoder';

import {
  HARNESSES, resolveStatus, parseEnvelope, parsePorcelainZ, claimMismatch,
  readOnlyVerdict, normaliseResult, tokens, envelope, deltaEnvelope,
  gitCapture, gitCompare, positiveIntEnv, finalizeOnce, makeRetention,
} from '../delegate.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DRIVER = path.join(HERE, '..', 'delegate.mjs');
const FIX = path.join(HERE, 'fixtures');

let pass = 0, fail = 0;
const failures = [];
const pending = [];

const ok = () => { pass++; process.stdout.write('.'); };
const bad = (name, e) => { fail++; failures.push([name, e]); process.stdout.write('x'); };

function t(name, fn) {
  try {
    const r = fn();
    // An async case is queued and awaited before the summary, so a rejection
    // cannot be swallowed into a false green.
    if (r && typeof r.then === 'function') {
      pending.push(r.then(ok, (e) => bad(name, e)));
      return;
    }
    ok();
  } catch (e) { bad(name, e); }
}

const fixture = (n) => fs.readFileSync(path.join(FIX, n), 'utf8');

/* =======================================================================
   CONTRACT 3a - terminal status precedence
   ======================================================================= */

const P = (over = {}) => ({
  status: 'successful', reason: '', complete: true, text: '', tokens: tokens({}), ...over,
});

t('CONTRACT 3a-1 timeout outranks everything', () => {
  const r = resolveStatus({ timedOut: true, exitCode: 0, parse: P(), self: { status: 'successful' } });
  assert.equal(r.status, 'abandoned');
  assert.equal(r.provenance.primary, 'timeout');
});

t('CONTRACT 3a-1 timeout keeps the success telemetry as evidence', () => {
  const r = resolveStatus({ timedOut: true, exitCode: 0, parse: P() });
  assert.ok(r.provenance.evidence.some((e) => e.includes('harness telemetry: successful')),
    'a timeout after partial success telemetry must not discard that fact');
});

t('CONTRACT 3a-2 spawn error outranks telemetry', () => {
  const r = resolveStatus({ spawnError: 'ENOENT', exitCode: null, parse: P() });
  assert.equal(r.status, 'failed');
  assert.equal(r.provenance.primary, 'spawn_error');
});

t('CONTRACT 3a-3 signal outranks exit code', () => {
  const r = resolveStatus({ signal: 'SIGKILL', exitCode: 0, parse: P() });
  assert.equal(r.status, 'failed');
  assert.equal(r.provenance.primary, 'signal');
});

// ---- the D1 repair -----------------------------------------------------
// v1 passed the process exit code into every adapter and no adapter read it,
// and the resolution had no exit-code branch. This exact input published
// `successful`, contradicting the precedence v1's own README documented.
t('REPAIR-D1 non-zero exit beats success-shaped telemetry', () => {
  const r = resolveStatus({ exitCode: 1, parse: P({ status: 'successful' }) });
  assert.equal(r.status, 'failed', 'v1 published this as successful');
  assert.equal(r.provenance.primary, 'exit_code');
});

t('REPAIR-D1 non-zero exit beats a self-reported success too', () => {
  const r = resolveStatus({ exitCode: 3, parse: P(), self: { status: 'successful' } });
  assert.equal(r.status, 'failed');
  assert.equal(r.provenance.primary, 'exit_code');
});

t('CONTRACT 3a-4 exit 0 does not rescue failed telemetry', () => {
  const r = resolveStatus({ exitCode: 0, parse: P({ status: 'failed', reason: 'turn.failed' }) });
  assert.equal(r.status, 'failed');
  assert.equal(r.provenance.primary, 'harness_telemetry');
});

t('CONTRACT 3a-5 a parse exception is failed, not successful', () => {
  const r = resolveStatus({ exitCode: 0, parse: P({ parseError: true, reason: 'parse error: boom' }) });
  assert.equal(r.status, 'failed');
  assert.equal(r.provenance.primary, 'parse_error');
});

t('CONTRACT 3a-6 incomplete telemetry is abandoned', () => {
  const r = resolveStatus({ exitCode: 0, parse: P({ complete: false, reason: 'no turn.completed event' }) });
  assert.equal(r.status, 'abandoned');
  assert.equal(r.provenance.primary, 'telemetry_incomplete');
});

// gotcha 1: the case the self-report exists to catch.
t('CONTRACT 3a-8 self-reported abandoned refines a clean exit', () => {
  const r = resolveStatus({ exitCode: 0, parse: P(), self: { status: 'abandoned' } });
  assert.equal(r.status, 'abandoned');
  assert.equal(r.provenance.primary, 'self_report');
});

t('CONTRACT 3a-8 self-reported success cannot rescue a failed harness', () => {
  const r = resolveStatus({ exitCode: 0, parse: P({ status: 'failed' }), self: { status: 'successful' } });
  assert.equal(r.status, 'failed');
});

t('CONTRACT 3b head movement forces review-required', () => {
  const r = resolveStatus({ exitCode: 0, parse: P(), headMoved: true, allowCommit: false });
  assert.equal(r.status, 'failed');
  assert.equal(r.provenance.primary, 'head_moved');
});

t('CONTRACT 3b --allow-commit suppresses the head-moved gate', () => {
  const r = resolveStatus({ exitCode: 0, parse: P(), headMoved: true, allowCommit: true });
  assert.equal(r.status, 'successful');
});

t('CONTRACT 3a-9 clean run is successful', () => {
  const r = resolveStatus({ exitCode: 0, parse: P(), self: { status: 'successful' } });
  assert.equal(r.status, 'successful');
});

t('CONTRACT 3b a staged change alone forces review-required', () => {
  const r = resolveStatus({ exitCode: 0, parse: P(), indexMoved: true, allowCommit: false });
  assert.equal(r.status, 'failed');
  assert.equal(r.provenance.primary, 'index_moved');
});

// The ladder must be TOTAL. An adapter regression that returns undefined must
// not escape the three-status vocabulary into the published result.
t('CONTRACT 3a the ladder is total: an invalid adapter status is parse_error', () => {
  const r = resolveStatus({ exitCode: 0, parse: P({ status: undefined }) });
  assert.equal(r.status, 'failed');
  assert.equal(r.provenance.primary, 'parse_error');
  const r2 = resolveStatus({ exitCode: 0, parse: P({ status: 'mostly-fine' }) });
  assert.equal(r2.status, 'failed');
  assert.equal(r2.provenance.primary, 'parse_error');
});

t('CONTRACT 3a evidence records the watchdog, not only the telemetry', () => {
  const r = resolveStatus({ timedOut: true, exitCode: null, parse: P() });
  assert.ok(r.provenance.evidence.some((e) => /watchdog fired/.test(e)));
});

t('CONTRACT 3a a spawn error is named in evidence', () => {
  const r = resolveStatus({ spawnError: 'EACCES', exitCode: null, parse: P() });
  assert.ok(r.provenance.evidence.some((e) => /EACCES/.test(e)));
});

// An integrity signal must never vanish just because an earlier rule won the
// primary slot - that would hide the very thing it exists to surface.
t('CONTRACT 3b a moved HEAD stays in evidence even when another rule wins', () => {
  const r = resolveStatus({ exitCode: 0, parse: P({ status: 'failed', reason: 'turn.failed' }), headMoved: true });
  assert.equal(r.provenance.primary, 'harness_telemetry');
  assert.ok(r.provenance.evidence.some((e) => /HEAD moved/.test(e)),
    'the commit still happened; losing it would hide an integrity event');
});

t('CONTRACT 3b --allow-commit is recorded in evidence, not silently applied', () => {
  const r = resolveStatus({ exitCode: 0, parse: P(), headMoved: true, allowCommit: true });
  assert.equal(r.status, 'successful');
  assert.ok(r.provenance.evidence.some((e) => /--allow-commit/.test(e)));
});

/* =======================================================================
   Adapter cross-product - every adapter, every harness-level outcome
   ======================================================================= */

for (const [id, h] of Object.entries(HARNESSES)) {
  t(`CONTRACT adapter ${id} survives empty stdout without throwing`, () => {
    const p = h.parse('', '', 0);
    assert.ok(['successful', 'failed', 'abandoned'].includes(p.status));
    assert.ok(p.tokens, 'every adapter must return a tokens object');
  });

  t(`CONTRACT adapter ${id} reports unavailable fidelity when it saw no usage`, () => {
    const p = h.parse('', '', 0);
    if (p.tokens.total === 0) {
      assert.notEqual(p.tokens.fidelity, 'exact',
        'zero tokens reported as "exact" claims the run was free when it is unknown');
    }
  });

  t(`CONTRACT adapter ${id} ignores non-JSON noise on stdout`, () => {
    const p = h.parse('warning: something\nnot json at all\n', '', 0);
    assert.ok(p, 'a banner ahead of the stream must not crash the adapter');
  });

  // A null cost or model must be traceable to "this CLI never says" rather than
  // read as a parsing failure.
  t(`CONTRACT adapter ${id} declares what its stream actually reports`, () => {
    assert.ok(h.reports && typeof h.reports.cost === 'boolean' && typeof h.reports.model === 'boolean',
      `${id} must declare reports:{cost,model}`);
  });

  t(`CONTRACT adapter ${id} declares a resume and capture tier`, () => {
    assert.ok(['verified', 'experimental', 'none'].includes(h.resume));
    assert.ok(['streaming', 'terminal'].includes(h.session_capture));
    assert.ok(['enforced', 'plan', 'tools-allowlist', 'default-deny'].includes(h.readOnly),
      `${id} must declare what --sandbox actually requests`);
  });
}

/* =======================================================================
   REPAIR-C4 - --sandbox must request a real read-only mode everywhere
   ======================================================================= */
// v1: copilot's sandbox branch passed --allow-all-tools (every tool), and
// opencode's merely dropped --auto. Neither requested a documented read-only
// mode, so containment was never established for 2 of 5 harnesses.

t('REPAIR-C4 copilot sandbox requests plan mode, not every tool', () => {
  const a = HARNESSES.copilot.args({ task: 'x', model: null, perm: 'sandbox', resume: null });
  assert.ok(a.includes('--mode') && a[a.indexOf('--mode') + 1] === 'plan');
  assert.ok(!a.includes('--allow-all-tools'), 'v1 passed --allow-all-tools on the sandbox path');
  assert.ok(!a.includes('--allow-all'));
});

t('REPAIR-C4 opencode sandbox selects the plan agent and never --auto', () => {
  const a = HARNESSES.opencode.args({ task: 'x', model: null, perm: 'sandbox', resume: null });
  assert.ok(a.includes('--agent') && a[a.indexOf('--agent') + 1] === 'plan');
  assert.ok(!a.includes('--auto'), '--auto would approve the very asks that make plan mode read-only');
});

t('CONTRACT every harness sandbox argv differs from its bypass argv', () => {
  for (const [id, h] of Object.entries(HARNESSES)) {
    const s = h.args({ task: 'x', model: null, perm: 'sandbox', resume: null }).join(' ');
    const b = h.args({ task: 'x', model: null, perm: 'bypass', resume: null }).join(' ');
    assert.notEqual(s, b, `${id}: --sandbox changes nothing`);
  }
});

t('CONTRACT permission_mode_applied is stated per harness', () => {
  for (const [id, h] of Object.entries(HARNESSES)) {
    assert.ok(h.mode('sandbox').length > 0, `${id} has no sandbox mode label`);
    assert.ok(h.mode('bypass').length > 0, `${id} has no bypass mode label`);
  }
});

/* =======================================================================
   Resume argv
   ======================================================================= */

t('CONTRACT resume argv is harness-shaped', () => {
  assert.deepEqual(
    HARNESSES.codex.args({ task: 't', model: null, perm: 'bypass', resume: 'th_1' }).slice(0, 3),
    ['exec', 'resume', 'th_1'], 'codex resume is a subcommand, not a flag');
  assert.ok(HARNESSES.claude.args({ task: 't', model: null, perm: 'bypass', resume: 's1' }).includes('--resume'));
  assert.ok(HARNESSES.opencode.args({ task: 't', model: null, perm: 'bypass', resume: 's1' }).includes('--session'));
  assert.ok(HARNESSES.copilot.args({ task: 't', model: null, perm: 'bypass', resume: 's1' }).includes('--resume=s1'));
  assert.ok(HARNESSES.pi.args({ task: 't', model: null, perm: 'bypass', resume: 's1' }).includes('--session'));
});

t('REPAIR-pi no --no-session, or there is nothing to resume from', () => {
  const a = HARNESSES.pi.args({ task: 't', model: null, perm: 'bypass', resume: null });
  assert.ok(!a.includes('--no-session'),
    'v1 hard-coded --no-session, which made pi structurally unresumable');
});

t('CONTRACT session extractors pull the id each CLI actually emits', () => {
  assert.equal(HARNESSES.codex.session({ thread_id: 'th_9' }), 'th_9');
  assert.equal(HARNESSES.codex.session({ thread: { id: 'th_8' } }), 'th_8');
  assert.equal(HARNESSES.claude.session({ session_id: 'cs_1' }), 'cs_1');
  assert.equal(HARNESSES.opencode.session({ sessionID: 'oc_1' }), 'oc_1');
  assert.equal(HARNESSES.copilot.session({ type: 'result', sessionId: 'cp_1' }), 'cp_1');
  assert.equal(HARNESSES.pi.session({ type: 'session', id: 'pi_1' }), 'pi_1');
  assert.equal(HARNESSES.pi.session({ type: 'message_end', id: 'not-a-session' }), null);
});

/* =======================================================================
   Token normalisation - gotcha 2, the thing a third-party relay got wrong
   ======================================================================= */

t('CONTRACT claude input fields are DISJOINT and must be summed', () => {
  const p = HARNESSES.claude.parse(fixture('claude-success.jsonl'), '', 0);
  // 2 fresh + 58063 cache-write + 0 cache-read. Reading input_tokens alone
  // reports 2 for a request that really sent 58,065.
  assert.equal(p.tokens.input_fresh, 2);
  assert.equal(p.tokens.input_total, 58065);
  assert.equal(p.tokens.fidelity, 'exact');
  assert.equal(p.usage_raw.input_tokens, 2, 'raw telemetry is retained for audit');
});

t('CONTRACT codex input_tokens INCLUDES cached - subtract for fresh', () => {
  const p = HARNESSES.codex.parse(fixture('codex-success.jsonl'), '', 0);
  assert.equal(p.tokens.input_total, 65946);
  assert.equal(p.tokens.cache_read, 53504);
  assert.equal(p.tokens.input_fresh, 65946 - 53504);
});

// Round 8: `step_finish` is emitted per step, including intermediate tool steps.
// Accepting any of them as terminal let a stream cut mid-run publish a verdict.
t('REPAIR-R8 opencode: a stream cut after a tool step is incomplete', () => {
  const p = HARNESSES.opencode.parse(
    '{"type":"step_finish","part":{"tokens":{"input":5,"output":1},"reason":"tool"}}\n', '', 0);
  assert.equal(p.complete, false, 'an intermediate tool step is not a terminal event');
  assert.equal(p.status, 'abandoned');
  const r = resolveStatus({ exitCode: 0, parse: p });
  assert.equal(r.provenance.primary, 'telemetry_incomplete');
});

t('CONTRACT opencode: terminal reasons end a turn', () => {
  const mk = (reason) => HARNESSES.opencode.parse(
    `{"type":"step_finish","part":{"tokens":{"input":5,"output":1},"reason":"${reason}"}}\n`, '', 0);
  assert.equal(mk('stop').complete, true);
  assert.equal(mk('stop').status, 'successful');
  assert.equal(mk('length').complete, true);
  assert.equal(mk('length').status, 'abandoned');
  assert.equal(mk('error').complete, true);
  assert.equal(mk('error').status, 'failed');
});

t('CONTRACT opencode sums per-step usage rather than last-wins', () => {
  const p = HARNESSES.opencode.parse(fixture('opencode-success.jsonl'), '', 0);
  assert.equal(p.tokens.input_fresh, 300, 'three steps of 100 must sum, not last-win');
  assert.equal(p.tokens.output_total, 60);
});

// C9/C10: an adapter must key completeness on a TERMINAL event, and must not
// claim `exact` fidelity when no usage was reported. Both were D1-shaped
// false-success paths: a stream with no terminal record read as a clean run.
t('REPAIR-C9 claude: arbitrary JSON is not a result record', () => {
  const p = HARNESSES.claude.parse('{"foo":1}\n', '', 0);
  assert.equal(p.complete, false, 'any last JSON object was previously read as a complete success');
  assert.equal(p.status, 'abandoned');
  assert.equal(p.tokens.fidelity, 'unavailable');
});

t('REPAIR-C10 claude: a result record with no usage is not "exact"', () => {
  const p = HARNESSES.claude.parse('{"type":"result","subtype":"success","result":"hi"}\n', '', 0);
  assert.equal(p.complete, true);
  assert.equal(p.tokens.fidelity, 'unavailable',
    'exact zeroes claim the run was free when the truth is unknown');
});

t('REPAIR-C9 pi: an intermediate usage object does not make a run complete', () => {
  const p = HARNESSES.pi.parse('{"type":"message_start","usage":{"input_tokens":5}}\n', '', 0);
  assert.equal(p.complete, false, 'a truncated stream previously read as successful');
  assert.equal(p.status, 'abandoned');
});

t('CONTRACT pi: a message_end terminates the run', () => {
  const p = HARNESSES.pi.parse('{"type":"session","id":"pi_1"}\n{"type":"message_end","message":{"role":"assistant","content":"hi","usage":{"input_tokens":5,"output_tokens":2}}}\n', '', 0);
  assert.equal(p.complete, true);
  assert.equal(p.status, 'successful');
});

t('REPAIR-C9 copilot: no result event is incomplete', () => {
  const p = HARNESSES.copilot.parse('{"type":"assistant.message","data":{"content":"hi"}}\n', '', 0);
  assert.equal(p.complete, false);
});

t('REPAIR-C10 codex: turn.completed with no usage is not "exact"', () => {
  const p = HARNESSES.codex.parse('{"type":"turn.completed"}\n', '', 0);
  assert.equal(p.complete, true);
  assert.equal(p.tokens.fidelity, 'unavailable');
});

t('REPAIR-C10 opencode: steps with no token block are not "exact"', () => {
  const p = HARNESSES.opencode.parse('{"type":"step_finish","part":{"reason":"stop"}}\n', '', 0);
  assert.equal(p.tokens.fidelity, 'unavailable');
});

t('CONTRACT copilot reports unavailable, not zero-as-free', () => {
  const p = HARNESSES.copilot.parse(fixture('copilot-success.jsonl'), '', 0);
  assert.equal(p.tokens.fidelity, 'unavailable');
  assert.equal(p.tokens.total, 0);
});

t('CONTRACT tokens.total is input_total + output_total', () => {
  const t1 = tokens({ input_total: 10, output_total: 5, cache_read: 99 });
  assert.equal(t1.total, 15, 'cache_read is a component of input_total, not an addend');
});

/* =======================================================================
   Telemetry completeness from real streams
   ======================================================================= */

t('CONTRACT codex turn.failed is failed telemetry', () => {
  const p = HARNESSES.codex.parse(fixture('codex-turn-failed.jsonl'), '', 0);
  assert.equal(p.status, 'failed');
  assert.equal(p.complete, true);
});

// gotcha 6: codex emits item.type "error" on runs that succeed.
t('CONTRACT an error event on a successful codex run is not failure', () => {
  const p = HARNESSES.codex.parse(fixture('codex-error-event-but-ok.jsonl'), '', 0);
  assert.equal(p.status, 'successful');
});

t('CONTRACT a truncated codex stream is incomplete, not successful', () => {
  const p = HARNESSES.codex.parse(fixture('codex-truncated.jsonl'), '', 0);
  assert.equal(p.complete, false);
  const r = resolveStatus({ exitCode: 0, parse: p });
  assert.equal(r.status, 'abandoned');
  assert.equal(r.provenance.primary, 'telemetry_incomplete');
});

/* =======================================================================
   REPAIR-D5 - typed envelope parse
   ======================================================================= */

t('CONTRACT the envelope round-trips', () => {
  const text = `done\n\n<<<DELEGATION_RESULT>>>\nstatus: successful\nsummary: I did it.\nfiles_changed: a.txt, b.txt\n<<<END_DELEGATION_RESULT>>>`;
  const e = parseEnvelope(text);
  assert.equal(e.status, 'successful');
  assert.equal(e.summary, 'I did it.');
  assert.equal(e.files_changed, 'a.txt, b.txt');
});

t('REPAIR-D5 literal "none" is not a changed file', () => {
  const text = `<<<DELEGATION_RESULT>>>\nstatus: successful\nsummary: read only.\nfiles_changed: none\n<<<END_DELEGATION_RESULT>>>`;
  assert.equal(parseEnvelope(text).files_changed, null,
    'v1 published the string "none" as a truthy files-changed report');
});

t('REPAIR-D5 an unknown status word is rejected, not passed through', () => {
  const text = `<<<DELEGATION_RESULT>>>\nstatus: mostly-ok\nsummary: hm.\n<<<END_DELEGATION_RESULT>>>`;
  assert.equal(parseEnvelope(text).status, null);
});

t('REPAIR-D5 duplicate keys take the FIRST, not last-wins', () => {
  const text = `<<<DELEGATION_RESULT>>>\nstatus: abandoned\nstatus: successful\nsummary: x\n<<<END_DELEGATION_RESULT>>>`;
  assert.equal(parseEnvelope(text).status, 'abandoned',
    'last-wins lets a delegate overwrite its own verdict');
});

t('CONTRACT no envelope means no self-report', () => {
  assert.equal(parseEnvelope('just some prose'), null);
  assert.equal(parseEnvelope(''), null);
});

/* =======================================================================
   Envelope policy - Amendment 4: resume repeats every rule
   ======================================================================= */

t('CONTRACT the envelope forbids committing by default', () => {
  const e = envelope({ task: 't', cwd: '/w', constraints: [], allowCommit: false });
  assert.match(e, /Do NOT run `git add` or `git commit`/);
});

t('CONTRACT --allow-commit replaces the prohibition', () => {
  const e = envelope({ task: 't', cwd: '/w', constraints: [], allowCommit: true });
  assert.ok(!/Do NOT run `git add`/.test(e));
});

t('AMENDMENT-4 a resumed dispatch repeats the no-commit rule', () => {
  const d = deltaEnvelope({ task: 'fix it', cwd: '/w', constraints: [], allowCommit: false, parent: 'codex-1' });
  assert.match(d, /Do NOT run `git add` or `git commit`/,
    'policy is not inherited: a parent session may be stale or adversarial');
  assert.match(d, /Stay inside the working directory/);
  assert.match(d, /<<<DELEGATION_RESULT>>>/, 'the resumed turn still owes a result block');
});

t('AMENDMENT-4 the delta envelope names its parent run', () => {
  const d = deltaEnvelope({ task: 'x', cwd: '/w', constraints: [], allowCommit: false, parent: 'codex-abc' });
  assert.match(d, /codex-abc/);
});

/* =======================================================================
   The retention window - tested directly, not only through side effects
   ======================================================================= */

// Round 6 mutation-tested three separate defects into an inlined version of this
// and all three survived a full end-to-end suite, because their damage was
// invisible from outside. It is a module now so the policy itself can be pinned.

t('CONTRACT retention keeps the most recent records within budget', () => {
  const r = makeRetention(100);
  for (const l of ['a'.repeat(30), 'b'.repeat(30), 'c'.repeat(30), 'd'.repeat(30)]) r.add(l);
  const kept = r.lines();
  assert.equal(kept[kept.length - 1][0], 'd', 'the newest record must survive');
  assert.ok(r._bytes() <= 100 || kept.length === 1);
  assert.ok(r.dropped > 0, 'evicted records must be counted');
});

t('CONTRACT retention always keeps one record, even oversized', () => {
  const r = makeRetention(10);
  r.add('x'.repeat(5000));
  assert.equal(r.lines().length, 1,
    'dropping the only (usually terminal) record to honour a byte bound defeats the purpose');
});

// The budget is BYTES. A UTF-16 length under-measures multibyte telemetry by up
// to 3x, so char counting would silently hold far more than the name promises.
t('CONTRACT retention counts UTF-8 bytes, not UTF-16 characters', () => {
  const rec = 'あ'.repeat(100);                       // 100 chars, 300 bytes
  assert.equal(rec.length, 100);
  assert.equal(Buffer.byteLength(rec, 'utf8'), 300);
  const r = makeRetention(320);
  for (let i = 0; i < 4; i++) r.add(rec);
  assert.equal(r.lines().length, 1,
    'counting characters would keep 3 records inside a 320-BYTE window');
  assert.equal(r.dropped, 3);
});

t('CONTRACT the retention backing array stays bounded under high churn', () => {
  const r = makeRetention(200);
  for (let i = 0; i < 20_000; i++) r.add(`{"i":${i}}`);
  assert.ok(r._size() < 2000,
    `the backing array grew to ${r._size()} - evicted slots are never compacted away`);
  assert.ok(r.lines().every((l) => l !== null));
});

/* =======================================================================
   CONTRACT 3b - git fields
   ======================================================================= */

t('CONTRACT porcelain -z parses NUL records', () => {
  const recs = parsePorcelainZ('?? new.txt\0 M src/a.js\0');
  assert.equal(recs.length, 2);
  assert.equal(recs[0].path, 'new.txt');
  assert.equal(recs[1].xy, ' M');
});

t('CONTRACT a rename record consumes its origin path', () => {
  const recs = parsePorcelainZ('R  dst.txt\0src.txt\0?? other.txt\0');
  assert.equal(recs.length, 2, 'the origin path is a field, not a record');
  assert.equal(recs[0].path, 'dst.txt');
  assert.equal(recs[0].orig, 'src.txt');
  assert.equal(recs[1].path, 'other.txt');
});

t('CONTRACT a path containing a space survives -z parsing', () => {
  const recs = parsePorcelainZ('?? my file.txt\0');
  assert.equal(recs[0].path, 'my file.txt');
});

t('CONTRACT conflicted entries are dirty like any other', () => {
  const recs = parsePorcelainZ('UU both.txt\0');
  assert.equal(recs[0].xy, 'UU');
});

t('CONTRACT null porcelain propagates as null, not empty', () => {
  assert.equal(parsePorcelainZ(null), null);
});

// The tri-state. Collapsing unknown to false is the false assurance a tripwire
// must never give.
t('CONTRACT read_only_violation true on a detected delta', () => {
  assert.equal(readOnlyVerdict({ dirty_paths_changed: ['a'], head_changed: false, index_changed: false, coverage_complete: true }), true);
});

t('CONTRACT read_only_violation true on a moved HEAD alone', () => {
  assert.equal(readOnlyVerdict({ dirty_paths_changed: [], head_changed: true, index_changed: false, coverage_complete: true }), true);
});

t('CONTRACT read_only_violation false only with complete coverage', () => {
  assert.equal(readOnlyVerdict({ dirty_paths_changed: [], head_changed: false, index_changed: false, coverage_complete: true }), false);
});

t('CONTRACT incomplete coverage is null, never false', () => {
  assert.equal(readOnlyVerdict({ dirty_paths_changed: [], head_changed: false, index_changed: false, coverage_complete: false }), null);
});

t('CONTRACT no git means null, never false', () => {
  assert.equal(readOnlyVerdict({ dirty_paths_changed: null, head_changed: null, index_changed: null, coverage_complete: false }), null);
});

t('CONTRACT proof of a write beats incomplete coverage', () => {
  assert.equal(readOnlyVerdict({ dirty_paths_changed: ['a'], head_changed: null, index_changed: null, coverage_complete: false }), true);
});

/* =======================================================================
   files_mismatch - compared against the DELTA only
   ======================================================================= */

t('CONTRACT a matching claim is not a mismatch', () => {
  assert.equal(claimMismatch('a.txt, b.txt', ['a.txt', 'b.txt'], true), false);
});

t('CONTRACT an under-claim is a mismatch', () => {
  assert.equal(claimMismatch('a.txt', ['a.txt', 'b.txt'], true), true);
});

t('CONTRACT baseline dirt must not become an accusation', () => {
  // The delegate touched a.txt. b.txt was already dirty before the run and is
  // NOT in the delta. Comparing against the whole dirty tree would call this a lie.
  assert.equal(claimMismatch('a.txt', ['a.txt'], true), false);
});

t('CONTRACT unknown coverage reports null, not agreement', () => {
  assert.equal(claimMismatch('a.txt', ['a.txt'], false), null);
  assert.equal(claimMismatch('a.txt', null, true), null);
});

t('CONTRACT "none" claimed against an empty delta agrees', () => {
  assert.equal(claimMismatch('none', [], true), false);
});

t('CONTRACT path separators are normalised before comparison', () => {
  assert.equal(claimMismatch('src\\a.js', ['src/a.js'], true), false);
});

/* =======================================================================
   CONTRACT 3c - v1 backward read
   ======================================================================= */

t('CONTRACT a v1 result is readable and labelled legacy', () => {
  const v1 = {
    run_id: 'codex-old', harness: 'codex', harness_label: 'OpenAI Codex', tier: 'verified',
    status: 'successful', summary: 'did a thing', files_changed: 'report.txt',
    tokens: tokens({ input_total: 10, output_total: 2 }), exit_code: 0, duration_ms: 100,
    task: 't', cwd: '/w', permission: 'bypass', started_at: 'x', ended_at: 'y',
  };
  const n = normaliseResult(v1);
  assert.equal(n.legacy, true);
  assert.equal(n.schema, 'delegate-task.result.v1');
  assert.equal(n.files_claimed, 'report.txt', "v1's files_changed was always a self-report");
  assert.equal(n.status_provenance.primary, 'legacy');
});

t('CONTRACT a v1 result never claims measurements it never made', () => {
  const n = normaliseResult({ run_id: 'x', status: 'successful', tokens: tokens({}) });
  for (const f of ['git_visible_after', 'dirty_paths_changed', 'head_changed',
    'index_changed', 'read_only_violation', 'session_id', 'harness_version']) {
    assert.equal(n[f], null, `${f} must be null on a v1 run, not a value`);
  }
  assert.equal(n.coverage_complete, false);
});

t('CONTRACT a v2 result passes through untouched', () => {
  const v2 = { schema: 'delegate-task.result.v2', run_id: 'r', status: 'successful' };
  assert.equal(normaliseResult(v2), v2);
});

/* =======================================================================
   REPAIR-D3 - argument validation happens before anything detaches
   ======================================================================= */

function driver(args, opts = {}) {
  return spawnSync(process.execPath, [DRIVER, ...args], {
    encoding: 'utf8', timeout: 30_000, env: { ...process.env, ...(opts.env || {}) },
  });
}

const scratchRuns = fs.mkdtempSync(path.join(os.tmpdir(), 'delegate-test-'));
const RUNS_ENV = { DELEGATE_RUNS_DIR: scratchRuns };

t('REPAIR-D3 a NaN timeout is rejected, not turned into an instant kill', () => {
  const r = driver(['start', '--harness', 'codex', '--task', 'x', '--timeout', 'abc'], { env: RUNS_ENV });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /--timeout must be a positive number/);
});

t('REPAIR-D3 a zero timeout is rejected', () => {
  const r = driver(['start', '--harness', 'codex', '--task', 'x', '--timeout', '0'], { env: RUNS_ENV });
  assert.notEqual(r.status, 0);
});

t('REPAIR-D3 a timeout past the timer ceiling is rejected', () => {
  const r = driver(['start', '--harness', 'codex', '--task', 'x', '--timeout', '99999999'], { env: RUNS_ENV });
  assert.notEqual(r.status, 0);
});

t('REPAIR-D3 a negative --wait is rejected', () => {
  const r = driver(['collect', 'nope', '--wait', '-5'], { env: RUNS_ENV });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /--wait must be a non-negative/);
});

t('REPAIR-D3 a missing --cwd is rejected before anything detaches', () => {
  const r = driver(['start', '--harness', 'codex', '--task', 'x', '--cwd',
    path.join(os.tmpdir(), 'definitely-not-here-9137')], { env: RUNS_ENV });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /--cwd does not exist/);
  assert.equal(fs.readdirSync(scratchRuns).length, 0, 'a rejected start must leave no run directory');
});

t('CONTRACT an unknown harness is rejected', () => {
  const r = driver(['start', '--harness', 'nope', '--task', 'x'], { env: RUNS_ENV });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /unknown harness/);
});

t('CONTRACT --raw and --resume are refused together', () => {
  const r = driver(['start', '--harness', 'codex', '--task', 'x', '--raw', '--resume', 'abc'], { env: RUNS_ENV });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /must carry its policy rules/);
});

t('CONTRACT resuming an unknown run fails loudly', () => {
  const r = driver(['start', '--harness', 'codex', '--task', 'x',
    '--resume', 'codex-19700101000000-abcdef'], { env: RUNS_ENV });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /no such run to resume/);
});

// Round 8 reproduced this: `status ../elsewhere` resolved outside the runs
// directory and returned a foreign run's result. The same resolver feeds
// collect, --resume and the internal supervise command, which write and launch.
t('CONTRACT a run id cannot escape the runs directory', () => {
  const outside = path.join(path.dirname(scratchRuns), 'delegate-foreign');
  fs.mkdirSync(outside, { recursive: true });
  fs.writeFileSync(path.join(outside, 'meta.json'), JSON.stringify({
    run_id: 'x', harness: 'codex', task: 'foreign', cwd: os.tmpdir(),
    permission: 'bypass', started_at: new Date(0).toISOString(), supervisor_pid: 2147483646,
  }));
  fs.writeFileSync(path.join(outside, 'result.json'), JSON.stringify({
    schema: 'delegate-task.result.v2', run_id: 'x', status: 'successful',
    status_provenance: { primary: 'harness_telemetry', evidence: [] }, tokens: {},
  }));

  const rel = `..${path.sep}${path.basename(outside)}`;
  for (const hostile of [rel, '../delegate-foreign', path.resolve(outside), 'a/b', '..', '.']) {
    for (const cmd of ['status', 'collect']) {
      const r = driver([cmd, hostile], { env: RUNS_ENV });
      assert.notEqual(r.status, 0, `${cmd} ${hostile} was accepted`);
      assert.match(r.stderr, /invalid run id|does not resolve inside/,
        `${cmd} ${hostile}: ${r.stderr}`);
      assert.ok(!/foreign/.test(r.stdout), `${cmd} ${hostile} leaked a foreign run`);
    }
  }
  fs.rmSync(outside, { recursive: true, force: true });
});

t('CONTRACT collect on an unknown run fails loudly', () => {
  const r = driver(['collect', 'codex-nope'], { env: RUNS_ENV });
  assert.notEqual(r.status, 0);
});

// A cap that parses to NaN fails every comparison, so `written > NaN` is always
// false and the "bound" silently becomes unlimited.
t('REPAIR-B6 an unparseable output cap falls back instead of meaning unlimited', () => {
  assert.equal(positiveIntEnv('__DELEGATE_TEST_CAP__', 1234), 1234);
  process.env.__DELEGATE_TEST_CAP__ = 'garbage';
  assert.equal(positiveIntEnv('__DELEGATE_TEST_CAP__', 1234), 1234);
  process.env.__DELEGATE_TEST_CAP__ = '-5';
  assert.equal(positiveIntEnv('__DELEGATE_TEST_CAP__', 1234), 1234);
  process.env.__DELEGATE_TEST_CAP__ = '4096';
  assert.equal(positiveIntEnv('__DELEGATE_TEST_CAP__', 1234), 4096);
  delete process.env.__DELEGATE_TEST_CAP__;
});

t('REPAIR-B19 a flag missing its value is a normal CLI error', () => {
  for (const flag of ['--model', '--cwd', '--keep-env', '--constraint', '--harness']) {
    const r = driver(['start', flag], { env: RUNS_ENV });
    assert.notEqual(r.status, 0, `${flag} with no value should fail cleanly`);
    assert.match(r.stderr, /needs a value|required/, `${flag}: ${r.stderr}`);
  }
});

t('CONTRACT argument validation runs before binary resolution', () => {
  // Otherwise a bad flag reports "not installed" on a machine lacking that CLI,
  // which is a misleading error and made the D3 tests order-dependent.
  const r = driver(['start', '--harness', 'codex', '--task', 'x', '--timeout', 'abc'],
    { env: { ...RUNS_ENV, DELEGATE_BIN_CODEX: path.join(os.tmpdir(), 'definitely-absent-cli') } });
  assert.match(r.stderr, /--timeout must be a positive number/,
    'the timeout error must win over the missing-binary error');
});

t('CONTRACT doctor runs and names every harness', () => {
  const r = driver(['doctor'], { env: RUNS_ENV });
  assert.equal(r.status, 0);
  for (const id of Object.keys(HARNESSES)) assert.ok(r.stdout.includes(id), `doctor omits ${id}`);
  assert.match(r.stdout, /Treat them as sensitive/, 'doctor must carry the artifact warning');
});

t('CONTRACT prune is a dry run without --yes', () => {
  const r = driver(['prune', '--keep', '0'], { env: RUNS_ENV });
  assert.equal(r.status, 0);
  assert.ok(!/^removing/m.test(r.stdout));
});

/* =======================================================================
   Streaming - chunk boundaries must not corrupt a session id
   ======================================================================= */

t('CONTRACT a multibyte character split across chunks decodes intact', () => {
  const dec = new StringDecoder('utf8');
  const buf = Buffer.from('{"thread_id":"th_café"}\n', 'utf8');
  const a = dec.write(buf.subarray(0, 18));
  const b = dec.write(buf.subarray(18));
  const line = (a + b).trim();
  assert.equal(JSON.parse(line).thread_id, 'th_café',
    'decoding per-chunk without a StringDecoder yields U+FFFD and a wrong session id');
});

/* =======================================================================
   Git integration - against a real throwaway repository
   ======================================================================= */

function hasGit() {
  try { execFileSync('git', ['--version'], { stdio: 'ignore' }); return true; } catch { return false; }
}

if (hasGit()) {
  const repo = fs.mkdtempSync(path.join(os.tmpdir(), 'delegate-git-'));
  const g = (...a) => execFileSync('git', ['-C', repo, ...a], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
  g('init', '-q');
  g('config', 'user.email', 'test@example.invalid');
  g('config', 'user.name', 'test');
  fs.writeFileSync(path.join(repo, 'tracked.txt'), 'one\n');
  g('add', '.');
  g('commit', '-qm', 'init');

  t('CONTRACT porcelain reports a clean tree as empty, not null', () => {
    const raw = execFileSync('git', ['-C', repo, '-c', 'status.relativePaths=false',
      'status', '--porcelain=v1', '-z'], { encoding: 'utf8' });
    assert.deepEqual(parsePorcelainZ(raw), []);
  });

  t('CONTRACT an edit to an ALREADY-DIRTY file is invisible to porcelain alone', () => {
    fs.writeFileSync(path.join(repo, 'tracked.txt'), 'two\n');
    const before = execFileSync('git', ['-C', repo, 'status', '--porcelain=v1', '-z'], { encoding: 'utf8' });
    fs.writeFileSync(path.join(repo, 'tracked.txt'), 'three\n');
    const after = execFileSync('git', ['-C', repo, 'status', '--porcelain=v1', '-z'], { encoding: 'utf8' });
    assert.equal(before, after,
      'this is exactly why the baseline set is content-fingerprinted, not just diffed by status line');
  });

  t('CONTRACT a real capture/compare round-trip detects a new file', () => {
    const before = gitCapture(repo);
    assert.ok(before.root, 'the throwaway repo must resolve a root');
    fs.writeFileSync(path.join(repo, 'fresh.txt'), 'x\n');
    const cmp = gitCompare(before, repo);
    assert.ok(cmp.dirty_paths_changed.includes('fresh.txt'));
    assert.equal(cmp.coverage_complete, true);
    assert.equal(readOnlyVerdict(cmp), true);
  });

  t('CONTRACT an edit to an already-dirty file IS caught by fingerprinting', () => {
    // The case porcelain alone cannot see - and the reason the baseline set is
    // content-hashed rather than status-diffed.
    fs.writeFileSync(path.join(repo, 'tracked.txt'), 'baseline-dirty\n');
    const before = gitCapture(repo);
    assert.ok(before.prints.has('tracked.txt'), 'the dirty file must be fingerprinted at baseline');
    fs.writeFileSync(path.join(repo, 'tracked.txt'), 'changed-during-run\n');
    const cmp = gitCompare(before, repo);
    assert.ok(cmp.dirty_paths_changed.includes('tracked.txt'),
      'porcelain is identical before and after; only the content hash catches this');
  });

  t('CONTRACT a file dirty before AND untouched during is NOT in the delta', () => {
    fs.writeFileSync(path.join(repo, 'tracked.txt'), 'left alone\n');
    const before = gitCapture(repo);
    fs.writeFileSync(path.join(repo, 'other.txt'), 'new\n');
    const cmp = gitCompare(before, repo);
    assert.ok(cmp.dirty_paths_changed.includes('other.txt'));
    assert.ok(!cmp.dirty_paths_changed.includes('tracked.txt'),
      'baseline dirt must never be reported as something the delegate changed');
  });

  t('CONTRACT a commit during the window sets head_changed', () => {
    const before = gitCapture(repo);
    g('add', '.');
    g('commit', '-qm', 'committed during the run window');
    const cmp = gitCompare(before, repo);
    assert.equal(cmp.head_changed, true);
    assert.equal(readOnlyVerdict(cmp), true, 'a moved HEAD alone is a violation signal');
  });

  t('CONTRACT staging without committing sets index_changed', () => {
    fs.writeFileSync(path.join(repo, 'staged.txt'), 'x\n');
    const before = gitCapture(repo);
    g('add', 'staged.txt');
    const cmp = gitCompare(before, repo);
    assert.equal(cmp.index_changed, true);
    assert.equal(readOnlyVerdict(cmp), true);
    g('reset', '-q');
  });

  // An untracked DIRECTORY (a submodule, or any tree) has a porcelain line that
  // never changes when its contents do. Calling that "covered" would manufacture
  // the false assurance the tri-state exists to prevent.
  t('REPAIR-C7 an unfingerprintable directory makes coverage incomplete', () => {
    fs.mkdirSync(path.join(repo, 'subtree'), { recursive: true });
    fs.writeFileSync(path.join(repo, 'subtree', 'inner.txt'), 'a\n');
    const before = gitCapture(repo);
    assert.ok(before.porcelain.some((r) => r.path.startsWith('subtree')));
    fs.writeFileSync(path.join(repo, 'subtree', 'inner.txt'), 'b\n');
    const cmp = gitCompare(before, repo);
    assert.equal(cmp.coverage_complete, false,
      'a directory cannot be content-hashed, so coverage is not complete');
    assert.equal(readOnlyVerdict(cmp), null,
      'unknown coverage with no proven delta must be null, never false');
    fs.rmSync(path.join(repo, 'subtree'), { recursive: true, force: true });
  });

  t('REPAIR-B13 a comma in a changed path makes the claim uncheckable, not a lie', () => {
    assert.equal(claimMismatch('a.txt', ['we,ird.txt'], true), null,
      'the envelope grammar is comma-separated; a comma in a path is ambiguous');
  });

  // M1 (round 3): nothing exercised the repository-identity guard, so deleting
  // it entirely went unnoticed. Replacing .git at the same path must not yield a
  // comparison presented as complete.
  t('CONTRACT a repository replaced at the same path is not comparable', () => {
    fs.writeFileSync(path.join(repo, 'before.txt'), 'x\n');
    const before = gitCapture(repo);
    assert.ok(before.id && before.id.rootCommit, 'baseline should have history');
    fs.rmSync(path.join(repo, '.git'), { recursive: true, force: true });
    execFileSync('git', ['-C', repo, 'init', '-q']);
    const cmp = gitCompare(before, repo);
    assert.equal(cmp.dirty_paths_changed, null,
      'two different repositories at one path are not comparable');
    assert.equal(cmp.coverage_complete, false);
    assert.equal(readOnlyVerdict(cmp), null);
    // put the repo back for any later case
    execFileSync('git', ['-C', repo, 'config', 'user.email', 'test@example.invalid']);
    execFileSync('git', ['-C', repo, 'config', 'user.name', 'test']);
  });

  fs.rmSync(repo, { recursive: true, force: true });
}

// A repository with no commits yet: HEAD is unborn, which is a KNOWN state.
// Conflating it with "unknown" made the first commit invisible to the gate.
if (hasGit()) {
  const fresh = fs.mkdtempSync(path.join(os.tmpdir(), 'delegate-unborn-'));
  const g2 = (...a) => execFileSync('git', ['-C', fresh, ...a], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
  g2('init', '-q');
  g2('config', 'user.email', 'test@example.invalid');
  g2('config', 'user.name', 'test');

  t('REPAIR-C6 the FIRST commit counts as HEAD movement', () => {
    fs.writeFileSync(path.join(fresh, 'a.txt'), 'x\n');
    const before = gitCapture(fresh);
    assert.equal(before.head, null);
    assert.equal(before.unborn, true, 'an unborn HEAD is known, not unknown');
    g2('add', '.');
    g2('commit', '-qm', 'first');
    const cmp = gitCompare(before, fresh);
    assert.equal(cmp.head_changed, true, 'v2.0 forced this to null, so the commit gate could not fire');
  });

  t('CONTRACT an unborn HEAD that stays unborn is not movement', () => {
    const bare = fs.mkdtempSync(path.join(os.tmpdir(), 'delegate-unborn2-'));
    execFileSync('git', ['-C', bare, 'init', '-q']);
    const before = gitCapture(bare);
    const cmp = gitCompare(before, bare);
    assert.equal(cmp.head_changed, false);
    fs.rmSync(bare, { recursive: true, force: true });
  });

  fs.rmSync(fresh, { recursive: true, force: true });
} else {
  t('SKIP git integration (git not on PATH)', () => {});
}

t('CONTRACT a non-git cwd reports null, never false', () => {
  const bare = fs.mkdtempSync(path.join(os.tmpdir(), 'delegate-nogit-'));
  const before = gitCapture(bare);
  assert.equal(before.root, null);
  const cmp = gitCompare(before, bare);
  assert.equal(cmp.dirty_paths_changed, null);
  assert.equal(cmp.head_changed, null);
  assert.equal(cmp.coverage_complete, false);
  assert.equal(readOnlyVerdict(cmp), null,
    'no repository means unknown - reporting false would be an assurance nothing measured');
  fs.rmSync(bare, { recursive: true, force: true });
});

/* =======================================================================
   Recovery - a supervisor that died without writing a result
   ======================================================================= */

t('CONTRACT a run whose supervisor is gone is lost, then synthesised', () => {
  const id = 'codex-19700101000000-deadbe';
  const dir = path.join(scratchRuns, id);
  fs.mkdirSync(dir, { recursive: true });
  // PID 0x7FFFFFFE will not be alive; the journal has a start but no terminal.
  fs.writeFileSync(path.join(dir, 'meta.json'), JSON.stringify({
    run_id: id, harness: 'codex', harness_label: 'OpenAI Codex', tier: 'verified',
    task: 'something that never finished', cwd: os.tmpdir(), permission: 'bypass',
    allow_commit: false, timeout_ms: 60000, started_at: new Date(0).toISOString(),
    supervisor_pid: 2147483646, nonce: 'abc',
  }));
  fs.writeFileSync(path.join(dir, 'journal.jsonl'),
    `{"t":"${new Date(0).toISOString()}","state":"created"}\n` +
    `{"t":"${new Date(0).toISOString()}","state":"supervisor_started","pid":2147483646}\n` +
    `{"t":"${new Date(0).toISOString()}","state":"session","session_id":"th_recovered"}\n`);
  fs.writeFileSync(path.join(dir, 'stdout.log'), '');

  const st = driver(['status', id], { env: RUNS_ENV });
  assert.equal(st.status, 0);
  assert.equal(JSON.parse(st.stdout).state, 'lost');

  const col = driver(['collect', id, '--json'], { env: RUNS_ENV });
  assert.equal(col.status, 0, 'collect must finalise a lost run rather than hanging');
  const r = JSON.parse(col.stdout);
  assert.equal(r.status, 'abandoned');
  assert.equal(r.status_provenance.primary, 'supervisor_lost');
  assert.equal(r.session_id, 'th_recovered', 'the journal preserves what the stream captured');
  assert.equal(r.dirty_paths_changed, null,
    'no run-start baseline survived, so the delta is unknown - not empty');
  assert.equal(r.head_changed, null);
  assert.ok(fs.existsSync(path.join(dir, 'result.json')), 'the synthesised result is persisted');
});

// Not cosmetic: a raw run has no self-report to refine a clean exit and no
// files_claimed. It must not read as an enveloped run that simply said nothing.
t('CONTRACT --raw is recorded as lower-fidelity in the result', () => {
  const mk = (id, raw) => {
    const dir = path.join(scratchRuns, id);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, 'meta.json'), JSON.stringify({
      run_id: id, harness: 'codex', harness_label: 'OpenAI Codex', tier: 'verified',
      task: 't', cwd: os.tmpdir(), permission: 'bypass', allow_commit: false, raw,
      timeout_ms: 1000, started_at: new Date(0).toISOString(), supervisor_pid: 2147483646,
    }));
    fs.writeFileSync(path.join(dir, 'journal.jsonl'),
      `{"t":"${new Date(0).toISOString()}","state":"supervisor_started","pid":2147483646}\n`);
    fs.writeFileSync(path.join(dir, 'stdout.log'), '');
    return JSON.parse(driver(['collect', id, '--json'], { env: RUNS_ENV }).stdout);
  };
  assert.equal(mk('codex-19700101000000-a00001', true).envelope, 'raw');
  assert.equal(mk('codex-19700101000000-e00001', false).envelope, 'standard');
});

t('CONTRACT a finalised result is never overwritten by a second writer', () => {
  const id = 'codex-19700101000000-deadbe';
  const dir = path.join(scratchRuns, id);
  const first = JSON.parse(fs.readFileSync(path.join(dir, 'result.json'), 'utf8'));
  driver(['collect', id, '--json'], { env: RUNS_ENV });
  const second = JSON.parse(fs.readFileSync(path.join(dir, 'result.json'), 'utf8'));
  assert.equal(first.ended_at, second.ended_at, 'the single-writer claim must hold');
});

/* =======================================================================
   END TO END through start/collect, with a fake harness
   ======================================================================= */

const FAKE = path.join(FIX, 'fake-harness.mjs');

// Plant a run directory by hand: meta + journal, no result. Used to drive the
// recovery paths deterministically without racing a real process.
function plant(id, { supervisorPid, childPid, journalExtra = [], meta = {} }) {
  const dir = path.join(scratchRuns, id);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'meta.json'), JSON.stringify({
    run_id: id, harness: 'codex', harness_label: 'OpenAI Codex', tier: 'verified',
    task: 'planted', cwd: os.tmpdir(), permission: 'bypass', allow_commit: false,
    timeout_ms: 60000, started_at: new Date(0).toISOString(), supervisor_pid: supervisorPid,
    nonce: 'abc', ...meta,
  }));
  const lines = [
    `{"t":"${new Date(0).toISOString()}","state":"created"}`,
    `{"t":"${new Date(0).toISOString()}","state":"supervisor_started","pid":${supervisorPid}}`,
    ...(childPid ? [`{"t":"${new Date(0).toISOString()}","state":"child_started","pid":${childPid}}`] : []),
    ...journalExtra,
  ];
  fs.writeFileSync(path.join(dir, 'journal.jsonl'), `${lines.join('\n')}\n`);
  fs.writeFileSync(path.join(dir, 'stdout.log'), '');
  return dir;
}

const DEAD_PID = 2147483646;

function e2e(id, env, extraArgs = []) {
  const start = spawnSync(process.execPath, [DRIVER, 'start',
    '--harness', 'codex', '--cwd', os.tmpdir(), '--timeout', '60',
    '--task', 'fake task', ...extraArgs], {
    encoding: 'utf8', timeout: 60_000,
    env: { ...process.env, ...RUNS_ENV, DELEGATE_BIN_CODEX: FAKE, ...env },
  });
  if (start.status !== 0) return { start, result: null };
  const runId = JSON.parse(start.stdout).run_id;
  const col = spawnSync(process.execPath, [DRIVER, 'collect', runId, '--wait', '45', '--json'], {
    encoding: 'utf8', timeout: 60_000, env: { ...process.env, ...RUNS_ENV },
  });
  return { start, runId, col, result: col.stdout ? JSON.parse(col.stdout) : null };
}

const CODEX_OK = '{"type":"thread.started","thread_id":"th_e2e"}\n'
  + '{"type":"item.completed","item":{"type":"agent_message","text":"done\\n\\n<<<DELEGATION_RESULT>>>\\nstatus: successful\\nsummary: I did the thing.\\nfiles_changed: none\\n<<<END_DELEGATION_RESULT>>>"}}\n'
  + '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":10}}\n';

// The test gap that mattered most: the REPAIR-D1 unit cases call resolveStatus
// directly, so they would still pass if the supervisor dropped or rewrote the
// real child exit code. This drives the whole pipeline.
t('E2E REPAIR-D1 success telemetry + exit 1 is published failed', () => {
  const { result } = e2e('d1', { FAKE_STREAM: CODEX_OK, FAKE_EXIT: '1' });
  assert.ok(result, 'collect produced no result');
  assert.equal(result.status, 'failed');
  assert.equal(result.status_provenance.primary, 'exit_code');
  assert.equal(result.exit_code, 1);
});

// Codex emits no cost and no model anywhere in its JSONL, so both are null by
// nature. The result must say which, and the human view must not print a bare
// null that reads like a bug.
t('E2E a harness that reports neither cost nor model says so', () => {
  const { result, runId } = e2e('reports', { FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0' });
  assert.equal(result.cost_usd, null);
  assert.equal(result.cost_reported, false, 'codex genuinely never emits a cost');
  assert.equal(result.model_reported, false);
  const human = spawnSync(process.execPath, [DRIVER, 'collect', runId],
    { encoding: 'utf8', timeout: 60_000, env: { ...process.env, ...RUNS_ENV } });
  assert.match(human.stdout, /cost {4}not reported by this harness/);
  assert.match(human.stdout, /model=/);
});

t('E2E the same stream at exit 0 is successful', () => {
  const { result } = e2e('ok', { FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0' });
  assert.equal(result.status, 'successful');
  assert.equal(result.status_provenance.primary, 'harness_telemetry');
  assert.equal(result.tokens.input_total, 100);
  assert.equal(result.tokens.input_fresh, 60);
});

t('E2E a session id is captured from the live stream and enables resume', () => {
  const { result } = e2e('sess', { FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0' });
  assert.equal(result.session_id, 'th_e2e');
  assert.equal(result.session_capture, 'streaming');
});

t('E2E a truncated stream is abandoned, not successful', () => {
  const { result } = e2e('trunc', {
    FAKE_STREAM: '{"type":"thread.started","thread_id":"th_t"}\n{"type":"item.compl',
    FAKE_EXIT: '0',
  });
  assert.equal(result.status, 'abandoned');
  assert.equal(result.status_provenance.primary, 'telemetry_incomplete');
});

// Real coverage for the scan loop, the decoder, journal persistence and the EOF
// flush. The chunk size is chosen so the two bytes of "é" land in DIFFERENT OS
// reads, and the fake pauses between writes so the kernel cannot coalesce them.
// Round 2 proved an earlier version of this test was theatre: replacing the
// driver's StringDecoder with per-chunk toString() left it green.
t('E2E a multibyte session id split across OS reads survives intact', () => {
  const head = '{"type":"thread.started","thread_id":"th_caf';
  const stream = `${head}é_split"}\n`
    + '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n';
  // Buffer.byteLength(head) puts the split exactly between the two bytes of é.
  const cut = Buffer.byteLength(head, 'utf8') + 1;
  const { result } = e2e('chunk', {
    FAKE_STREAM: stream, FAKE_EXIT: '0',
    FAKE_CHUNK: String(cut), FAKE_CHUNK_DELAY_MS: '40',
  });
  assert.equal(result.session_id, 'th_café_split',
    'decoding each chunk independently yields U+FFFD and a wrong session id');
});

t('E2E a slow but clean exit is still clean', () => {
  const { result } = e2e('slow', { FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0', FAKE_SLEEP_MS: '250' });
  assert.equal(result.status, 'successful');
});

// Windows has no signal delivery to observe, so this can only run on POSIX.
// Saying so is better than a test named for signals that never sends one.
if (process.platform === 'win32') {
  t('SKIP signal transport (no catchable signal exit on win32)', () => {});
} else {
  t('E2E a harness killed by a signal reports provenance signal', () => {
    const { result } = e2e('sig', {
      FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0', FAKE_SELF_SIGNAL: 'SIGKILL',
    });
    assert.equal(result.status, 'failed');
    assert.equal(result.status_provenance.primary, 'signal');
    assert.equal(result.signal, 'SIGKILL');
  });
}

// Crossing the output cap must not change status semantics: the rolling tail
// exists so a terminal event arriving after the cap is still parsed.
t('E2E terminal telemetry survives the output cap', () => {
  const filler = `${'{"type":"item.completed","item":{"type":"noise","text":"' + 'x'.repeat(400) + '"}}'}\n`;
  const { result } = e2e('cap', {
    FAKE_STREAM: filler.repeat(60) + CODEX_OK,
    FAKE_EXIT: '0',
    DELEGATE_MAX_LOG_BYTES: '4096',
  });
  assert.equal(result.truncated_output, true, 'the cap should have been crossed');
  assert.equal(result.status, 'successful',
    'dropping the post-cap tail would turn a finished run into telemetry_incomplete');
  assert.equal(result.status_provenance.primary, 'harness_telemetry');
});

// M3 (round 3): the cap test used many small chunks, so keeping the WRONG end of
// an oversized single chunk went unnoticed. One chunk larger than the tail budget
// must keep its tail - the terminal record lives at the end.
t('E2E an oversized post-cap chunk keeps its END, where the terminal record is', () => {
  // One write, larger than the tail budget, with the terminal record at its end.
  const filler = `{"type":"item.completed","item":{"type":"noise","text":"${'y'.repeat(5000)}"}}\n`;
  const { result } = e2e('bigchunk', {
    FAKE_STREAM: filler + CODEX_OK,
    FAKE_EXIT: '0',
    FAKE_CHUNK: '200000',
    DELEGATE_MAX_LOG_BYTES: '512',
    DELEGATE_LOG_TAIL_BYTES: '2048',
  });
  assert.equal(result.truncated_output, true);
  assert.equal(result.status, 'successful',
    'keeping the head of an oversized chunk discards the terminal event at its end');
});

// Round 4's must-fix: the TERMINAL RECORD ITSELF larger than the tail budget.
// A raw byte suffix cannot parse a record whose opening brace was evicted, so
// this turned a finished run into telemetry_incomplete and lost its evidence.
t('E2E a terminal record larger than the tail budget still parses', () => {
  const bigMessage = 'z'.repeat(300_000);
  const stream = '{"type":"thread.started","thread_id":"th_oversize"}\n'
    + `{"type":"item.completed","item":{"type":"agent_message","text":"${bigMessage}"}}\n`
    + '{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}\n';
  const { result } = e2e('bigterm', {
    FAKE_STREAM: stream, FAKE_EXIT: '0',
    DELEGATE_MAX_LOG_BYTES: '512',
    DELEGATE_LOG_TAIL_BYTES: '4096',      // far smaller than the agent_message record
  });
  assert.equal(result.truncated_output, true, 'the cap should have been crossed');
  assert.equal(result.status, 'successful',
    'a valid terminal event must survive the cap, whatever its size');
  assert.equal(result.status_provenance.primary, 'harness_telemetry');
  assert.equal(result.tokens.input_total, 7, 'the terminal usage record must still be read');
  assert.equal(result.session_id, 'th_oversize');
  // Round 5: the old version of this case asserted status and usage only, which
  // masked the message itself being evicted. A budget this small CANNOT hold a
  // 300 KB record - what matters is that the loss is REPORTED, not silent.
  assert.ok(result.records_dropped > 0,
    'records evicted past the cap must be counted, or a missing final answer looks like success');
});

// The same stream with a budget that CAN hold the message: nothing is dropped
// and the delegate's actual final answer survives.
t('E2E an adequate retention budget preserves the delegate\'s final answer', () => {
  const bigMessage = 'z'.repeat(120_000);
  const stream = '{"type":"thread.started","thread_id":"th_keep"}\n'
    + `{"type":"item.completed","item":{"type":"agent_message","text":"${bigMessage}"}}\n`
    + '{"type":"turn.completed","usage":{"input_tokens":9,"output_tokens":3}}\n';
  const { result } = e2e('bigkeep', {
    FAKE_STREAM: stream, FAKE_EXIT: '0',
    DELEGATE_MAX_LOG_BYTES: '512',
    DELEGATE_LOG_TAIL_BYTES: '400000',    // comfortably larger than the record
  });
  assert.equal(result.status, 'successful');
  assert.equal(result.records_dropped, 0, 'nothing should be dropped within budget');
  assert.ok(result.summary.length > 1000,
    `the final answer was lost: summary is ${result.summary.length} chars`);
});

// Round 6: a record over the per-line bound is split by real pipe delivery, so
// the buffer guard fires many times before any newline. Counting there would
// over-count; counting at the final suffix never fires, because the suffix does
// not start with `{`. The loss must be exactly one counted event.
t('E2E a chunked over-limit record is counted, not silently dropped', () => {
  const huge = 'q'.repeat(1_050_000);          // over MAX_LINE_CHARS
  const stream = '{"type":"thread.started","thread_id":"th_overmax"}\n'
    + `{"type":"item.completed","item":{"type":"agent_message","text":"${huge}"}}\n`
    + '{"type":"turn.completed","usage":{"input_tokens":17,"output_tokens":2}}\n';
  const { result } = e2e('overmax', {
    FAKE_STREAM: stream, FAKE_EXIT: '0',
    FAKE_CHUNK: '60000', FAKE_CHUNK_DELAY_MS: '1',
    DELEGATE_MAX_LOG_BYTES: '512',
    DELEGATE_LOG_TAIL_BYTES: '2000000',        // large, to isolate the LINE bound
  });
  assert.equal(result.status, 'successful');
  assert.equal(result.tokens.input_total, 17, 'the record AFTER the dropped one must still parse');
  assert.equal(result.session_id, 'th_overmax', 'the record BEFORE it must still parse');
  assert.equal(result.records_dropped, 1,
    `exactly one record was lost; got ${result.records_dropped} (0 = silent loss, >1 = counted per chunk)`);

  // The human-readable path must say so too - a structured field nobody prints
  // is not an actionable warning.
  const human = spawnSync(process.execPath, [DRIVER, 'collect', result.run_id],
    { encoding: 'utf8', timeout: 60_000, env: { ...process.env, ...RUNS_ENV } });
  assert.match(human.stdout, /record\(s\) dropped past the output cap/);
  assert.match(human.stdout, /summary may be incomplete/);
});

// Round 7: the two events can happen in EITHER order. Here the record exceeds
// the line bound BEFORE the raw cap is crossed, so counting only at discard-start
// reported zero while the evidence was genuinely lost.
t('E2E an over-limit record already discarding when the cap crosses is still counted', () => {
  const huge = 'w'.repeat(1_050_000);          // over MAX_LINE_CHARS
  const stream = '{"type":"thread.started","thread_id":"th_transition"}\n'
    + `{"type":"item.completed","item":{"type":"agent_message","text":"${huge}"}}\n`
    + '{"type":"turn.completed","usage":{"input_tokens":23,"output_tokens":2}}\n';
  const { result } = e2e('transition', {
    FAKE_STREAM: stream, FAKE_EXIT: '0',
    FAKE_CHUNK: '60000', FAKE_CHUNK_DELAY_MS: '1',
    // Cap ABOVE the line bound but BELOW the record length: the line limit trips
    // first, then the cap crosses while that record is still being discarded.
    DELEGATE_MAX_LOG_BYTES: '1020000',
    DELEGATE_LOG_TAIL_BYTES: '2000000',
  });
  assert.equal(result.status, 'successful');
  assert.equal(result.tokens.input_total, 23, 'the record after the dropped one must still parse');
  assert.equal(result.session_id, 'th_transition', 'the record before it must still parse');
  assert.equal(result.records_dropped, 1,
    `cap-crossing during an already-discarded record must count exactly once; got ${result.records_dropped}`);
});

// Round 5 proved this with a real reproduction: retaining records that the file
// ALREADY held made OpenCode - which sums every step_finish - publish 35 tokens
// for a run that used 24.
t('E2E an additive adapter does not double-count records across the cap', () => {
  const step = (input) => `{"type":"step_finish","part":{"tokens":{"input":${input},"output":1,"cache":{"read":0,"write":0}},"reason":"tool"}}`;
  const pad = `{"type":"text","part":{"text":"${'p'.repeat(600)}"}}`;
  const stream = `${step(11)}\n${pad}\n${pad}\n${step(13)}\n`
    + '{"type":"step_finish","part":{"tokens":{"input":0,"output":0,"cache":{"read":0,"write":0}},"reason":"stop"}}\n';
  // The cap must be crossed MID-stream, or there is no pre-cap/post-cap split to
  // duplicate: the 11-token step completes inside the written prefix, the
  // 13-token step arrives after the cap. Chunked writes force that boundary.
  const start = spawnSync(process.execPath, [DRIVER, 'start', '--harness', 'opencode',
    '--cwd', os.tmpdir(), '--timeout', '60', '--task', 'sum check'], {
    encoding: 'utf8', timeout: 60_000,
    env: {
      ...process.env, ...RUNS_ENV, DELEGATE_BIN_OPENCODE: FAKE,
      FAKE_STREAM: stream, FAKE_EXIT: '0', DELEGATE_MAX_LOG_BYTES: '900',
      FAKE_CHUNK: '200', FAKE_CHUNK_DELAY_MS: '5',
    },
  });
  assert.equal(start.status, 0, start.stderr);
  const runId = JSON.parse(start.stdout).run_id;
  const col = spawnSync(process.execPath, [DRIVER, 'collect', runId, '--wait', '45', '--json'],
    { encoding: 'utf8', timeout: 60_000, env: { ...process.env, ...RUNS_ENV } });
  const r = JSON.parse(col.stdout);
  assert.equal(r.truncated_output, true, 'the cap should have been crossed mid-stream');
  assert.equal(r.tokens.input_fresh, 24,
    `pre-cap records were replayed: expected 24, got ${r.tokens.input_fresh}`);
});

// M4 (round 3): the signal test signals the CHILD. Nothing signalled the RELAY,
// so removing its asynchronous drain went unnoticed.
if (process.platform === 'win32') {
  t('SKIP relay-shutdown drain (no deliverable signal on win32)', () => {});
} else {
  t('E2E signalling the RELAY still produces a drained terminal result', async () => {
    const start = spawnSync(process.execPath, [DRIVER, 'start', '--harness', 'codex',
      '--cwd', os.tmpdir(), '--timeout', '120', '--task', 'slow'], {
      encoding: 'utf8', timeout: 60_000,
      env: {
        ...process.env, ...RUNS_ENV, DELEGATE_BIN_CODEX: FAKE,
        FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0', FAKE_SLEEP_MS: '4000',
      },
    });
    assert.equal(start.status, 0, start.stderr);
    const runId = JSON.parse(start.stdout).run_id;
    const meta = JSON.parse(fs.readFileSync(path.join(scratchRuns, runId, 'meta.json'), 'utf8'));
    await new Promise((r) => setTimeout(r, 800));
    process.kill(meta.supervisor_pid, 'SIGTERM');
    await new Promise((r) => setTimeout(r, 4000));
    const res = JSON.parse(fs.readFileSync(path.join(scratchRuns, runId, 'result.json'), 'utf8'));
    assert.equal(res.status_provenance.primary, 'relay_aborted');
    assert.equal(res.session_id, 'th_e2e',
      'the stream captured before the signal must survive the drain');
  });
}

// Round 2 showed the previous clean-env test checked only our own metadata, so
// making buildEnv return the full environment left it green. This asks the
// harness what it actually received.
t('E2E --clean-env really withholds the variable from the harness', () => {
  const secret = 'DELEGATE_TEST_SECRET';
  const runWith = (args) => {
    const start = spawnSync(process.execPath, [DRIVER, 'start',
      '--harness', 'codex', '--cwd', os.tmpdir(), '--timeout', '60',
      '--task', 'env probe', ...args], {
      encoding: 'utf8', timeout: 60_000,
      env: {
        ...process.env, ...RUNS_ENV, DELEGATE_BIN_CODEX: FAKE,
        FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0', FAKE_REPORT_ENV: secret,
        [secret]: 'super-secret-value',
      },
    });
    assert.equal(start.status, 0, start.stderr);
    const runId = JSON.parse(start.stdout).run_id;
    spawnSync(process.execPath, [DRIVER, 'collect', runId, '--wait', '45', '--json'],
      { encoding: 'utf8', timeout: 60_000, env: { ...process.env, ...RUNS_ENV } });
    return fs.readFileSync(path.join(scratchRuns, runId, 'stderr.log'), 'utf8');
  };

  // The fixture's own control variables must be kept, or the probe cannot run at
  // all and an empty stderr would masquerade as isolation.
  const control = ['--keep-env', 'FAKE_REPORT_ENV', '--keep-env', 'FAKE_STREAM', '--keep-env', 'FAKE_EXIT'];

  assert.match(runWith([]), new RegExp(`"${secret}":true`),
    'without --clean-env the harness inherits everything');
  assert.match(runWith(['--clean-env', ...control]), new RegExp(`"${secret}":false`),
    'with --clean-env the harness must NOT see it');
  assert.match(runWith(['--clean-env', ...control, '--keep-env', secret]), new RegExp(`"${secret}":true`),
    '--keep-env must hand it back');
});

// The claim protocol's real hazard is contention, not a dead owner. Two
// collectors race the same lost run; exactly one result may exist, and neither
// may print `null` as though it were one.
t('E2E concurrent collect never splits the brain or prints null', async () => {
  // Its own runs dir: this case outlives the synchronous cases, and the prune
  // test would otherwise delete the directory out from under it.
  const raceRuns = fs.mkdtempSync(path.join(os.tmpdir(), 'delegate-race-'));
  const RACE_ENV = { DELEGATE_RUNS_DIR: raceRuns };
  const id = 'codex-19700101000000-0ace00';
  const dir = path.join(raceRuns, id);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'meta.json'), JSON.stringify({
    run_id: id, harness: 'codex', harness_label: 'OpenAI Codex', tier: 'verified',
    task: 'race', cwd: os.tmpdir(), permission: 'bypass', allow_commit: false,
    timeout_ms: 60000, started_at: new Date(0).toISOString(), supervisor_pid: DEAD_PID, nonce: 'r',
  }));
  fs.writeFileSync(path.join(dir, 'journal.jsonl'),
    `{"t":"${new Date(0).toISOString()}","state":"supervisor_started","pid":${DEAD_PID}}\n`);
  fs.writeFileSync(path.join(dir, 'stdout.log'), '');

  const run = () => new Promise((resolve) => {
    const c = spawn(process.execPath, [DRIVER, 'collect', id, '--json'],
      { env: { ...process.env, ...RACE_ENV } });
    let out = '', err = '';
    c.stdout.on('data', (d) => { out += d; });
    c.stderr.on('data', (d) => { err += d; });
    c.on('close', (code) => resolve({ code, out, err }));
  });
  const [a, b] = await Promise.all([run(), run()]);
  for (const r of [a, b]) {
    assert.ok(!/^\s*null\s*$/.test(r.out), 'a collector printed null instead of a result');
    if (r.code === 0) JSON.parse(r.out);            // must be valid JSON when it claims success
  }
  assert.ok(a.code === 0 || b.code === 0, `neither collector produced a result: ${a.err}${b.err}`);
  const onDisk = JSON.parse(fs.readFileSync(path.join(dir, 'result.json'), 'utf8'));
  for (const r of [a, b]) {
    if (r.code === 0) {
      assert.equal(JSON.parse(r.out).ended_at, onDisk.ended_at,
        'a returned result disagrees with the one on disk - split brain');
    }
  }
  fs.rmSync(raceRuns, { recursive: true, force: true });
});

t('E2E permission_mode_applied names what was actually requested', () => {
  const { result } = e2e('perm', { FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0' }, ['--sandbox']);
  assert.match(result.permission_mode_applied, /-s read-only/);
  assert.equal(result.permission_requested, 'sandbox');
});

t('E2E --clean-env records the retained names, never values', () => {
  const { result } = e2e('cleanenv', { FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0' },
    ['--clean-env', '--keep-env', 'FAKE_STREAM', '--keep-env', 'FAKE_EXIT']);
  assert.equal(result.clean_env, true);
  assert.ok(result.kept_env_names.includes('FAKE_STREAM'));
  const blob = JSON.stringify(result);
  assert.ok(!blob.includes('thread.started') || !blob.includes('"FAKE_STREAM":"'),
    'a retained variable name must never be published with its value');
});

/* =======================================================================
   Recovery - the live-child rule, and claim contention
   ======================================================================= */

// The contract's key safeguard, previously untested: a dead supervisor whose
// child is STILL RUNNING must not be finalised. On POSIX the child leads its own
// process group and genuinely outlives its supervisor.
t('CONTRACT a dead supervisor with a LIVE child is adrift, not lost', () => {
  const id = 'codex-19700101000000-adf001';
  plant(id, { supervisorPid: DEAD_PID, childPid: process.pid });   // our own pid is alive
  const st = driver(['status', id], { env: RUNS_ENV });
  assert.equal(JSON.parse(st.stdout).state, 'adrift');
});

t('CONTRACT collect REFUSES to finalise a run whose child is still alive', () => {
  const id = 'codex-19700101000000-adf001';
  const col = driver(['collect', id, '--json'], { env: RUNS_ENV });
  assert.notEqual(col.status, 0, 'publishing here would snapshot a run still in motion');
  assert.match(col.stderr, /still running/);
  assert.ok(!fs.existsSync(path.join(scratchRuns, id, 'result.json')),
    'no result may be written while the harness is still writing');
});

t('CONTRACT prune never deletes an adrift run', () => {
  const r = driver(['prune', '--keep', '0', '--yes'], { env: RUNS_ENV });
  assert.equal(r.status, 0);
  assert.ok(fs.existsSync(path.join(scratchRuns, 'codex-19700101000000-adf001')),
    'deleting the logs out from under a live child loses the only record of it');
});

t('REPAIR-B2 a stale claim is stolen, not left bricked', () => {
  const id = 'codex-19700101000000-57a1e0';
  const dir = plant(id, { supervisorPid: DEAD_PID, childPid: DEAD_PID });
  // An owner that died between claiming and writing. v2.0 returned JSON `null`
  // with exit 0 here - a non-result published as success.
  fs.writeFileSync(path.join(dir, 'result.json.claim'),
    JSON.stringify({ pid: DEAD_PID, t: Date.now() }));
  const col = driver(['collect', id, '--json'], { env: RUNS_ENV });
  assert.equal(col.status, 0);
  const r = JSON.parse(col.stdout);
  assert.ok(r && r.schema, 'collect must never print null as a result');
  assert.equal(r.status, 'abandoned');
  assert.equal(r.status_provenance.primary, 'supervisor_lost');
});

// A race is not reliably reproducible, so pin the PROTOCOL instead: ownership
// must be taken by an exclusive create, which leaves the new owner's pid in the
// claim. Overwriting a stale claim in place would let two contenders both
// believe they own it and publish different results.
t('CONTRACT stealing a stale claim takes exclusive ownership, not a blind overwrite', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'delegate-claim-'));
  const claimPath = path.join(dir, 'result.json.claim');
  fs.writeFileSync(claimPath, JSON.stringify({ pid: DEAD_PID, t: Date.now() }));

  const built = finalizeOnce(dir, () => ({
    schema: 'delegate-task.result.v2', status: 'abandoned',
    status_provenance: { primary: 'supervisor_lost', evidence: [] },
  }));
  assert.ok(built, 'a stale claim must be recoverable');

  const claim = JSON.parse(fs.readFileSync(claimPath, 'utf8'));
  assert.equal(claim.pid, process.pid,
    'the claim must record the new owner: a blind overwrite leaves no owner and permits split brain');

  // A second call sees the finished result and returns THAT, never a rebuild.
  const again = finalizeOnce(dir, () => { throw new Error('must not rebuild over a finished result'); });
  assert.equal(again.status, 'abandoned');
  fs.rmSync(dir, { recursive: true, force: true });
});

t('CONTRACT finalizeOnce returns null - never a result - while a live owner holds the claim', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'delegate-claim2-'));
  fs.writeFileSync(path.join(dir, 'result.json.claim'),
    JSON.stringify({ pid: process.pid, t: Date.now() }));
  const r = finalizeOnce(dir, () => { throw new Error('must not build behind a live owner'); });
  assert.equal(r, null);
  fs.rmSync(dir, { recursive: true, force: true });
});

t('CONTRACT a claim held by a LIVE writer yields retry, never null', () => {
  const id = 'codex-19700101000000-11ec01';
  const dir = plant(id, { supervisorPid: DEAD_PID, childPid: DEAD_PID });
  fs.writeFileSync(path.join(dir, 'result.json.claim'),
    JSON.stringify({ pid: process.pid, t: Date.now() }));   // alive and fresh
  const col = driver(['collect', id, '--json'], { env: RUNS_ENV });
  assert.notEqual(col.status, 0);
  assert.match(col.stderr, /finalising|retry/);
  assert.ok(!/^null/.test(col.stdout.trim()));
});

t('CONTRACT an unknown schema is refused, not relabelled v1', () => {
  const id = 'codex-19700101000000-f00001';
  const dir = plant(id, { supervisorPid: DEAD_PID, childPid: DEAD_PID });
  fs.writeFileSync(path.join(dir, 'result.json'),
    JSON.stringify({ schema: 'delegate-task.result.v99', run_id: id, status: 'successful' }));
  const col = driver(['collect', id, '--json'], { env: RUNS_ENV });
  assert.notEqual(col.status, 0);
  assert.match(col.stderr, /different driver/);
});

// Amendment 4, the half that was missing: a resumed dispatch restates the
// parent's ORIGINAL scope exclusions and deliverable, not merely the generic
// policy lines. Dropping them is exactly the inheritance failure it forbids.
t('AMENDMENT-4 resume restates the parent\'s original constraints', () => {
  const first = e2e('inherit', { FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0' },
    ['--constraint', 'ORIGINAL-SCOPE-RULE: touch only src/', '--deliverable', 'ORIGINAL-DELIVERABLE: a diff']);
  assert.equal(first.result.status, 'successful');

  const resumed = spawnSync(process.execPath, [DRIVER, 'start',
    '--harness', 'codex', '--cwd', os.tmpdir(), '--timeout', '60',
    '--resume', first.runId, '--task', 'just the delta'], {
    encoding: 'utf8', timeout: 60_000,
    env: { ...process.env, ...RUNS_ENV, DELEGATE_BIN_CODEX: FAKE, FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0' },
  });
  assert.equal(resumed.status, 0, resumed.stderr);
  const childId = JSON.parse(resumed.stdout).run_id;
  const prompt = fs.readFileSync(path.join(scratchRuns, childId, 'prompt.txt'), 'utf8');
  assert.match(prompt, /ORIGINAL-SCOPE-RULE/, 'the parent\'s scope exclusion was dropped on resume');
  assert.match(prompt, /ORIGINAL-DELIVERABLE/, 'the parent\'s deliverable was dropped on resume');
  assert.match(prompt, /Do NOT run `git add` or `git commit`/);
  assert.match(prompt, /just the delta/);
});

t('CONTRACT resume refuses a harness-version change', () => {
  const first = e2e('vergate', { FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0', FAKE_VERSION: '1.0.0' });
  const r = spawnSync(process.execPath, [DRIVER, 'start',
    '--harness', 'codex', '--cwd', os.tmpdir(), '--timeout', '60',
    '--resume', first.runId, '--task', 'delta'], {
    encoding: 'utf8', timeout: 60_000,
    env: { ...process.env, ...RUNS_ENV, DELEGATE_BIN_CODEX: FAKE, FAKE_VERSION: '2.0.0' },
  });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /not portable across CLI versions/);
});

t('CONTRACT resume refuses a different working directory', () => {
  const first = e2e('cwdgate', { FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0' });
  const other = fs.mkdtempSync(path.join(os.tmpdir(), 'delegate-other-'));
  const r = spawnSync(process.execPath, [DRIVER, 'start',
    '--harness', 'codex', '--cwd', other, '--timeout', '60',
    '--resume', first.runId, '--task', 'delta'], {
    encoding: 'utf8', timeout: 60_000,
    env: { ...process.env, ...RUNS_ENV, DELEGATE_BIN_CODEX: FAKE },
  });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /different directory/);
  fs.rmSync(other, { recursive: true, force: true });
});

// M2 (round 3): no test planted a stale heartbeat behind a LIVE supervisor, so
// collapsing that case to `lost` went unnoticed - and a lost run gets a
// competing terminal result written under a supervisor that may still finish.
t('CONTRACT a live supervisor with a stale heartbeat is stalled, not lost', () => {
  const id = 'codex-19700101000000-57a110';
  plant(id, { supervisorPid: process.pid, childPid: DEAD_PID });   // our pid is alive
  const st = driver(['status', id], { env: RUNS_ENV });
  assert.equal(JSON.parse(st.stdout).state, 'stalled',
    'a live supervisor must never be declared lost on heartbeat age alone');
  const col = driver(['collect', id, '--json'], { env: RUNS_ENV });
  assert.notEqual(col.status, 0, 'collect must not publish a competing result');
  assert.ok(!fs.existsSync(path.join(scratchRuns, id, 'result.json')));
});

t('CONTRACT prune never deletes a stalled run', () => {
  const r = driver(['prune', '--keep', '0', '--yes'], { env: RUNS_ENV });
  assert.equal(r.status, 0);
  assert.ok(fs.existsSync(path.join(scratchRuns, 'codex-19700101000000-57a110')));
});

t('CONTRACT a malformed heartbeat timestamp does not wedge a run as running', () => {
  const id = 'codex-19700101000000-bad757';
  plant(id, {
    supervisorPid: DEAD_PID, childPid: DEAD_PID,
    journalExtra: ['{"t":"not-a-date","state":"heartbeat"}'],
  });
  const st = driver(['status', id], { env: RUNS_ENV });
  assert.equal(JSON.parse(st.stdout).state, 'lost');
});

/* =======================================================================
   Isolated install - the skill must work detached from this repository
   ======================================================================= */

// Required by the plan and previously absent: the suite imports ../delegate.mjs
// in place, so a broken relative path or a file that only exists in this repo
// would never be noticed.
t('CONTRACT the skill runs from a copy with no repository around it', () => {
  const iso = fs.mkdtempSync(path.join(os.tmpdir(), 'delegate-iso-'));
  const skillSrc = path.join(HERE, '..');
  for (const entry of ['delegate.mjs', 'SKILL.md', 'README.md', 'contracts', 'references']) {
    fs.cpSync(path.join(skillSrc, entry), path.join(iso, entry), { recursive: true });
  }
  fs.mkdirSync(path.join(iso, 'test', 'fixtures'), { recursive: true });
  fs.cpSync(FAKE, path.join(iso, 'test', 'fixtures', 'fake-harness.mjs'));

  const isoDriver = path.join(iso, 'delegate.mjs');
  const isoRuns = path.join(iso, 'runs');

  const doc = spawnSync(process.execPath, [isoDriver, 'doctor'],
    { encoding: 'utf8', timeout: 60_000, env: { ...process.env, DELEGATE_RUNS_DIR: isoRuns } });
  assert.equal(doc.status, 0, `doctor failed in an isolated copy: ${doc.stderr}`);
  assert.match(doc.stdout, /codex/);

  const isoEnv = {
    ...process.env, DELEGATE_RUNS_DIR: isoRuns,
    DELEGATE_BIN_CODEX: path.join(iso, 'test', 'fixtures', 'fake-harness.mjs'),
    FAKE_STREAM: CODEX_OK, FAKE_EXIT: '0',
  };
  const st = spawnSync(process.execPath, [isoDriver, 'start', '--harness', 'codex',
    '--cwd', iso, '--timeout', '60', '--task', 'isolated'],
  { encoding: 'utf8', timeout: 60_000, env: isoEnv });
  assert.equal(st.status, 0, `start failed in an isolated copy: ${st.stderr}`);

  const runId = JSON.parse(st.stdout).run_id;
  const col = spawnSync(process.execPath, [isoDriver, 'collect', runId, '--wait', '45', '--json'],
    { encoding: 'utf8', timeout: 60_000, env: { ...process.env, DELEGATE_RUNS_DIR: isoRuns } });
  assert.equal(col.status, 0, `collect failed in an isolated copy: ${col.stderr}`);
  assert.equal(JSON.parse(col.stdout).status, 'successful');

  // The contracts the SKILL.md points at must travel with it.
  for (const doc2 of ['contracts/status-precedence.md', 'contracts/git-fields.md',
    'contracts/result-schema-v2.md', 'references/writing-the-brief.md']) {
    assert.ok(fs.existsSync(path.join(iso, doc2)), `${doc2} is missing from an installed copy`);
  }
  fs.rmSync(iso, { recursive: true, force: true });
});

await Promise.all(pending);
fs.rmSync(scratchRuns, { recursive: true, force: true });

/* ======================================================================= */

console.log(`\n\n${pass} passed, ${fail} failed`);
for (const [name, e] of failures) {
  console.log(`\nFAIL  ${name}\n      ${e.message.split('\n')[0]}`);
}
process.exit(fail ? 1 : 0);
