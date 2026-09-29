# Implementation orchestration: report

The second half of the execution protocol; see
[`execution-assign.md`](execution-assign.md) for the shared intro, starting a
dedicated orchestration agent and assigning work. This half covers updating the
report, finishing phases and continuing through delivery.

## Update the report and finish phases

The orchestration agent is the sole report writer. Update it on assignment,
completion, failure, recovery and each lifecycle transition. Use actual task IDs:

```text
python .specify/extensions/workflow/scripts/progress.py task --output specs/<feature>/workflow/progress --id T001 --status running --agent <worker-id> --note "Own src/example.py; depends on T000"
python .specify/extensions/workflow/scripts/progress.py task --output specs/<feature>/workflow/progress --id T001 --status done --agent <worker-id> --note "Acceptance check passed; evidence: evidence/T001.txt"
python .specify/extensions/workflow/scripts/progress.py event --output specs/<feature>/workflow/progress --message "Phase 1 tests passed; preparing phase commit"
python .specify/extensions/workflow/scripts/progress.py phase --output specs/<feature>/workflow/progress --name "Phase 1" --status complete --commit <sha>
```

Record token usage from the worker's own harness log whenever a task reaches
`done` or `blocked`. Pass the host agent ID the worker was spawned with:

```text
python .specify/extensions/workflow/scripts/progress.py usage --output specs/<feature>/workflow/progress --id T001 --agent <worker-id> --collect claude
python .specify/extensions/workflow/scripts/progress.py usage --output specs/<feature>/workflow/progress --id T002 --agent <worker-id> --collect codex
python .specify/extensions/workflow/scripts/progress.py usage --output specs/<feature>/workflow/progress --id T003 --agent <run-id> --collect delegate --log .delegate/runs/<run-id>/result.json
python .specify/extensions/workflow/scripts/progress.py usage --output specs/<feature>/workflow/progress --overhead orchestrator --agent <orchestrator-id> --collect claude
python .specify/extensions/workflow/scripts/progress.py sync --output specs/<feature>/workflow/progress
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

Use `pending`, `running`, `done` or `blocked` for task status. Mark task checkboxes
done only after reviewing their implementation and required checks. Preserve
failed attempts alongside subsequent successful evidence. Sync native task issues
through the dispatcher after accepted batches.

Continue until every implementation phase is finished. At each phase boundary,
run the required checks, inspect the combined diff, and have the orchestration
agent commit and push that phase's completed changes to the bound feature branch.
Stage only the intended paths; preserve unrelated user changes. Record the actual
commit SHA and push result. A completed local phase with a failed push remains
unpublished; diagnose the failure and retry without claiming remote success.
Keep the report directory out of receipt input manifests and implicit source
inventories; its routine updates must not stale source verification. Retain it
locally through merge, with stable evidence stored separately in the feature.

Existing authorization for phase commits and pushes carries forward. Respect an
explicit user restriction and record the precise limitation if publication is
not authorized. Under `required-only`, routine phase transitions and backend
choice do not need another approval. Human review tasks, unresolved requirements,
security decisions and deployment approvals remain real gates. Record concrete
blockers and continue independent authorized work.

## Continue through delivery

The orchestration agent returns the Execute evidence to the dispatcher. It stays
available to update the report and schedule fixes while the dispatcher runs
Verify, Review, selected documentation and Ready. Never complete a claim or call
the next lifecycle stage from a worker or from an executor hook.

When the user's request authorizes a PR, the dispatcher continues through Finalize
automatically once its prerequisites pass. When merge is also authorized, monitor
checks and reviews on the exact final head, delegate fixes, revalidate affected
evidence, and merge through the normal protected path only when required checks
are green and approvals are satisfied. Do not bypass branch protections. Without
merge authorization, keep the report at the actual PR state and request only the
missing authorization after the PR is concrete and reviewable.

```text
python .specify/extensions/workflow/scripts/progress.py pr --output specs/<feature>/workflow/progress --url <pr-url> --status open
python .specify/extensions/workflow/scripts/progress.py event --output specs/<feature>/workflow/progress --message "CI failure: <check>; fix assigned to <worker-id>"
python .specify/extensions/workflow/scripts/progress.py pr --output specs/<feature>/workflow/progress --url <pr-url> --status merged
```

Set `merged` only after reading GitHub's actual merged state and merge SHA. Record
the final check results and post-merge verification in the handoff and report.
PR creation, merge, deployment and live acceptance are separate facts. Keep the
report current through all work in the user's authorized scope; a progress page
does not replace test receipts, review evidence or the workflow checkpoint.
