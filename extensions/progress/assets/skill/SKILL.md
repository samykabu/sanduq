---
name: progress-report
description: Keep a live, deterministic progress report for a Markdown plan checklist or a Spec Kit feature. Collects task state from the plan file, hook events from Claude Code or Codex, and lane, blocker and decision facts you record, then renders a browser view and a Markdown export with no agent spent on upkeep. Use when asked to "track progress on this plan", "show a progress dashboard", "report which agents work on which tasks", to install progress hooks, or to record a lane assignment, blocker, decision or note.
metadata:
  internal: true
---

# Progress report

Reporting is a deterministic projection. Never spawn, retain, message or poll an agent solely to maintain it.
Record only missing assignment, decision or blocker facts.

Run the CLI from the repository root: `progress` below stands for `python <skill dir>/scripts/progress.py`
(`.claude/skills/progress-report`, `.agents/skills/progress-report`, or `$CLAUDE_PLUGIN_ROOT/skills/progress-report`).
Type the full command each time. Verbs print one line (`refresh` prints nothing); relay it.

## When to use it

- A plan file (Markdown with `- [ ]` / `- [x]` items) drives the work: **plan mode**, no Spec Kit needed.
- A Spec Kit feature has `specs/<feature>/tasks.md`: **feature mode**; Workflow files are collected when present.

## Plan mode quick start

1. `progress hooks install --host claude` (or `codex`; add `--scope user` for a plugin install) once, for model, effort, context and child agents. Skip it and tasks are still tracked.
2. `progress init --plan docs/plan.md` creates `.progress/plan/` (see `--name`, `--dir`) and prints `bind=<nonce>`; the next hook binds (`hooks install` prints one if a report exists).
3. Check items off in the plan file; the report follows. Progress never writes the plan.
4. `progress status` gives the one-line state; the view is `.progress/plan/.view/index.html`.

Items keep a written id (`T001`); others get stable `P001`... ids. With one plan or feature active no target flag is needed; otherwise pass `--plan NAME` or `--feature DIR`.

## Verbs

| Need | Command |
| --- | --- |
| Create a report | `progress init --plan PATH [--name N] [--dir D]` or `progress init` (Spec Kit) |
| One-line state | `progress status` |
| Assign a lane | `progress lane L1 --tasks P001-P004 --owner ID --harness H --model M --effort E` |
| Close a lane | `progress lane L1 --close` |
| Blocker | `progress block P007 --by L2` (or `P003`, `ext:"text"`); `progress unblock B4` |
| Decision | `progress decide ask "question" --options a,b`; `progress decide made D2 b --by user` |
| Note | `progress note "text" --target P005` |
| Export | `progress export --format md` |
| Hooks | `progress hooks install\|uninstall\|status --host claude\|codex [--scope project\|user]` |

## Rules

1. Record a lane when you assign work (`L#`; host children `C#` appear on their own). Starts, completions and retries need no command.
2. Never put secrets, absolute paths or transcript text in a note (200 characters at most).
3. Unknown values stay unknown. Do not estimate model, effort, context or time.
4. Errors read `progress: error CODE`; fix the cause, do not retry in a loop.

Details: `references/verbs.md`; contract `docs/contracts.md`; flags `docs/commands.md`.
