# Scope gate and bind inside a managed claim

The one copy of the managed binding rules for `scope.py gate` and `scope.py bind`. The Scope
guard and bind commands, the Scope-gate Specify overlay and the scope and specify stage
references point here.

## Printing the command

Take the command from the claim you hold, not from memory. For the initial claim print it with
`python .specify/extensions/workflow/scripts/execution_tools.py scope-command --mode initial
--command gate|bind --issue <number> --feature specs/<feature> --token <active-token> --session
<active-session> --analysis <resolved-analysis.json>`; all four values are required and Scope
refuses a partial set. To revalidate an existing claim use `--mode revalidate` with the issue
alone: Scope finds that claim from the selected feature and its checkpoint, and any feature,
token or session flag would push it onto the fresh path, so the helper rejects them. Bind forms
append `--apply`. The helper exits 2 on a missing or non-numeric issue. Run the printed command
unchanged: gate and bind reuse the analyst's `.specify/scope/issue-<number>-snapshot.json` by
themselves while it is current (`snapshot_reused` in the output).

## Fresh managed clarification return

For the current initial Scope or Specify claim, pass the exact dispatcher feature, token and
session to both gate and bind: `scope.py gate <issue> --feature specs/<feature> --token
<active-token> --session <active-session> --analysis <resolved-analysis.json>`, then during
Specify the same flags with `scope.py bind <issue> --apply`. This narrow path permits mapped
Feature Specification after answered clarification, verifies live applied decisions and the
unchanged published native leaf with its retained parent approval (none for a root issue kept
whole), and returns hashes without
republishing unchanged scope or creating a new approval. Use the explicit active feature, never
a historical `.specify/feature.json` pointer. A missing or foreign claim, wrong
branch/repository/issue, pending decision, stale scope, changed approved score or changed native
relationship fails closed. Other fresh statuses keep the Backlog gate; standalone invocation
and revalidation keep their guards.

Keep the initial gate output in the Scope receipt's evidence, using `--output
specs/<feature>/evidence/scope/gate.json`. Fresh managed gate and bind retain the original
approval, parent, exact native sibling list (`parent_children`) and prerequisites (`dependencies`).
Finish the published dependency plan's actual acceptance before this gate; a pending plan
still blocks admission.

## Binding restrictions

Fresh native `bind` requires the owned initial Specify claim before any local or remote write,
including the CLI lock. Scope may run the read gate but cannot bind a placeholder spec. An
unchanged published prompt stays authoritative; local analysis is `consulted` and supplies no
replacement scope authority. A revised prompt needs the exact `--analysis` file inside the
current feature, among verified applied Decision evidence with its current raw SHA256, and its
parsed content must match the consumed analysis. Record the reviewed resolved analysis with
Decisions `apply` alongside the accepted choices. A matching fingerprint, score or returned
analysis hash alone does not authorize it.
