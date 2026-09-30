# Stage reference: verify

Loaded when `claim` returns `stage: verify` (runtime `workflow:verification`).

Before the last Verify/Review/Ready pass, read the publication preflight in
`references/stage-pr.md#publication-preflight-and-post-merge-verification` and
prepare portable evidence there.

## Required work and evidence

Actual tests/review evidence and `blocking_findings: 0`. A command instruction or
checklist alone is not an executed test.

See `references/receipt-rules.md` for the full amendment and revalidation
recipes, including the `revalidate --stage verify --check-run <run id>` recovery
after source drift.
