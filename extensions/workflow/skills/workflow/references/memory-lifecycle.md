# Local Memory handoff

The host dispatcher owns this handoff: it calls the installed Memory helper and dispatches
semantic work through registered Memory commands. Memory is optional and installed separately;
this integration never enables it, renews approval or changes `.specify/workflow.yml`. Returned
arguments constrain each dispatch: process only the exact returned `--spec` when present, then
return to this dispatcher before choosing another feature.

## Execute

Native `workflow.py complete` saves the accepted Execute receipt, then runs the Memory handoff
for Core Implement and SuperSpec Execute. Follow `memory_handoff.actions` in order. In a managed
project the prepare hook is disabled; this handoff queues, with the policy's `default_checks`. An
existing queue entry is kept byte for byte. Missing or disabled Memory stays honestly pending. Missing check
selection returns `speckit.memory.prepare`: inspect the implementation, choose existing
configured checks, and retry:

```text
python .specify/extensions/workflow/scripts/workflow.py memory-handoff --transition execute --feature specs/412-refund-approval --check product
```

Repeat `--check` per check; never invent check names or substitute tooling checks. Existing
entries are never reset. A Memory failure returns `ok: false` and a state file under
`.specify/workflow/runtime/memory-handoffs/`; honor both exit and JSON. The product receipt
stays passed; never claim queueing or archival succeeded. Repair the reported condition and
retry this command without redoing Execute.

## Session entry

In a managed project the session hook is disabled. Each claim at Scope or Specify, and the
first claim of a new session, runs this handoff and returns it instead of a stage when it blocks
or has work to dispatch (`status: memory_blocked` or `memory_dispatch`). Run it yourself only
outside a claim:

```text
python .specify/extensions/workflow/scripts/workflow.py memory-handoff --transition session
```

Pass `--feature <exact-directory>` to limit it to one feature. An active transaction takes
precedence even when automatic mode is disabled: dispatch the returned `speckit.memory.session
--run <id>`, inspect its status and journal, and resume the registered recovery workflow. Never
finalize, abandon, roll back or remove a writer lock automatically. A busy writer or missing
number guard blocks new specification and commit work. `needs_verification` dispatches
`speckit.memory.session --spec <exact-directory>`; a ready entry returns `speckit.memory.run`
with exact `--spec`, `--automatic` and `--check` arguments. Invoke it in this host, one feature
at a time, then refresh the handoff. If its registration cannot be invoked, record that blocker
and stop. A returned action proves none of the run's verification, synthesis, review, deletion
or commits happened. Explicitly authorized manual Memory runs stay separate; never add
retirement, `--all-completed` or a verification override.

## Verified post-merge follow-up

After the verification in `stage-pr.md`, save a JSON binding beside the post-merge report,
filled from the actual bound PR and local evidence:

```json
{"feature":"specs/412-refund-approval","repository":"owner/booking-app",
 "pr_url":"https://github.com/owner/booking-app/pull/413",
 "target_branch":"develop","head_sha":"<exact final PR head SHA>",
 "merge_sha":"<exact merge SHA>","verified":true,"report_only":false}
```

`verified` records the host's completed external verification; the helper does not contact
GitHub. Then run in the approved local checkout:

```text
python .specify/extensions/workflow/scripts/workflow.py memory-handoff --transition postmerge --feature specs/412-refund-approval --report <binding.json>
```

It checks feature, checkpoint repository, original PR receipt URL, target, current branch and
local merge ancestry; a mismatch stays pending with its reason. It keeps historical receipts and
`pr_open`. A report-only follow-up PR sets `report_only: true` and stops after its report; its
different URL cannot satisfy the original feature's PR receipt.
