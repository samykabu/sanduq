---
name: delegate-task
description: Delegate a task to an external agent CLI harness — Claude Code, OpenAI Codex, OpenCode, GitHub Copilot, or Pi — and get back a normalised result with status (successful / failed / abandoned), a summary, what actually changed on disk measured against git, and total input and output token usage. Use when asked to "use codex to ...", "delegate this to opencode", "have another agent do X", "run this task on a different model", to get a second opinion from another harness, or to compare harnesses on the same task.
---

# Delegate a task to another agent CLI

Runs one task on an external agent CLI **in the background** and returns a normalised
result.

Driver: `delegate.mjs`, in this skill's own directory (Node ≥ 18, no dependencies).
Behaviour is defined by three contracts in `contracts/` — read them before changing the driver.

`start` returns a `run_id` immediately; `collect` retrieves the result. Nothing blocks you.

## Resolve the driver and the runs directory first

Where this skill is installed decides where `delegate.mjs` lives, and run artifacts default to
sitting **beside the driver**. Set both once per session, then use `$DELEGATE` in every command
below:

```bash
# Claude Code plugin install (agent-tools@sanduq)
DELEGATE="$CLAUDE_PLUGIN_ROOT/skills/delegate-task/delegate.mjs"

# npx skills install, or a copy committed into the repository
DELEGATE=".claude/skills/delegate-task/delegate.mjs"

# Keep run artifacts in the project being worked on, not next to the driver
export DELEGATE_RUNS_DIR="$PWD/.delegate/runs"
```

`DELEGATE_RUNS_DIR` is **required** for a plugin install: without it, artifacts from every project
accumulate inside the shared plugin directory, and they contain your task text and the harness's
raw output. Add `.delegate/` to the project's `.gitignore`. Every command that touches a run
— `start`, `status`, `collect`, `list`, `prune` — must see the same value.

## Check what is available first

```bash
node "$DELEGATE" doctor
```

`doctor` probes each CLI's version, so it distinguishes **not installed** from **installed but
broken** — and prints what `--sandbox` actually requests of each one.

| harness | id | tier | resume | `--sandbox` requests |
|---|---|---|---|---|
| Claude Code | `claude` | verified | verified | `--permission-mode plan` |
| OpenAI Codex | `codex` | verified | verified | `-s read-only` (CLI-enforced) |
| OpenCode | `opencode` | verified | verified | `--agent plan` |
| GitHub Copilot | `copilot` | **experimental** | experimental | `--mode plan` |
| Pi | `pi` | **experimental** | experimental | `--no-approve --tools read,grep,find,ls` |

Prefer `claude`, `codex`, or `opencode`.

## Run a delegation

```bash
node "$DELEGATE" start \
  --harness codex \
  --cwd /path/to/workspace \
  --timeout 600 \
  --task "Add input validation to parse_config() and a test covering the bad-input path."
```

Prints `{"run_id": "codex-…", "state": "running", ...}` and returns. Then:

```bash
node "$DELEGATE" collect codex-… --wait 300
```

`--wait N` polls for up to N seconds. Without it, `collect` exits 3 if the run is still going.

Other commands:

```bash
node "$DELEGATE" status <run_id>                 # starting|running|stalled|adrift|lost|done
node "$DELEGATE" collect <run_id> --json         # the machine-readable result — parse this
node "$DELEGATE" list                            # every run, oldest first
node "$DELEGATE" prune --keep 20 --yes           # delete old run artifacts
node "$DELEGATE" contract                        # machine-readable flags, fields, exit codes
```

## Reading the result

```
Status       SUCCESSFUL
Because      harness_telemetry

Changes
  measured   greeting.txt
  claimed    greeting.txt

Permission   requested=bypass  applied=codex: --dangerously-bypass-approvals-and-sandbox
```

Three fields carry most of the meaning:

- **`status`** — `successful` / `failed` / `abandoned`.
- **`status_provenance.primary`** — *why* that status, in one word: `timeout`, `spawn_error`,
  `signal`, `exit_code`, `parse_error`, `telemetry_incomplete`, `harness_telemetry`,
  `self_report`, `head_moved`, `index_moved`, `relay_aborted`, `supervisor_lost`, `legacy`.
  Never report a status without knowing which of these produced it. `evidence` lists **every**
  observation that was true, not just the one that won.
