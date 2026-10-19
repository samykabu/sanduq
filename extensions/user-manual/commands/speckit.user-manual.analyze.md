---
description: "Adds the feature's User Manual content and asset tasks to tasks.md. Use before implementation or when asked to 'add manual tasks'."
---

# Analyze User Manual Impact

Run after `tasks.md` exists and before implementation begins.

## User input

```text
$ARGUMENTS
```

Flags: `--feature <path>`, `--report-only`.

## Instructions

1. Load `.specify/extensions/user-manual/skills/user-manual/SKILL.md` and
   `references/incremental-update.md`.
2. Resolve the feature from `--feature`, then `.specify/feature.json`.
3. Read `User-Manual/manual.yml`. If it does not exist, add a task to run
   `speckit.user-manual.init`; do not invent an approved module map.
4. Map every user story, interface, route, endpoint, entity, enumeration, deployment change, and
   breaking behavior to existing or proposed modules. When `lifecycle.impact_scope` is `evidence`,
   run `python .specify/extensions/user-manual/scripts/manual_impact.py --feature <feature-path>`
   and start from its `modules`, `pages` and `audiences`; propose modules for its `unmatched` paths.
5. Load specialist skills only when applicable:
   - API surface: `skills/api-docs/SKILL.md`.
   - UI or mobile screens: `skills/ui-screenshots/SKILL.md`.
   - Compatibility, upgrade, or release behavior: `skills/release-docs/SKILL.md`.
   - Diagrams: run `python .specify/extensions/user-manual/scripts/deps.py ensure illustrate`
     first; on a non-zero exit report its line and add no diagram task (when it prints a
     `specify extension` recipe and the user approves, re-run with `--approve`; under a `manual`
     policy the user runs the printed command, then re-runs this command). On a zero exit, pass on
     any "newer compatible release available" note, read
     `.specify/extensions/illustrate/skill/references/type-index.md`, choose the type, and name it
     in the task; the stage that draws follows Illustrate's full procedure.
6. Add concrete tasks for affected audience pages, English content, optional Arabic updates,
   tutorials/how-to/reference/explanation, deterministic screenshots, API bundles/examples,
   architecture/infrastructure/ER diagrams, data dictionary changes, release notes, migration
   guides, navigation, preview build, and validation. Use marker-delimited blocks and do not
   duplicate tasks on rerun.
7. In all writing tasks, explicitly require plain English or plain Arabic appropriate to the target
   audience. Do not reuse technical prose on end-user pages.
8. In `--report-only` mode, report tasks without changing `tasks.md`; otherwise patch and validate it.
