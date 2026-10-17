# Local Memory handoff

The existing host dispatcher owns this handoff. It calls the installed Memory
helper and dispatches semantic work through registered Memory commands. Memory
remains an optional, separately installed extension; this integration never
enables it, renews approval or changes `.specify/workflow.yml`.
Returned arguments constrain each dispatch. Older Memory session instructions may
inspect the whole queue; process only the exact returned `--spec` when present,
then return to this host dispatcher before choosing any other feature.

## Execute

Native `workflow.py complete` saves the accepted Execute receipt, then invokes
the same Memory handoff for Core Implement and SuperSpec Execute. Read its
`memory_handoff` result and follow `actions` in order. An upstream Core hook may
already have queued the feature; the adapter preserves that entry byte for byte.
Do not invoke the prepare hook again after native completion.

Missing/disabled Memory remains honestly pending. Missing check selection returns
`speckit.memory.prepare` so the dispatcher can inspect implementation and choose
existing configured checks. Use its selection to retry through the native adapter:

```text
python .specify/extensions/workflow/scripts/workflow.py memory-handoff --transition execute --feature specs/412-refund-approval --check product
```

Repeat `--check` for each relevant configured check. Memory validates coverage;
the adapter never substitutes tooling checks or invents check names. Existing
entries are never reset, including after review fixes or renewed approval. Report
the installed helper's stale-input/approval reason and use the registered Memory
recovery/manual workflow only within existing authorization.

A Memory failure returns `ok: false` and a durable state file beneath
`.specify/workflow/runtime/memory-handoffs/`. Honor both process exit and JSON
result. The accepted product receipt remains passed; do not claim that queueing
or archival succeeded. Repair the reported Memory condition and retry this command
without redoing Execute or copying receipt fingerprints.

## Session entry

At local dispatcher entry, before creating a feature or claiming a stage, run:

```text
python .specify/extensions/workflow/scripts/workflow.py memory-handoff --transition session
```

Pass `--feature <exact-directory>` to constrain processing to one known feature.
This uses explicit queue entries, never the editor tab or all legacy folders.
An active transaction takes precedence even when automatic mode is disabled:
dispatch the returned `speckit.memory.session --run <id>`, inspect its reported
status/journal and resume the registered recovery workflow. Never automatically
finalize, abandon, roll back or remove a writer lock. A busy writer or missing
number guards blocks new specification/commit work as Memory's own gate requires.

On the approved checkout and configured local target, unfinished/unmerged/stale
work remains pending with the installed helper's reason. `needs_verification`
dispatches `speckit.memory.session --spec <exact-directory>`: inspect actual
completion and execute the approved checks through Memory. Refresh the native
handoff afterwards. A ready entry returns `speckit.memory.run` with exact
`--spec`, `--automatic` and configured `--check` arguments. Invoke that registered
skill in this host, one feature at a time, then refresh the native handoff.
If its registration cannot be invoked, record that concrete blocker and stop.

The registered run still performs verification, checkpointing, semantic synthesis,
independent review, exact fixture migration, exact folder deletion and its two
scoped commits. Returning an action proves none of that work ran. Preserve its
actual failures, pending reviews and recovery state. Explicitly authorized manual
Memory runs remain separate; do not convert them into automatic approval or add
retirement, `--all-completed` or a verification override.

## Verified post-merge follow-up

After the verification protocol in `stage-pr.md`, save a JSON binding alongside
the post-merge report. Populate these fields from the actual bound PR and local
target evidence, never guessed values:

```json
{"feature":"specs/412-refund-approval","repository":"owner/booking-app",
 "pr_url":"https://github.com/owner/booking-app/pull/413",
 "target_branch":"develop","head_sha":"<exact final PR head SHA>",
 "merge_sha":"<exact merge SHA>","verified":true,"report_only":false}
```

`verified` records the host's completed external verification, like a stage
receipt; the helper does not contact GitHub or certify remote checks. Keep the
supporting URLs, check outcomes and report. Run in the approved local checkout:

```text
python .specify/extensions/workflow/scripts/workflow.py memory-handoff --transition postmerge --feature specs/412-refund-approval --report <binding.json>
```

The adapter checks the explicit feature, checkpoint repository, original PR
receipt URL, configured/checkpoint target, current branch and local merge
ancestry. A mismatch remains pending/blocked with its exact reason. It preserves
historical receipts and `pr_open`; this is a follow-up operation, never a new
destructive lifecycle stage or a second coordinator.

A report-only follow-up PR must set `report_only: true` and stop after its report.
Do not select the original feature for another archive or refresh dependency
reports again. A report-only PR with a different URL also cannot satisfy the
original feature's bound PR receipt. Keep any authorized manual Memory run separate.
