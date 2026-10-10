# Contract 3a — terminal status precedence

Version `delegate-task.result.v2`. This contract is normative: the driver implements it and
`test/run.mjs` tests it as a cross-product per adapter.

## The three statuses

| Status | Meaning |
| --- | --- |
| `successful` | The objective was fully met. |
| `failed` | It was attempted and did not work, or the run broke. |
| `abandoned` | It stopped early — blocked, timed out, out of quota, out of room, or lost. |

## The ladder

Evaluated top to bottom. **The first rule that matches wins**, and it sets
`status_provenance.primary`. Every observation that was true — matched or not — is appended to
`status_provenance.evidence`, so a run that timed out *after* reporting success telemetry keeps
both facts.

| # | Condition | Status | `primary` |
| --- | --- | --- | --- |
| 1 | The watchdog fired | `abandoned` | `timeout` |
| 2 | The child failed to spawn | `failed` | `spawn_error` |
| 3 | The child died on a signal we did not send | `failed` | `signal` |
| 4 | **Process exit code is non-zero** | `failed` | `exit_code` |
| 5 | The adapter threw while parsing | `failed` | `parse_error` |
| 6 | Telemetry is incomplete — no terminal event | `abandoned` | `telemetry_incomplete` |
| 7 | The adapter returned a status outside the vocabulary | `failed` | `parse_error` |
| 8 | Harness telemetry reports failure or abandonment | as reported | `harness_telemetry` |
| 9 | The delegate's own envelope verdict is `failed` or `abandoned` | as reported | `self_report` |
| 10 | HEAD moved during the run window, without `--allow-commit` | `failed` | `head_moved` |
| 11 | The staged set changed, without `--allow-commit` | `failed` | `index_moved` |
| 12 | Nothing above matched | `successful` | `harness_telemetry` |

### Rule 7 makes the ladder total

An adapter that returns `undefined`, or any string outside
`successful` / `failed` / `abandoned`, is a defect **in the adapter** — not a new status. It is
reported as `parse_error` rather than escaping into a published result.

### Rules 10–11 are integrity gates, and they sit last on purpose

They cannot mask a real failure: a run that already failed keeps its own reason. But the movement
is **always recorded in `evidence`**, whichever rule wins the primary slot — an integrity signal
that vanishes because something else went wrong first would hide the very thing it exists to
surface.

### Rule 4 is the D1 repair

Before this contract, the exit code was passed to every adapter and read by none, and the
resolution had no exit-code branch. A harness that emitted success-shaped telemetry and then
exited non-zero was published `successful`, contradicting the precedence the README documented.
Rule 4 is that repair; `test/run.mjs` case `D1-exit-nonzero` pins it.

### Rule 8 only ever refines a clean run

The delegate's self-report cannot rescue a run that failed at rules 1–7, and cannot turn a
`failed` harness verdict into `successful`. It exists to catch the inverse — the case recorded in
gotcha 1, where a blocked run exits 0 having accomplished nothing. A self-report of `successful`
on an otherwise-clean run is accepted but changes nothing.

## `status_provenance`

```json
{
  "primary": "timeout",
  "evidence": [
    "watchdog fired after 600s",
    "harness telemetry: successful",
    "exit_code: -1",
    "self_report: absent"
  ]
}
```

`primary` is one of: `timeout`, `spawn_error`, `signal`, `exit_code`, `parse_error`,
`telemetry_incomplete`, `harness_telemetry`, `self_report`, `head_moved`, `index_moved`,
`supervisor_lost`, `relay_aborted`, `legacy`.

**Evidence is not a subset of the matched rule.** Every observation that was true is listed —
the watchdog firing, a spawn error, a moved HEAD, an `--allow-commit` override — regardless of
which rule produced `primary`.

The last two are written by the recovery path, not by this ladder:

- `relay_aborted` — the supervisor caught SIGTERM/SIGINT/SIGHUP and finalised before dying.
- `supervisor_lost` — no handler could run (SIGKILL, crash, native-Windows hard kill) and
  `collect` synthesised a terminal result from the journal, logs and a git snapshot.

Both produce `abandoned`.

## Cross-product to test

Per adapter, every combination of:

- harness telemetry: `successful` · `failed` · `abandoned` · absent · malformed
- exit code: `0` · non-zero · `null` (signal)
- self-report: `successful` · `failed` · `abandoned` · absent
- watchdog: fired · not fired

The suite does not enumerate all of them; it pins the boundary cases where two rules disagree,
which is where a regression would land.
