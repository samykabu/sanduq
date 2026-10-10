---
description: "Validate the explicit GitHub issue and score before any Specify side effects."
---

# Scope prerequisite guard

Input: $ARGUMENTS

Extract one explicit GitHub issue number from this Specify invocation, such as
`#8`, `GitHub issue #8`, or a same-repository issue URL. Never infer it from other
numbers, the active feature, branch, a previous invocation, or a stale local cache.
If missing or ambiguous, STOP with `SCOPE_REQUIRED: provide a GitHub issue number
and run /speckit-scope <issue> first.` Do not create or edit a specification.

Run `python .specify/extensions/scope/scripts/scope.py gate <number>`.
Standalone work requires **Backlog** before branch creation or specification writes.
The explicit fresh managed clarification-return path below is the narrow exception;
a historical feature pointer or workflow policy alone does not authorize it.
Any nonzero exit is a hard stop for Specify and its remaining hooks. Surface the
error and prerequisite table without hiding it. On success retain the returned
issue number and fingerprint in this invocation, and use its returned enriched
prompt as the authoritative scoped input to Specify. Extra user requirements
outside that scope require running Scope again, not quietly expanding the spec.
This guard does not create a branch or a feature; ignore the core command's
generic assumption that every before_specify hook returns branch metadata.


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
