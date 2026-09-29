# Stage reference: review

Loaded when `claim` returns `stage: review` (runtime `workflow:review`).

Before the last Verify/Review/Ready pass, read the publication preflight in
`references/stage-pr.md#publication-preflight-and-post-merge-verification` and
prepare portable evidence there.

## Required work and evidence

Actual tests/review evidence and `blocking_findings: 0`. A command instruction or
checklist alone is not an executed test.

See `references/receipt-rules.md` for the full amendment and revalidation
recipes, including the diff-reviewed `revalidate --stage review --diff-reviewed
<file>` recovery after source drift.

## SuperSpec Review provider (`speckit.superspec.review`)

When execution.checkpoints is required-only, project policy pre-authorizes
routine phase checkpoints and backend choice. Record the selected execution mode
and continue automatically. Explicit HUMAN-REVIEW tasks, unresolved requirements,
security decisions and deployment approvals still pause. Execute small batches
and hand off only at a reliably measured context limit. Without reliable telemetry,
continue automatically; never stop on estimates or reset a measured budget per task.
