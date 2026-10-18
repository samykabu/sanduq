# Receipt rules

Capturing prior document bytes: [evidence-capture.md](evidence-capture.md). Evidence-only
changes, drift and `STALE_RECEIPT`: [recovery.md](recovery.md).

## Recording the receipt

JSON: `stage`, `outcome: passed`, `summary`, `inputs` (every project-relative path relied on),
`evidence` (existing proof files) and the stage fields its reference names. Do not include
checkpoint files in input manifests. A generated report or checklist is not test execution;
keep command output and reviewer evidence. Failed, skipped or pending work cannot receive a
passed receipt. A pending or conflicted issue decision blocks a passed receipt. Reread the
issue decision ledger before completion and include it in the stage inputs.

`input_roles` (optional) maps an input to `{"role": "dependency"}` or `{"role": "consulted",
"because": "<one line>"}` (read for context only; when in doubt it is a dependency; evidence and
required artifacts always are). Without it every input is a dependency. A changed dependency
stales the receipt (`UPSTREAM_INPUT_CHANGED_DURING_STAGE` later); a changed consulted input is
`advisory_drift` to reread. `receipts.require_input_roles: true` requires a role for inputs
outside `specs/<feature>/` and `.specify/memory/`.

## Side effects

The claim's `side_effects` lists files this stage may change although earlier receipts depend on
them (Clarify: `spec.md`, `.specify/project-sync-state.json`, `checklists/*.md`); the lineage
records each change. Changing any other upstream input during the claim refuses the completion.
