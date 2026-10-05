---
description: Process pending merged archives in the next local agent session
---

# Pending archive session

Run `python .specify/extensions/memory/scripts/archive.py pending` from the root.
Do not load project memory (`specs/memory/`) for this check. Disabled mode stops cleanly.
This instruction runs at the start of a local agent session and before specifying.
It is not a background service or a remote merge hook.

Read `active_run`, `active_phase`, `writer` and `guard_blockers` even when automatic
mode is disabled. Read-only state checks work while a writer is busy. If a stale
lock is reported, confirm the recorded process has exited before removing that
single lock. Never remove a busy or unknown lock automatically.

If an active run exists, inspect `status` and complete/resume it before another
archive. For a permanently failing published run, explicit `rollback --run <id>`
restores its original recorded bytes and scoped index, preserves its checkpoint,
and removes its automatic queue entry. Never discard an active transaction.

Before starting a new specification, branch, broad staging or commit workflow,
run `... archive.py pending --gate`. A nonzero exit is a hard stop for that workflow.
Do not continue to `git.feature` or auto-commit hooks while recovery, a writer or
missing number guards are reported. Read-only work can continue. Repair overwritten
number guards after Spec Kit/git-extension updates before creating a new feature.

On locally merged target branch, process `needs_verification` entries: inspect that
implementation and all required downstream work are actually complete, then execute
the listed approved checks using `verify --spec <path> --complete --check <name>`.
Refresh `pending`. Do not interpret missing evidence as permission to skip checks.
Process each ready entry with the registered archive `run` workflow in automatic
mode. Re-read the result between features because each successful archive updates
memory. Unmerged or unfinished entries remain queued. Never automatically retire
features, archive unrelated legacy folders, change the policy, or prompt to approve
each operation after automatic mode has been enabled.
