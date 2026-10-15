# Stage reference: ready

Loaded when `claim` returns `stage: ready` (runtime `workflow:gates`).

In lean mode the lifecycle coordinator runs Ready without a delegated model.
Only the final coding review is admitted on implementation and testing alone;
Ready (and CI) require every required task, including review, docs and
artifact-analysis tasks, to be checked with a verified delegated outcome.
Review receipts, task issue mappings and
the selected documentation freshness checks still apply, and document outputs
must exist before their tasks can be marked complete.

Before this pass, read the publication preflight in
`references/stage-pr.md#publication-preflight-and-post-merge-verification` and
prepare portable evidence there: it must run before the last Verify/Review/Ready pass.

## Required work and evidence

Verify task completion by category, issue mapping, review/tests and selected
documentation. Receipt needs `blocking_findings: 0`. Document-generation tasks
become complete only after their outputs exist.

See `references/receipt-rules.md` for the `revalidate --stage ready` recovery
recipe (it re-runs task, mapping and documentation checks) once Verify and Review
are current.
