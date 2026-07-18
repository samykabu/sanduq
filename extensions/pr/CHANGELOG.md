# Changelog

All notable changes to the Pull Request Workflow extension.

## [4.0.0] - 2026-07-18

### Changed

- Updated the Illustrate dependency to `>=2.0.0,<3.0.0`.
- Changed new distributions from MIT to PolyForm Noncommercial 1.0.0. Previously published MIT
  versions retain their original terms.

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
