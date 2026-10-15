---
name: progress
description: Operate the Sanduq Progress report for a Spec Kit feature. Use for progress init, refresh, status, theme, export, or when you must record a lane assignment, blocker, decision or note.
---

# Progress

Reporting is a deterministic projection. Never spawn, retain, message or poll an agent solely to maintain it.
Record only missing assignment, decision or blocker facts.

Host hooks, `tasks.md` and the Workflow ledger are collected automatically. A refresh prints nothing.
Run the CLI from the repository root. In this skill `progress` stands for
`python .specify/extensions/progress/scripts/progress.py`; type the full command each time, since shell state may not persist.
Verbs print one line (`refresh` prints nothing); relay it, do not elaborate.

## Verbs

| Need | Command |
| --- | --- |
| Create the report | `progress init [--theme PRESET]` |
| Bind this session | `progress bind` (prints `bind=<nonce>`; the next hook completes it) |
| One-line state | `progress status` |
| Assign a lane | `progress lane L1 --tasks T001-T004 --owner ID --harness H --model M --effort E` |
| Close a lane | `progress lane L1 --close` |
| Blocker | `progress block T007 --by L2` (or `T003`, `ext:"text"`) |
| Resolve blocker | `progress unblock B4` |
| Ask a decision | `progress decide ask "question" --options a,b` |
| Record a decision | `progress decide made D2 b --by user` |
| Note | `progress note "text" --target T005` |
| Forced snapshot | `progress refresh --final` |
| Status line | `progress statusline install` |
| Theme | `progress theme --preset cobalt` |
| Markdown export | `progress export --format md` |

## Rules

1. Record a lane when you assign work (lane ids are `L#`; Workflow `W#` and host-child `C#` lanes appear on their own). Task start, completion, retries and reopening need no command.
2. Check a task off in `tasks.md` as usual; the report follows.
3. When Workflow is installed, decisions come from its ledger and `decide` is refused. Do not work around it.
4. Never put secrets, absolute paths or transcript text in a note. Text is capped at 200 characters.
5. Unknown values stay unknown. Do not estimate model, effort, context or time.
6. Errors read `progress: error CODE`. Fix the cause named; do not retry in a loop.

Details: `references/verbs.md`.
