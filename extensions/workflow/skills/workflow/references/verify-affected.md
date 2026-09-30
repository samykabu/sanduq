# verify-affected

Not a claimed stage; a utility entry point (B13) that runs the feature's affected
lanes locally instead of a full merge-tier run, matching the constitution's rule
that local Verify covers the lanes the PR tier would leave uncovered (F7, F9).

Run:

```text
python .specify/extensions/workflow/scripts/verify_affected.py --root <repo> \
  --feature specs/<feature> --base-ref origin/<target> [--lane NAME ...] [--results <path>]
```

It diffs `--base-ref` against the actual working tree (every committed change
since the merge-base, plus staged, unstaged and untracked files -- never only
`base_ref..HEAD`, which would give a false green for an uncommitted edit),
classifies the diffed paths through the project's `ci.gate.affected_command`
hook (the same classify contract Verify, Review and Ready already trust),
and unions the result with any `--lane` names the feature always requires.
When nothing is affected it reports `no_affected_lanes` and runs nothing,
mirroring the gate's own lane-free-drift rule. Otherwise it runs the
project's `ci.gate.verify_command` (optional, project-local; distinct from
`affected_command`, which only classifies) with `{"lanes": [...],
"results_path": "<path>"}` on stdin, in the repository root, and reads back
the results.json it must write -- the same shape the project's CI tier
produces, so a summarizer or the gate reads one format either way. A timeout
kills the whole process tree, and each output stream is capped before it is
ever put in an error message.

**This is not CI evidence.** Both the returned summary and the results.json
file are stamped `"source": "local"` and `"ci_grade": false`. It is useful
evidence for a developer to act on before pushing, but it must never be
recorded as a Verify receipt's `ci_evidence`: that field is written only by
`workflow.py revalidate --stage verify --check-run <run id>`, which re-reads
an actual CI run through the GitHub REST API. Do not substitute this run's
output for that command.

Both `ci.gate.affected_command` and `ci.gate.verify_command` are project
settings read from `.specify/workflow.yml`; neither is invented by this
script, and a project that has not configured `verify_command` gets a clear
`VERIFY_COMMAND_UNSET` instead of a silent no-op. `--results` (default
`specs/<feature>/workflow/verify-affected-results.json`) must stay inside the
repository. Record the result under the feature's own local-verification
notes before recording the Verify receipt; this entry point never writes the
receipt itself and never stands in for a real CI run.
