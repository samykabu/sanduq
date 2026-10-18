# Stage reference: verify

Runtime stage `workflow:verification`. Before the last Verify, Review or Ready pass, read the
publication preflight in `references/stage-pr.md#publication-preflight-and-post-merge-verification`
and prepare portable evidence there.

## Required work and evidence

Run the relevant real tests and checks. Receipt: actual test evidence and `blocking_findings:
0`; a command instruction or checklist alone is not an executed test. If lean policy selects a
`verification_plan`, run the exact relevant checks and record passing local evidence as
[verification-plan.md](verification-plan.md) says; completion captures a runtime snapshot, and
only unchanged passing checks are reused. Local records stay local evidence; the selected CI
checks and real local acceptance remain required. An exact fixed collection command belongs to
the coordinator and needs no model dispatch.

After source drift, `revalidate --stage verify --check-run <run id>` and the other recipes are
in [recovery.md](recovery.md).
