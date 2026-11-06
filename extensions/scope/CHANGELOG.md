# Changelog

## [2.0.0] - 2026-10-28

Breaking: Scope is retired as a package. Its code, commands, skills, references and tests moved into Workflow 2.0.0, and every command was renamed: `speckit.scope.<x>` is `speckit.workflow.scope-<x>` (`run`, `plan`, `guard`, `bind`, `after-specify`, `plan-guard`, `reconcile`).

- This last release has no code, presets or hooks. Installing it over Scope 1.x removes the old commands, skills and hook entries; Spec Kit prints its description, which is the migration step: `python .specify/extensions/workflow/scripts/upgrade.py --version 2.0.0 --apply`. Its one command, `speckit.scope.migrate`, prints the same step.
- It requires Workflow 2.0.0 or later. Workflow's installer removes any Sanduq Scope, this shim included, and keeps the state in `.specify/scope/`.
- The catalog entry is marked `deprecated` with `superseded_by: workflow`.
