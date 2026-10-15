# Progress

**Purpose:** show a live report for one Spec Kit feature: lanes, tasks, blockers, decisions and what the orchestrating
agent is using. The report is a deterministic projection of `tasks.md`, the optional Workflow ledger and the host's
native hook payloads. No agent is spent keeping it current.

| | |
| --- | --- |
| Lifecycle phase | After `tasks` through `implement`; native hooks keep it fresh |
| Hooks | Two optional lifecycle hooks and five native host events ([hooks](../reference/hooks.md)) |
| Commands | `init`, `refresh`, `status`, `theme`, `export` ([reference](../reference/commands.md#progress)) and a CLI with 16 verbs ([full reference](../../extensions/progress/docs/commands.md)) |
| Requires | Nothing; Python 3.11 or later. Workflow and Illustrate are optional |
| Standalone | Yes |
| License | PolyForm Noncommercial 1.0.0 (vendored skill code is MIT) |

## Setup

```bash
specify extension add progress
```

Add the Sanduq catalog first if you have not ([install by host](../start/install-by-host.md)). With Workflow, use
`install.py --with progress --apply` instead.

```text
$speckit-progress-init Create the progress report for specs/412-refund-approval.
```

Open `specs/412-refund-approval/progress/.view/index.html` in a browser. It polls every 3 seconds and needs no server.

## Example

```text
$speckit-progress-status Show the one-line progress status.
$speckit-progress-theme Use the cobalt theme for the progress report.
$speckit-progress-export Export the progress report as Markdown.
```

Record a lane when you assign work:

```bash
python .specify/extensions/progress/scripts/progress.py lane L1 --tasks T001-T003 --owner worker-a
```

```text
progress: L1 open 3 tasks
```

The agent records only what no other source holds: a lane assignment, a blocker, a plain Spec Kit decision or a note.
The skill at `extensions/progress/skills/progress/SKILL.ext.md` lists the verbs. Task state comes from `tasks.md`;
model, effort and context come from host hooks and are shown as unknown when a host does not send them.

## With Workflow

Progress is optional for [Workflow](workflow.md). Install it with `install.py --with progress`. Workflow then reports
through Progress and no longer asks an agent to keep a report current. If you leave Progress out, Workflow's own
report runs as before. `progress_bridge.py mode` prints the mode in use (`projection`, `refresh` or `legacy`); the
[modes and the old-call mapping](../workflow/operations.md#reporting-modes-and-the-legacy-call-mapping) are in the
operations guide. Details:

- Workflow's `progress.py` forwards its old subcommands to the Progress CLI, so existing prompts keep working.
  `--json` and `init --title` have no faithful mapping and fail with a compatibility error.
- Legacy usage is stored as an attempt labelled `legacy`. It never overrides the delegation ledger.
- Workflow's lean run status reads `progress runs --json` (schema `progress.runs.v1`).

## Plans outside Spec Kit

Progress also tracks a plain Markdown plan: `progress init --plan docs/plan.md` creates `.progress/plan/`, and
`progress hooks install --host claude|codex` adds the native hooks without editing other settings. Target a report with
`--plan NAME` or `--feature DIR`. The steps are in the
[package README](../../extensions/progress/README.md#plans-outside-spec-kit).

## Vendored code

The scripts, report page and reference docs come from the MIT `progress-report` skill in
[sanduq-skills](https://github.com/samykabu/sanduq-skills), pinned at `agent-tools-v1.2.0` in `vendor.lock.json`.
`extensions/progress/assets/skill/SKILL.md` is a reference copy of that skill's entry point; this extension's own entry
point stays `extensions/progress/skills/progress/SKILL.ext.md`.

## Limits

- Active work time is always shown as unknown. Hosts do not report it.
- Codex fields and the stop event of a background child are unverified against a running host.
- A session must be bound to a feature before its hooks are recorded. If the report does not update, start with
  [troubleshooting](../../extensions/progress/README.md#report-is-not-updating).

## More

The [package README](../../extensions/progress/README.md) has the install steps, what each report block shows,
file layout, theming, token results, upgrading and troubleshooting. The
[command reference](../../extensions/progress/docs/commands.md) lists every verb, flag, output line, exit code,
schema and the benchmark tools.
