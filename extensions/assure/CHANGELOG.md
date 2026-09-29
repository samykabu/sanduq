# Changelog

## Unreleased

- Replaced the verbatim "Ensure the Illustrate dependency" instruction block in
  `speckit.assure.analyze` and `speckit.assure.document` with one call each to the shared
  `scripts/deps.py ensure illustrate` (also shipped to `pr` and `user-manual`); same
  registry/policy/catalog checks and failure recipe, now in one tested script instead of
  duplicated prose (B9). The illustrate `SKILL.md` is now loaded only when a diagram task or asset
  is actually being added, not unconditionally at step 0a. A failure now points at
  `deps.py ensure illustrate --approve` for the user to re-run after approving, and an exit-0
  "newer compatible release" note is surfaced to the user instead of only appearing in the printed
  line.
- `scripts/deps.py`: fixed after Opus review — parses `specify extension info`'s real plain-text
  `Name (vX.Y.Z)` header (it has no `--json` output); feeds `specify extension update`'s
  unavoidable `typer.confirm` prompt an explicit `y` only on an authorised update and otherwise
  closes stdin so an unexpected prompt fails fast instead of hanging; every subprocess call now has
  a timeout (a timeout is a plain failure, not an exception); the version comparator follows SemVer
  precedence for pre-release/build-metadata suffixes, a leading `v`, space-separated clauses, and
  `^`/`~=`, and ignores a still-unparseable catalog version instead of failing an already-compatible
  install; `.dependency-checks.json` now records a check only when the catalog probe actually ran
  and succeeded. Dropped the PyYAML dependency: `dependencies.yml` and
  `.specify/extension-dependencies.yml` are read by a small built-in parser (nothing installs a
  package's `requirements.txt` before its commands run), tested against the real files of all three
  consuming packages.

## 2.2.2

- `assure_state.py` defaults `--base-ref` to the feature's bound target
  branch recorded in its Workflow checkpoint instead of always assuming the
  origin HEAD default branch, when the checkpoint recorded one. An explicit
  `--base-ref` still wins, and a feature with no checkpoint, or none recorded,
  keeps today's origin-HEAD default (F16).

## 2.2.1

- The bundled freshness helper shares Workflow's checkout-independent
  fingerprints: an unchanged tracked `.sql` or `-text` file that a Windows
  `core.autocrlf` checkout wrote with different line endings hashes as its
  committed blob, so QA state recorded on Windows stays current in Linux CI.

## 2.1.0 (unreleased)

- Use YAML parsing for hook initialization and shared source/output freshness with deletion detection.
- Managed initialization preserves dispatcher-owned hooks and uses the workflow's
  selected-process CI instead of creating an unconditional documentation gate.

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
