# Stage reference: ready

Runtime stage `workflow:gates`. Before this pass, read the publication preflight in
`references/stage-pr.md#publication-preflight-and-post-merge-verification` and prepare portable
evidence there: it must run before the last Verify/Review/Ready pass.

## Required work and evidence

Verify task completion by category, issue mapping (every task mapped, also under
`phase-lazy`), review and tests, and the selected documentation. Receipt: `blocking_findings:
0`. Document-generation tasks are complete only once their outputs exist. In lean mode the
coordinator runs Ready without a delegated model. Only the final coding review is admitted on
implementation and testing alone; Ready and CI require every required task, including review,
docs and artifact-analysis tasks, checked with a verified delegated outcome.

Once Verify and Review are current, `revalidate --stage ready` re-runs the task, mapping and
documentation checks ([recovery.md](recovery.md)).
