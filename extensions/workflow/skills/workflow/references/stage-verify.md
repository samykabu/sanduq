# Stage reference: verify

Loaded when `claim` returns `stage: verify` (runtime `workflow:verification`).

## Required work and evidence

Actual tests/review evidence and `blocking_findings: 0`. A command instruction or
checklist alone is not an executed test.

See `references/receipt-rules.md` for the full amendment and revalidation
recipes, including the `revalidate --stage verify --check-run <run id>` recovery
after source drift.
