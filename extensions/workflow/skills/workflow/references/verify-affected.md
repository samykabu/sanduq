# verify-affected

Not a claimed stage; a utility entry point (B13) that runs the feature's affected
lanes locally instead of a full merge-tier run, matching the constitution's rule
that local Verify covers the lanes the PR tier would leave uncovered (F7, F9).

Run:

```text
python .specify/extensions/workflow/scripts/verify_affected.py --root <repo> \
  --feature specs/<feature> --base-ref origin/<target> [--lane NAME ...] [--results <path>]
```

It diffs `--base-ref` against `HEAD`, classifies the diffed paths through the
project's `ci.gate.affected_command` hook (the same classify contract Verify,
Review and Ready already trust), and unions the result with any `--lane`
names the feature always requires. When nothing is affected it reports
`no_affected_lanes` and runs nothing, mirroring the gate's own lane-free-drift
rule. Otherwise it runs the project's `ci.gate.verify_command` (optional,
project-local; distinct from `affected_command`, which only classifies) with
`{"lanes": [...], "results_path": "<path>"}` on stdin, in the repository root,
and reads back the results.json it must write -- the same shape the project's
CI tier produces, so a summarizer or the gate reads one format either way.

Both `ci.gate.affected_command` and `ci.gate.verify_command` are project
settings read from `.specify/workflow.yml`; neither is invented by this
script, and a project that has not configured `verify_command` gets a clear
`VERIFY_COMMAND_UNSET` instead of a silent no-op. Record the result under the
feature's Verify evidence (`--results` defaults to
`specs/<feature>/workflow/verify-affected-results.json`) before recording the
Verify receipt; this entry point never writes the receipt itself.
