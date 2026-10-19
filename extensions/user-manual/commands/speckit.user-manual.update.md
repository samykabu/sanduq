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
2. Resolve the active feature and run
   `python .specify/extensions/user-manual/scripts/manual_state.py status --feature <feature-path>`.
   On `stale-input-or-output`, read its `changed_inputs` and the affected manual pages; otherwise
   (`missing`, legacy state, or `--full`) read the full set: specifications, plan, tasks, contracts,
   data model, quickstart, implementation diff, tests, and existing manual state.
3. When `lifecycle.impact_scope` in `manual.yml` is `evidence`, run
   `python .specify/extensions/user-manual/scripts/manual_impact.py --feature <feature-path>` and
   work from its `modules`, `pages` and `audiences`; its `unmatched` paths are module candidates.
   Verify new module candidates against source evidence and add them with `status: proposed`;
   require user approval before making them part of the stable navigation.
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
   a non-zero exit report its line and generate no diagram (when it prints a `specify extension`
   recipe and the user approves, re-run with `--approve`; under a `manual` policy the user runs the
   printed command, then re-runs this command). On a zero exit, pass on any "newer compatible
   release available" note, read `.specify/extensions/illustrate/skill/references/type-index.md`,
   choose the type, read its `type-*.md`, and read `SKILL.md` only when the diagram is created
   outside that recipe. Capture screenshots with deterministic synthetic fixtures; never use
   production data.
7. Update `User-Manual/.state/coverage.json`, including source evidence, affected modules, pages,
   audiences, languages, assets, and known gaps (`manual_impact.py` records its list under `impact`).
8. Unless `--no-build`, run `python .specify/extensions/user-manual/scripts/audit_manual.py` and
   `python .specify/extensions/user-manual/scripts/build_manual.py --all --archive` once; it builds
   every configured audience and language. Deploy an ephemeral preview only when `manual.yml`
   names an approved provider; in that case load `skills/preview-publishing/SKILL.md`, validate its
   checked-in provider descriptor, and preserve the private artifact even when hosted deployment
   succeeds or is skipped.
9. Record freshness:

   ```text
   python .specify/extensions/user-manual/scripts/manual_state.py record --feature <feature-path>
   ```

10. Report pages/assets changed, English and Arabic coverage, preview paths, and unresolved gaps.
