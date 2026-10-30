---
description: "Updates the User Manual modules a feature affects, audits them and builds a private preview. Use when asked to 'update the manual'."
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
2. Resolve the active feature and run, once,
   `python .specify/extensions/user-manual/scripts/manual_impact.py --feature <feature-path>`. It
   computes the freshness status and joins its changes with the manual's evidence as
   `lifecycle.impact_scope` says, printing `current`, `reason`, `changed_inputs`, `changed_outputs`,
   `modules`, `pages`, `audiences` and `unmatched`. By `reason`:
   - `--full` given, `missing`, or legacy state: read the full set: specifications, plan, tasks,
     contracts, data model, quickstart, implementation diff, tests, and existing manual state.
   - `stale-input-or-output`: read its `changed_inputs`, `changed_outputs` and `pages`, and work
     from its `modules`, `pages` and `audiences`.
   - `current`: nothing changed since the last record. Unless `--module` or the user asked for a
     specific refresh, report the manual current with that line and stop; otherwise refresh only that.
3. Treat `unmatched` paths as module candidates. Verify them against source evidence and add them
   with `status: proposed`; require user approval before making them part of the stable navigation.
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
6. Use the API, screenshot, release, and Illustrate skills only for applicable surfaces. For a
   diagram, run `python .specify/extensions/user-manual/scripts/deps.py ensure illustrate` first; on
   a non-zero exit report its line, follow it and generate no diagram. When it exits zero, pass on
   any "newer compatible release available" note and draw with the procedure in
   `.specify/extensions/illustrate/skill/SKILL.md`: the §0 theme gate first, then §10 (choose the
   type from `references/type-index.md`, read its `type-*.md`, apply and validate the theme, and run
   the step 7 checks). Run Illustrate's scripts from the repository root as
   `python .specify/extensions/illustrate/skill/scripts/<script>`. Capture screenshots with
   deterministic synthetic fixtures; never use production data.
7. Update `User-Manual/.state/coverage.json`, including source evidence, affected modules, pages,
   audiences, languages, assets, and known gaps (`manual_impact.py` records its list under `impact`).
8. Unless `--no-build`, run `python .specify/extensions/user-manual/scripts/audit_manual.py` and
   `python .specify/extensions/user-manual/scripts/build_manual.py --all` once; it builds every
   configured audience and language. Deploy an ephemeral preview only when `manual.yml` names an
   approved provider; in that case add `--archive` to that build (the provider publishes the
   archives; CI builds its own), read `skills/user-manual/references/preview-publishing.md`, validate its
   checked-in provider descriptor, and preserve the private artifact even when hosted deployment
   succeeds or is skipped.
9. Record freshness:

   ```text
   python .specify/extensions/user-manual/scripts/manual_state.py record --feature <feature-path>
   ```

   Write any freshness log or status report to `User-Manual/.state/features/<feature-name>/reports/`
   (`<feature-name>` is the feature folder's name), which freshness never reads. A report written after
   `record` into the feature folder or a `qa/` folder is a new input and makes the state stale.

10. Report pages/assets changed, English and Arabic coverage, preview paths, and unresolved gaps.
