# Progress command reference

Every Spec Kit command, CLI verb, flag, output line, exit code and schema of the Progress extension. For an overview,
read the [README](../README.md). The normative file formats are in [contracts](contracts.md).

Contents: [Spec Kit commands](#spec-kit-commands) · [The CLI](#the-cli) · [Verbs](#verbs) ·
[Hook entry](#hook-entry) · [Status line](#status-line-wrapper) · [Theme](#theme-verb-and-theme-file) ·
[Export](#export-formats) · [Schemas](#json-schemas) · [Benchmarks](#benchmarks)

## Spec Kit commands

Spec Kit registers these through your host's integration. Codex shows them as `$speckit-progress-init`; Claude Code as
`/speckit-progress-init`. Each command loads the skill, then runs one CLI verb and relays its single line. Text after the
command name is appended to the verb as arguments.

| Command | Runs | Use | Example |
| --- | --- | --- | --- |
| `speckit.progress.init` | `progress.py init $ARGUMENTS` | Once per feature, after the task list exists. Also an optional `after_tasks` hook | `$speckit-progress-init Create the progress report for specs/001-demo.` |
| `speckit.progress.refresh` | `progress.py refresh --verbose $ARGUMENTS` | A forced snapshot. Also an optional `after_implement` hook. It does not mean the feature is complete | `$speckit-progress-refresh Write a final progress snapshot.` |
| `speckit.progress.status` | `progress.py status $ARGUMENTS` | The one-line summary; add `--json` for the projection | `$speckit-progress-status Show the one-line progress status.` |
| `speckit.progress.theme` | `progress.py theme $ARGUMENTS` | Choose a preset, import the Illustrate theme, load a file or show the theme | `$speckit-progress-theme Use the cobalt theme for the progress report.` |
| `speckit.progress.export` | `progress.py export $ARGUMENTS` | Write the projection as Markdown or JSON | `$speckit-progress-export Export the progress report as Markdown.` |
| `speckit.progress.hook-session-start` | `scripts/hook.py session_start` | Internal. Never invoked by an agent | |
| `speckit.progress.hook-pre-tool-use` | `scripts/hook.py pre_tool_use` | Internal | |
| `speckit.progress.hook-post-tool-use` | `scripts/hook.py post_tool_use` | Internal | |
| `speckit.progress.hook-stop` | `scripts/hook.py stop` | Internal | |
| `speckit.progress.hook-session-end` | `scripts/hook.py session_end` | Internal | |

Agents record lanes, blockers, decisions and notes with the other verbs below. There is no Spec Kit command for them, so
the skill ([`skills/progress/SKILL.ext.md`](../skills/progress/SKILL.ext.md)) lists the command lines.

## The CLI

```text
python .specify/extensions/progress/scripts/progress.py <verb> [options]
```

Run it from the repository root. This page writes `progress` for that command. Fifteen verbs exist:
`init`, `bind`, `refresh`, `status`, `lane`, `block`, `unblock`, `decide`, `note`, `attempt`, `runs`, `theme`,
`export`, `hook` and `statusline`.

**Options every verb takes.** They go after the verb name, for example `progress lane --feature specs/001-demo L1`.

| Option | Default | Meaning |
| --- | --- | --- |
| `--feature DIR` | resolved, see below | The feature directory, `specs/<dir>` or the bare `<dir>`. A path with `.` or `..`, a nested path and a symlinked directory that leaves `specs/` are refused |
| `--actor ACTOR` | `agent:coordinator`, or `$SANDUQ_PROGRESS_ACTOR` | Who is recording. `user`, `hook`, `legacy` or `agent:<id>` (1 to 64 characters of `A-Za-z0-9._-`). Anything else is `PROGRESS_FORBIDDEN_CONTENT` |

`--root DIR` is accepted before the verb, hidden from `--help`, and used by Workflow to run Progress from another
directory.

**Which feature.** In order: `--feature`, the `SPECIFY_FEATURE` environment variable, the `feature` of the Workflow
checkpoint whose branch is the current branch, then the current git branch when it names a `specs/<branch>` directory.
If none matches, the verb exits 2 with `PROGRESS_NO_FEATURE`. If `--feature` is given and wrong, the other sources
are not tried.

**Which repository.** `$SANDUQ_PROGRESS_ROOT`, else the nearest parent holding `.specify`, else the nearest holding `.git`.

**Output.** Each verb prints one line that starts `progress:`, and nothing else, with these exceptions: `refresh` prints
nothing unless `--verbose`; `status --json`, `runs --json`, `theme --show` and `export` without `--out` print a
document; `init --theme X` prints a second line (the theme line); `hook` and `statusline run` never print errors. Relay
the line and do not elaborate.

**Exit codes.**

| Code | Meaning |
| ---: | --- |
| 0 | Done |
| 2 | Usage error, no feature, not initialised, not found, invalid theme |
| 3 | Refused: Workflow owns decisions, forbidden content, unsafe link |
| 4 | Another Progress process holds the feature lock. A verb retries 3 times, 200 ms apart, first |

**Error lines** read `progress: error CODE message`. The codes are `PROGRESS_USAGE`, `PROGRESS_NO_FEATURE`,
`PROGRESS_NOT_INITIALIZED`, `PROGRESS_NOT_FOUND`, `PROGRESS_THEME_INVALID`, `PROGRESS_THEME_UNAVAILABLE`,
`PROGRESS_DECISION_AUTHORITY`, `PROGRESS_FORBIDDEN_CONTENT`, `PROGRESS_UNSAFE_TARGET` and `PROGRESS_LOCK_BUSY`. The
[README table](../README.md#error-codes) gives the cause and fix of each.

**Environment.**

| Variable | Effect |
| --- | --- |
| `SANDUQ_PROGRESS_ROOT` | Repository root, instead of searching upward from the working directory |
| `SANDUQ_PROGRESS_ACTOR` | Default for `--actor` |
| `SANDUQ_PROGRESS_NOW` | A fixed ISO-8601 clock, for tests |

**Text rules for every fact.** Free text is stripped of control characters and capped (200 characters unless a verb
says otherwise). The whole record is checked before it is written. A string that looks like a secret, or an absolute
path outside the repository (drive, UNC or POSIX form, on any platform), is refused with `PROGRESS_FORBIDDEN_CONTENT`
and exit 3. Never put secrets, absolute paths or transcript text in a note.

Ids are assigned by the CLI: lanes `L1`, `L2`, ...; blockers `B1`; decisions `D1`; notes `N1`; attempts `A1`. Workflow
delegation lanes are `W1`... and host child agents `C1`... They appear on their own.

## Verbs

### init

```text
progress init [--feature DIR] [--statusline yes|no] [--theme PRESET]
```

Creates the report for a feature and prepares to bind this session. Safe to run again: facts, config and theme are kept,
and the report files are copied afresh (run it again after an upgrade).

| Flag | Default | Meaning |
| --- | --- | --- |
| `--statusline` | `no` | `yes` also installs the [status line wrapper](#status-line-wrapper) |
| `--theme` | none | A preset name, applied like [`theme --preset`](#theme-verb-and-theme-file) |

It creates `specs/<feature>/progress/` with `facts.jsonl` and `.view/`, `.specify/progress/config.json`, adds the
git-ignored paths to `.git/info/exclude`, writes the first projection, and starts the bind handshake.

```text
$ progress init
progress: ready specs/001-demo/progress/.view/index.html bind=0b04e35005e9
```

The `bind=` nonce is valid for 120 seconds. The host's `post_tool_use` hook for that same shell call carries the
session id and completes the bind, so run `init` through the shell tool and do not edit the line.

With `--theme cobalt` the output is two lines: `progress: theme cobalt`, then the `ready` line. An unknown preset
prints `progress: error PROGRESS_THEME_INVALID unknown preset nope` first and still creates the report and exits 0.

Errors: `PROGRESS_NO_FEATURE` (2), `PROGRESS_UNSAFE_TARGET` (3), `PROGRESS_LOCK_BUSY` (4).

### bind

```text
progress bind [--session ID] [--host claude|codex]
```

Binds a session to the feature. A session must be bound before hooks attach anything to the report. `init` already
starts a handshake, so `bind` is needed only when `init` was run in another session, or the 120 seconds passed.

| Form | Output |
| --- | --- |
| `progress bind` | `progress: pending bind=765046966098` (the next hook for that shell call completes it) |
| `progress bind --session abc123` | `progress: bound abc123` (binds directly; `--host` defaults to `claude`) |

Direct binding is for hosts without hooks and for tests. Error: `PROGRESS_NOT_INITIALIZED` (2).

### refresh

```text
progress refresh [--final] [--verbose]
```

Rebuilds the projection now. Automatic collection already does this after each hook event (at most once per 5 seconds),
so use it for a forced snapshot, or when no host collects.

| Flag | Meaning |
| --- | --- |
| `--final` | Accepted for compatibility. Every refresh is a full one |
| `--verbose` | Prints `progress: refreshed rev 4`. Without it the verb prints nothing |

Errors: `PROGRESS_NOT_INITIALIZED` (2), `PROGRESS_LOCK_BUSY` (4).

### status

```text
progress status [--json]
```

Reads the current state and prints it. It rebuilds the projection in memory and writes no file. Without a flag:

```text
$ progress status
progress: 0/6 tasks, 1 lanes active, 0 blocked, 0 decisions pending (rev 15)
```

`--json` prints the whole projection, schema `sanduq.progress.v2` ([fields](#status---json-sanduqprogressv2)). Error:
`PROGRESS_NOT_INITIALIZED` (2).

### lane

```text
progress lane ID [--tasks RANGE] [--owner ID] [--label TEXT] [--harness H] [--model M] [--effort E] [--close]
```

Assigns tasks to a lane, or closes it. Record a lane when you hand work to a worker.

| Argument | Meaning |
| --- | --- |
| `ID` | `L1`, `L2`, ... or `new` for the next free number |
| `--tasks` | A list such as `T001-T004,T009`. A range ascends. Omit it to keep the lane's tasks. Giving it reopens a closed lane |
| `--owner` | The worker's stable id (up to 80 characters). Host child agents and delegation identities that equal it merge into the lane |
| `--label` | A short name (up to 60 characters). Defaults to the lane id |
| `--harness`, `--model`, `--effort` | What you asked for (up to 60 characters each). They are the requested values and never shown as observed |
| `--close` | Marks the lane closed |

```text
$ progress lane L1 --tasks T001-T003 --owner worker-a --label Core --harness codex --model gpt-6.1-sol --effort high
progress: L1 open 3 tasks
$ progress lane new --tasks T004,T005
progress: L2 open 2 tasks
$ progress lane L2 --close
progress: L2 closed 2 tasks
```

Errors: `PROGRESS_USAGE` for `lane id must look like L1 (or "new")` and `bad task range T9-T1`.

### block

```text
progress block TARGET --by BLOCKER
```

Opens a blocker on a task or lane.

| Argument | Meaning |
| --- | --- |
| `TARGET` | A task (`T004`) or lane (`L1`, `W1`, `C1`) id |
| `--by` | What blocks it: a lane (`L2`), a task (`T003`), a decision (`SD2` or `D2`) or free text as `ext:"waiting for the API key"` (up to 120 characters) |

```text
$ progress block T004 --by L1
progress: B1 open T004 by L1
$ progress block T005 --by 'ext:waiting for API key'
progress: B2 open T005 by waiting for API key
```

A second call with the same target and blocker prints the existing id and adds nothing. Error: `PROGRESS_USAGE` when
`--by` or the target is not one of the forms above.

### unblock

```text
progress unblock ID
progress unblock --all-for TARGET
```

Resolves one open blocker, or every open blocker on a target.

```text
$ progress unblock B1
progress: B1 resolved
$ progress unblock --all-for T005
progress: B2 resolved
```

When several are resolved, the line reads `progress: 3 resolved`. Errors: `PROGRESS_NOT_FOUND` (`no matching open blocker`),
and `PROGRESS_USAGE` when you give both or neither of the id and `--all-for`.

### decide

```text
progress decide ask QUESTION --options a,b[,c...]
progress decide made ID SELECTED --by user|agent-recommendation|assumption [--evidence TEXT]
```

Records a decision in plain Spec Kit. Put `--feature` and `--actor` before `ask` or `made`. When Workflow is installed and
`specs/<feature>/workflow/decisions.json` exists, Workflow owns decisions and both forms exit 3 with
`PROGRESS_DECISION_AUTHORITY`. Do not work around it.

| Form | Meaning |
| --- | --- |
| `ask` | `QUESTION` up to 200 characters. `--options` is comma separated, needs two or more values (80 characters each) |
| `made` | `SELECTED` must match one of the options, ignoring case, and is stored as the option's own spelling. `--by` says who decided. `--evidence` is up to 200 characters, for example a URL or "chat" |

```text
$ progress decide ask "Which parser library?" --options "lark,hand-written"
progress: D1 pending
$ progress decide made D1 lark --by user --evidence chat
progress: D1 made lark
```

Errors: `PROGRESS_NOT_FOUND` (`no decision D9`), `PROGRESS_USAGE` (`--options needs at least two comma separated values`,
`selected must be one of: lark, hand-written`).

### note

```text
progress note TEXT [--target ID]
```

Records a short note, up to 200 characters, optionally attached to a task or lane. Use it for a retry, a failure or a
budget overrun that a person should see. Notes appear in Events.

```text
$ progress note "Retried T003 after a lint failure" --target T003
progress: N1 noted
```

Error: `PROGRESS_USAGE` (`note target is a task or lane id`).

### attempt

```text
progress attempt record (--lane L1 | --overhead LABEL) --run ID --status STATUS
                        [--started TIME] [--ended TIME] [--usage-json PATH]
```

An integration verb for [Workflow's legacy `progress.py`](https://github.com/samykabu/sanduq/blob/main/extensions/workflow/README.md#progress-reporting). Agents do not call it. It
writes one attempt fact with origin `legacy`, actor `legacy` and source `workflow-shim`. A legacy attempt never changes
a lane's status and never overrides an attempt a producer reports.

| Flag | Meaning |
| --- | --- |
| `--lane` | The lane, such as `L1`. Required unless `--overhead` is given |
| `--overhead` | A label for work that belongs to no lane, such as `review` |
| `--run` | The run id (up to 80 characters). One fact exists per lane or label and run id; a later record replaces it |
| `--status` | `pending`, `running`, `done`, `blocked`, `failed` or `successful` |
| `--started`, `--ended` | ISO-8601 times. A re-record keeps a time it does not restate; an empty string clears it |
| `--usage-json` | A JSON file with a measurement (below) |

The usage file holds an object with `fidelity` (`exact`, `reported` or `unavailable`, required) and optional `agent`,
`harness`, `model`, `reason`, the counters `fresh_input`, `cache_read`, `cache_write`, `output` and `reasoning`
(non-negative integers, else null), `since` and `until` (ISO-8601) and `log`. A `log` inside the repository is stored
relative; any other absolute path is stored as `external:<name>`. Nothing else is kept.

```text
$ progress attempt record --lane L1 --run r1 --status running --started 2026-10-15T10:00:00Z
progress: A1 running L1 run r1
$ progress attempt record --overhead review --run rv1 --status done
progress: A2 done review run rv1
```

Attempts without a lane appear under a top-level `overhead` list of the projection.

### runs

```text
progress runs [--json] [--runs-dir DIR]... [--now TIME] [--stall-seconds N]
```

Summarises delegate runs. It needs no initialised feature and writes nothing. It is the only supported way for another
tool to read run history; callers must not import Progress code.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--json` | off | Print the `progress.runs.v1` document |
| `--runs-dir` | `.delegate/runs` | A folder of run directories (relative to the repository root). Repeat it to merge several |
| `--now` | the clock | An ISO-8601 time to measure elapsed time against |
| `--stall-seconds` | 300 | Quiet time after which a live run is called `stalled` |

```text
$ progress runs
progress: 1 runs, 1 live, 0 malformed
```

Each run directory holds `meta.json`, `journal.jsonl` and optionally `result.json`. The schema is
[below](#runs---json-progressrunsv1). Error: `PROGRESS_USAGE` when `--now` is not a time.

### theme

See [Theme](#theme-verb-and-theme-file).

### export

See [Export](#export-formats).

### hook

```text
progress hook EVENT [--host claude|codex]
```

Handles one host event with the hook JSON on stdin. It is the same code `scripts/hook.py` runs. It never prints, never
fails and always exits 0. See [Hook entry](#hook-entry).

### statusline

```text
progress statusline [run|install|uninstall]
```

`install` and `uninstall` print one line. `run` is the default and is what Claude Code calls. See
[Status line wrapper](#status-line-wrapper).

## Hook entry

The host calls `python .specify/extensions/progress/scripts/hook.py <event>` with the event's JSON on stdin. Spec Kit
builds this call from each `speckit.progress.hook-*` command, so there is one command per event.

| Event | Command | Matcher | Timeout |
| --- | --- | --- | ---: |
| `session_start` | `speckit.progress.hook-session-start` | | 10 s |
| `pre_tool_use` | `speckit.progress.hook-pre-tool-use` | `Task\|Agent\|spawn_agent` | 10 s |
| `post_tool_use` | `speckit.progress.hook-post-tool-use` | | 10 s |
| `stop` | `speckit.progress.hook-stop` | | 10 s |
| `session_end` | `speckit.progress.hook-session-end` | | 10 s |

`user_prompt_submit` is understood by the handler but no command is registered for it. The handler accepts the event
name as `post_tool_use`, `PostToolUse` or `post-tool-use`, and falls back to the payload's `hook_event_name`.

**What it does.** Reads the payload, finds the repository and the bound feature for that session, merges the model,
effort, context, elapsed time and child agents it carries into the host snapshot in `.host/`, then refreshes the report
if the last refresh is older than `debounce_seconds` (5). Inside the window it marks the report dirty instead, and
publishes that once, so the page shows its pending banner. `stop` and `session_end` always refresh. On Codex,
`session_start`, `user_prompt_submit`, `stop` and `session_end` also read effort and context from the rollout file.

**Which sessions count.** Only a bound session, or a child whose parent session is bound, is recorded. A fresh
handshake on a `post_tool_use` payload (its tool input or response holds the `bind=` nonce, within 120 seconds, with a
`cwd` inside the worktree) binds the session first. Everything else is dropped.

**Silence rule.** A hook prints nothing to stdout or stderr and exits 0 in every case: bad JSON, an empty payload, an
unbound session, a busy lock, an exception. The host forwards a hook's stdout to the model, so a hook that printed
would cost tokens and a non-zero exit would be shown as a failure. The reason for a dropped event goes to a
[diagnostics log](../README.md#diagnostics-logs). A project where Progress was never initialised gets nothing
written. `hook.py` uses only the standard library and returns before importing Progress for a session it can already
tell is unbound (about 30 ms).

## Status line wrapper

Claude Code only. It gives the report the exact model, context use and session duration that the hook payloads lack.

```text
$ progress statusline install
progress: statusline installed
$ progress statusline uninstall
progress: statusline removed
```

- **install** sets `statusLine` in `.claude/settings.json` to `python3 ".specify/extensions/progress/scripts/progress.py" statusline`
  (`python` on Windows), keeps an existing `padding`, and saves the previous status line object in
  `.specify/progress/config.json` under `statusline.previous`. When the previous one was a command, it is also saved as
  `statusline.chained`. Installing twice changes nothing. `init --statusline yes` does the same.
- **run** reads the status line JSON from stdin. For a bound session it merges the snapshot into the report. Then it runs
  the chained command with the same stdin and passes its output through byte for byte. With no chained command it prints
  one line, for example `Opus | ctx 41%`. It never prints an error.
- **uninstall** restores the saved status line exactly, or removes `statusLine` if there was none. If you changed
  `statusLine` yourself since, it leaves your setting alone and only clears the saved state.

## Theme verb and theme file

```text
progress theme --preset NAME
progress theme --from-illustrate
progress theme --file PATH
progress theme --show
```

The verb needs an initialised feature (`PROGRESS_NOT_INITIALIZED` otherwise) and takes no other option, so
`theme --help` is not available. Any other form prints
`progress: error PROGRESS_USAGE theme --preset X | --from-illustrate | --file PATH | --show`.

| Form | Effect | Output |
| --- | --- | --- |
| `--preset NAME` | Replaces `.specify/progress/theme.json` with `{"v":1,"preset":"NAME"}` | `progress: theme cobalt` |
| `--from-illustrate` | Reads `active.theme` from `.github/illustration-theme.yml` and writes the matching colours as tokens | `progress: theme emerald` |
| `--file PATH` | Validates your file and stores it as `theme.json` | `progress: theme classic` (the file's preset) |
| `--show` | Prints the resolved theme, with every default filled in, as JSON | the JSON document |

A successful change rewrites `theme.css` and `layout.js` in the `.view/` of every feature. Open pages pick it up on the next
poll. Failures print `progress: error PROGRESS_THEME_INVALID reason` and exit 2, for example `unknown preset nope`,
`unknown key bogus`, `no .github/illustration-theme.yml` and `unsupported illustrate theme X`. Only the `cobalt`,
`emerald` and `classic` Illustrate themes are mapped.

**Presets.** Each has a light and a dark set of the twelve tokens.

| Preset | Look | Light `bg` / `brand` / `accent` | Dark `bg` |
| --- | --- | --- | --- |
| `sanduq` (default) | Warm grey with a dark green brand and an orange accent | `#f6f7f4` / `#233c32` / `#c65b36` | `#121916` |
| `cobalt` | Blue | `#f6f8fc` / `#1d4ed8` / `#2563eb` | `#101827` |
| `emerald` | Green | `#f4f8f5` / `#0877a8` / `#0f8a64` | `#10231e` |
| `classic` | Grey with an orange accent | `#f5f5f5` / `#2e5aa8` / `#eb6c36` | `#2d3142` |

**The file, `progress.theme.v1`.** Every key is optional. An unknown key is an error.

| Key | Type and default | Meaning |
| --- | --- | --- |
| `v` | `1` | The version. Only 1 is accepted |
| `preset` | a preset name, default `sanduq` | The base for every token you do not set |
| `title` | string up to 200 characters, or null | Replaces the feature title in the header and the browser tab |
| `logo` | string, or null | An image path or URL shown beside the title. `javascript:` and `vbscript:` values are ignored |
| `density` | `comfortable` (default) or `compact` | Spacing |
| `blocks` | list of block names | Display order. Blocks you leave out follow in the default order |
| `hidden` | list of block names | Blocks not drawn |
| `tokens` | `{"light": {...}, "dark": {...}}` | Colour overrides, below |
| `font` | `{"sans": "...", "mono": "..."}` | A font stack, up to 200 characters, none of `; { } < > \` or a newline |

Block names are `header`, `orchestrator`, `lanes`, `boards`, `decisions`, `blockers` and `events`. Lists hold unique known names.

Tokens are `#rgb` or `#rrggbb` colours:

| Token | Used for |
| --- | --- |
| `bg`, `surface` | Page background; card and table background |
| `text`, `muted` | Primary and secondary text |
| `line` | Borders and rules |
| `brand` | Headings, links and the selected filter |
| `accent` | The keyboard focus outline |
| `active`, `waiting`, `blocked`, `done`, `failed` | Status colours |

Example, `.specify/progress/theme.json`:

```json
{
  "v": 1,
  "preset": "classic",
  "title": "Demo report",
  "density": "compact",
  "blocks": ["header", "lanes", "boards"],
  "hidden": ["events"],
  "tokens": {"light": {"accent": "#00aa77"}},
  "font": {"sans": "Inter, sans-serif"}
}
```

This draws the header, lanes and boards first, then the blocks not listed (orchestrator, decisions, blockers) in their
default order, and hides events.

## Export formats

```text
progress export [--format md|json] [--out PATH]
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--format` | `md` | `md` for a Markdown document, `json` for the projection |
| `--out` | stdout | A file to write. Prints `progress: exported PATH` |

Export reads the last written projection (`report.json`). It builds one only when none exists, so run `progress refresh`
first if you need the very latest. The output is deterministic: the same projection gives the same bytes, with no clock
and no revision number. Exporting costs no model tokens.

The Markdown export has these sections, in order: the title; a one-line feature and task summary; **Orchestrator** (host,
model, effort, context, elapsed, each marked `(partial)` or `(estimated)` when not exact, and `unknown` when missing);
**Lanes** (a table of lane, label, status, requested and observed model, and task ids by state, plus any unassigned
tasks); **Tasks** (a checklist grouped by phase, with dependencies and lanes); **Decisions**; **Blockers**; and **Recent
events**.

```text
$ progress export
# Tasks: Demo feature

Feature `001-demo`, branch `001-demo`.

Tasks 0/6 done, 1 active lanes, 0 open blockers, 0 pending decisions.

## Orchestrator

- Host: unknown
- Model: unknown
- Effort: unknown
- Context: unknown
- Elapsed: 3 (estimated)

## Lanes

| Lane | Label | Status | Requested | Observed model | Done | Active | Waiting | Blocked |
|---|---|---|---|---|---|---|---|---|
| L1 | Core | active | codex/gpt-6.1-sol/high | unknown |  | T001 | T002 T003 |  |
```

The JSON export is the full projection, indented, followed by a newline.

## JSON schemas

### status --json: `sanduq.progress.v2`

`progress status --json`, the exported JSON and `.view/report.json` are the same document.

| Field | Content |
| --- | --- |
| `schema`, `rev`, `generated_at`, `stale_after_seconds` | `sanduq.progress.v2`; the refresh counter; the UTC time; 600 by default |
| `collection` | `automatic` (a host has reported), `hosts`, `dirty`, `last_event_at`, `diagnostics` (lines in the feature's log) |
| `feature` | `id`, `title`, `dir`, `branch`, `issue` (`number`, `url`, or null), `stage` (`value`, `source`, or null), `started_at`, `workflow` |
| `orchestrator` | `host`, `session_id`, `since`, and the measurements `model`, `effort`, `context`, `elapsed`, `active` |
| `lanes[]` | `id`, `label`, `owner`, `origin` (`facts`, `workflow-delegation`, `host-child`, `coordinator`), `requested` (`harness`, `model`, `effort`), `observed` (`model`, `effort`), `status`, `elapsed`, `active`, `last_observed_at`, `attempts[]`, `tasks` (`active`, `waiting`, `blocked[]`, `done`) |
| `unassigned_tasks` | The same four task lists, for tasks no lane owns |
| `tasks` | By id: `title`, `phase`, `done`, `parallel`, `depends_on`, `lane` |
| `decisions` | `pending[]` and `made[]`: `id`, `question`, `options`, `selected`, `decided_by`, `at`, `url`, `source` |
| `blockers[]` | `id`, `target`, `by` (`type`, `ref`), `since`, `source` (`facts`, `workflow-pause`, `delegation`) |
| `events[]` | The last 30, oldest first: `at`, `kind`, `text` |
| `summary` | `tasks_total`, `tasks_done`, `lanes_active`, `blocked`, `decisions_pending` |
| `overhead[]` | Only when present: attempts that belong to no lane |

A **measurement** is `{"value", "source", "observed_at", "fidelity"}` with `fidelity` one of `exact`, `partial`,
`estimated` or `unknown`. An unknown value is `null`, with source `none`. Every duration in the projection is a whole
number of seconds. An **attempt** in `lanes[].attempts` has `run_id`, `status`, `started_at`, `ended_at`, `tokens`,
`fidelity` and, for legacy records, `origin: "legacy"`.

### runs --json: `progress.runs.v1`

```json
{"schema": "progress.runs.v1", "generated_at": "2026-10-15T10:02:00Z", "stall_seconds": 300,
 "runs": [{"run_id": "claude-1", "harness": "claude", "source": "claude-1", "started_at": "2026-10-15T10:00:00Z",
           "model": "claude-sonnet-5-5", "model_reported": null, "task_verdict": "unknown", "review_verdict": "unknown",
           "next_action": null, "harness_status": "running", "phase": "active", "usage": null, "elapsed_seconds": 120,
           "journal_events": 1, "latest_event": "running", "latest_event_at": "2026-10-15T10:01:00Z", "ended_at": null}],
 "duplicates": [], "malformed": [], "caveats": ["...", "...", "..."]}
```

| Field | Meaning |
| --- | --- |
| `runs[]` | Sorted by start time, then id. `phase` is `active`, `finishing`, `stalled` or `done` |
| `model` and `model_reported` | The model asked for at launch, and the model the harness says it ran (null if it did not say). Only the second is evidence of the model that ran |
| `usage` | Null unless the harness reported exact counters (`input_total`, `input_fresh`, `cache_read`, `cache_write`, `output_total`, `reasoning`, `total`) |
| `task_verdict`, `review_verdict`, `next_action` | Copied from a final `result.json`; `unknown` or null when absent |
| `conflict` | Present only when two records of one run id disagree; lists the fields |
| `duplicates`, `malformed` | Run ids seen twice; directories skipped, each with `source` and `error` |
| `caveats` | Three fixed statements: elapsed is wall time, not active work time; `stalled` is a heuristic; `harness_status` is the harness's verdict, not acceptance |

### Attempt record

The fact `progress attempt record` appends to `facts.jsonl`:

```json
{"v":1,"ts":"2026-10-15T18:39:41Z","kind":"attempt","id":"A1","actor":"legacy","source":"workflow-shim","lane":"L1","label":null,"run":"r1","status":"done","usage":null,"origin":"legacy","started_at":"2026-10-15T10:00:00Z","ended_at":"2026-10-15T10:20:00Z"}
```

`usage` holds the file's whitelisted fields, or null. The other fact kinds (`lane`, `block`, `decision`, `note`) and
the host snapshot are specified in [contracts](contracts.md).

## Benchmarks

The token benchmark compares Progress with a hand-edited report and Workflow's legacy protocol. It counts tokens and
spends none of your budget. Run it from `extensions/progress` in a source checkout, with `pip install -r test-requirements.txt`:

```bash
python -m tests.bench.report            # rewrites docs/token-benchmark.md
python -m tests.bench.report --check    # exit 1 if the committed file differs from a fresh run
```

The unit test `tests/test_token_budget.py` fails when the committed benchmark is out of date, when a Progress verb costs
more than the hand-edited approach, when a verb prints more than one line, or when the skill passes 60 lines. Regenerate the
file after you change the skill.

`scripts/live_ab.py` is a manual tool that measures real harness token usage. It spends tokens, so no test runs it. It
needs the `tests/bench` trace, which exists only in a source checkout. Each pair runs the same scripted update trace twice
through the `delegate-task` driver: arm `new` records the updates with the Progress CLI, arm `md` edits a Markdown report
by hand.

```text
python extensions/progress/scripts/live_ab.py [--delegate PATH] [--node NODE] [--targets LIST] [--pairs N]
                                              [--updates N] [--timeout SECONDS] [--runs-dir DIR] [--out DIR] [--dry-run]
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--delegate` | `$DELEGATE`, else a path on the author's machine | Path to `delegate.mjs` |
| `--node` | `node` | The Node.js executable |
| `--targets` | `claude:claude-haiku-5-5,codex:gpt-6-luna` | Comma list of `harness:model`. Each needs an explicit model |
| `--pairs` | 3 | Pairs per target. Pairs alternate arm order |
| `--updates` | 20 | Trace events per run |
| `--timeout` | 900 | Seconds per run |
| `--runs-dir` | `.delegate/runs` | Where the driver writes its runs |
| `--out` | `live-ab-report` | Folder for `live-ab.json` and `live-ab.md` |
| `--dry-run` | off | Print the planned runs and exit without a sandbox or a harness |

```text
$ python extensions/progress/scripts/live_ab.py --dry-run --pairs 1 --updates 5
Planned 4 runs (1 pairs x 2 targets x 2 arms), 5 trace events each.
 1. harness=claude model=claude-haiku-5-5 pair=1 arm=new task=861 chars
 2. harness=claude model=claude-haiku-5-5 pair=1 arm=md task=868 chars
 ...
Dry run: no sandbox created, no harness started. driver: ... (found)
```

The report counts a run's cost only when the driver measured it. A failed or invalid run is counted apart and never
summed as zero. `unknown` means no run was measured. The report claims no Claude tokenizer count.
