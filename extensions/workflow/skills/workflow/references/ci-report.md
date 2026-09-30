# ci-report

Not a claimed stage; a read-only reporting entry point (B13, retrospective D1)
that turns the last N runs of a CI workflow into a leg/lane/critical-path
table instead of a worker reading raw run and job JSON by hand.

Run:

```text
python .specify/extensions/workflow/scripts/ci_report.py \
  --repository <owner>/<repo> --workflow <workflow file or id> \
  [--limit 10] [--branch <name>] [--fixed-job NAME ...] [--json]
```

Reads only through the GitHub REST API (`gh api`, the same client Verify
evidence already uses), so it needs no separate credential. For each of the
last `--limit` runs it reports conclusion, cancellation, the critical path
(earliest job start to latest job completion) and, per job (leg), its
duration. `--fixed-job NAME` (repeatable) marks a job's time as fixed
overhead; every other job's time counts as test time. Without any
`--fixed-job`, everything counts as test time and fixed is reported as zero:
an honest default, since Sanduq has no generic way to tell a project's setup
job from its test job. Use this before proposing a lane or runner change, to
see whether the actual bottleneck is fixed overhead or test time, and to
count cancelled runs (F9's host-load flakes) rather than guessing at them.

This entry point never writes checkpoint state; it is safe to run at any time
and produces no receipt.
