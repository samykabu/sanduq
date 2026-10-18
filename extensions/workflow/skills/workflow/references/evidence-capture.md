# Evidence capture

## Capturing prior document bytes

Before editing a document whose prior bytes the stage needs as evidence, run
`python .specify/extensions/workflow/scripts/execution_tools.py evidence-capture --path <file>
--out <feature>/evidence/<unique-name>.snapshot.json` (repeat `--path`; new output path each
time) and list the descriptor in both `evidence` and `evidence_snapshots`. Each input is limited
to 16777216 bytes. Recover bytes with `execution_tools.py evidence-resolve --snapshot
<descriptor> --path <file> --out <new-output-file>`. Keep the snapshot and its `.objects`
directory together; a missing or altered proof blocks reuse.

