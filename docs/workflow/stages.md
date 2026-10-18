# Workflow stages and dispatcher

This page describes the stage chain the Workflow dispatcher runs, its context budget, and how the core skill points each claimed stage at its own reference file. Read it when you need to know which file carries the rules for a stage, or what the execution protocol requires of workers. For a worked example of every stage, see the [lifecycle walkthrough](lifecycle.md).

Back to the [Workflow guide](../../extensions/workflow/README.md).

## Stage chain

Choose QA Assure and User Manual independently during project initialization.
Daily entry points are `speckit.workflow.scope`, `.clarify`, `.continue`, and
`.finalize`. They are entry points into one resumable dispatcher, not mandatory
pauses between every stage.

Scope -> Specify -> Clarify/Brainstorm -> Plan -> one task generator -> selected
QA/manual analysis -> Analyze (or `workflow:lint`) -> core Tasks-to-Issues -> one executor -> verification
and review -> selected QA/manual documentation -> explicit Finalize -> one PR.
Workflow illustrations use Illustrate, which Scope requires; clarification questions may use
Mermaid or an Illustrate image. PR, Assure and User Manual pin their own Illustrate versions.

The dispatcher calls actual installed agent commands. The Python runtime manages
claims, evidence, invalidation and handoffs; it does not implement semantic agent
work or launch a fresh host session by itself. Missing native invocation support
is a blocker, not an instruction to pretend a stage ran.

When Memory is installed, accepted Execute completion queues its exact feature
through the same native handoff for Core and SuperSpec. Session entry and verified
post-merge follow-up use that handoff too. It preserves existing queue entries and
returns registered Memory actions for work that needs synthesis or independent
review. Disabled approval remains pending; a Memory failure keeps its actual
blocked reason without changing an accepted product receipt. See the
[local Memory contract](../../extensions/workflow/skills/workflow/references/memory-lifecycle.md).

## Context

Target a maximum 60% context occupancy with a checkpoint at 50% and a 10% reserve.
The default `measured-only` policy continues automatically without reliable host telemetry.
Estimated, missing, stale or invalid readings never force a context pause or a new session. A strict guarantee requires a host that enforces per-call bounds; prompt
instructions alone cannot provide that guarantee. Each handoff includes completed
stages, pending task IDs, identity, evidence and a fresh-session resume prompt.

## Profiles and tiers

With `profiles.enabled: true` in `.specify/workflow.yml`, the Scope receipt's `effort_score` (1,
2, 3, 5, 8, 13 or 21) picks a tier when Plan is first claimed, and the checkpoint keeps it as
`profile: {tier, score, fixed_at}`:

| Tier | Score (default) | Stage changes |
| --- | --- | --- |
| `lite` | up to `profiles.lite.max_score` (3) | Tasks merged into Plan, Analyze runs as `workflow:lint`, QA analysis, manual analysis, QA document and manual update skipped, research, data model, quickstart and contracts optional |
| `standard` | up to `profiles.standard.max_score` (8) | Tasks merged into Plan, Analyze runs as `workflow:lint`, task issues may be `phase-lazy` |
| `full` | above | the full stage list |

Without `profiles`, every feature runs the full list. `next` and `status` show skipped stages,
and `lifecycle.jsonl` records a `skipped` event for each. Lean execution defaults to on for the
lite and standard tiers unless the policy sets `lean_execution.enabled: false`.

`workflow:lint` runs `scripts/lint.py`: requirement coverage, task ids and dependencies, task
headline length, leftover clarification markers, unreferenced contracts and the
`artifacts.budgets` byte budgets. A clean result records the Analyze receipt itself
(`--record`); a semantic gap escalates to a model Analyze on the flagged findings.

## Dispatcher core and per-stage references

`skills/workflow/SKILL.md` (skill name `speckit-workflow`, at most 6 KB) holds the entry points,
the stage loop and the profiles summary. `claim` returns `reference` (the
`references/stage-<stage>.md` path) and `reference_text` (its content), so the dispatcher reads
each stage reference once, from the claim. Every stage reference is self-sufficient for its
stage. The dispatcher reads a small pointer set once per session:

| Reference | Holds |
| --- | --- |
| `receipt-rules.md` | recording a receipt, input roles, side effects, `amend` |
| `recovery.md` | drift recovery: `revalidate-upstream`, Verify, Review and Ready revalidation |
| `dispatcher-operations.md` | continue, status, doctor and its cache, reconcile, context, Project Sync points, the managed-overlay contract, handoff and GitHub rules |
| `delegation-and-decisions.md` | invoking a claimed command, delegation, lean execution, GitHub decisions |
| `setup-and-updates.md` | init, package updates, `migrate`, `relocate`, `host` |
| `scope-binding.md` | the managed Scope gate and bind flags and binding restrictions, shared by the Scope commands and the Scope-gate Specify overlay |
| `superspec-checkpoints.md` | the `required-only` checkpoint rule shared by the SuperSpec providers |

Execute reads `execution-assign.md` (start, resume, assign) and `execution-report.md` (finish
phases, phase-lazy task issues, delivery, legacy reporter calls). Each overlay in
`presets/workflow/commands/*.md` is a short pointer into the skill and its claimed reference,
except Clarify and SuperSpec Brainstorm, which use `strategy: replace` and carry the useful
upstream taxonomy themselves. The `speckit-superpowers-bridge` overlays point at
`references/legacy-guard.md`.

`extensions/workflow/tests/test_skill_split.py` checks a curated rule inventory
(`tests/fixtures/rules-inventory.json`: file, rule, reason) so wording can be tightened without
losing a gate rule, and that shared paragraphs live in one file.
`extensions/scripts/smoke_install.py` and `test_execution_policy.py` check the built package and
an installed fixture project carry every stage's reference and stay under the core budget.

`reporting.md` is the only place that decides how the report is kept: `projection`, `refresh` or
`legacy`, and in every mode no agent is spawned, retained, messaged or polled solely for reporting. The legacy
`progress.py` call sequences sit at the end of `execution-report.md`.

`execution-assign.md` and `execution-report.md` also carry the execution-protocol rules: workers
are spawned with blocking, concurrent tool calls whose results return to the orchestration agent
directly; no agent ends a turn while it still owns running background work; the dispatcher
reports only on an actual state change; a turn-budget table per task class and a planned
hand-off once a worker's context passes about 150K tokens; a fixed ten-line worker result; a
verification summary read before raw reporter output; `git stash` and `git add -A`/`git add .`
forbidden for workers; and a consumers checklist after every fix. Task-issue state syncs once
per phase boundary, routine calls use `--summary`, and the light-tier collection rules
(`--owned`, ledger-verified `successful` attempts, `accept`, `adopt`, `trust-reset`) are stated
once in `execution-report.md`. `extensions/workflow/tests/test_execution_protocol_b11.py`
asserts these rules are present in the installed reference files.

## Related pages

- [Utility entry points](utilities.md)
- [State files](state-files.md)
- [Development and packaging](development.md)
- [Commands reference](../reference/commands.md)
