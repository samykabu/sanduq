# delegate-task

> النسخة العربية: [README.ar.md](README.ar.md)

Hand one task to another agent CLI — Claude Code, OpenAI Codex, OpenCode, GitHub Copilot or Pi —
run it in the background, and get back a result you can actually trust.

It is a [Claude Code skill](https://docs.claude.com/en/docs/claude-code/skills), so Claude picks it
up when you say *"use codex to refactor this"*. It is also just a Node script, so you can drive it
from any shell.

## Install

`delegate-task` ships in the [sanduq](https://github.com/samykabu/sanduq) `agent-tools` plugin
bundle.

```text
/plugin marketplace add samykabu/sanduq
/plugin install agent-tools@sanduq
```

Or install just this skill into the current project:

```bash
npx skills add samykabu/sanduq --skill delegate-task
```

Where it lands decides where the driver is, so resolve it once and reuse it:

```bash
# plugin install
DELEGATE="$CLAUDE_PLUGIN_ROOT/skills/delegate-task/delegate.mjs"
# npx skills install, or a copy committed into the repository
DELEGATE=".claude/skills/delegate-task/delegate.mjs"

# keep run artifacts in the project, not beside the driver
export DELEGATE_RUNS_DIR="$PWD/.delegate/runs"
```

Set `DELEGATE_RUNS_DIR` on a plugin install and add `.delegate/` to the project's `.gitignore`.
Artifacts hold your task text and the harness's raw output; without it they accumulate in the
shared plugin directory, mixed across every project.

## Why it exists

Shelling out to another CLI is the easy part. Finding out what happened is not.

Every harness tells you it finished. None of them tells you whether the job got done. And the three
signals you would naturally reach for are each misleading on their own:

**Exit code 0 means nothing.** A sandboxed run that was blocked from writing exits perfectly
cleanly, having achieved nothing at all. That run is in our test fixtures.

**The delegate's summary is a claim.** It will tell you which files it touched. It can be wrong,
and it has no way to notice.

**Token numbers don't mean what you think.** One CLI's `input_tokens` excludes cache, another's
includes it, a third reports per step and needs summing. Read them raw and you can be off by four
orders of magnitude. We measured a run that reported `input_tokens: 2` for a request that really
sent 58,065.

So this skill measures the run instead of relaying it. Every result carries a status **and the rule
that produced it**, what git actually saw change on disk next to what the delegate said it changed,
normalised token counts with a flag saying how far to trust them, and a run registry that outlives
the session that started it.

Five harnesses sit in one lookup table. Adding a sixth is a table entry, not a new program.

## How a run works

![One delegated run, start to collect](assets/delegate-run-lifecycle.png)

*Source: [`assets/delegate-run-lifecycle.html`](assets/delegate-run-lifecycle.html)*

The baseline is the whole point. Fingerprinting the tree *before* the harness starts is what lets a
result say "these three files changed during this run" instead of "here is everything dirty in your
repo, good luck".

## Requirements

- **Node 18+.** No dependencies, nothing to install.
- At least one agent CLI on `PATH`, already logged in.
- `git`, for the measurement layer. Without it every git field reports `null`, never `false`.

```bash
node "$DELEGATE" doctor
```

`doctor` probes each CLI's version, so it can tell *not installed* from *installed but broken*, and
it prints what `--sandbox` actually asks of each one.

## Example prompts

You can ask Claude in plain English, or drive the script yourself. Both are shown.

### Hand a bounded job to Codex

> use codex to add input validation to `parse_config()` in `src/config.py`, plus a test for the
> bad-input path. Run `pytest -q` and make it green. Don't touch anything else.

```bash
node "$DELEGATE" start \
  --harness codex --cwd ~/work/myrepo --timeout 1800 \
  --constraint "Touch only src/config.py and tests/test_config.py." \
  --task 'The job: parse_config() accepts malformed TOML and fails later with a confusing
KeyError. Validate up front and raise ConfigError naming the offending key.

Gates: run `pytest -q` and `ruff check src/`, make both green.

Report: what changed, files touched, the pytest count, and anything you decided that
this brief did not settle.'
```

### Get a second opinion without letting it write

> ask codex to review the auth middleware for security problems, read-only

```bash
node "$DELEGATE" start \
  --harness codex --cwd ~/work/myrepo --sandbox --timeout 900 \
  --deliverable "A findings list. Do not modify anything." \
  --task 'Review src/middleware/auth.py for authentication and session-handling flaws.
Ground every claim in a line reference. Label inferences as inferences.'
```

`--sandbox` asks the CLI for its real read-only mode and switches on the tripwire, so afterwards
the result tells you whether anything moved anyway.

### Pin a specific model

> run that one on opus instead

```bash
# Claude Code
delegate.mjs start --harness claude --model opus --cwd ~/work/myrepo \
  --task 'Explain why the retry loop in worker.py can spin forever, then fix it.'

# Codex
delegate.mjs start --harness codex --model gpt-5.5 --cwd ~/work/myrepo --task '...'

# OpenCode wants a provider-qualified name
delegate.mjs start --harness opencode --model anthropic/claude-sonnet-4-5 \
  --cwd ~/work/myrepo --task '...'
```

Model naming is the harness's own. We pass it through untouched.

### Continue the same session instead of starting over

This is the one that saves real money. The first run pays to load your repo context. A resume
reuses it.

```bash
# first run
delegate.mjs start --harness codex --cwd ~/work/myrepo \
  --task 'Add a --dry-run flag to the migrate command.'
# → codex-20260825164159-5f4cd3

delegate.mjs collect codex-20260825164159-5f4cd3 --wait 600

# it works, but the tests mock something they shouldn't. Send only the correction:
delegate.mjs start --harness codex --cwd ~/work/myrepo \
  --resume codex-20260825164159-5f4cd3 \
  --task 'The flag is right, but the test mocks the DB session. Use the real migrated
fixture and drop the now-unused import.'
```

The delegate still holds its own context, which is why the delta can be that short. In our testing
a resume brief that said only *"the file you just created"* — never naming it — edited exactly the
right file.

A resume gets a **new** `run_id` carrying `parent_run_id`, and it refuses if the harness, model,
CLI version, working directory or repository identity don't line up.

### Compare two harnesses on the same task

> give the same refactor to codex and opencode and show me what each one cost

```bash
T='Extract the retry logic from worker.py into a reusable decorator. Keep behaviour identical.'

delegate.mjs start --harness codex    --cwd ~/work/copy-a --task "$T"
delegate.mjs start --harness opencode --cwd ~/work/copy-b --task "$T"

delegate.mjs list      # both side by side: status, provenance, tokens
```

Give each one its own copy of the tree. Two harnesses editing one directory will each report the
other's changes, for reasons covered below.

### Let it commit (off by default)

```bash
delegate.mjs start --harness codex --cwd ~/work/myrepo --allow-commit \
  --task 'Bump the version to 2.4.0, update CHANGELOG.md, commit both.'
```

Without `--allow-commit` a moved `HEAD` forces the result to review-required. The driver never
undoes the commit. It might have been yours.

### Keep your environment out of a third-party binary

```bash
delegate.mjs start --harness codex --cwd ~/work/myrepo \
  --clean-env --keep-env CODEX_API_KEY \
  --task 'Summarise what this service does, from the code.'
```

By default the harness inherits everything you have exported, including credentials for services
that have nothing to do with it.

## Running several at once

`start` returns immediately, so fanning out is just several `start` calls. There is nothing extra
to configure.

![Three runs at once, one tree each](assets/delegate-parallel-fanout.png)

*Source: [`assets/delegate-parallel-fanout.html`](assets/delegate-parallel-fanout.html)*

Measured here, three Codex runs against one repo:

| | |
|---|---|
| Dispatched | all three within 1 second |
| Wall clock | 130 s for all three |
| Per-run duration | 125.5 s · 125.4 s · 115.5 s |
| Outcome | all `successful`, all three files created |

Sequentially that would have been roughly the sum. The saving is real because harness startup
dominates a small task.

```bash
for n in alpha beta gamma; do
  delegate.mjs start --harness codex --cwd ~/work/$n --timeout 600 \
    --task "...the task for $n..."
done

delegate.mjs list                            # watch them
delegate.mjs collect <run_id> --wait 600     # once per run
```

⚠️ **Give each parallel run its own working directory.** In the run above all three shared one
repo, and every result listed all three files as changed with `files_mismatch: true`. That is the
measurement layer being honest rather than wrong: it watches the tree, not the author. The contract
says as much — `read_only_violation: true` means *something changed in this window*, never *this
delegate did it*.

Parallel **review** is the case where sharing a directory is fine, because nobody writes:

```bash
for h in codex claude opencode; do
  delegate.mjs start --harness $h --cwd ~/work/myrepo --sandbox \
    --task 'Review the diff on this branch for correctness bugs. Cite line numbers.'
done
```

## Reading the result

```text
Delegation codex-20260825164159-5f4cd3
Harness      OpenAI Codex codex-cli 0.147.0  model=not reported by this harness
Status       SUCCESSFUL
Because      harness_telemetry
Duration     56.7s   exit=0

Summary
  I created greeting.txt with exactly one line containing HELLO. I verified its
  byte content and did not modify any other file.

Changes
  measured   greeting.txt
  claimed    greeting.txt

Permission   requested=bypass  applied=codex: --dangerously-bypass-approvals-and-sandbox

Tokens (exact)
  input   total 66167  (fresh 12663, cache read 53504, cache write 0)
  output  total 409  (reasoning 68)
  TOTAL   66576
  cost    not reported by this harness

Session      01a039cc-d62a-7260-9afa-61ee7c8e03e4   resume with: --resume codex-20260825164159-5f4cd3

Logs         .delegate/runs/codex-20260825164159-5f4cd3
```

Four things to read, in this order:

**`Because`** — the rule that decided the status. `self_report` means the delegate's own word
settled it. `exit_code`, `timeout`, `head_moved` and the rest each mean something quite different,
and `evidence` in the JSON lists everything else that was true.

**`measured` against `claimed`** — git versus the delegate. Disagreement gets a warning; a claim
that couldn't be checked says so, rather than showing you a quiet pass.

**The session line** — the full id, and the exact command to continue it. It is never abbreviated
in the result or in `--json`.

**Token fidelity** — `exact`, `partial` or `unavailable`. On `unavailable` the zeroes mean
*unknown*, not *free*.

Not every CLI reports everything. Codex emits no cost and no model anywhere in its stream, so both
read *not reported by this harness* rather than a bare null that looks like a bug. Claude reports
both; OpenCode reports cost.

## Commands

| Command | What it does |
|---|---|
| `start --harness <id> --task <text>` | queue a run, print the `run_id`, return at once |
| `collect <run_id> [--wait SEC] [--json]` | fetch the result; exits `3` if still going |
| `status <run_id>` | `starting` · `running` · `stalled` · `adrift` · `lost` · `done` |
| `list` | every run, oldest first, with status, provenance and tokens |
| `doctor` | which harnesses resolve, versions, what `--sandbox` asks of each |
| `prune [--keep N] [--older-than DAYS] [--yes]` | delete old artifacts; dry run without `--yes` |

## Flags

| Flag | Use |
|---|---|
| `--cwd DIR` | working directory. **Always set it.** |
| `--model M` | pin a model, in the harness's own naming |
| `--timeout SEC` | default 1800, validated up front; on expiry the tree is killed → `abandoned` |
| `--deliverable TEXT` | what to hand back ("a unified diff, do not commit") |
| `--constraint TEXT` | an extra rule, repeatable |
| `--sandbox` | ask the harness for its read-only mode, and switch on the tripwire |
| `--allow-commit` | let it commit, and stop treating a moved `HEAD` as review-required |
| `--resume <run_id>` | continue a finished run's session with a delta |
| `--clean-env` / `--keep-env NAME` | hand the CLI only runtime basics; name what it needs |
| `--raw` | send the task verbatim; loses the status block, can't be resumed |

## Contracts

Behaviour is written down before it is coded. Three documents in [`contracts/`](contracts/) are
normative, and the test suite runs against them:

- [`status-precedence.md`](contracts/status-precedence.md) — the ladder that decides a status
- [`git-fields.md`](contracts/git-fields.md) — what the measurement layer sees, and what it cannot
- [`result-schema-v2.md`](contracts/result-schema-v2.md) — the result shape, v1 backward read, the
  journal, the single-writer rule

## The measurement layer

Before the harness starts and after it exits, in the run's `--cwd`:

- `HEAD`, the staged set, and `git status --porcelain=v1 -z` (NUL-safe, rename origins consumed)
- **content fingerprints of the paths that were already dirty**, because editing a file that was
  already modified never changes its porcelain line

`dirty_paths_changed` is the delta. `git_visible_after` is the whole dirty tree, baseline included.
`files_claimed` is the delegate's word. `files_mismatch` compares the claim against **the delta
only** — comparing against the whole tree would turn a file you left dirty yesterday into an
accusation.

### `read_only_violation` has three values

`true`, `false`, and **`null`**. You get `null` whenever git couldn't answer or fingerprint coverage
was incomplete. It is never quietly turned into `false`, because that is the one answer a tripwire
must never give when it doesn't know.

- **`false` is not "nothing was written."** It means no covered final-state change was detected. It
  cannot see a write-then-revert, anything gitignored, or writes outside the repo.
- **`true` is not "the delegate did it."** Your own editor saving a file in that window looks
  exactly the same.

### The commit boundary

The envelope tells the delegate not to commit. That is policy, not enforcement — a bypassed CLI can
ignore it. What backs it is measurement: if `HEAD` moves, the status is forced to `failed` with
provenance `head_moved`, unless you passed `--allow-commit`. The driver never resets, checks out or
cleans anything. It keeps the evidence and reports what it saw.

## Status precedence

First matching rule wins; every observation is kept as evidence either way.

| # | Condition | Status | provenance |
|---|---|---|---|
| 1 | watchdog fired | `abandoned` | `timeout` |
| 2 | child failed to spawn | `failed` | `spawn_error` |
| 3 | died on a signal | `failed` | `signal` |
| 4 | **non-zero exit** | `failed` | `exit_code` |
| 5 | adapter threw | `failed` | `parse_error` |
| 6 | no terminal event | `abandoned` | `telemetry_incomplete` |
| 7 | adapter returned a status outside the vocabulary | `failed` | `parse_error` |
| 8 | harness reported failure | as reported | `harness_telemetry` |
| 9 | delegate self-reported failure | as reported | `self_report` |
| 10 | `HEAD` moved, no `--allow-commit` | `failed` | `head_moved` |
| 11 | staged set changed, no `--allow-commit` | `failed` | `index_moved` |
| 12 | nothing above | `successful` | `harness_telemetry` |

Rule 4 is a repair. The exit code used to be passed to every adapter and read by none, so a
success-shaped event plus exit 1 was published as `successful` — the opposite of what this file
documented. The integrity gates sit last so they can't mask a real failure, but the movement is
recorded in `evidence` whichever rule wins.

## Recovery

`start` waits for the detached supervisor to record `supervisor_started` in the journal before
reporting `running`. A supervisor that never acknowledges produces a terminal start-failure instead
of a run that claims `running` forever.

While the run is live the supervisor heartbeats. The states are deliberately cautious:

| State | Supervisor | Harness | `collect` |
|---|---|---|---|
| `running` | alive, heartbeat current | — | waits |
| `stalled` | **alive**, heartbeat stale | — | **refuses** — it may still finish |
| `adrift` | gone | **alive** | **refuses** — a result now would freeze a run in motion |
| `lost` | gone | gone | writes a terminal result |

A lost run is rebuilt from the journal, the logs and a git snapshot. **Its git delta is `null`**,
because no run-start baseline survived and `false` would be a claim nobody measured.

On POSIX, SIGTERM/SIGINT/SIGHUP handlers finish the job before dying. Windows has no catchable
SIGTERM, and nothing survives SIGKILL, which is what the heartbeat path is there for.

## Understanding the token numbers

The harnesses disagree about what `input_tokens` means:

| Harness | Convention | What we do |
|---|---|---|
| Claude | `input` / `cache_creation` / `cache_read` are **separate** | sum them into `input_total` |
| Codex | `input_tokens` **already includes** cached | subtract cached for `input_fresh` |
| OpenCode | one `step_finish` **per step** | sum across all steps |

Use `input_total` for everything sent, `input_fresh` for the uncached part that drives cost.
`usage_raw` keeps each harness's own object so an old run can be recomputed if a parser later turns
out wrong. It is never displayed as a total.

**Totals aren't comparable between harnesses.** The same trivial task came to 66,341 (codex),
117,014 (claude) and 426,523 (opencode). OpenCode re-sends context every step and we count each
one. That is not an efficiency ranking.

## Safety

**The default is full bypass.** The delegate runs arbitrary shell commands unsupervised. That is
deliberate, and it is real: on the very first bypass test an OpenCode delegate wrote a file
*outside* its `--cwd` before tidying up after itself.

`--sandbox` asks each CLI for its documented read-only mode:

| Harness | Requests |
|---|---|
| `codex` | `-s read-only`, enforced by the CLI |
| `claude` | `--permission-mode plan` |
| `opencode` | `--agent plan`, never `--auto` |
| `copilot` | `--mode plan` |
| `pi` | `--no-approve --tools read,grep,find,ls` |

`--clean-env` hands over only runtime basics, with `--keep-env NAME` for each variable the CLI
genuinely needs. It filters inherited variables. It does not protect files, other same-user
secrets, or anything the CLI prints itself.

⚠️ **Run artifacts are sensitive.** `prompt.txt` holds your whole task; `stdout.log` holds whatever
the harness printed, which can include secrets. On POSIX the runs directory is `chmod 0700`; on
Windows permissions are inherited and we cannot restrict them. Clear them with `prune`.

Run ids are validated (`<harness>-<14 digits>-<6 hex>`) and must resolve directly inside the runs
directory, so a supplied id cannot walk out of it.

## Adding a harness

One entry in the `HARNESSES` table. Nothing else changes.

```js
myagent: {
  bin: 'myagent', label: 'My Agent', tier: 'experimental',
  readOnly: 'plan', resume: 'none', session_capture: 'terminal',
  reports: { cost: false, model: false },
  versionArgs: ['--version'],
  args: ({ task, model, perm, resume }) => [ /* build argv */ ],
  mode: (perm) => (perm === 'bypass' ? '--yolo' : '--plan'),
  session: (event) => event.sessionId ?? null,
  parse: (stdout, stderr, exitCode) => ({
    status: 'successful',        // successful | failed | abandoned
    reason: '', complete: true,  // complete:false => telemetry_incomplete
    text: '<final assistant message>',
    usage_raw: null,
    tokens: tokens({ /* normalised counts */ fidelity: 'exact' }),
  }),
}
```

Three rules learned the hard way:

- Set `fidelity: 'unavailable'` when you found no usage. Reporting `exact` zeroes claims a run was
  free when the truth is that nobody knows.
- Set `complete: false` when no terminal event arrived. A truncated stream is `abandoned`, not
  `successful`.
- Don't infer failure from error events. Codex emits `item.type: "error"` on runs that succeed.

## Files

```text
delegate-task/
  SKILL.md          agent-facing instructions, auto-loaded
  README.md         this file, humans only, never loaded into context
  README.ar.md      the Arabic edition
  delegate.mjs      the driver
  assets/           the diagrams in this README, and their HTML sources
  contracts/        normative behaviour specs
  references/       how to brief a delegate, and how to review what comes back
  test/run.mjs      169 cases; fixtures/ holds per-harness event streams

$DELEGATE_RUNS_DIR/<run_id>/
  prompt.txt · meta.json · journal.jsonl · stdout.log · stderr.log · result.json
```

Override the runs location with `DELEGATE_RUNS_DIR`, the per-stream log cap with
`DELEGATE_MAX_LOG_BYTES`, the post-cap retention window with `DELEGATE_LOG_TAIL_BYTES`, and where a
binary is found with `DELEGATE_BIN_<HARNESS>`.

## Verification

| Check | Result |
|---|---|
| `test/run.mjs` | **169 passed, 0 failed** |
| Suite has teeth | mutation-tested: deliberate defects injected, the suite required to catch each |
| Adversarial review | 9 rounds against an external agent, run through this skill, each round mutation-testing the suite independently |
| Live write run | measured `greeting.txt`; a file dirty *before* the run stayed out of the delta |
| Live resume | a delta saying only *"the file you just created"* edited the right file, session preserved |
| Live `--sandbox` | write blocked, file absent, exit **0**, caught by the self-report; no false positive over a pre-dirty tree |
| Live parallel | three runs dispatched within 1 s, 130 s wall clock, all successful |
| Recovery | a dead supervisor yields `abandoned` / `supervisor_lost`, session recovered from the journal |
| Isolation | the skill runs from a copy with no repository around it |

## Known limitations

- Copilot can't report tokens. Not fixable here; the numbers aren't in its output.
- Pi's success path and token shape are unverified — no provider configured on this machine.
- Copilot and Pi resume are wired but not exercised end to end.
- Linux and macOS shim resolution is implemented, untested.
- `prune` clears this driver's artifacts, not pi's own session store.
- **Process incarnation isn't persisted.** Runs are identified by pid, so pid reuse can leave one
  stuck as `stalled` or `adrift` rather than finishing. That is the cautious failure: it never
  publishes a competing result. Delete the run directory to clear it.
- **The relay-shutdown drain is only exercisable on POSIX.** Windows can't deliver a catchable
  signal to the supervisor, so that test skips there.
- **Two unborn repositories at one path are indistinguishable.** Identity uses the git directory
  plus the root commit, and an empty repo has neither, so a `.git` replaced before any commit
  reports `coverage_complete: false` rather than a false clean result.
- **Parallel runs sharing a directory cross-contaminate the measurement**, as shown above. Give
  each write-capable run its own tree.
