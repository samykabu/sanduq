# Execute: legacy reporter

This part applies when the claim's `reporting` is `legacy`: Progress is absent or disabled
([reporting.md](../reporting.md) decides the mode).

## Legacy reporter calls (mode legacy only)

The calls below are unchanged from earlier releases. When Progress is installed and enabled each
of them exits 2 without writing and names the Progress command to use instead.

The current coordinator creates the report before assigning the first task:

```text
python .specify/extensions/workflow/scripts/progress.py init --tasks specs/<feature>/tasks.md --output specs/<feature>/workflow/progress --summary
```

The report opens at `specs/<feature>/workflow/progress/index.html`. The report is titled from the plan's `# Tasks: <feature>` heading. Pass
`--title "<feature title>"` to name it explicitly; rerunning `init` with a new
title renames an existing report without losing its evidence. The report shows
the Sanduq logo and page icon, a Phase column, token usage, Status and Phase
filters and a separate Activity tab; filters and the chosen tab survive the
automatic refresh.

The current coordinator is the sole writer. Update the report on assignment,
completion, failure, recovery and each lifecycle transition. Use actual task IDs:

```text
python .specify/extensions/workflow/scripts/progress.py task --output specs/<feature>/workflow/progress --id T001 --status running --agent <worker-id> --note "Own src/example.py; depends on T000" --summary
python .specify/extensions/workflow/scripts/progress.py task --output specs/<feature>/workflow/progress --id T001 --status done --agent <worker-id> --note "Acceptance check passed; evidence: evidence/T001.txt" --summary
python .specify/extensions/workflow/scripts/progress.py event --output specs/<feature>/workflow/progress --message "Phase 1 tests passed; preparing phase commit" --summary
python .specify/extensions/workflow/scripts/progress.py phase --output specs/<feature>/workflow/progress --name "Phase 1" --status complete --commit <sha> --summary
```

Record token usage from the worker's own harness log whenever a task reaches
`done` or `blocked`. Pass the host agent ID the worker was spawned with:

```text
python .specify/extensions/workflow/scripts/progress.py usage --output specs/<feature>/workflow/progress --id T001 --agent <worker-id> --collect claude --summary
python .specify/extensions/workflow/scripts/progress.py usage --output specs/<feature>/workflow/progress --id T002 --agent <worker-id> --collect codex --summary
python .specify/extensions/workflow/scripts/progress.py usage --output specs/<feature>/workflow/progress --id T003 --agent <run-id> --collect delegate --log .delegate/runs/<run-id>/result.json --summary
python .specify/extensions/workflow/scripts/progress.py usage --output specs/<feature>/workflow/progress --overhead orchestrator --agent <orchestrator-id> --collect claude --summary
python .specify/extensions/workflow/scripts/progress.py sync --output specs/<feature>/workflow/progress --summary
```

`claude` finds `~/.claude/projects/*/*/subagents/agent-<id>.jsonl`, `codex` finds
the rollout whose name ends with the thread ID, and `delegate` reads a
delegate-task `result.json`. Pass `--log` for any other location, including the
dispatcher's own session transcript. Only token counters are read. `sync`
rebuilds the visible delegation history from the tracked feature ledger;
run it after each collected attempt and before the final report review. It shows
the actual model only when the harness reported it. Raw prompts and transcripts
stay in ignored `.delegate/runs/` artifacts. Collecting the same agent again
replaces its figure, so collect overhead at each phase commit and
at Finalize. A worker reused across tasks is split by each task's `running` to
`done` window, so mark a task `running` when assigning it. When no log exists,
record the worker's self-reported counts with `--fresh-input`, `--cached-input`
and `--output-tokens`; the report marks them. A log that cannot be found or read
is recorded as unavailable and shown as a gap, never as zero. The report shows
fresh input, cached input and output per task, the total of the filtered tasks,
per phase, overhead and the feature; it covers implementation only.

At every phase commit, the orchestration agent also records the dispatcher's own
overhead, reading its session transcript path from the handoff:

```text
python .specify/extensions/workflow/scripts/progress.py usage --output specs/<feature>/workflow/progress --overhead dispatcher --agent <dispatcher-session-id> --collect claude --log <dispatcher's own session transcript> --summary
```

Do this immediately after that phase's `progress.py phase --status complete`
call, so dispatcher overhead is measured at the same cadence as the phase
itself instead of reconstructed afterwards.


When accepting a task, the orchestration agent compares the task's recorded `progress.py usage`
figure against its class budget and logs the overrun. Budget overruns and pull request state
use the same script:

```text
python .specify/extensions/workflow/scripts/progress.py event --output specs/<feature>/workflow/progress --message "Budget overrun T###: <class> <figure>/<budget>: <reason>" --summary
python .specify/extensions/workflow/scripts/progress.py pr --output specs/<feature>/workflow/progress --url <pr-url> --status open --summary
python .specify/extensions/workflow/scripts/progress.py event --output specs/<feature>/workflow/progress --message "CI failure: <check>; fix assigned to <worker-id>" --summary
python .specify/extensions/workflow/scripts/progress.py pr --output specs/<feature>/workflow/progress --url <pr-url> --status merged --summary
```
