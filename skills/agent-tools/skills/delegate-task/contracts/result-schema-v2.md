# Contract 3c — result schema v2 and backward read

Normative. This is compatibility, not a migration framework: nothing rewrites an old run.

## Discriminator

Every result written by this driver carries:

```json
{ "schema": "delegate-task.result.v2" }
```

`collect` dispatches on that field. A run directory whose `result.json` **has no `schema` key**
is a v1 run, written before this contract existed. It is read, not rewritten.

## Reading a v1 run

`collect` presents a v1 result through the v2 shape, filling what it can and leaving the rest
`null` rather than inventing it:

| v2 field | From v1 | Note |
| --- | --- | --- |
| `schema` | — | synthesised as `delegate-task.result.v1` |
| `legacy` | — | `true` |
| `status`, `summary`, `tokens`, `cost_usd`, `exit_code`, `duration_ms` | same names | carried across |
| `files_claimed` | `files_changed` | v1's field was always the delegate's self-report |
| `status_provenance` | — | `{ primary: "legacy", evidence: ["v1 run: provenance not recorded"] }` |
| `git_visible_after`, `dirty_paths_changed`, `head_changed`, `index_changed`, `read_only_violation` | — | `null` — v1 measured nothing |
| `coverage_complete` | — | `false` |
| `harness_version`, `session_id`, `parent_run_id`, `usage_raw` | — | `null` |
| `permission_requested` | `permission` | carried across |
| `permission_mode_applied`, `containment_evidence` | — | `null` |

A v1 run is labelled **`(v1)`** in `list` and carries a line in the printed result saying which
fields were never measured. It is never silently presented as though it had been.

## The v2 result

```json
{
  "schema": "delegate-task.result.v2",
  "run_id": "codex-20260825161438-0a9108",
  "parent_run_id": null,
  "harness": "codex",
  "harness_label": "OpenAI Codex",
  "harness_version": "0.147.0",
  "tier": "verified",

  "status": "successful",
  "status_reason": "",
  "status_provenance": { "primary": "harness_telemetry", "evidence": ["…"] },
  "summary": "…",

  "files_claimed": "report.txt",
  "git_visible_after": ["?? report.txt"],
  "dirty_paths_changed": ["report.txt"],
  "files_mismatch": false,
  "head_changed": false,
  "index_changed": false,
  "coverage_complete": true,
  "read_only_violation": null,

  "permission_requested": "bypass",
  "permission_mode_applied": "codex: --dangerously-bypass-approvals-and-sandbox",
  "containment_evidence": "not requested — run was write-capable",

  "tokens": { "input_total": 0, "input_fresh": 0, "cache_read": 0, "cache_write": 0,
              "output_total": 0, "reasoning": 0, "fidelity": "exact", "total": 0 },
  "usage_raw": { },
  "cost_usd": null,
  "cost_reported": false,
  "model_reported": false,

  "session_id": "0198…",
  "session_capture": "streaming",
  "envelope": "standard",
  "exit_code": 0,
  "signal": null,
  "duration_ms": 67028,
  "truncated_output": false,
  "records_dropped": 0,

  "task": "…",
  "cwd": "…",
  "model": null,
  "started_at": "…",
  "ended_at": "…",
  "artifacts": { "dir": "…", "stdout": "…", "stderr": "…", "journal": "…" }
}
```

## `envelope`

Which prompt wrapper the run used, and therefore how much of the result can be trusted to exist:

| Value | Meaning |
| --- | --- |
| `standard` | the full envelope — a self-report and `files_claimed` are expected |
| `delta` | a resumed dispatch; the same policy rules, restated, plus a delta objective |
| `raw` | `--raw`: no envelope at all, so **no self-report and no `files_claimed`** |

A `raw` run is lower-fidelity by construction: rule 8 of the status ladder can never fire, so a
blocked run that exits 0 has nothing to catch it. The field exists so a raw run cannot be mistaken
for an enveloped run whose delegate simply said nothing.

## `truncated_output` and `records_dropped`

Raw stream output is capped per stream at `DELEGATE_MAX_LOG_BYTES`. Past that point the driver
stops writing raw bytes and instead retains **complete parsed records**, bounded by
`DELEGATE_LOG_TAIL_BYTES`, which are appended before the adapter parses.

This matters because a byte suffix cannot parse a record whose opening delimiter was evicted: an
oversized terminal event would otherwise turn a finished run into `telemetry_incomplete`.

Retention begins **only once the cap is crossed**. Retaining earlier would replay records the log
already holds, and an additive adapter — OpenCode sums every `step_finish` — would count them
twice.

