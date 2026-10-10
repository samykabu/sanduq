# Changelog

## [2.3.2] - 2026-10-10

- README links point to the new extension page, install-by-host page and command reference.

## [2.3.1] - 2026-10-06

- Link setup and complete usage examples from the package README; links work in installed copies.

## 2.3.0

- **B7 — quiet output.** `assure_state.py` gains `--summary` (one line:
  `ok`/`error`, e.g. `ok action=record kind=document outputs=1
  recorded=1`) as an alternative to the previous full JSON output, which is
  unchanged and now also selectable explicitly with `--json`. `--summary`
  and `--json` together is rejected; default (no flag) behaviour and the
  exit code are unchanged. A `reason` with embedded whitespace or newlines
  is collapsed to a single line so `--summary` always prints exactly one
  line.
- **B9 — shared dependency script.** `speckit.assure.analyze` and
  `speckit.assure.document` now ensure the `illustrate` dependency with the
  shared `scripts/deps.py ensure illustrate` (also shipped to `pr` and
  `user-manual`) instead of duplicated prose: it checks the Spec Kit
  registry, follows the project's `update_policy`, and prints one line,
  failing closed with `deps.py ensure illustrate --approve` as the
  recovery when illustrate cannot be brought into range; an exit-0 "newer
  compatible release" note is surfaced to the user. Illustrate's
  `SKILL.md` now loads only when a diagram task or asset is actually being
  added, not unconditionally at step 0a.

  `deps.py` itself parses `specify extension info`'s real plain-text
  `Name (vX.Y.Z)` header (it has no `--json` output); answers `specify
  extension update`'s unavoidable `typer.confirm` prompt with an explicit
  `y` only on an authorised update, closing stdin otherwise so an
  unexpected prompt fails fast; every subprocess call has a timeout; the
  version comparator follows SemVer precedence for pre-release/build-
  metadata suffixes, a leading `v`, space-separated clauses, `^`/`~=`, and
  npm-semver's pre-release range rule (a plain `>=2.0.0,<3.0.0` never
  admits a pre-release version). `.dependency-checks.json` records a check
  only when the catalog probe actually ran and succeeded. It ships no
  third-party dependency: `dependencies.yml` and
  `.specify/extension-dependencies.yml` are read by a small built-in
  parser (nothing installs a package's `requirements.txt` before its
  commands run) that rejects a tab in leading whitespace, a duplicate or
  quoted key, a flow-style value, and an unbalanced quote, and reports a
  malformed list item's own line number.

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