- **`dirty_paths_changed`** — what **git measured**, as opposed to `files_claimed`, which is what
  the delegate *said*. `files_mismatch` flags disagreement.

## Permissions

**Default is full bypass.** The delegate runs arbitrary commands unattended.

`--sandbox` requests each CLI's real read-only mode (table above) and turns on the tripwire:
`read_only_violation` is `true` / `false` / **`null`**. `null` means *unknown* — git was
unavailable or fingerprint coverage was incomplete. It is never collapsed to `false`.

**`false` does not mean "no writes occurred."** It means no covered final-state delta was
detected. It cannot see a write-then-revert, anything gitignored, or any write outside the repo.
**`true` does not mean the delegate did it** — a concurrent edit in the same worktree looks
identical.

The envelope tells the delegate not to commit, but that is **policy, not enforcement**. What
enforces it is measurement: if HEAD moves during the run window the result is forced to
review-required (`head_moved`) unless you passed `--allow-commit`.

## Continuing a run

```bash
node "$DELEGATE" start --harness codex --cwd <same dir> --resume <run_id> \
  --task "The fix is right, but use the real fixture instead of a mock."
```

Send only the delta. Resume gets a **new** `run_id` with `parent_run_id` set, and refuses if the
harness, the working directory, or the parent's session id do not line up.

A resumed dispatch **repeats every policy rule** rather than assuming the parent session still
honours them.

## Flags

| flag | use |
|---|---|
| `--cwd DIR` | working directory — **always set it explicitly** |
| `--model M` | override the model |
| `--timeout SEC` | default 1800; validated up front; on expiry the tree is killed → `abandoned` |
| `--deliverable TEXT` | what to hand back ("a unified diff, do not commit") |
| `--constraint TEXT` | repeatable extra rule |
| `--sandbox` | request the harness's read-only mode |
| `--allow-commit` | permit committing, and stop treating a moved HEAD as review-required |
| `--resume <run_id>` | continue a finished run's session with a delta task |
| `--clean-env` / `--keep-env N` | hand the CLI only runtime basics; repeat `--keep-env` per variable needed for auth |
| `--raw` | send the task verbatim (loses status/summary; incompatible with `--resume`) |

## Gotchas

1. **Exit code 0 does not mean the task was done** — and until this refactor, a **non-zero exit
   did not mean it failed**. Adapters were handed the exit code and none read it, so a
   success-shaped event plus exit 1 was published `successful`. Fixed; pinned by
   `test/run.mjs` case `REPAIR-D1`. Always read `status_provenance`, never `exit_code` alone.
2. **Token fields mean different things per harness.** Claude's `input_tokens` /
   `cache_creation` / `cache_read` are **disjoint** — sum them (a probe reported `input_tokens: 2`
   for a request that really sent 58,065). Codex's `input_tokens` is **inclusive** of
   `cached_input_tokens` — subtract for the fresh count. Use `input_total` / `input_fresh`;
   `usage_raw` keeps the harness's own numbers for audit but is never displayed as a total.
3. **Totals are not comparable across harnesses.** OpenCode emits one `step_finish` per step and
   the driver sums them, so context re-sent each step is counted each time. Same trivial task:
   66,341 (codex), 117,014 (claude), 426,523 (opencode). Not an efficiency ranking.
4. **Delegating to `claude` has a ~58k token floor.** `claude -p` loads CLAUDE.md and every
   discovered skill before reading the task.
5. **Codex inherits your MCP servers.** If codex feels slow, read `runs/<run_id>/stderr.log` —
   the delay is usually MCP, not the model.
6. **Codex emits `item.type: "error"` events on successful runs.** Only `turn.failed` or a
   missing `turn.completed` counts.
7. **Full bypass really is unsandboxed.** An OpenCode delegate once wrote a file *outside* its
   `--cwd`. Use `--sandbox`, or a throwaway directory.
8. **Not every harness reports every field.** Copilot emits no token counts at all
   (`fidelity: "unavailable"` — zeroes mean *unknown*, not *free*). **Codex emits neither a cost
   nor a model** anywhere in its JSONL, so `cost_usd` and `model` are null by nature, not by a
   parsing failure — `cost_reported` / `model_reported` say which, and the printed result reads
   "not reported by this harness". Claude reports both; OpenCode reports cost.
