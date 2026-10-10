# Changelog

## [2.1.2] - 2026-10-10

- README links point to the new extension page, install-by-host page and command reference.

## [2.1.1] - 2026-10-06

- Link setup and complete usage examples from the package README; links work in installed copies.

## 2.1.0

- Typed links: entries may list `constrains` (live entries whose behavior this entry limits) and `supersedes`
  (entries describing an older state) beside the untyped `relations` (see also). Both are optional, so existing
  entry files are unchanged.
- `memory query` ranks a constraining entry just below the entry it constrains (reason `constrains`), even outside
  a `--domain` filter. A superseded hit drops below its replacement, which joins the results (reasons
  `superseded-by` and `supersedes`). Rendered entries list `Constrains`, `Constrained by`, `Supersedes` and
  `Superseded by`, and linked entries not returned include incoming typed links.
- `memory check`, delta validation, `fragment-check` and `merge` resolve typed links. A link may not point to its
  own entry or repeat an id across the three lists, and `constrains` targets must be live.

## 2.0.0

Breaking: project memory moves from the single `specs/project-memory.md` to an atomic store under `specs/memory/`.
Finish any 1.x run, add the new policy keys and run `archive.py migrate` once; migration is lossless and proves a
byte-exact export.

- One entry per file, a governed taxonomy, append-only per-run provenance ledgers, and generated INDEX and catalog
  pages within token budgets (`memory_budgets`, `tokenizer`).
- `memory query/show/provenance/catalog/check/index/export`: budgeted, ranked retrieval with match reasons and a
  continuation cursor; `impact` is query-first.
- Delta candidates validated as one materialized result; review binds the base and result memory roots and the
  exact outputs; finalize and rollback cover entry files and ledgers.
- Parallel drafting (`packets`, `fragment-check`, `merge`) with entry ownership, proposals and conflict classes, and
  partitioned review (`review-packets`) in parts of at most 40k tokens plus an integration packet.
- Reviewed corrections may carry a `reason` instead of a source unit in the run.
- Pathspecs go to Git on stdin, so large archives no longer exceed the Windows command-line limit.

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
