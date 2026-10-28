# Invoking the claimed command: delegation and decisions

Stage loop step 4: invoke the claimed command and pause for a material decision. A claim that
carries a `delegation` route or an `environment` (lean execution) also follows
[delegation.md](delegation.md) and its [routing rule](delegation.md#routing-rule); read it then.

## Invoking

Invoke the selected command in this host through its installed skill or command registration.
Read its current instruction source rather than guessing from a name. Native semantic commands
may pause for real decisions; the managed preset prevents duplicate chaining. With `mode:
revalidate`, keep the bound issue, feature path and branch, and update existing artifacts in
place: no new spec directory, no overwritten task history, no forced move back to Backlog.
Scope still checks approval, labels, prerequisites and requirement fingerprints; a claim never
bypasses stale scope or unresolved human questions.

## Decisions

For a material choice in any stage, run `scripts/decisions.py --feature specs/<bound-feature>
ask --question ... --option ... --option ...` to post a stable question on the bound issue as an
unticked task list (`--mode multiple` when several may apply, `--recommended B` to mark, never
tick, a suggestion). With `clarification_transport: github-comments` on the claim, never ask
for the answer in the IDE: pause the claim with the question URL and token. With `local`, `ask`
writes the question to `specs/<f>/clarifications.md` instead of the issue: ask the user in this
conversation, record only their own reply there (`SDn: B`), and nothing goes to GitHub. On
return run `decisions.py ... sync --project-field` (the ledger only, with `local`), inspect
authorized answers, conflicts and `unparsed` (replies that name a question but were not
understood, with their URL or line: tell the user), apply the result to the artifacts, and
record it with `decisions.py ... apply --id SDn --evidence <path>`. Never tick a box for the
reviewer or infer an answer from the Project field, a recommendation or prose. Edited answers
reopen the decision. Reuse question IDs on retries. `decisions.py ... upgrade-questions` makes
earlier-release questions selectable.

Only a paused pre-Specify checkpoint may read on a changed branch; bound or active work uses the
checkpoint branch. Active decision commands need `SANDUQ_WORKFLOW_CLAIM_TOKEN` and
`SANDUQ_WORKFLOW_SESSION_ID` from the current claim. Pending decisions park the issue in mapped
Backlog or Feature Specification; answers return an owned park to Feature Specification and
advanced states stay protected. Decision and Status writes are reread, and a durable pre-write
intent recovers lost-response retries.
