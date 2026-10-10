# Changelog

## [4.2.2] - 2026-10-10

- README links point to the new extension page, install-by-host page and command reference.

## [4.2.1] - 2026-10-06

- Link setup and complete usage examples from the package README; links work in installed copies.

All notable changes to the Pull Request Workflow extension.

## [4.2.0] - 2026-09-30

### Changed

- **B9 — shared dependency script.** Replaced the verbatim "Ensure the
  Illustrate dependency" instruction block in `speckit.pr.generate` with one
  call to the shared `scripts/deps.py ensure illustrate` (also shipped to
  `assure` and `user-manual`); the illustrate `SKILL.md` now loads only when
  step 4 actually decides a diagram is warranted, not unconditionally at
  step 0. `deps.py` parses `specify extension info`'s real plain-text `Name
  (vX.Y.Z)` header (it has no `--json` output); answers `specify extension
  update`'s unavoidable `typer.confirm` prompt with an explicit `y` only on
  an authorised update, closing stdin otherwise so an unexpected prompt
  fails fast; every subprocess call has a timeout; the version comparator
  follows SemVer precedence for pre-release/build-metadata suffixes, a
  leading `v`, space-separated clauses, `^`/`~=`, and npm-semver's
  pre-release range rule; the built-in parser for `dependencies.yml` and
  `.specify/extension-dependencies.yml` (no PyYAML; nothing installs a
  package's `requirements.txt` before its commands run) rejects a tab in
  leading whitespace, a duplicate or quoted key, a flow-style value, and an
  unbalanced quote, and reports a malformed list item's own line. A failure
  points at `deps.py ensure illustrate --approve`; an exit-0 "newer
  compatible release" note is surfaced to the user.

  **Upgrade note:** `pr` now requires Python on the host (it is what runs
  `deps.py`), declared in `extension.yml`; it still ships no third-party
  dependency.
- Moved the mandatory PR image-embedding rules out of the command body into
  `references/pr-image-embedding.md`, loaded only when the PR has a diagram
  or screenshot to embed; it keeps the commit-pinned `?raw=true` /
  never-`raw.githubusercontent.com` rules verbatim and adds the standing
  contents-API verification line (`gh api repos/<o>/<r>/contents/<path>?ref=<sha>`)
  that the inline instructions had not spelled out explicitly.

### Fixed

- PR generation instructions require every reviewer-facing diagram and
  screenshot to be embedded inline, with an asset inventory and no
  link-only substitutions. Private-repository images use supported
  attachments or verified repository URLs; rendered HTML and authenticated
  image loading are checked separately. Generated skills inherit this
  canonical command contract.
- Removed the assumption that a commit-pinned `?raw=true` URL or a literal
  `<img>` match alone proves private image visibility. Missing exports,
  inaccessible images and body limits remain explicit incomplete outcomes.
  This is an instruction update; live private-PR acceptance is still
  required.

## [4.0.0] - 2026-07-18

### Changed

- Updated the Illustrate dependency to `>=2.0.0,<3.0.0`.
- Use PolyForm Noncommercial 1.0.0 for Sanduq original contributions.

## [3.1.0] - 2026-07-18

### Added

- Enforced `QA.Document` before PR creation when the installed QA lifecycle policy requires it and
  feature evidence is missing or stale.
- Enforced incremental `UserManual.Update` before PR creation when the User Manual is initialized.
- Rechecked both feature-scoped freshness records before allowing PR creation or update.

## [3.0.0] - 2026-07-18

### Changed

- Replaced the renamed `diagram-design` dependency with `illustrate >=1.0.0,<2.0.0` and updated
  diagram generation/export paths to the unified skill package.

## [2.1.0] - 2026-07-18

### Changed

- Expanded visual selection from fourteen to all twenty-seven Diagram Design v2 types.
- Routed PNG generation through Diagram Design's bundled deterministic exporter.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [2.0.0] - 2026-07-18

### Added

- `speckit.pr.review-feedback` (`/speckit-pr-review-feedback`) for approval-gated processing of
  unresolved pull-request review feedback.

### Changed

- Consolidated PR generation and PR review processing under the single `pr` extension.
- `speckit.pr.generate` now creates a pull request by default when the current branch has none;
  `--no-pr` remains the explicit docs-only opt-out.
- PR documentation now selects from all fourteen Diagram Design types and manages the versioned
  `diagram-design` dependency through the Spec Kit registry.
- Renamed the review command from `speckit.pr-review.process` to
  `speckit.pr.review-feedback`.

### Removed

- The separately installable `pr-review` extension. Install or update `pr` for both commands.

## [1.1.2] - 2026-07-09

### Changed

- Aligned repository metadata and release catalog links with the sanduq marketplace.

## [1.1.0] — 2026-07-04

### Added
- Architecture and process-flow diagram asset generation for PR documentation when an implementation
  changes architecture, integrations, service boundaries, user journeys, validations, jobs, or error
  recovery flows.
- Source HTML and exported PNG output under `docs/<feature-slug>/assets/diagrams/`, with PNGs
  embedded and HTML sources linked from the generated feature-details document.

## [1.0.0] — 2026-06-11

### Added
- `speckit.pr.generate` command (`/speckit-pr-generate`): generates a feature `CHANGELOG.md` and a
  plain-English `<Feature>-Explained.md` under `docs/<feature-slug>/` from Spec Kit artifacts, then
  creates or updates the pull request description with the feature details under the heading
  **"What have been developed and how to review it"**.
- Idempotency markers (`<!-- speckit-pr:start -->` / `<!-- speckit-pr:end -->`) so re-runs refresh
  the PR section instead of duplicating it.
- Optional `after_implement` lifecycle hook.
- Graceful degradation when `gh`/`git`/remote are unavailable (docs still generated, PR step skipped).
