# Changelog

## [1.6.0] - 2026-10-10

- The implementation dependency plan and clarification diagrams use Sanduq Illustrate
  (replaces Archify). `extension.yml` now requires `illustrate >=2.2.1,<3.0.0`.
- `accept_plan.py` accepts an Illustrate dependency-graph HTML whose wave nodes and edges
  carry `data-plan-node` / `data-plan-from` / `data-plan-to`. It keeps the issue coverage,
  reachability, freshness-hash, pending-marker, failed-render and receipt rules, runs
  Illustrate's `self_check.py`, `verify-geometry.py` and `export_diagram.py` (SVG and PNG),
  and renders the plan in headless Chromium at three desktop viewports, failing on script
  errors and invisible, overlapping or out-of-bounds nodes. Screenshots and hashes go in the
  receipt; managed projects still require `--review` before the marker clears.
- New flags: `--html` (replaces `--spec`), optional `--illustrate <skill-dir>`, and
  `--migrate-only`. `--spec` stays as an alias of `--html` and the previous renderer flag is
  accepted and ignored with a warning until 1.7.0.
- Pending plans from 1.5.x are converted, never dropped: the marker stays pending with the
  original under `migrated_from`, an unreviewed receipt is kept as
  `scope-plan-receipt.legacy.json`, and `PLAN_REGENERATION_REQUIRED` names the issue.
- Clarification questions take `diagram_image` (a pushed Illustrate PNG) with a required
  `diagram_text`. The image is embedded through a commit-pinned GitHub blob URL verified
  with the contents API, so it loads in private repositories; otherwise the text version is
  posted with the reason and listed under `image_fallbacks`. Managed Mermaid diagrams now
  fail with `ILLUSTRATE_REQUIRED`; `raw.githubusercontent.com` images are rejected.
- `references/illustrate-plan.md` replaces the previous plan reference.

**Upgrade note.** Install Illustrate 2.2.1 or newer beside Scope (Workflow 1.9.0 installs
it), and for plan acceptance `pip install playwright && playwright install chromium`. Run
`python .specify/extensions/scope/scripts/accept_plan.py --migrate-only` if a plan was
pending before the upgrade, then regenerate it with `/speckit-scope-plan`. Replace
`--spec <file>` with `--html <file>` in your own scripts before 1.7.0.

## [1.5.2] - 2026-10-10

- Documentation: neutral provenance wording; no behavior change.

## [1.5.1] - 2026-10-06

- Link setup and complete usage examples from the package README; links work in installed copies.

## 1.5.0

- `extension.yml` now declares `requires.extensions: workflow >=1.8.0,<2.0.0`
  (required), because `bound_claim` uses workflow's checkpoint identity gate.
  Spec Kit does not enforce `requires.extensions`; the workflow installer
  does (see workflow 1.8.0).
- `bound_claim` (`workflow_policy.py`) no longer compares a checkpoint's
  absolute `repo_path` (machine- and clone-specific; still written by
  workflow 1.8.0+ so an older reader does not `KeyError`, but never read
  or compared by it) against the current repository root; the `issue`
  field it already checks just above binds the claim to the portable
  GitHub repo string instead. Fixes the same checkpoint-identity design
  bug `workflow.py`'s `Run.load()` fixes. It now also runs workflow's own
  checkpoint identity gate (`repo_identity`, or a legacy checkpoint's
  reachable history, and the issue naming this repository's GitHub remote)
  before accepting the claim, and refuses it on any failure. This needs the
  sibling workflow extension (1.8.0 or newer) installed beside scope; with
  none loadable the claim is refused.
- Serve Project board reads and writes (`item-list`, `field-list`, `item-add`, and
  single-select/text `item-edit`) from the REST Projects API when the GraphQL budget is
  exhausted. The real budget is checked, because `gh project` can report exhaustion as an
  unrelated error such as "unknown owner type". GraphQL is used again after the reported reset.
- Name the transport on stderr when falling back, and add `transport` (`graphql`, `rest` or
  `graphql+rest`) to printed JSON results of Scope and clarification commands that touched the
  Project. Saved `--output` files are unchanged.

## 1.4.0

- Move canonical source into Sanduq; add managed effort policy, automatic clarification reread and configurable board/artifact mappings.
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
