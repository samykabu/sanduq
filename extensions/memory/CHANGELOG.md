# Changelog

## 1.1.0

- Allow explicit manual archives to skip verification with a recorded reason.
- Keep automatic verification required and preserve review, fixture/reference validation and recoverable scoped commits.
- Bind the override to the checkpoint and reviewer acknowledgment; record skipped status in the archive index and CLI results.

## 1.0.1

- Remove project-specific references from documentation, examples and installer messages.
- Detect conflicting archive tooling by its capabilities rather than a project-specific ID.

## 1.0.0

- Introduce Sanduq Memory as a project-configurable specification archive extension.
- Provide seven commands for Codex, Claude Code and Copilot, lifecycle hooks, independent review and source coverage.
- Preserve scoped checkpoints, current-memory reconciliation, fixture/consumer repair, number reservations, final commits and journaled resume/explicit rollback.
- Configure merge branch, implementation inputs and actual named verification checks per project.
- Install guards with context checks; preserve custom scripts and require approval before replacing existing archive tooling.
