# Changelog

All notable changes to the Assure extension.

## [2.0.0] - 2026-07-19

### Breaking

- Renamed the extension from `qa` to `assure` because the `qa` id conflicts with an existing
  extension in the Spec Kit community catalog. Commands are now `/speckit-assure-*`, the install
  directory is `.specify/extensions/assure/`, and the config file is `assure-config.yml`.
  No compatibility alias is retained.

### Migration

- Remove `qa`, install `assure`, and rerun `/speckit-assure-init` to regenerate hooks and config.
  QA output directories (for example `docs/<feature>/qa/`) and task markers are unchanged, so
  generated documentation is preserved. Prior `qa-v*` release tags remain available in Git history.

## [1.0.0] - 2026-07-18

### Breaking

- Replaced the `how-to-test` extension and commands immediately with the `qa` extension and
  `/speckit-qa-*` commands. No compatibility alias is retained.

### Added

- Added `QA.Init` with integrated and manual project lifecycle policies.
- Added a mandatory `before_implement` analysis gate in integrated mode.
- Added feature-scoped analyze/document freshness evidence for PR preflight enforcement.
- Added a reusable QA skill with progressively loaded analysis and documentation contracts.

### Migration

- Remove `how-to-test`, install `qa`, and run `/speckit-qa-init`. The former extension's release
  history remains available in Git history and its published release tags.
