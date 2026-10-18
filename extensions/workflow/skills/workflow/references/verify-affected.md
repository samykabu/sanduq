# verify-affected

A utility entry point, not a claimed stage: run the feature's affected lanes locally instead of a
full merge-tier run.

```text
python .specify/extensions/workflow/scripts/verify_affected.py --root <repo> \
  --feature specs/<feature> --base-ref origin/<target> [--lane NAME ...] [--results <path>]
```

It diffs `--base-ref` against the working tree (committed, staged, unstaged and untracked
changes), classifies paths through `ci.gate.affected_command`, adds any `--lane` names, and runs
`ci.gate.verify_command` with `{"lanes": [...], "results_path": "<path>"}` on stdin, reading
back its results.json. Nothing affected reports `no_affected_lanes` and runs nothing. An unset
`verify_command` reports `VERIFY_COMMAND_UNSET`. `--results` (default
`specs/<feature>/workflow/verify-affected-results.json`) must stay inside the repository.

This is not CI evidence: output is stamped `"source": "local"` and `"ci_grade": false`. Never
record it as a Verify receipt's `ci_evidence`, which only `workflow.py revalidate --stage verify
--check-run <run id>` writes from an actual CI run. Record it in the feature's local
verification notes before the Verify receipt.
