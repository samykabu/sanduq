# Stage reference: specify

## Required work and evidence

Bind the actual feature path and source issue and keep the Scope guard. Resolve any reserved
versus actual feature-path mismatch first. Gate and bind flags inside this claim:
[scope-binding.md](scope-binding.md).

## Bind-only mode

When the claim returns `mode: bind-only`, spec.md was rendered from the approved Scope
analysis: do not run Specify. Run Scope bind for the issue (the claim's `scope_command` in
lean mode; flags in scope-binding.md), then `workflow.py bind --feature <path> --token
<active-token>`, and record the receipt with spec.md (its render marker hash) in `inputs`.

## Managed overlay (`speckit.specify`)

Pass the run's exact feature path as `SPECIFY_FEATURE_DIRECTORY`; never allocate a second
feature. For a new issue-bound run, pass the branch from `workflow.py prepare --issue <number>`
as `GIT_BRANCH_NAME` to an enabled Git before_specify hook (without that hook `prepare` already
created the branch). Keep both values as argv or environment data; never interpolate an issue
title into a shell command. A standalone non-issue Specify follows upstream naming outside the
dispatcher. Keep pending ambiguities in spec.md as `[NEEDS CLARIFICATION: ...]` for the
Clarify stage; do not run the upstream chat question loop.

For a `mode: revalidate` claim, review the bound specification in place: no new feature, branch
or template overwrite, and keep plan, tasks and implementation. Run the Scope guard and binding
checks against the same issue; a matching managed claim lets an open feature keep its board
position while rechecked, without waiving fresh scope.

After Specify and Scope bind, run `workflow.py bind --feature <path> --token <active-token>`,
which accepts the branch only when scope-source.json names the same repository and issue. Then
record the Specify receipt and return.
