# Changelog

## Unreleased

- `project-sync` (Bash and PowerShell) gains `-Summary`/`--summary`: exactly
  one stdout line (`ok issue=<n> status=<status> created=<n> closed=<n>` on
  success; `skipped reason=<reason>` on a graceful degradation — a skip is
  not success, so it never starts with `ok`; `error <message>` on a usage
  error or a mid-run failure) as an alternative to the `-Json`/`--json`
  summary, which is unchanged. Under `-Summary`/`--summary` the run log
  (PowerShell `Write-Log`, Bash `log`/`warn`) moves off stdout so it never
  breaks the one-line contract; a genuine mid-run failure (bash `set -e`,
  PowerShell `$ErrorActionPreference = 'Stop'`) is now also caught and
  reported as that one `error` line instead of a raw shell trace or
  uncaught exception. `-Summary`/`--summary` and `-Json`/`--json` together
  is rejected. Default (no flag) behaviour and every exit code are
  unchanged (B7).
- Fix: the PowerShell script's own `$summary` local variable collided
  case-insensitively with the `-Summary` switch parameter, so assigning it
  overwrote `-Summary` with a `PSCustomObject` and crashed every non-skip
  run with a `MetadataError` right before printing the final summary.
  Renamed to `$jsonSummary` (B7 review fix).
- `project-sync` (Bash and PowerShell) falls back to the GitHub REST API when the GraphQL budget
  is exhausted: Project item add/lookup and Status edits, parent issue lookup/creation, sub-issue
  creation and linking, sub-issue closing and the open-PR check. The real budget is checked, since
  `gh project` can misreport exhaustion (for example "unknown owner type").
- The run log and the `-Json`/`--json` summary report the `transport` used (`graphql` or `rest`).

## 2.1.0 (unreleased)

- Managed mode preserves the bound parent and delegates task issue creation and state changes to the workflow adapter.
- Both setup scripts preserve managed hooks, map workflow phases from project policy
  and retain Scope-only board columns. Managed sync is required.

All notable changes to the GitHub Project Lifecycle Sync extension.

## [2.0.0] - 2026-07-18

### Changed

- Changed new distributions from MIT to PolyForm Noncommercial 1.0.0. Previously published MIT
  versions retain their original terms.

## [1.1.0] - 2026-07-18

### Added

- Ask during project initialization whether lifecycle sync hooks should be required/automatic or
  optional/manual.
- Support non-interactive selection through `-HooksMode` (PowerShell) and `--hooks-mode` (Bash).

### Changed

- Persist the selected hook policy in `config.json` and apply it to every `project` hook in
  `.specify/extensions.yml`.

## [1.0.1] - 2026-07-09

### Changed

- Aligned release metadata with the sanduq automated extension pipeline and public catalog.

## [1.0.0] - 2026-07-09

### Added

- Initial release of the `project` Spec Kit extension for GitHub Project (v2) lifecycle sync.
- Parent feature issues, native task sub-issues, lifecycle status movement, and graceful skips when
  GitHub CLI or project configuration is unavailable.