9. **Task text never reaches a shell.** Each CLI is resolved to a real executable and spawned
   with `shell:false`.
10. **`pi` persists a session in its own store.** `--no-session` is deliberately not passed —
    without a session there is nothing to resume. Sessions land in
    `~/.pi/agent/sessions/<cwd-slug>/`, keyed by working directory; `prune` does not touch them.
    Pi's auth is file-based (`~/.pi/agent/auth.json`), so `--clean-env` does not break it.
11. **A run whose supervisor is killed is `lost`, not stuck.** `collect` synthesises a terminal
    result from the journal and logs. Its git delta is `null`: no run-start baseline survived, and
    reporting `false` would be an assurance nothing measured.
12. **Run ids are validated.** They must match `<harness>-<14 digits>-<6 hex>`, and must resolve
    directly under the runs directory. A caller-supplied id cannot traverse out of it.
13. **A dead supervisor whose harness is still alive is `adrift`, not `lost`.** `collect` refuses
    to publish, because a result written then would snapshot a run still in motion. Wait for the
    child, or kill the pid `status` names. `prune` will not delete an adrift run either.
14. **`DELEGATE_BIN_<HARNESS>` overrides where a binary is found** — e.g.
    `DELEGATE_BIN_CODEX=/opt/codex/bin/codex`. It is also how the test suite drives a fake harness
    end to end without spending a token.

## Troubleshooting

| symptom | cause / fix |
|---|---|
| `<bin> not found on PATH` | that CLI is not installed; run `doctor` |
| `found <path> but could not resolve what it launches` | the CLI is installed behind a non-npm `.cmd` shim this driver cannot decode |
| `doctor` shows `BROKEN: probe timed out` | usually a cold start; re-run `doctor` before concluding anything |
| `supervisor failed to start` (exit 5) | the detached supervisor never acknowledged; check `runs/<id>/journal.jsonl`. The run is finalised `failed` with `containment_evidence: "the harness never launched"`; if the journal holds only `created` and `terminal` and the supervisor pid is gone, no agent ran |
| `run <id> still executing` (exit 3) | add `--wait <seconds>` |
| `Refusing to publish … still running` (exit 6) | the run is `adrift`: the supervisor died but the harness lives. Wait, or kill the pid it names |
| `another process is finalising this run` (exit 7) | a live writer holds the claim; retry in a moment |
| `written by a different driver` (exit 8) | the result carries an unknown schema; this build will not guess at it |
| status `abandoned`, provenance `supervisor_lost` | the supervisor was killed; inspect the working tree before re-dispatching |
| status `failed`, provenance `head_moved` / `index_moved` | something committed or staged during the run; the tree is preserved, review it |
| Summary reads `(no summary produced)` | the delegate never emitted the result block; read `runs/<run_id>/stdout.log` |

## Files

Run artifacts live in `$DELEGATE_RUNS_DIR/<run_id>/` (`prompt.txt`, `meta.json`, `journal.jsonl`,
`stdout.log`, `stderr.log`, `result.json`). Unset, `DELEGATE_RUNS_DIR` defaults to `runs/` beside
the driver — which is the shared plugin directory on a plugin install, so set it. Cap log size
with `DELEGATE_MAX_LOG_BYTES` (default 32 MB per stream) and the post-cap retention window with
`DELEGATE_LOG_TAIL_BYTES` (default 512 KB).

Past the cap the driver keeps **complete parsed records** rather than a byte suffix, so telemetry
still parses. Records the window cannot hold are counted in **`records_dropped`** — a non-zero
value means the status is still sound but the delegate's own final answer may be incomplete.

⚠️ **Artifacts hold your task text, the full prompt and the harness's raw output — treat them as
sensitive.** On POSIX the runs directory is `chmod 0700`; on Windows permissions are inherited and
this driver cannot restrict them. Clean up with `prune`.

## Going deeper

- `contracts/status-precedence.md` — how a status is decided, and the cross-product to test
- `contracts/git-fields.md` — what the tripwire measures and what it cannot see
- `contracts/result-schema-v2.md` — the result shape, v1 backward read, journal, single-writer
- `references/writing-the-brief.md` — how to write a task the delegate can execute blind
- `references/reviewing-the-result.md` — how to review what comes back, including the sweep
- `references/task-queues.md` — running several dependent tasks without losing the thread

Tests: `node test/run.mjs`, from this skill's directory.
