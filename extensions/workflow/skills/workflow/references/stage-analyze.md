# Stage reference: analyze

## Required work and evidence

Resolve blocking cross-artifact findings, rerunning affected stages when inputs change. A
material ambiguity becomes a decision question on the bound issue through `decisions.py`, and
the stage pauses. The owning Specify, Plan or Tasks stage applies an accepted answer; Analyze
records the finding and revalidates the artifacts. Never resolve a team decision through a
local chat question or silently edit upstream work.

## `workflow:lint` (standard and lite tiers)

When the command is `workflow:lint`, run `python .specify/extensions/workflow/scripts/lint.py
--feature specs/<f> --json`. It checks requirement coverage, task ids, the dependency graph,
headline length, leftover `[NEEDS CLARIFICATION`, unreferenced contracts and the
`artifacts.budgets` byte budgets. Fix every error finding in the owning artifact (a budget
error means cutting the artifact, not raising the budget). When `ok` is true and
`needs_model_analyze` is false, record with `lint.py --feature specs/<f> --record --token
<active-token>`; it writes the receipt itself. When `needs_model_analyze` is true (a requirement
without a task, a task without a requirement, contradictory status markers), escalate: run
`speckit.analyze` on the flagged findings only, then record a normal receipt with the lint
output in `evidence`.
