# Native check batches and bounded collection

`check-runner.mjs` runs a sequential batch of local programs with Node 18+ and no dependencies.
Use it for deterministic checks whose argv is already known. One batch invocation executes each
check once; one collector reads the evidence. Keep bookkeeping in these CLIs.

## Plan and invocation

`run --plan FILE` reads UTF-8 JSON (an optional BOM is accepted), at most 1 MiB:

```json
{
  "batch_id": "booking-checks",
  "cwd": "C:/work/booking-project",
  "env": { "PYTHONUTF8": "1" },
  "interpreters": { "python": "C:/Python313/python.exe" },
  "checks": [
    {
      "name": "booking Node tests",
      "argv": ["C:/Program Files/nodejs/node.exe", "--test", "tests/booking.test.mjs"],
      "timeout_s": 300
    },
    {
      "name": "booking Python tests",
      "argv": ["{{python}}", "-m", "unittest", "discover", "-s", "tests", "-p", "test_booking.py"],
      "timeout_s": 120
    }
  ]
}
```

These are synthetic project paths and conventional real interpreter locations; adjust them to
the installed binaries and the booking project's tests. Save the plan as
`C:/work/booking-project/checks.json`. From PowerShell, use single-quoted literal arguments:

```powershell
$env:DELEGATE_RUNS_DIR = 'C:/work/booking-project/.delegate/runs'
& 'C:/Program Files/nodejs/node.exe' 'C:/tools/delegate-task/check-runner.mjs' run --plan 'C:/work/booking-project/checks.json' --max-bytes 16384
& 'C:/Program Files/nodejs/node.exe' 'C:/tools/delegate-task/check-runner.mjs' collect --batch 'booking-checks' --limit 10 --output-bytes 1024 --max-bytes 16384
```

This uses one batch and one collector. Program arguments live in JSON, where quotes, newlines,
spaces, Unicode and empty arguments remain data. `argv[0]` must contain a nonempty executable.
`{{node}}` expands only as a whole argv element to the current Node executable. `{{python}}`
requires `"interpreters": { "python": "C:/Python313/python.exe" }` with a real absolute Python
binary that passes an isolated interpreter probe; Windows app aliases and script shims are refused.
There is no environment-variable or substring interpolation. Optional per-check `cwd` and `env`
override the batch values. Every cwd is absolute and every env value is an explicit string.

Plans contain 1–100 uniquely named checks; names are at most 128 characters. Each argv contains
at most 256 string elements of at most 65,536 characters. Every check specifies `timeout_s`,
positive and within Node's timer range. Choose timeouts appropriate to each check's workload.
The runner uses `shell:false` and `windowsHide:true`; on Windows use `.exe`/`.com` binaries,
or put the real interpreter first and its script second. Unsupported shims fail with a diagnostic;
the runner never falls back to a shell or launches an agent on its own.

## Ownership and evidence

`DELEGATE_RUNS_DIR` must be an explicit absolute directory; keep `.delegate/` ignored. Each run
appends `checks/<batch_id>/attempt-<time>-<nonce>/` with UTF-8 JSON metadata, immutable check
checkpoints, and incrementally captured stdout/stderr bytes. Raw logs remain intact, including
oversized records. They can contain secrets and consume disk space until removed by the owner.

An exclusive execution lock is held for the whole batch, including all checks. A second owner
exits 3 without executing any check. Recovery removes only the dead owner's immutable filename,
then removes the empty lock directory. Unknown, incomplete or live ownership blocks execution;
age alone never proves death. Launch intent and the active child are recorded under that lock;
recovery also refuses a live child/group or an uncertain launch. On Windows, an interrupted active
tree remains protected even if its root pid has gone. PID reuse can conservatively block recovery. No process read from
a lock is killed, and a runner never removes another owner's attempt or artifacts.

An existing attempt also protects a batch after its execution lock is released. Default `run`
returns the latest bounded receipt with `requires_explicit_retry: true`,
`execution_performed: false` and exit 4. It executes no check again, including when the previous
attempt failed. An intentional retry names the exact latest attempt:

```powershell
& 'C:/Program Files/nodejs/node.exe' 'C:/tools/delegate-task/check-runner.mjs' run --plan 'C:/work/booking-project/checks.json' --retry-of 'attempt-1700000000000-aabbccddeeff' --max-bytes 16384
```

Replace that synthetic attempt ID with the returned `attempt_id`. Wrong or stale IDs are refused
before execution. The retry is recorded as `retry_of` in a new attempt; previous attempts remain
unchanged. A SHA-256 manifest binds ordered check names/argv, effective explicit cwd/env settings,
timeouts, interpreter configuration, the current Node executable, real directory file identities,
and Git worktree registration when available. Changing a plan or replacing/moving its worktree
requires a new `batch_id`. Ordinary source edits and HEAD changes are allowed: they are the normal
reason to rerun the same checks. Ambient environment values are not part of the manifest.

Retry authorization is checked while holding execution ownership. A live or unknown owner,
active child, or unresolved interrupted launch still blocks a retry. Historical attempts created
before manifest binding remain collectable but require a new batch ID for execution. A failed
Python interpreter probe occurs only on an authorized execution, never when returning an existing
receipt. An incomplete launched attempt requires explicit ownership/child resolution before retry.

Failures do not trigger retries. Following checks still run. Per-check statuses distinguish
`passed`, `failed`, `launch_failed`, `timeout`, `abandoned`, `pending` and `skipped`; exit codes,
signals, launch errors and artifact errors are retained. Success means every named check passed.
Timeouts and caught interrupts terminate the owned process group on POSIX or the owned tree
with Windows `taskkill /T /F`. Descendants that deliberately escape their group/tree require
OS-level containment. A hard-killed runner may leave a child alive; recovery does not kill it.
Before recovering such a batch, the owner must resolve its recorded child separately.

