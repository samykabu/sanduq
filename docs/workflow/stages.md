# Workflow stages and dispatcher

This page describes the stage chain the Workflow dispatcher runs, its context budget, and how the core skill points each claimed stage at its own reference file. Read it when you need to know which file carries the rules for a stage, or what the execution protocol requires of workers. For a worked example of every stage, see the [lifecycle walkthrough](lifecycle.md).

Back to the [Workflow guide](../../extensions/workflow/README.md).

## Stage chain

Choose QA Assure and User Manual independently during project initialization.
Daily entry points are `speckit.workflow.scope`, `.clarify`, `.continue`, and
`.finalize`. They are entry points into one resumable dispatcher, not mandatory
pauses between every stage.

Scope -> Specify -> Clarify/Brainstorm -> Plan -> one task generator -> selected
QA/manual analysis -> Analyze -> core Tasks-to-Issues -> one executor -> verification
and review -> selected QA/manual documentation -> explicit Finalize -> one PR.
All workflow and clarification illustrations use Illustrate, which Scope (1.6.0 and newer)
requires. PR, Assure and User Manual pin their own Illustrate versions.

The dispatcher calls actual installed agent commands. The Python runtime manages
claims, evidence, invalidation and handoffs; it does not implement semantic agent
work or launch a fresh host session by itself. Missing native invocation support
is a blocker, not an instruction to pretend a stage ran.

## Context

Target a maximum 60% context occupancy with a checkpoint at 50% and a 10% reserve.
The default `measured-only` policy continues automatically without reliable host telemetry.
Estimated, missing, stale or invalid readings never force a context pause or a new session. A strict guarantee requires a host that enforces per-call bounds; prompt
instructions alone cannot provide that guarantee. Each handoff includes completed
stages, pending task IDs, identity, evidence and a fresh-session resume prompt.

## Dispatcher core and per-stage references

`skills/workflow/SKILL.md` is a core dispatcher (<= 6 KB): entry points, the stage
loop and receipt rules, each pointing at the reference that carries its detail.
`claim`'s response carries a `reference` field (`workflow.stage_reference(stage)`)
naming the exact `skills/workflow/references/stage-<stage>.md` for the claimed
stage; read that file, never guess it from the stage name. Cross-cutting detail
lives in `references/dispatcher-operations.md` (init/continue/status/doctor/
reconcile, context/telemetry, Project Sync, the managed-overlay contract,
interruption/GitHub behavior and package updates), `references/
delegation-and-decisions.md` (invoking a claimed command through delegation or a
paused decision) and `references/receipt-rules.md` (input roles, `amend`, and the
G6 recovery recipes). The former single `references/execution.md` is now
`references/execution-assign.md` (start/resume, assign work) and `references/
execution-report.md` (update the report, finish phases, continue through
delivery); `references/stage-execute.md` points at both. Each overlay in
`presets/workflow/commands/*.md` is a <= 5-line pointer into the skill and its
claimed reference; `presets/workflow/commands/speckit.speckit-superpowers-bridge.
*.md` instead point at `references/legacy-guard.md`. `extensions/workflow/tests/
test_skill_split.py` proves every rule from the pre-split files was moved, not
dropped (an explicit, reasoned exception list covers the handful of pointer
sentences whose target relocated); `extensions/scripts/smoke_install.py` and
`test_execution_policy.py` check the built package and an installed fixture
project carry every stage's reference and stay under the core budget.

`execution-assign.md` and `execution-report.md` also carry the retrospective's
execution-protocol rules (B11): workers are spawned with blocking, concurrent
tool calls whose results return to the orchestration agent directly rather than
through the dispatcher (F1); no agent ends a turn while it still owns running
background work (F2); the dispatcher reports only on an actual state change
(F3); a turn-budget table per task class (implementation, qa_author, qa_collect,
documentation, review) and a planned hand-off once a worker's context passes
~150K tokens (T0); a worker's result is a fixed ten-line structure (T7); a
verification summary is read before raw reporter output, which is opened only
for a failed lane (T8); `git stash` and `git add -A`/`git add .` are forbidden
for workers (S6); and a consumers checklist runs after every fix (F11). It also
places `task_issues.py --sync-states` at the phase boundary rather than per task
(from B7), records dispatcher overhead with `progress.py usage --overhead
dispatcher --agent <id> --collect claude --log <path>` at every phase commit,
and puts `--summary` (B7: `ok`/`error` plus counts, or `skipped reason=...`
when a call had nothing to do) on every routine `task_issues.py` and
`progress.py` example call, reserving `--json` for a call whose result must be
parsed programmatically. `execution-report.md`'s "Light-tier collection results
(B12)" section carries B12's consensus text: a light-tier `qa_collect` `start`
requires `--owned <path>`; `collect` trusts only a produced-file list inside
those paths and among the driver's own measured changes; `complete` and the
Ready gate both require the dispatcher's own ledger to show `successful`; an
`unverified` run is resolved only by `reassign` or a checked
`delegate_dispatch.py accept`, never by a note. `references/dispatcher-
operations.md`'s task-marker list gained `[Collect]` alongside `[Impl]`,
`[QA]`, `[Docs]` and `[Review]`, and its `--sync-states` rule now matches
execution-report.md's phase-boundary cadence and names the dispatcher as
owner. `extensions/workflow/tests/test_execution_protocol_b11.py` asserts
these rules are present in the installed reference files, including an
exact-text check of the B12 section.

## Related pages

- [Utility entry points](utilities.md)
- [State files](state-files.md)
- [Development and packaging](development.md)
- [Commands reference](../reference/commands.md)
