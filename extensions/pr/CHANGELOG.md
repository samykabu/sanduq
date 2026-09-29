# Changelog

All notable changes to the Pull Request Workflow extension.

## [Unreleased]

### Changed

- Replaced the verbatim "Ensure the Illustrate dependency" instruction block in
  `speckit.pr.generate` with one call to the shared `scripts/deps.py ensure illustrate` (also
  shipped to `assure` and `user-manual`); same registry/policy/catalog checks and failure
  recipe, now in one tested script instead of three duplicated prose copies (B9).
- The illustrate `SKILL.md` is now loaded only when step 4 actually decides a diagram is
  warranted, not unconditionally at step 0.
- Moved the mandatory PR image-embedding rules out of the command body into
  `references/pr-image-embedding.md`, loaded only when the PR has a diagram or screenshot to embed;
  it keeps the commit-pinned `?raw=true` / never-`raw.githubusercontent.com` rules verbatim and adds
  the standing contents-API verification line (`gh api repos/<o>/<r>/contents/<path>?ref=<sha>`,
  rule 6 / F21) that the inline instructions had not spelled out explicitly.
- `scripts/deps.py`: fixed after Opus review of the first B9 cut —
  - `specify extension info` has no `--json` output (specify_cli 1.0.11, the commit pinned in
    `.github/workflows/ci.yml`); the catalog freshness probe now parses the real plain-text
    `Name (vX.Y.Z)` header instead of expecting JSON that was never going to arrive.
  - `specify extension update` always shows an interactive `typer.confirm` with no `--yes`
    equivalent; an authorised update now gets `input='y\n'`, every other call closes stdin
    (`subprocess.DEVNULL`) so an unexpected prompt fails fast instead of hanging, and every
    subprocess call has a timeout (`subprocess.TimeoutExpired` is a plain failure, not an
    exception).
  - The version comparator now follows SemVer precedence for pre-release/build-metadata suffixes,
    a leading `v`, space-separated clauses, and the `^`/`~=` operators; a still-unparseable catalog
    version is ignored (advisory only), so it can never turn an already-compatible install into a
    reported failure.
  - `.specify/extensions/.dependency-checks.json` now records a check only when the catalog probe
    actually ran and succeeded, not on every `due` cycle (a skipped or failed probe no longer hides
    the next real check for `check_interval_hours`).
  - Dropped the PyYAML dependency and `requirements.txt`: nothing in the install/upgrade path
    installs a package's `requirements.txt` before its commands run, so `dependencies.yml` and
    `.specify/extension-dependencies.yml` are now read by a small built-in parser instead
    (tested against the real files of all three consuming packages). `python` stays a required
    tool for `pr` — it is what runs `deps.py` — but ships no third-party dependency.
  - A failure now points at `deps.py ensure illustrate --approve` for the user to re-run after
    approving, instead of a bare "re-run this command"; an exit-0 result's "newer compatible
    release" note is now explicitly surfaced to the user instead of only appearing in the printed
    line.

### Fixed

- PR generation instructions require every reviewer-facing diagram and screenshot to be embedded
  inline, with an asset inventory and no link-only substitutions. Private-repository images use
  supported attachments or verified repository URLs; rendered HTML and authenticated image loading
  are checked separately. Generated skills inherit this canonical command contract.
- Removed the assumption that a commit-pinned `?raw=true` URL or a literal `<img>` match alone proves
  private image visibility. Missing exports, inaccessible images and body limits remain explicit
  incomplete outcomes. This is an instruction update; live private-PR acceptance is still required.

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
