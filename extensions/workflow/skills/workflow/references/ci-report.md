# ci-report

A read-only utility entry point, not a claimed stage: turns the last N runs of a CI workflow
into a leg, lane and wall-clock table.

```text
python .specify/extensions/workflow/scripts/ci_report.py \
  --repository <owner>/<repo> --workflow <workflow file or id> \
  [--limit 10] [--branch <name>] [--fixed-job NAME ...] [--json]
```

It reads through `gh api` with pagination and reports, per run, conclusion, cancellation, the
wall-clock span (earliest job start to latest job end, not a critical path) and each job's
duration. `--fixed-job` marks a job's time as fixed overhead; without it everything counts as
test time. Use it before proposing a lane or runner change and to count cancelled runs. It
writes no checkpoint state and produces no receipt.