**The window keeps one record unconditionally.** If a single record exceeds
`DELEGATE_LOG_TAIL_BYTES` it is still kept when nothing newer has replaced it — the last record is
usually the terminal event, and evicting it to honour a byte bound would defeat the point of
retaining anything. So the real memory ceiling is the window **plus one record**, itself bounded by
the per-line anti-DoS limit (1,000,000 characters, which can exceed that many UTF-8 bytes).

- `truncated_output` — the cap was crossed on either stream.
- `records_dropped` — complete records the retention window could not hold, plus any record
  exceeding the per-line anti-DoS bound. **Non-zero means evidence is missing**: the terminal
  status is still sound, but the delegate's final answer may be truncated. Silence here would be
  the same class of false assurance the tri-state git verdict exists to prevent.

## `cost_reported` and `model_reported`

Not every CLI reports every field. Codex emits neither a cost nor a model anywhere in its event
stream, so both are `null` **by nature, not by a parsing failure**.

These two booleans say which: `false` means the harness never reports it, so the `null` is
expected and final. A `null` value with the flag `true` means we expected a figure and did not get
one — which is a defect worth chasing.

The printed result renders the difference as "not reported by this harness" rather than a bare
null, for the same reason `tokens.fidelity` exists: an absent measurement must not read as a
measured zero.

## `usage_raw`

The harness's own usage object, unmodified, kept beside the normalised `tokens`. It exists for
audit and for parser evolution — when an adapter's normalisation is later found wrong, the raw
record is what lets an old run be recomputed.

**Only normalised figures are displayed.** Rendering a raw field as though it were a total is the
defect this skill documents in gotcha 2 and found in a third-party relay; `usage_raw` is storage,
not presentation.

## `tokens.fidelity`

| Value | Meaning |
| --- | --- |
| `exact` | parsed from the harness's own usage report |
| `partial` | some fields found, some absent |
| `unavailable` | no usage was reported — the zeroes mean *unknown*, not *free* |

## Single-writer rule

A result is written **exactly once**, and never patched afterwards — a post-write amendment
reopens the window the claim exists to close.

Ownership is taken by an exclusive create (`wx`) of `result.json.claim`, recording the owner's
pid. The winner writes `result.json.tmp.<pid>` and renames it into place. The normal completion
path, a signal handler and a `collect` synthesising from a dead run all contend through that
claim.

**Recovery must not be a blind overwrite, and must not be an unlink.** Overwriting a stale claim
lets two contenders both believe they own it. Unlinking is not a compare-and-swap either: the
claim inspected need not be the claim deleted (an ABA race). A stealer therefore:

1. refuses outright if the recorded owner process is **alive** — age alone never revokes a live
   writer, which may simply be doing slow git work;
2. **renames** the claim to a unique capture name — a given source rename succeeds for exactly
   one caller, the losers get `ENOENT`;
3. re-reads the object it actually captured, and puts it back untouched if that owner turns out
   to be alive.

A caller that loses gets `null`, which means **retry** — never a result.

## Journal

`journal.jsonl`, one JSON object per line, append-only:

```jsonl
{"t":"2026-08-25T16:14:38.001Z","state":"created"}
{"t":"…","state":"supervisor_started","pid":12345,"nonce":"a1b2c3"}
{"t":"…","state":"child_started","pid":12377}
{"t":"…","state":"session","session_id":"0198…"}
{"t":"…","state":"heartbeat"}
{"t":"…","state":"terminal","status":"successful"}
```

`collect` reads it to classify a run with no terminal result. Only one of these states may be
finalised:

| State | Supervisor | Harness | `collect` |
| --- | --- | --- | --- |
| `running` | alive, heartbeat current | — | waits |
| `stalled` | **alive**, heartbeat stale | — | **refuses** — it may still finish |
| `adrift` | gone | **alive** | **refuses** — a result now would snapshot a run in motion |
| `lost` | gone | gone | finalises as `abandoned` / `supervisor_lost` |

**A late heartbeat is not death.** A live supervisor is never declared lost on heartbeat age
alone, and a live child is never finalised around. A heartbeat timestamp that is unparseable, or
meaningfully in the future, counts as *no* heartbeat rather than as proof of life — otherwise a
bad clock would keep a dead run looking alive forever.

Runs are identified by pid, with no persisted process incarnation. Pid reuse can therefore leave a
run wedged in `stalled` or `adrift`. That is the conservative failure: it never publishes a
competing result.
