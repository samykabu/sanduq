# Changelog

All notable changes to the QA extension.

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
