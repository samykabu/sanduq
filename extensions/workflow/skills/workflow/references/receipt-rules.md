# Receipt rules

Capturing prior document bytes: [evidence-capture.md](evidence-capture.md). Evidence-only
changes, drift and `STALE_RECEIPT`: [recovery.md](recovery.md).

## Recording the receipt

Start from the claim's `receipt_template` (the fields the runtime checks for this stage). Fill
`summary`, `inputs` (other paths relied on; the runtime adds required artifacts and the decision
ledger), `evidence` (existing proof files) and every `<...>` value. Every gating field
(`outcome`, `blocking_findings`, `unresolved`, `answers_applied`, `native_links_verified`,
`images_verified`, `effort_score`, `pr_url`) is a placeholder that you set from what the stage
actually produced; the template never pre-fills a passing value, and `complete` refuses a
placeholder left in place with `RECEIPT_PLACEHOLDER` naming the field. Do not include checkpoint
files in input manifests. A generated report or checklist is not test
execution; keep command output and reviewer evidence. Failed, skipped or pending work cannot
receive a passed receipt. A pending or conflicted issue decision blocks a passed receipt. Reread
the issue decision ledger before completion.

`input_roles` (optional) maps an input to `{"role": "dependency"}` or `{"role": "consulted",
"because": "<one line>"}` (read for context only; when in doubt it is a dependency; evidence and
required artifacts always are). Without it every input is a dependency. A changed dependency
stales the receipt (`UPSTREAM_INPUT_CHANGED_DURING_STAGE` later); a changed consulted input is
`advisory_drift` to reread. `receipts.require_input_roles: true` requires a role for inputs
outside `specs/<feature>/` and `.specify/memory/`.
Before Execute, a source file that Execute will change is never a dependency: leave it out of
`inputs` or give it the consulted role. The runtime records an input without a role as consulted
when the feature's tasks.md names it, on every host.

## Side effects

The claim's `side_effects` lists files this stage may change although earlier receipts depend on
them (Clarify: `spec.md`, the configured Project Sync state file, `checklists/*.md`); the
lineage records each change. Changing any other upstream input during the claim refuses the
completion. The state file counts as changed only when the bound feature's binding changes, never
for a status write ([dispatcher-operations.md](dispatcher-operations.md#project-sync-and-task-issue-sync)).
QA Document and Manual Update outputs (the receipt's `evidence` and the stage's side effects, such as
`qa/*.html` and `.github/memory/project-memory.md`) are not inputs of the earlier Verify and Review:
their source inventories take the new hashes (lineage `outputs_not_inputs`) instead of going stale.
