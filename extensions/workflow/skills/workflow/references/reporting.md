# Reporting

The one place that decides how the progress report is maintained. Other references link here; they do not repeat it.

**Never spawn, retain, message or poll an additional agent solely for reporting.** This holds in every mode. The current
coordinator (the dispatcher, or the orchestration agent only when it already does real scheduling and integration work)
makes the few calls below as part of its own turn. Opening the report once for the human is fine. Re-opening it,
re-verifying it or waiting to see it refresh is not. Waiting for a worker to finish is a different thing and stays: block
on `delegate_dispatch.py collect` with a bounded loop.

Pick the mode once per Execute claim or resume:

```text
python .specify/extensions/workflow/scripts/progress_bridge.py mode
```

The host is detected from the environment and an unknown host selects `refresh`. A Codex coordinator passes
`--host codex`.

It prints `reporting: projection`, `reporting: refresh` or `reporting: legacy`. In the commands below `progress` stands
for `python .specify/extensions/progress/scripts/progress.py`; every verb prints one line.

| Mode | When | Coordinator does |
| --- | --- | --- |
| `projection` | Progress is installed and enabled, and its hooks are registered and enabled for the active host | `progress init` once (idempotent). Then only record facts nothing else records: `progress lane L1 --tasks T001-T004 --owner <worker-id> --harness H --model M --effort E` when assigning, `progress block T007 --by L2` / `progress unblock B4`, `progress note "text" --target T007`. Decisions come from the Workflow ledger. At Finalize run `progress refresh --final` once. |
| `refresh` | Progress is installed and enabled, but the active host does not collect automatically (or the host is unknown) | The `projection` calls, plus `progress refresh` after each collected attempt and phase commit. |
| `legacy` | Progress is absent or disabled | The legacy calls in [`execution-report.md`](execution-report.md#legacy-reporter-calls-mode-legacy-only): init, task, usage, sync, phase and pr, exactly as before. |

In `projection` and `refresh` mode task state comes from `tasks.md`, retries and attempts from the delegation ledger, and
model, effort, context and run usage from host hooks and delegate results. Do not call task, usage, sync, phase or pr
reporters for them. Check task boxes in `tasks.md` as usual. A budget overrun is a `progress note`.

If a legacy `progress.py` call is made while Progress is installed it is forwarded to the Progress CLI. An unsupported
request prints a compatibility error and exits non-zero; do not retry it, use the verb named above instead.
Do not pass secrets, absolute paths or transcript text to any reporting call. Lean mode follows the same table.
