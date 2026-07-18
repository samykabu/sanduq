---
description: "Analyze the active Spec Kit feature for required User Manual content and asset tasks before implementation."
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
   `UserManual.Init`; do not invent an approved module map.
4. Map every user story, interface, route, endpoint, entity, enumeration, deployment change, and
   breaking behavior to existing or proposed modules.
5. Load specialist skills only when applicable:
   - API surface: `skills/api-docs/SKILL.md`.
   - UI or mobile screens: `skills/ui-screenshots/SKILL.md`.
   - Compatibility, upgrade, or release behavior: `skills/release-docs/SKILL.md`.
   - Diagrams: installed Illustrate skill and the matching type reference.
6. Add concrete tasks for affected audience pages, English content, optional Arabic updates,
   tutorials/how-to/reference/explanation, deterministic screenshots, API bundles/examples,
   architecture/infrastructure/ER diagrams, data dictionary changes, release notes, migration
   guides, navigation, preview build, and validation. Use marker-delimited blocks and do not
   duplicate tasks on rerun.
7. In all writing tasks, explicitly require plain English or plain Arabic appropriate to the target
   audience. Do not reuse technical prose on end-user pages.
8. In `--report-only` mode, report tasks without changing `tasks.md`; otherwise patch and validate it.
