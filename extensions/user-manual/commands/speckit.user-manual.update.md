---
description: "Create or incrementally update the audience-aware User Manual for the active implemented feature."
---

# Update User Manual

Update only affected modules while keeping the complete manual coherent.

## User input

```text
$ARGUMENTS
```

Flags: `--feature <path>`, `--full`, `--module <id>`, `--skip-runtime`, `--no-build`.

## Instructions

1. Load `.specify/extensions/user-manual/skills/user-manual/SKILL.md`. If `User-Manual/manual.yml`
   is absent, follow the initialization workflow instead of producing disconnected pages.
2. Resolve the active feature and read its specifications, plan, tasks, contracts, data model,
   quickstart, implementation diff, tests, and existing manual state.
3. Verify new module candidates against source evidence. Add them with `status: proposed`; require
   user approval before making them part of the stable navigation.
4. Update affected content using the three audience contracts:
   - End User: goals, prerequisites, simple steps, outcomes, common problems, and no unnecessary
     implementation vocabulary.
   - Administrator/Operator: configuration, permissions, operations, monitoring, recovery, and
     consequences.
   - Technical Reference: exact interfaces, architecture, infrastructure, APIs, entities, every
     column and type, nullability, defaults, keys, indexes, constraints, relationships,
     enumerations and values, and sensitive-data classification.
5. Write plain English. When Arabic is enabled, write natural plain Arabic with RTL-safe structure;
   do not transliterate technical prose or leave machine-like literal translations.
6. Use the API, screenshot, release, and Illustrate skills only for applicable surfaces. Capture
   screenshots with deterministic synthetic fixtures; never use production data.
7. Update `User-Manual/.state/coverage.json`, including source evidence, affected modules, pages,
   audiences, languages, assets, and known gaps.
8. Unless `--no-build`, run the audit and build scripts for all configured editions. Always create a
   private preview archive. Deploy an ephemeral preview only when `manual.yml` names an approved
   provider; in that case load `skills/preview-publishing/SKILL.md`, validate its checked-in provider
   descriptor, and preserve the private artifact even when hosted deployment succeeds or is skipped.
9. Record freshness:

   ```text
   python .specify/extensions/user-manual/scripts/manual_state.py record --feature <feature-path>
   ```

10. Report pages/assets changed, English and Arabic coverage, preview paths, and unresolved gaps.
