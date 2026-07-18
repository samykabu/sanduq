# `project` — GitHub Project lifecycle sync (Spec Kit extension)

Mirrors every Spec Kit feature onto a **GitHub Project (v2)**:

- one **parent feature issue** per feature, whose **Status** column advances through the
  Spec Kit lifecycle;
- one native **sub-issue per task** (fills the board's *Sub-issues progress* bar), closed as
  its task is checked off in `tasks.md`.

Idempotent and **no-regress** — re-running a step, or running `auto`, only moves the board
forward or reconciles it. **Board-agnostic**: run `project init` once per repo to map the
lifecycle onto whatever Status columns your board has.

## Lifecycle

| Spec Kit step                | phase             |
| ---------------------------- | ----------------- |
| `/speckit.specify` (after)   | `open`            |
| `/speckit.plan` (after)      | `analysis`        |
| `/speckit.analyze` (after)   | `engineer-review` |
| `/speckit.tasks` (first run) | `ready` (+ sub-issues) |
| `/speckit.implement` (start) | `in-progress`     |
| open PR on the branch        | `in-review` (auto) |
| all sub-issues closed        | `done`            |

## Install & setup

```bash
# via Spec Kit catalog (the installer wires hooks + renders the commands):
specify extension add project
# or copy this folder to .specify/extensions/project and run install.sh from the repo root

gh auth refresh -h github.com -s project,read:project   # one-time scope
/speckit-project-init                                   # discover board + map columns -> config.json
```

`project init` asks whether lifecycle sync hooks are **required** (automatic) or **optional**
(manual/user-approved), discovers the project id, Status field, and columns, then maps each phase
to a column (**exact → fuzzy → prompt → optional auto-create**). It writes `config.json` and updates
the `project` hooks in `.specify/extensions.yml`; commit both files.

For unattended initialization, select the policy explicitly:

```powershell
pwsh scripts/powershell/project-init.ps1 -HooksMode required -NonInteractive
```

```bash
scripts/bash/project-init.sh --hooks-mode required --non-interactive
```

## Usage

```bash
pwsh scripts/powershell/project-sync.ps1 -Phase <phase> [-DryRun] [-NoSubIssues] [-Force] [-Json]
scripts/bash/project-sync.sh --phase <phase> [--dry-run] [--no-sub-issues] [--force] [--json]
```

`<phase>` ∈ `open | analysis | engineer-review | ready | in-progress | in-review | done | auto`.

## Files

- `config.default.json` — DEFAULT phase→column names + sub-issue policy (no ids).
- `config.json` — written by `project init` (board ids + mapping); **committed per repo**.
- `scripts/{powershell,bash}/project-init.*` — one-time board discovery + mapping.
- `scripts/{powershell,bash}/project-sync.*` — the lifecycle engine.
- `commands/*.md` — command sources (rendered into each assistant target on install).
- State (runtime, committed): `.specify/project-sync-state.json`.

## Graceful degradation

If `gh` is missing/unauthenticated/lacks `project` scope, `origin` isn't GitHub, or
`config.json` is absent, the engine logs the reason and exits 0 — it never blocks a hook.
Re-run `-Phase auto` after fixing the precondition to reconcile.

## Safety

Operates only on the Project you configured and issues in the repo matching `origin`. Never
creates issues elsewhere. Sub-issue volume is guarded by `subIssues.warnAboveCount` (warn)
and `subIssues.maxCount` (hard cap, 0 = unlimited); it logs anything skipped rather than
truncating silently.
