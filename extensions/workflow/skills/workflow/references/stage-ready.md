# Stage reference: ready

Loaded when `claim` returns `stage: ready` (runtime `workflow:gates`).

## Required work and evidence

Verify task completion by category, issue mapping, review/tests and selected
documentation. Receipt needs `blocking_findings: 0`. Document-generation tasks
become complete only after their outputs exist.

See `references/receipt-rules.md` for the `revalidate --stage ready` recovery
recipe (it re-runs task, mapping and documentation checks) once Verify and Review
are current.
