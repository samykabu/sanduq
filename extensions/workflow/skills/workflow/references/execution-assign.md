# Implementation orchestration: assign

Core Implement and SuperSpec Execute both follow this protocol. The dispatcher keeps the
Execute claim and alone chooses lifecycle stages. This half covers assigning work;
[`execution-report.md`](execution-report.md) covers finishing phases and delivery. The claim adds
the parts for its mode from `execute/`: who owns orchestration (lean or a dedicated orchestration
agent), delegation when enabled, and the reporting calls ([`reporting.md`](reporting.md), or the
legacy reporter); no agent exists solely for reporting.

The current coordinator creates the progress report before assigning the first task, with the
call the reporting part names. Record phase results under the exact phase heading from
`tasks.md`. Open the report once when that helps the human; it reloads by itself. Do not
re-open or re-verify it in a loop. Without browser control, give the absolute file link and do
not claim to have opened it. Keep the report local unless publication is authorized, and keep
credentials and transcripts out of notes.

## Assign work

Read the task dependency graph and the real files before building each batch.
Record each assignment's stable task IDs, prerequisites, owned paths, shared
resources, acceptance checks and worker ID in the handoff, and in the report as
`reporting.md` says (one lane per workstream in projection mode, updated, not duplicated, when it moves to a new worker). Give workers
only their scope and the context needed to implement it. Workers must not stage,
commit, push, merge, change shared report files or invoke another executor.
`git stash` and `git add -A`/`git add .` are forbidden for a task worker, as
are `delegate_dispatch.py accept`, `delegate_dispatch.py reassign`,
`delegate_dispatch.py trust-reset` and `delegate_dispatch.py adopt`: a stash
can hide another agent's uncommitted change, a wildcard add can stage paths
outside the worker's owned scope, and `accept`/`reassign`/`trust-reset`/`adopt`
are ledger-trust decisions. They run only in the top-level dispatcher session:
the guard refuses them in every host subagent, the orchestration agent included.
The orchestration agent reports "needs accept/adopt for T###" (or reassign) at a
batch boundary and the dispatcher runs the command. `trust-reset` also needs the
user's explicit approval in the conversation, quoted in its `--reason`. The one
exception is the delegated Execute stage, an external delegated process rather
than a host subagent: it runs with an orchestrator scope over its own feature's
`T###` tasks and legitimately calls `start`, `collect`, `accept`, `reassign` and
`adopt` for them; `trust-reset` stays forbidden even for it. An ordinary task
worker never has that scope. Staging
stays with the orchestration agent, which stages a worker's owned paths by
explicit name. The guard hook also refuses these commands where it runs; on
Codex it runs only once approved (`workflow.py doctor` reports it), so this
rule holds either way.

Without delegation, routing comments in `tasks.md` are ignored: use the user's selected
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

## Spawn pattern, blocking waits and turn budgets

Spawn a batch of ready workers with several tool calls in the same message,
blocking rather than backgrounded: every worker in the batch runs concurrently,
and each worker's own result is delivered straight to the orchestration agent
that spawned it. Never route a worker's result to the dispatcher for relay and
re-summarising; the dispatcher hears from the orchestration agent only at batch
boundaries (tasks accepted, the phase commit SHA, a blocker).

No agent in this protocol, dispatcher, orchestration agent or worker, ends its
turn while it still owns background work that is running. Block on it (a
foreground wait with a bounded, re-armed timeout, or the host's own blocking or
monitor primitive) and report exactly once, when the work concludes. This is about
worker completion only. Watching the report itself, or checking that it refreshed,
is never background work and is not allowed (`reporting.md`).
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
accepting a task, the coordinator logs any overrun, as the reporting part says,
instead of cutting the worker off mid-task.

| Task class | Turn budget (fresh + output) | Notes |
| --- | --- | --- |
| implementation | ~120K (~200K for an integration-heavy task) | Unit-scoped work stays near the lower figure. |
| qa_author | ~300K | Authoring a Playwright spec, an API-sample test or a 20+-state capture; never Haiku. |
| qa_collect | ~60K | Running an existing, stable spec or script and collecting its counts or files; Haiku-eligible only when the task line carries the `[collect]` marker or an explicit override, never by default. |
| documentation | ~180K | QA Document, Manual Update and similar lifecycle writes. |
| review | ~200K for a first independent pass; ~50K for the same reviewer's later pass | Reusing the reviewer by message across passes is markedly cheaper than a fresh spawn per pass. |

When a worker's own context passes roughly 150K tokens resident, plan a hand-off
at the next safe boundary, such as a finished subtask, a passing test or a
committed file, rather than letting it grow further. Record the hand-off point
and the evidence already produced in the report, so the replacement worker
resumes from there instead of redoing it.
