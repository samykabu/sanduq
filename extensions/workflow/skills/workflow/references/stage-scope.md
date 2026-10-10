# Stage reference: scope

Loaded when `claim` returns `stage: scope`.

## Entry point

**scope**: require an explicit issue. Inspect its scope prerequisites and project policy;
never choose a feature from an editor tab. For a new issue-bound feature, run
`workflow.py prepare --issue <number>` and use its exact `feature` and `branch`
derived from the issue number and current title. If the Git extension owns
`before_specify`, pass its branch as `GIT_BRANCH_NAME` to that hook; otherwise
`prepare` creates the branch with Git argument arrays. For an existing bound feature,
reuse its saved feature path and branch even if the issue title has changed.
Resolve or reserve the matching feature identity,
then `start --feature specs/<feature> --issue owner/repo#number`. Pass this exact
path into Specify as SPECIFY_FEATURE_DIRECTORY. Run the stage loop in the core skill.

## Required work and evidence

Issue identity, prerequisite snapshot, project preferences, managed issue/labels and
complete spec-prompt. Policy-settled keep-together decisions skip decomposition
questions. Return actual publication evidence.


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
