# Execute: delegated workers

This part applies when `.specify/workflow.yml` enables delegation.

## Start and collect workers

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
For a terminal result that is still too complex or incomplete, the top-level
dispatcher session can run `delegate_dispatch.py reassign --feature specs/<feature> --run-id <id>
--reason "<specific gap>"`; this starts at most one stronger attempt within the
same limit and records the reason. Review partial edits before choosing that
path. `accept`, `adopt`, `reassign` and `trust-reset` run only in the top-level
dispatcher session, never in a host subagent: an orchestration agent reports
"needs accept/adopt for T###" at a batch boundary instead. Each of the four needs
`--nonce <value>`: the `dispatcher_nonce` a `start` result returned, or the file
`DELEGATION_NONCE_REQUIRED` names. Never put it in a worker's brief.

When a start fails with `DELEGATION_ROUTES_UNAVAILABLE`, no candidate could start or each
was proved never launched; the attempt is `blocked`: fix the CLI or route (`workflow.py doctor
--project`) and start again. `DELEGATION_START_UNCERTAIN` and `DELEGATION_LEDGER_BUSY` follow
[delegation.md](../delegation.md#delegation): recover or abandon the
intent, never start the task again or hand it to another worker; `abandon` refuses for 300
seconds after a start that recorded no outcome.

Record each abandoned intent's reason in the handoff. The ledger keeps it too.
Treat routing type as model choice only: a delegated run is writable unless you
isolate it yourself.

When the Execute stage itself is delegated (`delegate_dispatch.py start --id stage:execute`), its
orchestrator-scoped process is the orchestration agent for this purpose: it spawns and collects
its own feature's task workers directly, through its own `start`/`collect` calls, and reports to
the dispatcher only at batch boundaries, the same as an in-session orchestration agent.

## Light-tier collection results

When delegation is enabled, `start` a light-tier or `qa_collect` task with
`--owned <path>` (repeatable) — it is now required, never a silent
whole-directory default. A light-tier `successful` result is never accepted on
a bare claim: `collect` only trusts a produced-file list that is both inside
the declared owned paths and among the driver's own measured changes — never
counts from a worker's summary.

Completing a delegated stage or checking off a delegated task is not enough
either: `complete` and the Ready gate both require the dispatcher's own
ledger — untampered, and for `complete`, started under the exact claim being
completed — to show the attempt `successful`; any other status, including
`unverified`, `running` or a hand-edited ledger, is refused.

Resolve `unverified` with `reassign` to a standard tier, or
`delegate_dispatch.py accept --run-id <id> --command "<check>" --expect
counts|files [--owned <path>]`, which runs that check itself (never a
`.bat`/`.cmd` shim on Windows — use the underlying executable) and records
sha256/size evidence. `accept --owned` may only narrow the paths recorded at
`start`. A note never accepts an `unverified` run.

Ledger trust is tri-state, not pass/fail: no local `.written` marker (a fresh
checkout or CI runner) is a warning only, not a block — status is still
enforced. A genuine tamper (a marker that disagrees) is sticky and survives a
later legitimate write. `trust-reset` needs the user's explicit approval in this
conversation: pause, show the user exactly what changed in the ledger (quote the
diff), and only after they approve run `delegate_dispatch.py trust-reset
--feature <f> --reason "approved by <user>: <why>"` from the top-level
dispatcher session. This catches accidental and local tampering only, never a
forged commit, so CI integrity still rests on review. After upgrading to this
release, re-delegate any stage claimed under an older checkpoint once, since its
recorded attempt has no `claim_token` and can never satisfy `complete`.
`trust-reset` is never run by a worker, a host subagent or the orchestration
agent.

A checked task with no delegation attempt reaches Ready only through
`delegate_dispatch.py adopt --feature <feature> --id <task> --command
"<acceptance check>" --expect counts|files [--owned <path>]`. It refuses
(`DELEGATION_ADOPT_HAS_ATTEMPT`) if any attempt already exists for that task,
and otherwise runs the acceptance check with the same machinery as `accept`
(no shell, `.bat`/`.cmd` shims refused, bounded timeout, output cap,
owned-path containment, sha256 evidence), recording a successful attempt only
when the check passes. There is no self-certification or exemption path: a
project that enables delegation mid-feature adopts each already-checked task
individually, with a real check.

An adopted attempt is bound to the task's content: `adopt` records a sha256 of
the task line (minus its checkbox state, whitespace normalised), and Ready
re-checks that hash at completion time, refusing with
`DELEGATION_ADOPT_TASK_CHANGED` if the task was edited or replaced under the
same id since adoption. Since an adopted attempt has no dispatcher route to
escalate, `reassign` refuses it with
`DELEGATION_REASSIGN_ADOPTED_UNSUPPORTED`; the supported recovery is to
re-run `adopt` with a corrected acceptance check, or to `start` the task
normally.

Every delegated worker inherits `SANDUQ_DELEGATED_RUN` in its environment, so
`adopt`, `accept`, `reassign` and `trust-reset` refuse with
`DELEGATION_WORKER_CONTEXT` when run from inside a worker's own session
(defence in depth, not a boundary). The Ready gate also warns, with
`DELEGATION_TASK_ADOPTED` or `DELEGATION_TASK_ACCEPTED` naming the command, on
every task that reached Ready because the orchestrator ran and judged the
check rather than because a worker's own delegated attempt succeeded; review
those warnings before merging.

The delegated Execute stage runs under `SANDUQ_DELEGATED_ROLE=orchestrator`
and `SANDUQ_DELEGATED_FEATURE=<feature>` (never `SANDUQ_DELEGATED_RUN`), which
lets it, and only it, run `delegate_dispatch.py start`, `collect`, `accept`,
`reassign` and `adopt` for its own feature's `T###` tasks. `trust-reset`, a
`stage:*` identity or another feature all refuse with
`DELEGATION_ORCHESTRATOR_SCOPE`. The task workers it dispatches get an
ordinary `SANDUQ_DELEGATED_RUN` environment of their own and never inherit
this role.
