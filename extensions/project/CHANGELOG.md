# Changelog

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
