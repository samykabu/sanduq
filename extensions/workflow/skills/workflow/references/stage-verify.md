# Stage reference: verify

Loaded when `claim` returns `stage: verify` (runtime `workflow:verification`).

If lean policy selects `verification_plan`, run the exact relevant checks and
record passing local evidence with `references/verification-plan.md`. Verify
completion captures a runtime-owned snapshot of their commands, sources,
fixtures, environment and evidence. Reuse is allowed only for unchanged
passing checks. Local records remain local evidence; the selected CI checks
and genuine local acceptance remain required. An exact fixed collection
command belongs to the coordinator and needs no extra model dispatch.

Before the last Verify/Review/Ready pass, read the publication preflight in
`references/stage-pr.md#publication-preflight-and-post-merge-verification` and
prepare portable evidence there.

## Required work and evidence

Actual tests/review evidence and `blocking_findings: 0`. A command instruction or
checklist alone is not an executed test.

See `references/receipt-rules.md` for the full amendment and revalidation
recipes, including the `revalidate --stage verify --check-run <run id>` recovery
after source drift.
