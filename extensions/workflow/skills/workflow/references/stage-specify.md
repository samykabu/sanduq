# Stage reference: specify

Loaded when `claim` returns `stage: specify`.

## Required work and evidence

Bind the actual feature path and source issue; retain the scope guard. Resolve any
reserved/actual feature-path mismatch before continuing.

## Managed overlay (`speckit.specify`)

Pass the active run's exact feature path as SPECIFY_FEATURE_DIRECTORY. Do not
allocate a second feature. For a new issue-bound run, pass the branch from
`workflow.py prepare --issue <number>` as `GIT_BRANCH_NAME` to an enabled Git
before_specify hook; when that hook is absent, `prepare` has already created the
branch. Pass the exact issue-derived feature directory separately. Keep both
values as argv or environment data; never interpolate an issue title into a shell
command. A standalone non-issue Specify invocation follows upstream naming and
does not enter the issue-bound dispatcher. Preserve pending ambiguities in spec.md and route them
through the next Clarify stage, without invoking the upstream chat question loop.
For a `mode: revalidate` claim with an existing bound specification, review that
specification in place. Skip new-feature/branch creation and template overwrites;
preserve its plan, tasks and implementation. Run the Scope guard and binding checks
against the same issue. A matching managed claim permits an existing open feature
to retain its board position while being rechecked; it does not waive fresh scope.
After core Specify and Scope Bind, run `workflow.py bind --feature <path> --token
<active-token>` to accept the new branch only after scope-source.json matches the
same repository and issue. Then record the Specify receipt and return.
