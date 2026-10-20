# Receipt rules

Capturing prior document bytes: [evidence-capture.md](evidence-capture.md). Evidence-only
changes, drift and `STALE_RECEIPT`: [recovery.md](recovery.md).

## Recording the receipt

Start from the claim's `receipt_template` (the fields the runtime checks for this stage). Fill
`summary`, `inputs` (other paths relied on; the runtime adds required artifacts and the decision
ledger), `evidence` (existing proof files) and every `<...>` value. Do not include checkpoint
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

## Side effects

The claim's `side_effects` lists files this stage may change although earlier receipts depend on
them (Clarify: `spec.md`, the configured Project Sync state file, `checklists/*.md`); the
lineage records each change. Changing any other upstream input during the claim refuses the
completion. The state file counts as changed only when the bound feature's binding changes, never
for a status write ([dispatcher-operations.md](dispatcher-operations.md#project-sync-and-task-issue-sync)).
