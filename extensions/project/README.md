# `project` — GitHub Project lifecycle sync (Spec Kit extension)

For setup and a worked example, see [Install by host](https://github.com/samykabu/sanduq/blob/main/docs/start/install-by-host.md)
and the [project page](https://github.com/samykabu/sanduq/blob/main/docs/extensions/project.md).
Every command and its example is in the [command reference](https://github.com/samykabu/sanduq/blob/main/docs/reference/commands.md#project).


Mirrors every Spec Kit feature onto a **GitHub Project (v2)**:

- one **parent feature issue** per feature, whose **Status** column advances through the
  Spec Kit lifecycle;
- in standalone use, one native **sub-issue per task** (fills the board's *Sub-issues progress*
  bar), closed as its task is checked off in `tasks.md`. Under Sanduq Workflow, Workflow owns
  task issues and Project creates none.

Idempotent and **no-regress** — re-running a step, or running `auto`, only moves the board
forward or reconciles it. **Board-agnostic**: run `project init` once per repo to map the
lifecycle onto whatever Status columns your board has.

## Lifecycle

| Spec Kit step                | phase             |
| ---------------------------- | ----------------- |
| `/speckit.specify` (after)   | `open`            |
| `/speckit.plan` (after)      | `analysis`        |
| `/speckit.analyze` (after)   | `engineer-review` |
| `/speckit.tasks` (first run) | `ready` (+ sub-issues, standalone) |
| `/speckit.implement` (start) | `in-progress`     |
| open PR on the branch        | `in-review` (auto) |
| `done`, passed explicitly    | `done` (closes checked tasks' sub-issues); never automatic |

## Install & setup

```bash
# via Spec Kit catalog (the installer wires hooks + renders the commands):
specify extension add project
# local or offline test: build the package, extract it, then `specify extension add --dev <extracted>`

gh auth refresh -h github.com -s project,read:project   # one-time scope
/speckit-project-init                                   # discover board + map columns -> config.json
```

`project init` asks whether lifecycle sync hooks are **required** (automatic) or **optional**
(manual/user-approved), discovers the project id, Status field, and columns, then maps each phase
to a column (**exact → fuzzy → optional auto-create**). It writes `config.json` and updates
the `project` hooks in `.specify/extensions.yml`; commit both files. The script never prompts: a
choice it cannot make (several projects, an unreadable owner type) exits 4 with JSON `needs`.

Creating or renaming a column replaces every Status option on GitHub, which clears every item's Status. Init
therefore reads each item's Status first, archived items included, and sets it again by name afterwards. GitHub
refuses to edit an archived item, so init unarchives it, sets the Status and archives it again. Each item it
could not set is named, and init exits 1. If the items cannot be read, init changes nothing unless you pass
`--allow-status-reset` (`-AllowStatusReset`), which accepts that every item loses its Status.

For unattended initialization, select the policy explicitly:

```bash
python scripts/project_init.py --hooks-mode required
```

`scripts/bash/project-init.sh` and `scripts/powershell/project-init.ps1` still work for one release: they
print the `project_init.py` line and pass every flag through, in either spelling.

## Usage

```bash
python scripts/project_sync.py --phase <phase> [--dry-run] [--no-sub-issues] [--force] [--json] [--summary]
```

One stdlib Python script on every host and OS (installed at
`.specify/extensions/project/scripts/project_sync.py`); it needs `python` and `gh`, not `jq`.
`<phase>` ∈ `open | analysis | engineer-review | ready | in-progress | in-review | done | auto`.

`--summary` prints exactly one line to stdout instead of the `--json` summary:
`ok issue=<n> status=<status> created=<n> closed=<n>` on success, `skipped reason=<reason>` on a
graceful degradation (never `ok`: a skip is not success), or `error exit=<rc> reason=<message>` on a
usage error (`--summary` with `--json`, exit 2) or a mid-run failure (exit 1). Under `--summary` the
run log goes to stderr; an unrecognised argument is always a stderr warning. GraphQL (`gh project`,
`gh issue`, `gh pr`) is preferred; once its budget is exhausted the same operations use the REST
API, and `--json` reports the `transport`.

## Files

- `config.default.json` — DEFAULT phase→column names + sub-issue policy (no ids).
- `config.json` — written by `project init` (board ids + mapping); **committed per repo**.
- `scripts/project_init.py` — one-time board discovery + mapping (stdlib; `jq` is no longer needed).
- `scripts/{powershell,bash}/project-init.*` — deprecated stubs that run `project_init.py`.
- `scripts/project_sync.py` — the lifecycle engine.
- `commands/*.md` — command sources (rendered into each assistant target on install).
- State (runtime, committed): `.specify/project-sync-state.json`.

## Graceful degradation

If `gh` is missing/unauthenticated/lacks `project` scope, `origin` isn't GitHub, or
`config.json` is absent, the engine logs the reason and exits 0 — it never blocks a hook.
Re-run `--phase auto` after fixing the precondition to reconcile.

## Safety

Operates only on the Project you configured and issues in the repo matching `origin`. Never
creates issues elsewhere. Sub-issue volume is guarded by `subIssues.warnAboveCount` (warn)
and `subIssues.maxCount` (hard cap, 0 = unlimited); it logs anything skipped rather than
truncating silently.
