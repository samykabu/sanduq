#!/usr/bin/env node
// A stand-in harness CLI, driven entirely by environment variables, so the suite
// can exercise start -> supervise -> collect end to end without launching a real
// agent CLI or spending a token.
//
// Reached through DELEGATE_BIN_<HARNESS>, which delegate.mjs honours in place of
// a PATH lookup.
//
//   FAKE_VERSION   what `--version` prints                (default: 9.9.9)
//   FAKE_STREAM    the stdout body for a normal run       (default: empty)
//   FAKE_STDERR    the stderr body                        (default: empty)
//   FAKE_EXIT      the process exit code                  (default: 0)
//   FAKE_SLEEP_MS  delay before exiting                    (default: 0)
//   FAKE_CHUNK     if set, stdout is emitted in N-byte chunks so a multibyte
//                  character and a JSON line both straddle a chunk boundary

const argv = process.argv.slice(2);

if (argv.includes('--version')) {
  process.stdout.write(`${process.env.FAKE_VERSION || '9.9.9'}\n`);
  process.exit(0);
}

const body = process.env.FAKE_STREAM || '';
const errBody = process.env.FAKE_STDERR || '';
const code = Number(process.env.FAKE_EXIT || 0);
const sleepMs = Number(process.env.FAKE_SLEEP_MS || 0);
const chunk = Number(process.env.FAKE_CHUNK || 0);
// A real gap between writes, so each chunk becomes its own OS read on the pipe.
// Without it the kernel coalesces them and a chunk-boundary test proves nothing.
const chunkDelay = Number(process.env.FAKE_CHUNK_DELAY_MS || 25);

if (errBody) process.stderr.write(errBody);

// Report what the harness ACTUALLY received in its environment, so an isolation
// test can check delivery rather than the caller's own self-report.
if (process.env.FAKE_REPORT_ENV) {
  const names = process.env.FAKE_REPORT_ENV.split(',').map((s) => s.trim()).filter(Boolean);
  const present = {};
  for (const n of names) present[n] = process.env[n] !== undefined;
  process.stderr.write(`ENV_PROBE ${JSON.stringify(present)}\n`);
}

if (chunk > 0) {
  const buf = Buffer.from(body, 'utf8');
  let i = 0;
  const pump = () => {
    if (i >= buf.length) { finish(); return; }
    process.stdout.write(buf.subarray(i, i + chunk));
    i += chunk;
    setTimeout(pump, chunkDelay);
  };
  pump();
} else {
  process.stdout.write(body);
  finish();
}

function finish() {
  const bye = () => {
    // Die on a real signal, so the supervisor observes a signal exit rather than
    // an exit code. POSIX only - Windows has no signal delivery to observe.
    if (process.env.FAKE_SELF_SIGNAL && process.platform !== 'win32') {
      process.kill(process.pid, process.env.FAKE_SELF_SIGNAL);
      return;
    }
    process.exit(Number.isFinite(code) ? code : 0);
  };
  if (sleepMs > 0) setTimeout(bye, sleepMs);
  else bye();
}
