# Changelog

## [4.7.3] - 2026-10-28

- `pr_publish.py` adds `Closes <owner/repo>#<issue>` for the bound issue to the published section when the explainer does not close it already, so merging the PR closes its issue; the lint refuses a body that never closes it (`BOUND_ISSUE_NOT_CLOSED`). The explainer and the rest of the body are unchanged (lite re-measure N1).
- `pr_publish.py` rewrites relative Markdown links to `https://github.com/<repo>/blob/<HEAD sha>/<path>`, keeping the anchor, after the same commit and contents-API checks as images; absolute URLs, `#anchors` and code are left alone, so links need no hand rewrite and no second publish (N4). Image and link destinations are parsed, not cut at the first parenthesis: `<angle brackets>`, balanced parentheses, an optional title and backslash-escaped punctuation work. `speckit.pr.generate` commits (and, for an existing PR, pushes) every linked document before publishing, and a file that is not committed is named in the error with the `git add`/`git commit`/`git push` commands.

## [4.7.2] - 2026-10-28

- `speckit.pr.generate` says `pr_publish.py` is the only way the body is built: never write, lint or send a body by hand, and rerun the script after editing the explainer. A lite run built and sent one body by hand, then had the script rewrite it (lite re-measure, driver 2).

## [4.7.1] - 2026-10-28

- `requires.tools` declares Python `>=3.11`, the floor every Sanduq extension now states (SAMY-11).

## [4.7.0] - 2026-10-27

- `speckit.pr.review-feedback`: the plan file carries the summary comment as `summary`, covered by the approved digest, and step 7 posts that text instead of an unapproved `report.md`. In a managed project (`.specify/workflow.yml`) step 6 runs `gate_explain.py` after the push and follows its revalidate recipe before reporting, since a pushed fix after Ready makes receipts stale.

## [4.6.1] - 2026-10-26

- License: this package is MIT; versions before this one were PolyForm Noncommercial 1.0.0. The archive now ships its LICENSE.

## [4.6.0] - 2026-10-21

- `pr_feedback.py plan|reply|resolve` carry out an approved review plan. The plan file binds the repository, the PR and the exact replies and threads to resolve; `plan` checks it read-only and prints its digest, which the user approves. `reply` and `resolve` refuse a plan whose digest changed and threads or comments of another PR, and write nothing then. After the push, the pushed commit (`head` in the plan) gets its own approval digest. `resolve` needs both approvals, waits until the PR head on GitHub contains that commit and each thread's approved reply is posted, and counts a thread as resolved only when GitHub's answer says so (gh exits 0 on GraphQL errors). A thread to reply in with more than 100 comments is refused, since an earlier reply could be unseen. Work already done is skipped, so a rerun after a partial failure finishes the rest. `speckit.pr.review-feedback` posts replies and resolves threads through it; its trust rules and approval gate are unchanged.
- `pr_publish.py`, `pr_changelog.py` and `pr_feedback.py` run `gh` through the shared `sanduq_gh` transport bundled in the archive, with their timeouts (120 s, 60 s for the changelog) and no retries.

### Migration

- `speckit.pr.review-feedback` now writes a plan file outside the working tree and shows its digest at the approval step. Approve that digest; if you change the plan, it shows a new one. After the push it shows the pushed commit and a second digest; approve that before threads are resolved.

## [4.5.1] - 2026-10-21

Fixes from the review of round 4 (PR #101).

- `pr_feedback.py gather` reports `truncated` (and warns on stderr) when GitHub returned only the newest 100 reviews or the first 100 comments of a thread, and `review-feedback` tells the agent to read the rest on the PR; before, that feedback was dropped silently.

## [4.5.0] - 2026-10-21

Optimization round 4. No renames.

Round 4.

- `pr_publish.py` never edits a merged or closed PR: when the branch has no open PR, gh returns the newest closed one, and the script now exits 3 with "PR #n is merged" instead of rewriting its body. A new PR's branch is pushed when its upstream is behind, not only when it has none. The new PR's URL comes from `gh pr create` (one `gh pr view` call fewer).
- `pr_changelog.py` finds the base through the same default-branch rule as `pr_publish.py` (origin/HEAD, else GitHub). It no longer writes "(no commits on `main..HEAD`)" on a `master` repository; when no base resolves, the commit line is left out.
- The closing-reference lint is the shared `sanduq_pr_lint` module bundled in the archive (the rule Workflow's `pr-lint` runs). An installed Workflow's `execution_tools.py` is no longer loaded.
- `speckit.pr.generate` reads the Assure gate through `assure_state.py status --kind document --gate --summary` instead of searching the config text, so a commented-out key no longer turns the gate on.
- New read-only `scripts/pr_feedback.py gather`: one paged GraphQL query plus the general comments, filtered as step 1 asked. `speckit.pr.review-feedback` step 1 uses it: 3 to 4 `gh` calls instead of 7, every thread read (the old query stopped at 100), 5,201 bytes instead of 5,518.
- `speckit.pr.generate` step 0 is one sentence: run `deps.py ensure illustrate` and follow its output (it prints the approval step itself).
- `speckit.pr.generate` description: "Use when asked to 'write the PR description'". Under Workflow, `speckit.workflow.finalize` keeps "open the PR".

### Migration

- A rerun of `speckit.pr.generate` after the PR merged now reports exit 3 and publishes nothing. Open a new branch for further changes.

## [4.4.0] - 2026-10-20

Optimization round 3 (fixes to 4.3.0).

- `pr_publish.py`: a failed PR lookup is an error, not "no PR"; unpaired, repeated or reversed markers are refused; relative images become pinned blob URLs verified at HEAD before the lint, so the published body's images resolve and the lint hash covers the final body.

## [4.3.0] - 2026-10-19

Optimization round 2.

- `scripts/pr_publish.py` splices the PR body, runs Workflow's pr-lint, refuses on findings, creates or edits the PR and prints the receipt fields the PR stage verifies. Exit codes: 0 published, 1 lint findings, 2 bad input, 3 gh or git failed.
- `scripts/pr_changelog.py` seeds the feature CHANGELOG from git, tasks, progress and evidence inside a regenerated facts block; the model writes the prose around it.
- `speckit.pr.generate.md` is 11,183 bytes instead of 18,060. Diagrams load `references/pr-diagram-recipe.md` plus one Illustrate type reference instead of the whole Illustrate skill, so one PR run reads 22.7 KB of instructions instead of 72.6 KB.
- Image verification has two tiers, `api` and `browser`, recorded as `image_verification` in the receipt, so a host without a browser verifies through the API.
- Workflow's guard hook refuses `gh pr create|edit --body-file` whose lint receipt does not match the body, and `gh pr create` on the default branch.
- One description per command.

## [4.2.3] - 2026-10-15

- Add the lean Workflow pre-publication check for closing references, binding the prepared body to its issue and prerequisites. Standalone PR use remains supported.

## [4.2.2] - 2026-10-10

- README links point to the new extension page, install-by-host page and command reference.
- `references/pr-image-embedding.md` names Illustrate as the diagram source. No behavior change.

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
