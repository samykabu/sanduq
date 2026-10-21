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

## Decision (2026-10-20)

Recommended set, saved on the report page (db `selection/current`, version 22): keep every id, display name,
command name and preset. Decided changes, carried into phase 2:

- D1 three description fixes: Project's managed mode (no per-task sub-issues under Workflow);
  `workflow.finalize` vs `pr.generate` ("open the PR"); `workflow.status` vs `progress.status`.
- D2 docs note on the community `scope` and `memory` (README and the two extension pages).
- D3 (st:memory) Workflow owns `speckit.memory.session` and `speckit.memory.prepare` in managed projects;
  `impact` stays a hook. Gate: one managed run that shows the duplication.
- D4 (st:project) the remote normaliser becomes one shared helper packaged into Project; `project_sync.py`
  stops loading `workflow.py`.
- D5 (st:progress) retire `workflow/scripts/progress_shim.py`; the legacy reporter stays.

## Phase 2 streams (read-only reviews)

BEFORE numbers: `docs/internal/benchmarks/round-4-before-{instructions,full,lite}.*` at 51043b8.
R1 workflow; R2 scope and presets; R3 assure and user-manual; R4 pr, project and memory; R5 illustrate and
progress; R6 cross-cutting. Each writes `round-4-review-<group>.md`. Then a Codex cross-check, a plan on the
report page, and the user's approval before implementation.
