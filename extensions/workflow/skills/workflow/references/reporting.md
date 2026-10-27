# Reporting

The one place that decides how the progress report is maintained. Other references link here; they do not repeat it.

**Never spawn, retain, message or poll an additional agent solely for reporting.** This is the Progress skill's rule
(`.specify/extensions/progress/skills/progress/SKILL.md`), in every mode. The current coordinator (the dispatcher, or the
orchestration agent only when it already does real scheduling and integration work) makes the few calls below as part of
its own turn. Opening the report once for the human is fine; re-opening, re-verifying or watching it refresh is not.
Waiting for a worker stays: block on `delegate_dispatch.py collect` with a bounded loop.

The Execute claim prints `reporting` (`mode`, `reason`) and carries this file for `projection` and `refresh`, or the
legacy reporter for `legacy`. Outside a claim the same decision is:

```text
python .specify/extensions/workflow/scripts/progress_bridge.py mode
```

The host is detected from the environment and an unknown host selects `refresh`; pass `--host codex` on Codex. It prints `reporting: projection`, `reporting: refresh` or `reporting: legacy`. On Codex, registered Progress hooks that the
user has not approved print `reporting: refresh (codex hooks not approved)` (`--json` has a `reason` field): Codex skips
untrusted projects and unapproved hooks. Ask the user to trust the project and approve the Progress hooks as the
[Workflow README](../../../README.md#progress-reporting) describes. In the commands below `progress` stands for
`python .specify/extensions/progress/scripts/progress.py`; every verb prints at most one line (`refresh` prints
nothing unless given `--verbose`).

| Mode | When | Coordinator does |
| --- | --- | --- |
| `projection` | Progress is installed and enabled, and its hooks are registered and enabled for the active host | `progress init` once (idempotent). Then only record facts nothing else records: `progress lane L1 --tasks T001-T004 --owner <worker-id> --harness H --model M --effort E --workstream` once per Execute workstream (task group), never per run (`M` is the requested model; the reported one comes from the worker's `Model:` line into the handoff and receipt) (leave `--workstream` out for a Progress older than 1.2.0); a new worker for it updates that lane's owner. Lifecycle stage runs (scope, specify, clarify...) are recorded by the delegation ledger: no `progress lane` for them. `progress block T007 --by L2` / `progress unblock B4`, `progress note "text" --target T007` (one line, only for facts no producer records). Decisions come from the Workflow ledger. At Finalize run `progress refresh --final` once. |
| `refresh` | Progress is installed and enabled, but the active host does not collect automatically (or the host is unknown) | The `projection` calls, plus `progress refresh` after each collected attempt and phase commit. |
| `legacy` | Progress is absent or disabled | The legacy calls in [`execute/reporting-legacy.md`](execute/reporting-legacy.md#legacy-reporter-calls-mode-legacy-only): init, task, usage, sync, phase and pr, exactly as before. |

On a Codex worktree whose hooks are not approved (`codex hooks not approved`), the coordinator also runs `progress bind --host codex --model <m> --effort <e>` once per session. It is a labelled self-report, never host-observed telemetry, and needs Progress 1.2.0 or later. From 1.2.0 a workstream lane fact carries `semantics: "workstream"` (`progress lane <id> ... --workstream`).

In `projection` and `refresh` mode task state comes from `tasks.md`, retries and attempts from the delegation ledger, and
model, effort, context and run usage from host hooks and delegate results. Do not call task, usage, sync, phase or pr
reporters for them. Check task boxes in `tasks.md` as usual. The report opens at `specs/<feature>/progress/.view/index.html`.
Budget overruns and PR state are notes: `progress note "Budget overrun T###: <class> <figure>/<budget>: <reason>" --target
T###`, `progress note "PR open: <pr-url>"`, `"CI failure: <check>; fix assigned to <worker-id>"` and `"PR merged: <pr-url>"`.

A legacy `workflow/scripts/progress.py` call made while Progress is installed and enabled writes nothing, exits 2 and
names the Progress command to use instead; do not retry it.
Do not pass secrets, absolute paths or transcript text to any reporting call. Lean mode follows the same table.
