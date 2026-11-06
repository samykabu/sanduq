# Evidence capture

## Reusing a canonical fact source

Capture the reviewed scenario/result index and its credential-free proof files once for each
validated result set, using `evidence-capture` below. Reuse that immutable descriptor in the
`evidence` and `evidence_snapshots` of stages relying on those facts. QA documentation, the PR
explainer, progress notes and manuals link the same descriptor and relevant proof paths instead
of copying complete inventories or raw logs. Summaries state outcomes and limits; failed, skipped,
pending and not-run results stay distinct. A changed result set gets a new descriptor.

Keep each stage's required receipt fields, input roles, source freshness and provider checks.
A snapshot proves captured bytes, not that tests passed or a human accepted the result. Retain
the original proofs and their integrity checks. Use the selected manual impact result and module
map to choose documentation scope; unmatched inputs need explicit handling. Preserve required
coverage, redaction, screenshots and reference fidelity. Reuse never waives selected QA/manual
work or authorizes publishing. Progress remains a deterministic projection of existing records;
record only missing facts with its normal verbs.

## Capturing prior document bytes

Before editing a document whose prior bytes the stage needs as evidence, run
`python .specify/extensions/workflow/scripts/execution_tools.py evidence-capture --path <file>
--out <feature>/evidence/<unique-name>.snapshot.json` (repeat `--path`; new output path each
time) and list the descriptor in both `evidence` and `evidence_snapshots`. Each input is limited
to 16777216 bytes. Recover bytes with `execution_tools.py evidence-resolve --snapshot
<descriptor> --path <file> --out <new-output-file>`. Keep the snapshot and its `.objects`
directory together; a missing or altered proof blocks reuse.

