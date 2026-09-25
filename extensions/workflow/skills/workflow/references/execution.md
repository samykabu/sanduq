# Implementation orchestration

Use this protocol for both core Implement and SuperSpec Execute in a managed
Sanduq workflow. The installed preset supplies it without editing either upstream
command. The dispatcher keeps the Execute claim and remains the only agent that
chooses lifecycle stages.

## Start and resume

Create a dedicated orchestration agent before implementation starts. Give it the
bound feature, repository, branch, issue, current claim identity, task list,
approved decisions and project instructions. Record its actual host agent ID in
the feature handoff. On resume, inspect that handle and reuse it while it is live.
An observation timeout alone does not prove an agent has stopped. Recover a
terminal or missing agent from the handoff before assigning new work.

In Codex, use the available agent spawn, message and status tools. In Claude, use
the installed host's agent/team tools. Check their actual capabilities and limits;
do not invent tool names or assume a child can spawn workers. If nested spawning
is unavailable, the dispatcher creates workers on the orchestration agent's
behalf and forwards results. The orchestration agent still controls assignments.
Reserve capacity for it and the dispatcher, and release idle workers when needed.
If the host has no usable subagent support or cannot fit a worker, record that
specific blocker and request a supported host/configuration. Do not report a
simulated role or serial parent execution as agent delegation.

The orchestration agent creates the report before assigning the first task:

```text
python .specify/extensions/workflow/scripts/progress.py init --tasks specs/<feature>/tasks.md --output specs/<feature>/workflow/progress
```

The report is titled from the plan's `# Tasks: <feature>` heading. Pass
`--title "<feature title>"` to name it explicitly; rerunning `init` with a new
title renames an existing report without losing its evidence. The report shows
the Sanduq logo and page icon, a Phase column, token usage, Status and Phase
filters and a separate Activity tab; filters and the chosen tab survive the automatic refresh. Record
phase results under the exact phase heading from `tasks.md` so each phase
appears once.

Open `specs/<feature>/workflow/progress/index.html` in the host browser or a
platform-supported browser command. Verify that it loads. The page reloads while
the report changes. If browser control is unavailable, record that limitation and
provide the absolute file link; do not claim to have opened it. Keep the report
local unless publication is explicitly authorized. Exclude credentials and full
transcripts from notes.

## Assign work

Read the task dependency graph and the real files before building each batch.
Record each assignment's stable task IDs, prerequisites, owned paths, shared
resources, acceptance checks and worker ID in the report and handoff. Give workers
only their scope and the context needed to implement it. Workers must not stage,
commit, push, merge, change shared report files or invoke another executor.

Fill available worker slots with ready, independent tasks. Reconsider the queue
when a worker finishes or a dependency clears. Task order and a parallel marker
are inputs to scheduling; inspect actual dependencies before running tasks
together. Never run competing writers against the same file, migration sequence,
generated output, package lock or mutable service. Allocate separate databases,
ports and output directories for independent test suites and bound workers to
available CPU and memory. Keep ordered scenarios together. Use isolated worktrees
when useful, but account for integration dependencies and overlapping edits.

When tasks share an interface, settle the contract first and then run its consumers
in parallel. Reserve an integration owner for shared files. If only one task is
ready, delegate it to one worker and record the dependency preventing concurrency.
Never invent extra work merely to occupy slots. The orchestration agent reviews
worker results, integrates changes, checks acceptance evidence and requests fixes.
Unverified worker claims remain pending.

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
```

`claude` finds `~/.claude/projects/*/*/subagents/agent-<id>.jsonl`, `codex` finds
the rollout whose name ends with the thread ID, and `delegate` reads a
delegate-task `result.json`. Pass `--log` for any other location, including the
dispatcher's own session transcript. Only token counters are read. Collecting the
same agent again replaces its figure, so collect overhead at each phase commit and
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
