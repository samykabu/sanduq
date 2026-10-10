---
description: "Bind the specification to its validated source GitHub issue."
---

# Bind source issue

Use the explicit issue number successfully checked by the guard in this same
Specify invocation. If absent, STOP; never infer it from global pending state.
Run `python .specify/extensions/scope/scripts/scope.py bind <number> --apply`.
This must succeed before the existing `after_specify` Project sync hook runs.
It writes `scope-source.json` beside the spec and initializes that feature's
Project sync state with the original issue ID and Project item, preserving task
sub-issues. It must not create a second feature issue. It must then set the live
Project Status and local sync state to **Feature Specification**. A status write
failure is a hard failure, not a successful Specify completion.


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
