# Implementation orchestration: assign

Use this protocol for both core Implement and SuperSpec Execute in a managed
Sanduq workflow. The installed preset supplies it without editing either upstream
command. The dispatcher keeps the Execute claim and remains the only agent that
chooses lifecycle stages. This half covers starting, resuming and assigning work;
[`execution-report.md`](execution-report.md) covers updating the report, finishing
phases and continuing through delivery.

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
behalf and forwards results. Where this fallback applies, the dispatcher
spawns the batch with blocking calls and forwards each T7 result once,
unchanged, the same as the orchestration agent would; it does not relay,
re-summarise or add commentary. The orchestration agent still controls assignments.
Reserve capacity for it and the dispatcher, and release idle workers when needed.
If the host has no usable subagent support or cannot fit a worker, record that
specific blocker and request a supported host/configuration. Do not report a
simulated role or serial parent execution as agent delegation.

The orchestration agent creates the report before assigning the first task:

```text
python .specify/extensions/workflow/scripts/progress.py init --tasks specs/<feature>/tasks.md --output specs/<feature>/workflow/progress --summary
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
`git stash` and `git add -A`/`git add .` are forbidden for a worker, as are
`delegate_dispatch.py accept`, `delegate_dispatch.py trust-reset` and
`delegate_dispatch.py adopt`: a stash can hide another agent's uncommitted
change, a wildcard add can stage paths outside the worker's owned scope, and
`accept`/`trust-reset`/`adopt` are ledger-trust decisions the orchestration
agent alone makes. Staging stays with the orchestration agent, which stages a
worker's owned paths by explicit name.

When `.specify/workflow.yml` enables delegation, start each ready `T###` worker
with `python .specify/extensions/workflow/scripts/delegate_dispatch.py start
--feature specs/<feature> --id T###`. Pass `--task-file <path>` with its bounded
assignment, owned paths, dependencies and acceptance checks. Pass `--cwd
<isolated-worktree>` for concurrent writers. Collect the returned run ID with
`delegate_dispatch.py collect`; follow any `replacement` ID and review the final
result before accepting work. The adapter snapshots the route and driver copy
at start, records unavailable candidates, rejected models and fallbacks, and
refuses a second start of a task that is already starting or running. It makes
one automatic stronger retry (`delegation.stronger_retry`) only for failed work
whose measurement shows no edits: empty `dirty_paths_changed`, unchanged HEAD
and index, and `coverage_complete: true`. Unknown or incomplete measurement means
no automatic retry, so
review the worktree yourself. Do not reassign a running run when YAML changes.
For a terminal result that is still too complex or incomplete, the orchestrator
can run `delegate_dispatch.py reassign --feature specs/<feature> --run-id <id>
--reason "<specific gap>"`; this starts at most one stronger attempt within the
same limit and records the reason. Review partial edits before choosing that
path.

When a start fails:

- `DELEGATION_ROUTES_UNAVAILABLE`: no candidate could start, and each either
  created no run or left one proved never launched (driver exit 5, a
  `failed` never-launched result, no supervisor event, supervisor gone). The attempt is recorded as `blocked`; fix the CLI or route (see
  `workflow.py doctor --project`) and start the task again.
- `DELEGATION_START_UNCERTAIN: recover intent <id>`: do not start the task
  again or hand it to another worker. Run `delegate_dispatch.py recover
  --feature specs/<feature> --intent-id <id>`. If it binds a run, collect it.
  If it reports `found: false`, run `delegate_dispatch.py abandon --feature
  specs/<feature> --intent-id <id> --reason "<why>"` and then start again.
  `abandon` refuses while a driver run exists for the intent, and for 300
  seconds after a start that recorded no outcome.
- `DELEGATION_LEDGER_BUSY`: another dispatcher is writing the ledger; retry.
  A lock whose owner died on this host is recovered on its own. Delete a lock
  file by hand only after confirming the process and host it names are not a
  running dispatcher.

Record each abandoned intent's reason in the handoff. The ledger keeps it too.
Treat routing type as model choice only: a delegated run is writable unless you
isolate it yourself.
When delegation is disabled, ignore routing comments and use the user's selected
model with the existing worker tools.

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

## Spawn pattern, blocking waits and turn budgets (F1, F2, T0)

Spawn a batch of ready workers with several tool calls in the same message,
blocking rather than backgrounded: every worker in the batch runs concurrently,
and each worker's own result is delivered straight to the orchestration agent
that spawned it. Never route a worker's result to the dispatcher for relay and
re-summarising; the dispatcher hears from the orchestration agent only at batch
boundaries (tasks accepted, the phase commit SHA, a blocker). This applies
whether the batch runs in-session or through `delegate_dispatch.py`.

No agent in this protocol, dispatcher, orchestration agent or worker, ends its
turn while it still owns background work that is running. Block on it (a
foreground wait with a bounded, re-armed timeout, or the host's own blocking or
monitor primitive) and report exactly once, when the work concludes.
"Waiting for X" is never a valid final message from any agent in this protocol.
For a run started through `delegate_dispatch.py`, block with a bounded
foreground loop around `delegate_dispatch.py collect` until the run's status is
terminal (not `starting` or `running`), rather than ending the turn to wait for
a separate notification.

Turn budgets bound how large a worker's resident context is allowed to grow,
because turn count, not what a worker reads at the start, explains almost all of
its token cost. Each figure below is a policy budget on fresh input plus output
tokens only; it excludes cache reads, which are about 96% of a worker's total
token volume and are not part of the budget. It is not a hard stop: when
accepting a task, the orchestration agent compares the task's recorded
`progress.py usage` figure against its class budget, and logs any overrun
instead of cutting the worker off mid-task:

```text
python .specify/extensions/workflow/scripts/progress.py event --output specs/<feature>/workflow/progress --message "Budget overrun T###: <class> <figure>/<budget>: <reason>" --summary
```

| Task class | Turn budget (fresh + output) | Notes |
| --- | --- | --- |
| implementation | ~120K (~200K for an integration-heavy task) | Unit-scoped work stays near the lower figure. |
| qa_author | ~300K | Authoring a Playwright spec, an API-sample test or a 20+-state capture; never Haiku (standing rule 5). |
| qa_collect | ~60K | Running an existing, stable spec or script and collecting its counts or files; Haiku-eligible only when the task line carries the `[collect]` marker or an explicit override (B12), never by default. |
| documentation | ~180K | QA Document, Manual Update and similar lifecycle writes. |
| review | ~200K for a first independent pass; ~50K for the same reviewer's later pass | Reusing the reviewer by message across passes is markedly cheaper than a fresh spawn per pass. |

When a worker's own context passes roughly 150K tokens resident, plan a hand-off
at the next safe boundary, such as a finished subtask, a passing test or a
committed file, rather than letting it grow further. Record the hand-off point
and the evidence already produced in the report, so the replacement worker
resumes from there instead of redoing it.
