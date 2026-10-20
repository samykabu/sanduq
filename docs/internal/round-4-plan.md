# Round 4: naming, then optimization

Asked 2026-10-20, after Workflow 1.16.0 (issue 99) released. Worktree `D:\Projects\Personal\sanduq-round4`,
branch `feat/round-4`, base b482e06 (main).

Scope: the nine extensions (workflow, scope, assure, user-manual, pr, project, illustrate, memory, progress) and
the three presets (workflow, scope-gate, scope-brainstorm).

## Phase 1: naming and structure (decision gate)

Round 3 decided on 2026-10-19 to keep every id and display name (round-3 report db `selection/current` v13).
Round 4 does not repeat round 3's research. It re-checks the facts that can change and adds the question
round 3 left open: whether any extensions or presets should be consolidated.

- N1 `round-4-naming.md`: names against what each item does today (Workflow 1.16.0 moved more project-sync
  logic into Workflow), live community catalogs, Spec Kit upstream support for id aliases or renames,
  refreshed blast radius, options per item with rationale.
- N2 `round-4-structure.md`: overlap and consolidation candidates (workflow and project, the three presets,
  progress and workflow status, memory and the workflow handoff, assure and user-manual shared code), each
  with what it would save and what it would break.

Output: an HTML report with a stored selection. Stop for the user's decision. No optimization review starts
before the decision.

## Phase 2: optimization (after the decision)

Reviews per extension, starting from the round-3 deferred list (W6, W9, SC2, SC8, X7, X9, PM2, PM5, PM9), a
Codex cross-check, a plan, implementation in streams with one owner per shared surface, BEFORE and AFTER
measurement, and a migration path for anything the decision renames, moves or merges.
