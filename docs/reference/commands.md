# Command reference

This is the authoritative list of Sanduq's 42 public extension commands, with one example each.
Package READMEs and extension pages link here. Examples use the
[synthetic booking application](../README.md#example-conventions) and issue 412. Guards still
enforce issue binding and stage order; an example does not bypass them.

## Command names

Each command has a manifest identifier. Your [host](glossary.md#host) shows it under its own syntax:

| Host | Example |
| --- | --- |
| Codex | `$speckit-assure-analyze --feature specs/412-refund-approval` |
| Claude Code | `/speckit-assure-analyze --feature specs/412-refund-approval` |
| Manifest identifier | `speckit.assure.analyze` |

The tables below use Codex syntax. In Claude Code, replace the leading `$` with `/`. Prompts are
agent requests, not shell commands. Claude Desktop does not run extensions.

## Contents

- [Workflow](#workflow) (13 commands)
- [Scope](#scope) (7 commands)
- [Project](#project) (2 commands)
- [Assure](#assure) (3 commands)
- [User Manual](#user-manual) (4 commands)
- [PR](#pr) (2 commands)
- [Illustrate](#illustrate) (4 commands)
- [Memory](#memory) (7 commands)
- [Workflow utilities from the shell](#workflow-utilities-from-the-shell)
- [Internal skills and overlays](#internal-skills-and-overlays)

## Workflow

[Extension page](../extensions/workflow.md) · [package README](../../extensions/workflow/README.md)

| Command | When and example |
| --- | --- |
| `$speckit-workflow-init` | Set project policy: `Enable QA and User Manual for the booking application; use an advisory managed-only gate and our existing Project.` |
| `$speckit-workflow-scope` | Start explicitly: `412 Assess refund approval and continue through implementation under project policy.` |
| `$speckit-workflow-clarify` | After issue answers: `Reread issue 412's edited answers and resume the bound feature.` |
| `$speckit-workflow-continue` | After interruption: `Resume specs/412-refund-approval from its checkpoint; inspect recorded worker handles first.` |
| `$speckit-workflow-finalize` | Authorize the PR handoff: `Finish current checks and documentation; create or update the refund feature's PR.` |
| `$speckit-workflow-status` | Inspect: `Show issue 412's active claim, remaining stages, and stale evidence.` |
| `$speckit-workflow-doctor` | Diagnose: `Check actual Project mappings, dependencies, policy, and host commands.` |
| `$speckit-workflow-reconcile` | Repair integration: `Restore managed hooks and presets while preserving unrelated hooks.` |
| `$speckit-workflow-verify-affected` | Before pushing: `Run the refund feature's affected lanes against origin/main using our configured hooks.` |
| `$speckit-workflow-ci-report` | Investigate slow checks: `Summarize the last 10 runs of ci.yml in example-org/booking-app; distinguish fixed job overhead from test time.` |
| `$speckit-workflow-gate-explain` | Diagnose drift: `Explain the failing gate for specs/412-refund-approval against origin/main before changing evidence.` |
| `$speckit-workflow-worker-brief` | Bound a worker task: `Generate the brief for T012 in specs/412-refund-approval with its owned paths and verbatim requirements.` |
| `$speckit-workflow-apply-pending` | Reconcile shared artifacts: `Preview pending refund contract proposals; check each against implementation before applying.` |

## Scope

[Extension page](../extensions/scope.md) · [package README](../../extensions/scope/README.md)

| Command | When and example |
| --- | --- |
| `$speckit-scope-run` | Analyze: `412 Inspect existing refund behavior and propose the remaining feature boundary.` |
| `$speckit-scope-guard` | Before Specify: `Validate issue 412's current approved scope and prerequisite status.` |
| `$speckit-scope-bind` | After Specify: `Bind the refund spec to the explicit issue validated in this Specify invocation.` |
| `$speckit-scope-reconcile` | After child changes: `Refresh the refund parent from its native children's actual state.` |
| `$speckit-scope-plan` | After decomposition: `Regenerate and validate the refund dependency plan as an Illustrate diagram.` |
| `$speckit-scope-after-specify` | Continue clarification: `Dispatch installed Brainstorm, or core Clarify, for the newly bound refund feature.` |
| `$speckit-scope-plan-guard` | Before Plan: `Verify that unresolved GitHub questions do not block the refund plan.` |

## Project

[Extension page](../extensions/project.md) · [package README](../../extensions/project/README.md)

| Command | When and example |
| --- | --- |
| `$speckit-project-init` | Once: `Discover the booking application's Project, map lifecycle columns, and select required sync.` |
| `$speckit-project-sync` | Reconcile: `Synchronize the refund parent and completed task IDs without duplicate native sub-issues.` |

## Assure

[Extension page](../extensions/assure.md) · [package README](../../extensions/assure/README.md)

| Command | When and example |
| --- | --- |
| `$speckit-assure-init` | Once: `Configure required QA analysis and tester documentation for the booking application.` |
| `$speckit-assure-analyze` | Before implementation: `--feature specs/412-refund-approval Add missing duplicate settlement, rejection, permission, and accessibility coverage.` |
| `$speckit-assure-document` | After checks: `--feature specs/412-refund-approval Document runnable refund scenarios and the actual test evidence.` |

## User Manual

[Extension page](../extensions/user-manual.md) · [package README](../../extensions/user-manual/README.md)

| Command | When and example |
| --- | --- |
| `$speckit-user-manual-init` | Once: `Discover Booking, Payments, and Operations modules; interview me, require English, and offer Arabic.` |
| `$speckit-user-manual-analyze` | Before implementation: `Find refund tutorials, API, entity, release, and screenshot gaps in this feature's tasks.` |
| `$speckit-user-manual-update` | After implementation: `Update only affected refund pages and assets; build the private preview and record freshness.` |
| `$speckit-user-manual-release` | At a verified application release: `Build the approved v3.0.0 audience/language HTML archives and PDFs.` |

## PR

[Extension page](../extensions/pr.md) · [package README](../../extensions/pr/README.md)

| Command | When and example |
| --- | --- |
| `$speckit-pr-generate` | Publish: `--feature specs/412-refund-approval Update the existing PR with behavior, verified checks, and readable diagrams.` |
| `$speckit-pr-review-feedback` | After review: `example-org/booking-app#438 Classify unresolved feedback and present the concrete fix/reply plan for approval.` |

## Illustrate

[Extension page](../extensions/illustrate.md) · [package README](../../extensions/illustrate/README.md)

| Command | When and example |
| --- | --- |
| `$speckit-illustrate-theme` | Configure: `set cobalt light` or `validate` for the tracked project theme. |
| `$speckit-illustrate-generate` | Explain: `Create a state diagram of refund request, approval/rejection, and settlement from the real implementation.` |
| `$speckit-illustrate-export` | Embed: `docs/refund-approval.html --svg-only` |
| `$speckit-illustrate-import` | Redraw: `docs/legacy/order-flow.mmd --size doc-wide --detail balanced` in the active project theme with a fidelity ledger. |

## Memory

[Extension page](../extensions/memory.md) · [package README](../../extensions/memory/README.md)

| Command | When and example |
| --- | --- |
| `$speckit-memory-init` | Once: `Configure main as this sample application's merge branch and register its real test commands and covered paths.` |
| `$speckit-memory-prepare` | After implementation: `Queue specs/412-refund-approval for eligibility checking after merge.` |
| `$speckit-memory-run` | Explicit selection: `specs/412-refund-approval Archive this verified, fully completed feature.` |
| `$speckit-memory-session` | Next local session: `Inspect interrupted transactions and process approved pending archives after merge.` |
| `$speckit-memory-enable` | Once per concrete policy/implementation: `Present the configured branch, checks, hooks, and guards for owner review before enabling automatic mode.` |
| `$speckit-memory-impact` | Before a new spec: `Consult current refund constraints and settlement decisions relevant to this proposed change.` |
| `$speckit-memory-status` | Inspect: `Show policy approval, queued refund work, writer state, and recovery phase.` |

## Workflow utilities from the shell

The five utilities do not claim or complete a stage. Affected verification requires the project's
`ci.gate.affected_command` and `verify_command`, writes local results, and does not count as remote
CI evidence. CI Report measures job durations and wall-clock span, not a dependency-aware critical
path. Worker Brief refuses an oversized brief unless explicitly allowed.

Gate Explain's auto-fix applies only to eligible evidence-only drift with a real reason and
`unchanged|changed` assessment. Apply Pending is a dispatcher operation: it previews by default,
refuses active claims and delegated mutation, and may stale dependent receipts. Follow the returned
recovery recipe. [Utility source contracts](../../extensions/workflow/skills/workflow/references/).

The corresponding CLI recipes run from the consumer root. Substitute its repository and base branch:

```bash
python .specify/extensions/workflow/scripts/verify_affected.py --root . --feature specs/412-refund-approval --base-ref origin/main
python .specify/extensions/workflow/scripts/ci_report.py --repository example-org/booking-app --workflow ci.yml --limit 10
python .specify/extensions/workflow/scripts/gate_explain.py --root . --feature specs/412-refund-approval --base-ref origin/main
python .specify/extensions/workflow/scripts/worker_brief.py --root . --feature specs/412-refund-approval --task T012
python .specify/extensions/workflow/scripts/apply_pending.py --root . --feature specs/412-refund-approval
```

## Internal skills and overlays

These skills ship inside extensions; they are not additional `npx skills` installs.

| Skill source | Owner and use in the refund example |
| --- | --- |
| [assure](../../extensions/assure/skills/assure/SKILL.ext.md) | Assure Analyze/Document route QA analysis and test walkthroughs. |
| [scope-analyst](../../extensions/scope/skills/scope-analyst/SKILL.ext.md) | Scope Run owns issue evidence, prerequisite checks, effort, and decomposition. |
| [github-clarification](../../extensions/scope/skills/github-clarification/SKILL.ext.md) | Clarify/Brainstorm reread issue 412's human answers and preserve binding. |
| [sanduq-workflow](../../extensions/workflow/skills/workflow/SKILL.ext.md) | Workflow commands claim stages, invoke their references, and validate receipts. |
| [speckit-scope alias](../../extensions/workflow/skills/speckit-scope/SKILL.ext.md) | The short entry routes issue 412 into the managed dispatcher. |
| [Bridge alias](../../extensions/workflow/skills/speckit-superpowers-bridge/SKILL.ext.md) | Routes continuation to its current owner and prevents a competing executor. |
| [user-manual](../../extensions/user-manual/skills/user-manual/SKILL.ext.md) | Manual commands own module discovery and incremental refund documentation. |
| [api-docs](../../extensions/user-manual/skills/api-docs/SKILL.ext.md) | Manual Update loads safe refund contracts only when API work is needed. |
| [release-docs](../../extensions/user-manual/skills/release-docs/SKILL.ext.md) | Manual Release loads actual application release/migration evidence. |
| [ui-screenshots](../../extensions/user-manual/skills/ui-screenshots/SKILL.ext.md) | Capture deterministic approved/refused refund states. |
| [preview-publishing](../../extensions/user-manual/skills/preview-publishing/SKILL.ext.md) | Use the approved provider for the private manual preview. |
| [Illustrate package skill](../../extensions/illustrate/skill/SKILL.md) | Generate/export useful refund diagrams through extension commands. |
| [Delegate Task (vendored)](../../extensions/workflow/assets/delegate-task/SKILL.md) | Workflow dispatches bounded worker tasks through this driver, vendored from [sanduq-skills](https://github.com/samykabu/sanduq-skills). |

Canonical [Workflow](../../presets/workflow/preset.yml), [Scope Gate](../../presets/scope-gate/preset.yml),
and [Scope Brainstorm](../../presets/scope-brainstorm/preset.yml) presets prepend policy to provider
commands. Installing an overlay does not install SuperSpec or Bridge. The
[worked lifecycle](../workflow/lifecycle.md#core-superspec-and-bridge-overlays) covers every overlay and its
consistent prompt. [Contributing](../../CONTRIBUTING.md#find-the-owning-source) explains where to contribute.

## Hooks

Which commands run automatically, and when, is in the generated [hooks reference](hooks.md).
