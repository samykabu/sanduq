# Implementation orchestration: report

The second half of the execution protocol; see
[`execution-assign.md`](execution-assign.md) for the shared intro, starting a
dedicated orchestration agent and assigning work. This half covers updating the
report, finishing phases and continuing through delivery.

## Update the report and finish phases

The orchestration agent is the sole report writer. Update it on assignment,
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

Use `pending`, `running`, `done` or `blocked` for task status. Mark task checkboxes
done only after reviewing their implementation and required checks. Preserve
failed attempts alongside subsequent successful evidence.

Sync native task issues once per phase, not once per task: the dispatcher owns
this call and runs `task_issues.py --sync-states --feature ... --parent ...
--apply --summary` exactly once per phase, after every task in the phase is
committed and its documentation tasks (QA Document, Manual Update, where
selected) are done. `sync_states()` already walks every task in `tasks.md` on
each call, so a single call at the phase boundary reports and applies every
completed task's state together; calling it after each task repeats the same
walk for no new information. Never infer human-review completion from
generated evidence: a human-review task's issue closes only on the human's own
signal, never because its evidence file exists.

Prefer `--summary` (a one-line result with counts) for routine protocol calls
to `task_issues.py`, `progress.py`, `assure_state.py`, `manual_state.py` and
`project-sync`: it prints `ok` or `error` plus counts, or `skipped
reason=<why>` when the call had nothing to do. Reserve `--json` for a call
whose result must be parsed programmatically.

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

## Report only on state change (F3)

A wake-up that carries no new information produces no message beyond the
minimum the harness requires: a background task still running, a poll with an
unchanged status, or a repeat of the same "still running" note are not state
changes. Report when a task is accepted, a commit is pushed, a blocker appears
or a decision is needed, and stop there; do not re-narrate the same pending
state after every notification.

## Structured worker results (T7)

A worker returns its result in exactly this ten-line form; the orchestration
agent forwards these lines, or a pointer to them, never the worker's full
prose, to the dispatcher and to the report:

```text
Task: <T### and title>
Status: done | blocked | partial
Files touched: <paths, or "none">
Tests: <RED-to-GREEN summary, e.g. "12 passed, 0 failed (dotnet test, persistence-integration)">
Evidence: <path(s) under specs/<feature>/evidence/>
Diff: <+/- line counts per file, uncommitted>
Consumers checked: <which consumers were checked, or "n/a" with why>
Tokens: <fresh/cached/output if the worker's harness reports them, else "unlogged">
Blockers: <none, or the exact blocking condition>
Next: <what the orchestrator should do, or "none">
```

## Read verification summaries before raw output (T8)

When a task's evidence is a verification run, read its summary first: run ID,
per-lane pass/fail counts and artifact paths, from whatever the project's
verification tooling prints. Open a raw reporter file (Playwright, vitest,
dotnet test JSON) only for a lane that failed, and only that failing test's
section. A fully green run is read from its summary alone; the raw artifacts
stay on disk either way, for anyone who needs them later.

## Consumers checklist after a fix (F11)

Before returning a result for any fix, a review finding, a mid-execute defect,
a rename or a contract change, the worker checks each of the following and
records which applied in the result's "Consumers checked" line; a consumer is
skipped only when it verifiably does not apply, never by default:

- End-to-end/integration specs that reference the changed name, route or contract.
- The lane registry (titles, counts) if a test's identity or count changed.
- QA capture specs and their generated sample output.
- Manual/User-Manual pages and sample copies describing the changed behavior.
- Contract docs, through the project's pending-artifact-updates convention where one exists.
- PR image pins, when a changed screenshot is embedded in the PR body.

## Light-tier collection results (B12)

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
later legitimate write; resolve it with `delegate_dispatch.py trust-reset
--feature <f> --reason "<text>"` only after reviewing exactly what changed —
this catches accidental and local tampering only, never a forged commit, so CI
integrity still rests on review. After upgrading to this release, re-delegate
any stage claimed under an older checkpoint once, since its recorded attempt
has no `claim_token` and can never satisfy `complete`. `trust-reset` is an
orchestration-agent command, never a worker's.

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
python .specify/extensions/workflow/scripts/progress.py pr --output specs/<feature>/workflow/progress --url <pr-url> --status open --summary
python .specify/extensions/workflow/scripts/progress.py event --output specs/<feature>/workflow/progress --message "CI failure: <check>; fix assigned to <worker-id>" --summary
python .specify/extensions/workflow/scripts/progress.py pr --output specs/<feature>/workflow/progress --url <pr-url> --status merged --summary
```

Set `merged` only after reading GitHub's actual merged state and merge SHA. Record
the final check results and post-merge verification in the handoff and report.
PR creation, merge, deployment and live acceptance are separate facts. Keep the
report current through all work in the user's authorized scope; a progress page
does not replace test receipts, review evidence or the workflow checkpoint.