The runner keeps completed checkpoints even if it dies before the terminal result. Collection
reports that attempt as `incomplete` and unlaunched checks as `pending`, never passed.
An unfinished launched check is `running` with a live owner, otherwise `interrupted`.

## Collection

`run --plan FILE [--retry-of ATTEMPT] [--max-bytes N]` executes or returns a retry-required receipt.
`collect --batch ID [--attempt ID] [--limit 1..20] [--output-bytes 0..4096] [--max-bytes N]`
`[--cursor TOKEN] [--check-index 0..99]` reads metadata
without loading whole logs. Defaults: latest 10 attempts, 1024 excerpt bytes per stream/check.
The collection reports total/omitted attempts and status counts, including failed attempts outside
the selected window. Select a prior attempt by ID to inspect its evidence. Metadata over 1 MiB
per file is rejected. The stored result schema is `delegate-task.check-batch.v1`; the collection
schema is `delegate-task.check-collection.v1`.

Both commands enforce a **total UTF-8 byte budget**, including the final newline. `--max-bytes`
defaults to **16384**, accepts integers **2048–1048576**, and is validated before execution.
Each receipt reports its exact `projection.emitted_bytes` and `max_bytes`. Fixed typed attempt
headers retain status/provenance (null when unrecorded), identities, aggregate check counts and
IDs. Collection retains all-history attempt/check counts and failure status even when a page
contains none of the failed records. Other header metadata stays in the original artifacts and
is identified by `metadata_projected: true`.

Check records are included whole or omitted whole. The encoder serializes complete JSON objects
and measures their UTF-8 bytes; it never slices serialized JSON. `projection` reports selected,
emitted and omitted check counts, oversized records, a `next_cursor`, and a `narrow` target. Each
included check carries its zero-based `check_index`. Attempt headers and check excerpts may be
omitted to honor the total budget; counts remain aggregate evidence, not a claim that omitted
checks passed. Default `run` detail is limited to 1024 excerpt bytes per stream before applying
the global budget. `collect --output-bytes` sets that per-stream limit independently.

Use `next_cursor` with collection and the same `--attempt`, `--limit` and `--check-index` selection.
For a cursor returned by `run`, collect that returned `attempt_id` explicitly. A changed latest
attempt invalidates a cursor; restart collection. Cursors can be reused and collection never
takes an execution lock or modifies evidence. A single record too large for an empty page is
omitted with `oversized_records: 1`, an advanced cursor, and a narrowing target containing its
attempt/check index and relative checkpoint path. For example:

```powershell
& 'C:/Program Files/nodejs/node.exe' 'C:/tools/delegate-task/check-runner.mjs' collect --batch 'booking-checks' --attempt 'attempt-1700000000000-aabbccddeeff' --check-index 0 --output-bytes 0 --max-bytes 32768
```

Raise the budget or inspect the named original checkpoint if the record's metadata alone is
larger than a page. Oversized metadata files still trigger the 1 MiB read limit; they are refused
without fabricating aggregate outcomes. A cursor describes traversal over current evidence;
terminal immutable attempts provide stable readback, while an incomplete attempt may advance
as its live owner writes checkpoints.

Excerpts contain complete lines from bounded head/tail reads, byte totals, omitted bytes and a
truncation flag. An oversized line can be omitted entirely. Public output redacts credential
assignments, common token formats, known credential environment values and explicit plan env
values; raw artifacts retain their original bytes. Arbitrary unlabeled secrets cannot be inferred.
Share only the projection after checking its contents.

`run` exits 0 for all checks passed, 1 for a completed batch with any non-pass, 2 for invalid
input/driver error (including invalid retry/identity), 3 for a competing owner, and 4 when an
existing attempt requires an explicit retry. `collect` exits 0 on successful readback even
when an attempt failed; consumers inspect the recorded statuses. Its invalid-input/error exit is 2.

## Delegate collection and startup

`delegate.mjs collect ID --summary [--max-chars 128..8000] [--max-items 1..100]` emits a bounded
JSON projection after normal v1/v2 normalization. Defaults are 2000 characters per string and
40 array items, with 32,000 total string characters, 1000 visited nodes and depth 12. Keys are
bounded too. `projection.omissions` identifies loss; normalised usage, status/provenance and
model reporting flags remain available. Actual model stays null when unobserved; the legacy
`model` fallback is still only a request. Raw usage is projected after core fields. Result metadata
over 8 MiB is refused in summary mode. Lost-run recovery in summary mode reads the journal with
bounded records and latest-state retention, and refuses raw logs over 64 MiB per stream; use the
legacy collector for recovery of larger historical runs. Existing `--json`, human output and raw artifacts retain
their previous behavior; summary collection never rewrites an existing result.

`status.execution` distinguishes `supervisor_preparing`, `heartbeat_only`, `unstructured_output`, `startup_stalled`, and
`harness_events`, and includes `last_structured_event_at`, `last_output_at`, stream byte counts
and a bounded diagnostic. A structured event is a complete stdout JSON object with a string
`type`; it proves event delivery, not task completion. Heartbeats alone prove only supervisor
liveness. The default `--no-output-after 60` window diagnoses a startup without structured
events; it never terminates a task or declares success.

An explicit `start --startup-timeout SEC` bounds the wait from child launch to its first structured
event. Expiry terminates the owned tree and records `abandoned` with `startup_timeout` provenance
and the last structured event time (null when absent). Stderr alone does not cancel the deadline.
There is no startup deadline by default; the existing overall `--timeout` remains independent.
No diagnostic retries a task or changes its requested model.
