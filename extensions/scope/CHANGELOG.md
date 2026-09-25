# Changelog

## Unreleased

- Serve Project board reads and writes (`item-list`, `field-list`, `item-add`, and
  single-select/text `item-edit`) from the REST Projects API when the GraphQL budget is
  exhausted. The real budget is checked, because `gh project` can report exhaustion as an
  unrelated error such as "unknown owner type". GraphQL is used again after the reported reset.
- Name the transport on stderr when falling back, and add `transport` (`graphql`, `rest` or
  `graphql+rest`) to printed JSON results of Scope and clarification commands that touched the
  Project. Saved `--output` files are unchanged.

## 1.4.0 (unreleased)

- Move canonical source from Bunyan; add managed effort policy, automatic clarification reread and configurable board/artifact mappings.
- Revalidate open progressed features under matching workflow claims without resetting
  their board status; retain current approval and unresolved-question guards.

## 1.3.0

- Automatically invoke Plan from either Clarify or Brainstorm after a fully resolved
  review has published successfully and the live issue is Ready.
- Carry the exact source issue and specification through the shared handoff and
  preserve Plan's mandatory guards and Project hooks.
- Do not trigger Plan for previews, pending questions, exhausted rounds, failed
  publication, or closure that waives unresolved decisions.

## 1.2.1

- Present lettered, initially unchecked choices with a bold Recommended suffix.
- Read a single checked option as answer evidence; support normal comments with
  question IDs and optional feedback, including several answers in one comment.
- Collapse supporting context and diagrams while keeping the recommendation visible.
- Detect changed selections during publication and reject ambiguous checkbox evidence.

## 1.2.0

- Present complexity findings and let the user choose the total number of new issues.
- Require explicit approval of the exact proposal before any publication writes.
- Bind local approval receipts to the proposal, source, prerequisites and selected count.
- Keep honest scores for approved larger issues instead of forcing recursive splits.
- Prevent cancelled, rolled-back operations from being resumed.

## 1.1.0

- Require Backlog before Specify and set Feature Specification after binding the spec.
- Automatically dispatch available Superspec Brainstorm, falling back to Clarify.
- Share unattended GitHub question rounds, creator mentions, answer evidence and spec integration.
- Remove question-count caps; enforce a creator-configurable seven-round limit.
- Stop waiting issues immediately; use Need Clarifications and Ready consistently.
- Gate planning on Ready and preserve customization through composable presets.

## 1.0.0

- Added issue inspection, prerequisite reporting, effort validation and publication.
- Added recursive decomposition, native sub-issues and dependency reconciliation.
- Added Specify gating, original-issue binding, parent rollup and Archify plan handoff.
