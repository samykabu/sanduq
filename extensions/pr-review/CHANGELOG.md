# Changelog

All notable changes to the PR Review Processor extension.

## [1.0.2] - 2026-07-04

### Fixed

- Renamed the internal command ID to `speckit.pr-review.process` so it follows the
  `speckit.{extension}.{command}` pattern required by the `specify` extension validator while keeping
  the generated slash command `/speckit-pr-review-process`.

## [1.0.0] - 2026-07-04

### Added

- `speckit.pr-review.process` command (`/speckit-pr-review-process`) for approval-gated GitHub PR review feedback
  processing.
- Safety rules for treating reviewer comments as untrusted input.
- Workflow for gathering review threads, classifying comments, presenting a plan, applying approved
  fixes/replies, pushing, posting a summary, and resolving addressed threads.
