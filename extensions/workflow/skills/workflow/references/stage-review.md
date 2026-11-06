# Stage reference: review

Runtime stage `workflow:review`. Before the last Verify, Review or Ready pass, read the
publication preflight in `references/stage-pr.md#publication-preflight-and-post-merge-verification`
and prepare portable evidence there.

## Required work and evidence

Review against the spec and constitution and fix blocking findings. Receipt: actual review and
test evidence and `blocking_findings: 0`; a checklist alone is not an executed test. In lean
mode, claim, completion, revalidation and review-worker admission wait until every
implementation and authored or collected test task is complete with successful, trusted
delegation evidence where selected. Review and documentation tasks are excluded from that test.
Artifact analysis (`analyze` or `[artifact-analysis]` tasks) may run before coding and is not
the final coding review, which stays independent after all coding and testing batches.

After source drift, the diff-reviewed `revalidate --stage review --diff-reviewed <file>` and the
other recipes are in [recovery.md](recovery.md). For SuperSpec Review under `required-only`
checkpoints, also follow [superspec-checkpoints.md](superspec-checkpoints.md).
