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


Fresh managed clarification return (Scope 1.6.1): for the current initial Scope/Specify
claim, pass the exact dispatcher feature, token and session to both native guard and bind:
`scope.py gate <issue> --feature specs/<feature> --token <active-token> --session <active-session> --analysis <resolved-analysis.json>`;
then during Specify use the same flags with `scope.py bind <issue> --apply`.
This narrow path permits mapped Feature Specification after answered clarification, verifies
live applied decisions and the unchanged published v2 native leaf with retained parent
approval, and returns hashes without republishing unchanged scope or creating new approval.
Use the explicit active feature, never a historical `.specify/feature.json` pointer. A missing
or foreign claim, wrong branch/repository/issue, pending decision, stale scope, changed approved
score or native relationship fails closed. Other fresh statuses retain the Backlog gate.
Standalone invocation and existing revalidation keep their previous guards. This material
binding change requires focused independent review before installing the local candidate.


W01d binding restrictions: fresh native `bind` requires the owned initial **Specify**
claim before local or remote writes (including the CLI lock). Scope may run the read gate,
but cannot bind a placeholder spec. An unchanged published prompt remains authoritative;
local analysis is `consulted` and supplies no replacement scope authority. A revised prompt
requires the exact `--analysis` file, inside the current feature, among verified applied
Decision evidence with its current raw SHA256; parsed content must match the consumed analysis.
Use supported Decisions `apply` to record the reviewed resolved analysis alongside accepted
choices. Matching fingerprint/score or a returned analysis hash alone does not authorize it.
