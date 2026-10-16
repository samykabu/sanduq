# Sanduq Progress Report

**Purpose:** a live report for one Spec Kit feature: which lanes run which tasks, what is blocked, which decisions
are open, and what the orchestrating agent is using. The report is a deterministic projection. It is rebuilt from the
feature files and the host's native hook payloads, so no agent is spent keeping it up to date.

![Progress report, light theme](docs/assets/progress-light.png)

Contents: [Install](#install) · [Quick start](#quick-start) · [How it plugs in](#how-it-plugs-in) ·
[What the report shows](#what-the-report-shows) · [What is measured](#what-is-measured-and-how-well) ·
[Files](#files) · [Theming](#theming) · [Token cost](#token-cost) · [Workflow](#using-with-sanduq-workflow) · [Plans outside Spec Kit](#plans-outside-spec-kit) ·
[Upgrading](#upgrading-from-100) · [Troubleshooting](#troubleshooting) · [Limits](#limits)

A **lane** is one unit of assignment: a worker, a delegated run or a host subagent that owns a list of tasks. A
**projection** is a report rebuilt from its sources on every refresh, so deleting it loses nothing.

## Install

Requires Spec Kit 1.1.1 or later and Python 3.11 or later. Workflow and Illustrate are optional
([dependencies](dependencies.yml)).

Plain Spec Kit, from the Sanduq catalog:

```bash
specify extension catalog add --name sanduq --priority 10 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
specify extension add progress
```

With Sanduq Workflow, let its installer add and keep Progress in step:

```bash
python .specify/extensions/workflow/scripts/install.py --with progress          # preview
python .specify/extensions/workflow/scripts/install.py --with progress --apply
```

The install registers five native hooks (see [How it plugs in](#how-it-plugs-in)) and the commands listed in
[the command reference](docs/commands.md). Progress writes nothing to a feature until you run `init`.

## Quick start

1. Install the extension (above) and create the task list with Spec Kit's `tasks` step. Progress reads
   `specs/<feature>/tasks.md`.
2. Create the report. Codex syntax is shown. Claude Code uses `/speckit-progress-init`.

   ```text
   $speckit-progress-init Create the progress report for specs/001-demo.
   ```

   The agent runs `progress init` and relays its one line:

   ```text
   progress: ready specs/001-demo/progress/.view/index.html bind=0b04e35005e9
   ```

   The `bind=` value binds the current session to the feature: the host's next hook for that shell call completes it.
3. Open `specs/001-demo/progress/.view/index.html` in a browser. It works from `file://`, needs no server and polls
   for new data every 3 seconds.
4. Assign work. Record a lane when you hand tasks to a worker:

   ```bash
   python .specify/extensions/progress/scripts/progress.py lane L1 --tasks T001-T003 --owner worker-a --label Core --harness codex --model gpt-6.1-sol --effort high
   ```

   ```text
   progress: L1 open 3 tasks
   ```

5. Work as usual. Check tasks off in `tasks.md`. Hooks add model, effort, context and child agents. Read the state
   from the page, or ask for the one-line summary:

   ```text
   progress: 0/6 tasks, 1 lanes active, 0 blocked, 0 decisions pending (rev 15)
   ```

In the rest of this page `progress` stands for `python .specify/extensions/progress/scripts/progress.py`, run from the
repository root.

## How it plugs in

| Setup | What feeds the report |
| --- | --- |
| Plain Spec Kit | `tasks.md` (task state, dependencies), native host hooks (model, effort, context, child agents), and a small tracked fact file for what nothing else records: lane assignments, blockers, decisions, notes |
| With Sanduq Workflow | The same, plus Workflow's checkpoint, delegation ledger and decisions. Retries and attempts become attempts of one lane. Decisions come from Workflow, so `progress decide` is refused |

Spec Kit calls two lifecycle hooks, both optional and both offered as a prompt:

- `after_tasks` offers to run `speckit.progress.init`, so the report exists as soon as the task list does.
- `after_implement` offers one forced snapshot with `speckit.progress.refresh`. It does not mean the feature is
  complete.

Five native host events keep the report fresh: `session_start`, `pre_tool_use` (matcher `Task|Agent|spawn_agent`, the
subagent launches), `post_tool_use`, `stop` and `session_end`. Each runs a script-only command, `scripts/hook.py <event>`,
that prints nothing and always exits 0. `hook.py` uses only the standard library and returns before importing Progress
when Progress was never initialised in the project, or the session is not bound.

Under Workflow, `speckit.workflow.reconcile` leaves these hooks and events enabled. The agent's part is small. Read
[the skill](skills/progress/SKILL.ext.md): record a lane when you assign work, and a blocker, decision or note when one
appears. Everything else is collected. Reporting is a deterministic projection, and no agent is spawned, kept,
messaged or polled to maintain it.

## What the report shows

Each block can be hidden or reordered in [the theme file](#theming).

| Block | Shows | Comes from |
| --- | --- | --- |
| Header | Feature title, id, issue link, branch, Workflow stage, a progress bar, and counts of tasks done, lanes active, blocked and decisions pending | `tasks.md` heading and checkboxes; git branch; the Workflow checkpoint (stage, issue) |
| Orchestrator | Host, model, effort, context used (gauge), elapsed time, session id | Host hooks and, on Claude Code, the status line. Each value shows its fidelity |
| Lanes | One row per lane: owner, requested and observed model and effort, status, elapsed, active time, last observed, attempts. A filter narrows the boards to one lane | `lane` facts; Workflow delegation attempts; host child agents (`C1`, `C2`, ...) |
| Boards | Tasks grouped as Active, Waiting, Blocked and Done, per lane, plus an Unassigned board | `tasks.md` checkboxes; open blockers; the lane that owns each task |
| Decisions | Pending questions with their options, and made decisions with who decided and an evidence link | `decide` facts, or the Workflow ledger when Workflow is installed |
| Blockers | Id, blocked task or lane, what blocks it, since when, source | `block` facts; Workflow pauses; delegation state |
| Events | The last 30 derived events: lane changes, attempts, notes, subagent starts | The other sources, in time order |

Lane status is one of `pending`, `active`, `waiting`, `blocked`, `done` or `failed`. A task is Active when it is the
first unchecked, unblocked task of an active lane. Checking the box in `tasks.md` is the only thing that completes
a task.

Two banners sit above the report:

- **Stale.** Shown when the last refresh is older than `stale_after_seconds` (600 by default), or when updates are
  pending inside the 5-second debounce window. It means the page is behind the project, not that anything failed. See
  [Troubleshooting](#report-is-not-updating).
- **Automatic collection unavailable.** Shown when no host has reported yet. Values come from files only. Run
  `progress refresh` to update them.

A failed load shows **Update failed** and keeps the last good view.

## What is measured, and how well

Every measured value carries its source and fidelity. Unknown is shown as unknown and is never filled with a guess.

| Fact | Claude Code | Codex |
| --- | --- | --- |
| Task state, dependencies | Exact, from `tasks.md` | Exact, from `tasks.md` |
| Lane, blocker, decision, note | Exact, recorded by verb | Exact, recorded by verb |
| Model | Exact from the status line when installed; partial from hooks | Partial, from the rollout file |
| Effort | Exact from hook and status line payloads where the host sends it | Partial, from the rollout file |
| Context use | Exact from the status line | Partial, from the rollout file |
| Elapsed | Session duration from the status line; otherwise estimated from the feature start | Estimated |
| Active work time | Unknown. Hosts give no interval evidence, so it is never inferred | Unknown |
| Child agents | Started on launch, ended on a terminal tool result; a background child stays running until a stop payload names it | Parent links when the payload has them; otherwise dropped and counted |
| Observed child model | Only when the payload carries it | Only when the payload carries it |

Codex field names are partly unverified against a running host; see [hosts](docs/hosts.md) for what was checked and
what was not. A session is bound to a feature by an explicit handshake, so hooks never attach an observation to a
guessed feature.

## Files

```text
specs/<feature>/progress/
  facts.jsonl      tracked in git: lanes, blockers, decisions, notes, legacy attempts
  .host/           git-ignored, durable: host snapshots, the home of child agent identity
  .view/           git-ignored, disposable: the report (index.html, data.js, report.json, theme.css, state.json, lock)
.specify/progress/
  config.json      debounce_seconds (5), stale_after_seconds (600), status line state
  theme.json       optional theme
  bindings.json    session bindings (local, git-ignored)
  diagnostics.log  hook problems (local, git-ignored)
```

`facts.jsonl` is the only file you commit. Lines are appended and never rewritten. Delete `.view/` at any time:
`progress refresh` rebuilds it, and child agent ids survive because they live in `.host/`. `init` adds the
git-ignored paths to `.git/info/exclude`, never to a tracked `.gitignore`. A write never goes through a symbolic
link or junction (`PROGRESS_UNSAFE_TARGET`). The layout and every schema are in [contracts](docs/contracts.md).

## Commands

| Command | Use |
| --- | --- |
| `$speckit-progress-init` | Create the report, bind this session, optionally install the status line |
| `$speckit-progress-refresh` | Force a snapshot |
| `$speckit-progress-status` | One-line summary, or `--json` for the projection |
| `$speckit-progress-theme` | Choose a preset, import the Illustrate theme or load a file |
| `$speckit-progress-export` | Write the projection as Markdown or JSON |

The `lane`, `block`, `unblock`, `decide`, `note`, `attempt` and `runs` verbs run through the CLI. Every verb, flag,
output line, exit code, schema and example is in [the command reference](docs/commands.md). The internal
`speckit.progress.hook` command (one script for all five hook events) is not registered as a skill.

## Theming

Four presets (`sanduq`, `cobalt`, `emerald`, `classic`) in light and dark, tokens only. `--from-illustrate` maps the
project's Illustrate theme. Block order, hidden blocks, density, title, logo and fonts are set in
`.specify/progress/theme.json`.

![Progress report, dark theme](docs/assets/progress-dark.png)

![Progress report at narrow width](docs/assets/progress-narrow.png)

```text
$speckit-progress-theme Use the cobalt preset.
```

The schema and a full example are in [the command reference](docs/commands.md#theme-verb-and-theme-file).

## Token cost

The benchmark replays a 55-update, 24-task, four-lane trace and counts the model-visible content each approach needs.
Counts use `o200k_base`, which is exact for that encoding; Claude figures are unverified because no exact local Claude
tokenizer exists.

| Approach | Updates | Setup |
| --- | ---: | ---: |
| Progress verbs | 1,857 | 636 |
| Hand-edited Markdown report | 59,967 | 581 |
| Legacy Workflow report protocol | 12,030 | 3,926 |

Task start, completion and reopening cost nothing because they are read from `tasks.md`. The skill is the setup cost
you pay on each load, so it stays short. The full table by update class, the assumptions and the cl100k_base counts
are in [the token benchmark](docs/token-benchmark.md). Measured usage from real harness runs comes from
`scripts/live_ab.py`, a manual tool that spends tokens ([details](docs/commands.md#benchmarks)).

## Using with Sanduq Workflow

Progress is optional for Workflow, and Workflow never imports Progress code. It uses only the CLI and versioned JSON.

- **Install.** `install.py --with progress --apply` (above). An installed Progress is kept in step on later installs
  and upgrades.
- **Mode.** Workflow's `scripts/progress_bridge.py mode [--host claude|codex]` prints `reporting: projection`,
  `reporting: refresh` or `reporting: legacy`. In every mode no agent is spawned, kept, messaged or polled only to
  maintain the report. The three modes and the old-call mapping are in the
  [Workflow README](https://github.com/samykabu/sanduq/blob/main/extensions/workflow/README.md#progress-reporting).
- **Old calls.** Workflow's `scripts/progress.py` forwards `init`, `task`, `event`, `phase`, `usage`, `sync` and `pr`
  here. Usage keeps its explicit log path, time window and reported counters as a fact with origin `legacy`; legacy
  facts never override the ledger. `--json` and `init --title` are refused with a compatibility error.
- **Runs.** `progress runs --json` returns schema `progress.runs.v1`, built from `.delegate/runs`. Workflow's lean
  status renders from it. Elapsed time is wall time, `stalled` is a heuristic, and a harness's terminal status is not
  acceptance.

## Upgrading from 1.0.0

Update the extension with `specify extension update progress`, or run Workflow's
[upgrade](https://github.com/samykabu/sanduq/blob/main/docs/start/upgrades.md#workflow-and-its-dependencies) if
Workflow manages it. Then, once per feature, run `progress init` to copy the newer report files into `.view/`. It keeps your facts,
config and theme.

- **Host snapshots move.** 1.0.0 kept them in `.view/host`. 1.0.1 keeps them in `.host/`, because deleting the
  disposable `.view/` must not renumber child agents. The first hook after the upgrade moves them in one rename.
  A file that would collide is kept as `.host/legacy-<name>`. A `.view/host` that is a link or points outside the
  feature is left alone, and a failed move is retried on the next event.
- **Git exclude is updated for you.** The same hook, and `init`, add `specs/*/progress/.host/` to
  `.git/info/exclude`, together with `.specify/progress/*.lock` and `diagnostics.log*`. Do not add them by hand.
- **Hooks run `scripts/hook.py`.** A project where Progress was never initialised gets nothing written, and an
  unbound session is logged once per session id.

The full list of changes is in [the changelog](CHANGELOG.md).

## Plans outside Spec Kit

Progress also reports on any Markdown plan with `- [ ]` / `- [x]` items; no Spec Kit feature is needed. The code is the
portable `progress-report` skill, vendored from [sanduq-skills](https://github.com/samykabu/sanduq-skills) at
`agent-tools-v1.2.0` (see `vendor.lock.json`; edit it there, not here).

```bash
progress hooks install --host claude        # once: model, effort, context and child agents (or --host codex)
progress init --plan docs/plan.md           # creates .progress/plan/ and prints bind=<nonce>
progress status                             # one-line state
```

Open `.progress/plan/.view/index.html`. Check items off in the plan file; Progress never writes it. Items without an id get
stable `P001`... ids. With several reports, target one with `--plan NAME` or `--feature DIR`. `progress hooks
install|uninstall|status` edits only its own tagged entries in `.claude/settings.json` or `.codex/hooks.json` (`--scope user`
for a user-wide install). Plan-mode flags, ids and the `.progress/` layout are in
[the command reference](docs/commands.md) and [contracts](docs/contracts.md).

## Troubleshooting

### Report is not updating

Work through these in order.

1. **Read the banner.** `Stale` with pending updates means events arrived inside the 5-second debounce window and the
   next event, `stop` or `progress refresh` publishes them. `Stale` with a time means nothing has refreshed for
   `stale_after_seconds` (600): the session ended, or the hooks are not reaching Progress. `Automatic collection
   unavailable` means no host has reported for this feature.
2. **Force a refresh.** `progress refresh --verbose` prints `progress: refreshed rev N`. If the page changes, files
   and facts are fine and the problem is collection.
3. **Check the binding.** Hooks only attach to a bound session. Look in `.specify/progress/diagnostics.log` for a line
   such as `unbound claude session s1 dropped`. Fix it by running `progress init` or `progress bind` through the
   shell tool in that session; the next tool call completes the bind within 120 seconds. `progress bind --session ID`
   binds directly when you know the id.
4. **Check the hooks are installed.** The host's config must hold the Progress hooks: `.claude/settings.json` (or
   `settings.local.json`) for Claude Code, `.codex/hooks.json` or `.codex/config.toml` for Codex, each with commands
   that contain `speckit.progress.hook`. If they are missing, reinstall with `specify extension add progress`.
   Confirm what Workflow sees with
   `python .specify/extensions/workflow/scripts/progress_bridge.py mode --host claude`: `projection` means the hooks are
   registered and enabled.
5. **Check the host trusts them.** Hosts ask you to review project hooks before running them. If you declined, or the
   prompt never showed, they do not run. Claude Code's `disableAllHooks: true` (project, local or user settings)
   switches them all off.
6. **Codex hooks feature flag.** Codex hooks sit behind a feature flag. A `[features]` entry set to `false` (`hooks`,
   or its older name `codex_hooks`) in the project or user `config.toml` turns every hook off, and Workflow reports
   `refresh` instead of `projection`. Set it to `true` (check your Codex version's hook documentation for the
   current name) and start a new session. Pass `--host codex` to `progress_bridge.py mode`, because Codex is not
   always detectable from the environment.
7. **Check `tasks.md`.** Tasks are lines such as `- [ ] T001 Title`. A task id inside a code span or code block is
   ignored, and dependencies come only from `(depends on T001)` or `(after T001)`.

### What the stale banner means

It never means a task failed. It means the page was generated a while ago or updates are queued. Opening the page
later than `stale_after_seconds` after the last event always shows it.

### Diagnostics logs

Hooks and verbs never print errors to the host. They write them to bounded logs (256 KB, one rotated copy
`diagnostics.log.1`):

| File | Holds |
| --- | --- |
| `.specify/progress/diagnostics.log` | Dropped hook events: unbound session (logged once per id), empty or invalid payload, payload without a session id, `cwd` outside the bound worktree, handler errors, status line errors |
| `specs/<feature>/progress/.view/diagnostics.log` | Per-feature problems: lock busy (observation dropped), theme unavailable (fallback CSS written), report files not found, host snapshot migration skipped |

The projection counts the lines in the second file as `collection.diagnostics`.

### Error codes

Every verb error is one line, `progress: error CODE message`, and the exit code below.

| Code | Exit | Meaning and fix |
| --- | ---: | --- |
| `PROGRESS_USAGE` | 2 | Bad arguments or values. The message names the problem |
| `PROGRESS_NO_FEATURE` | 2 | No feature found, or the path leaves `specs/<dir>`. Pass `--feature specs/<dir>` |
| `PROGRESS_NOT_INITIALIZED` | 2 | The feature has no `progress/` folder. Run `progress init` |
| `PROGRESS_NOT_FOUND` | 2 | The blocker or decision id does not exist or is not open |
| `PROGRESS_THEME_INVALID` | 2 | Unknown preset, bad theme file, missing Illustrate theme. The message says which |
| `PROGRESS_THEME_UNAVAILABLE` | 2 | The theme module failed to load; a fallback `theme.css` was written. Reinstall |
| `PROGRESS_DECISION_AUTHORITY` | 3 | Workflow owns decisions for this feature. Answer in Workflow |
| `PROGRESS_FORBIDDEN_CONTENT` | 3 | The text looks like a secret, holds an absolute path outside the repository, or the `--actor` is not `user`, `hook`, `legacy` or `agent:<id>` |
| `PROGRESS_UNSAFE_TARGET` | 3 | A symbolic link or junction sits where Progress would write. Remove it |
| `PROGRESS_LOCK_BUSY` | 4 | Another Progress process holds the feature lock after 3 tries 200 ms apart. Retry once |

Hooks and the status line never fail: they drop the event, log it and exit 0.

## Limits

- Active work time is always unknown. Hosts give no interval evidence, and Progress does not infer it.
- Codex payload fields and the delivery of a background child's `stop` event are unverified against a running
  host ([hosts](docs/hosts.md)). A child with no terminal evidence ages into `waiting`; it is never marked done.
- Token counts for Claude models are unverified. The benchmark counts a different encoding.
- Task text and state are owned by `tasks.md`. Progress never writes to it, so a task is done only when its box is
  checked.
- The page reads local files. It makes no network request and needs a browser with JavaScript.

## Contract and hosts

[Commands](docs/commands.md) is the user reference. [Contracts](docs/contracts.md) are normative.
[Hosts](docs/hosts.md) records how Spec Kit dispatches events and what each host sends.
[Extension page](https://github.com/samykabu/sanduq/blob/main/docs/extensions/progress.md).

## License

The extension is PolyForm Noncommercial 1.0.0. The vendored `progress-report` code (`scripts/`, `assets/ui/`, `docs/`,
`skills/progress/references/`) is MIT in sanduq-skills; the notice is in `THIRD_PARTY_NOTICES.md`. See [licenses](https://github.com/samykabu/sanduq/blob/main/docs/reference/licenses.md).
