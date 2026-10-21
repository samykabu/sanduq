# Project

**Purpose:** mirror each Spec Kit feature on a GitHub Project (v2). Project creates a parent issue,
moves its Status column through the lifecycle and, in standalone use, creates one sub-issue per task.

| | |
| --- | --- |
| Lifecycle phase | After `specify`, `plan`, `analyze` and `tasks`; before and after `implement` |
| Hooks | Six optional hooks; Project Init can make them mandatory ([hooks](../reference/hooks.md)) |
| Commands | `init`, `sync` ([reference](../reference/commands.md#project)) |
| Requires | Python 3; uses `gh` when available |
| Standalone | Yes |
| License | PolyForm Noncommercial 1.0.0 |

## Setup

```bash
specify extension add project
gh auth refresh -h github.com -s project,read:project
```

```text
$speckit-project-init Discover the booking application's Project, map lifecycle columns, and select required sync.
```

Init asks whether sync hooks are **required** (automatic) or **optional** (ask first). It maps each
phase to a real board column and writes `config.json`. Commit it with `.specify/extensions.yml`.

## Example

```text
$speckit-project-sync Synchronize the refund parent and completed task IDs without duplicate sub-issues.
```

For a dry run, call the sync script directly:
`python .specify/extensions/project/scripts/project_sync.py --phase auto --dry-run`. Add
`--summary` for one result line (`ok`, `skipped` or `error`).

## How it runs

![Project sequence: project.init discovers and approves the board mapping and sync policy (required, optional or manual); when a Spec Kit phase completes, project.sync reconciles the actual board columns and records the result, and a skipped sync does not count as complete.](../diagrams/extension-project.animated.svg)

Required sync runs automatically at each phase. Optional hooks ask first. In the managed Workflow,
Workflow requires automatic sync and its own adapter creates and closes task sub-issues. Each
Workflow claim names the phase and the exact sync command, so the dispatcher runs it without
opening the sync command file.
[Editable source](../diagrams/extension-project.html).

## Limits

- If `gh`, its scopes, a GitHub remote or `config.json` is missing, sync logs a skip and exits 0.
  A skip is not a completed sync.
- A malformed `.specify/project-sync-state.json` stops the sync with a message. Restore it from git
  or fix it, then rerun. Sync no longer resets it, which made the next run create duplicate issues.
- An interrupted run adopts the task sub-issues it already created, so a rerun does not duplicate them.
- `done` runs only when you pass it; Project does not move a feature to done by itself.
- An organization board needs `ownerType: org`. Init detects it; rerun Init if an older Init
  recorded `user`.
- Project only touches the configured board and issues in the `origin` repository.

Package details: [Project README](../../extensions/project/README.md).
