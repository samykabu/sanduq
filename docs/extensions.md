# Spec Kit extensions

Extensions add versioned commands and hooks to a Spec Kit project. Use one extension for a
bounded process, or let Workflow coordinate selected processes. Installation and process
initialization are separate steps. Start with [Getting started](getting-started.md).

## Table of contents

- [Workflow](#workflow)
- [Scope](#scope)
- [Project](#project)
- [Assure](#assure)
- [User Manual](#user-manual)
- [PR](#pr)
- [Illustrate](#illustrate)
- [Memory](#memory)
- [Internal skills and overlays](#internal-skills-and-overlays)

The tables cover every command in the eight [source manifests](../extensions/README.md).
Examples use [issue 412 in the synthetic booking application](README.md#example-conventions).
They illustrate the command's purpose; guards still enforce issue binding and stage order.

## Workflow

Workflow owns the resumable Scope-to-PR dispatcher. Initialize it once with QA/manual and evidence
gate choices, then use Scope, Clarify, Continue, and Finalize for daily work. It selects one task
generator and one executor. [Package reference](../extensions/workflow/README.md).

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

The five utilities do not claim or complete a stage. Affected verification requires the project's
`ci.gate.affected_command` and `verify_command`, writes local results, and does not count as remote
CI evidence. CI Report measures job durations and wall-clock span, not a dependency-aware critical
path. Worker Brief refuses an oversized brief unless explicitly allowed.

Gate Explain's auto-fix applies only to eligible evidence-only drift with a real reason and
`unchanged|changed` assessment. Apply Pending is a dispatcher operation: it previews by default,
refuses active claims and delegated mutation, and may stale dependent receipts. Follow the returned
recovery recipe. [Utility source contracts](../extensions/workflow/skills/workflow/references/).

The corresponding CLI recipes run from the consumer root. Substitute its repository and base branch:

```bash
python .specify/extensions/workflow/scripts/verify_affected.py --root . --feature specs/412-refund-approval --base-ref origin/main
python .specify/extensions/workflow/scripts/ci_report.py --repository example-org/booking-app --workflow ci.yml --limit 10
python .specify/extensions/workflow/scripts/gate_explain.py --root . --feature specs/412-refund-approval --base-ref origin/main
python .specify/extensions/workflow/scripts/worker_brief.py --root . --feature specs/412-refund-approval --task T012
python .specify/extensions/workflow/scripts/apply_pending.py --root . --feature specs/412-refund-approval
```

Expected result: a bound feature, stage receipts, current verification, and an HTML progress report
at `specs/412-refund-approval/workflow/progress/index.html`; Finalize creates/updates one PR.
Merge and deployment require separate authorization. See [worked stages](skill-guide.md).

## Scope

Scope checks a GitHub issue before a specification exists. It verifies prerequisites, inventories
requirements, assesses effort, and publishes only the approved decomposition or valid project-policy
decision. Workflow installs its matching Sanduq version; do not select an ambiguous `scope` package
from another catalog. [Package reference](../extensions/scope/README.md).

| Command | When and example |
| --- | --- |
| `$speckit-scope-run` | Analyze: `412 Inspect existing refund behavior and propose the remaining feature boundary.` |
| `$speckit-scope-guard` | Before Specify: `Validate issue 412's current approved scope and prerequisite status.` |
| `$speckit-scope-bind` | After Specify: `Bind the refund spec to the explicit issue validated in this Specify invocation.` |
| `$speckit-scope-reconcile` | After child changes: `Refresh the refund parent from its native children's actual state.` |
| `$speckit-scope-plan` | After decomposition: `Regenerate and validate the refund dependency plan through installed Archify.` |
| `$speckit-scope-after-specify` | Continue clarification: `Dispatch installed Brainstorm, or core Clarify, for the newly bound refund feature.` |
| `$speckit-scope-plan-guard` | Before Plan: `Verify that unresolved GitHub questions do not block the refund plan.` |

Expected result: source-backed scope, preserved issue content/images, an approved spec prompt,
explicit dependencies, and a checked implementation plan when split. Archify must be available
for Scope's required plan export; it is an external capability, not one of these seven portable skills.
GitHub questions have stable IDs and initially unchecked recommendations. Answer `C1Q1: A`
or edit a choice, then invoke Workflow Clarify. Managed reinvocation rereads answers without a manual
board move. Unmanaged Scope follows its own status and approval contract.

## Project

Project maps Spec Kit phases onto the actual GitHub Project columns. Initialize with authenticated
`gh` and Project access. In managed Workflow, preserve dispatcher-owned hooks and task-issue ownership.
[Package reference](../extensions/project/README.md).

| Command | When and example |
| --- | --- |
| `$speckit-project-init` | Once: `Discover the booking application's Project, map lifecycle columns, and select required sync.` |
| `$speckit-project-sync` | Reconcile: `Synchronize the refund parent and completed task IDs without duplicate native sub-issues.` |

Expected result: committed `config.json` and `.specify/project-sync-state.json`, one feature parent,
and reconciled task status. Outside Workflow, Project can own task sub-issues; managed Workflow's
adapter owns their creation/completion. A logged graceful skip is not a completed synchronization.
Use `--dry-run` or `-DryRun` on the package's Bash/PowerShell sync helper before diagnosis changes.

## Assure

Assure adds tester-readiness analysis and a QA walkthrough. It is distinct from application user
documentation and does not itself prove tests passed. Initialize integrated or manual policy, or
select QA through Workflow Init. [Package reference](../extensions/assure/README.md).

| Command | When and example |
| --- | --- |
| `$speckit-assure-init` | Once: `Configure required QA analysis and tester documentation for the booking application.` |
| `$speckit-assure-analyze` | Before implementation: `--feature specs/412-refund-approval Add missing duplicate settlement, rejection, permission, and accessibility coverage.` |
| `$speckit-assure-document` | After checks: `--feature specs/412-refund-approval Document runnable refund scenarios and the actual test evidence.` |

Expected result: identified missing tasks, tester steps, synthetic test data, expected results,
screenshots where evidenced, and feature freshness manifests under `.specify/extensions/assure/state/`.
An old walkthrough is insufficient after the implementation changes. Illustrate is required for
applicable diagrams. Legacy `qa` and `how-to-test` extension aliases are retired.

## User Manual

User Manual maintains canonical `User-Manual/` content and filtered End User,
Administrator/Operator, and Technical editions. Approve the discovered module map before
scaffolding. Select manual maintenance through Workflow Init in managed projects.
[Package reference](../extensions/user-manual/README.md).

| Command | When and example |
| --- | --- |
| `$speckit-user-manual-init` | Once: `Discover Booking, Payments, and Operations modules; interview me, require English, and offer Arabic.` |
| `$speckit-user-manual-analyze` | Before implementation: `Find refund tutorials, API, entity, release, and screenshot gaps in this feature's tasks.` |
| `$speckit-user-manual-update` | After implementation: `Update only affected refund pages and assets; build the private preview and record freshness.` |
| `$speckit-user-manual-release` | At a verified application release: `Build the approved v3.0.0 audience/language HTML archives and PDFs.` |

Expected result: approved module configuration, canonical Markdown, audited coverage, and rendered
editions. Material is the default; other installed MkDocs themes and custom overrides are supported.
PR artifacts are private; a public repository needs the package's encrypted-preview configuration.
Hosted previews require an approved provider; Administrator and Technical editions require actual
access enforcement. Illustrate supplies useful visuals. See the [focused skill examples](skills.md).

## PR

PR builds feature explanations and creates or updates the current branch's PR after required QA
and manual freshness checks. Git and authenticated `gh` are needed for remote operations.
[Package reference](../extensions/pr/README.md).

| Command | When and example |
| --- | --- |
| `$speckit-pr-generate` | Publish: `--feature specs/412-refund-approval Update the existing PR with behavior, verified checks, and readable diagrams.` |
| `$speckit-pr-review-feedback` | After review: `example-org/booking-app#438 Classify unresolved feedback and present the concrete fix/reply plan for approval.` |

Expected result: `docs/<feature-slug>/CHANGELOG.md`, a feature explanation, useful illustration
sources/exports, and an updated marker-delimited PR section. Use `--no-pr` for documents only.
Generation creates a PR by default when possible. Feedback requires approval of its actual plan
before edits, replies, commits, pushes, or thread resolution. Missing remote prerequisites leave
document output and an accurate skipped-PR report. The old `pr-review` extension is retired.

## Illustrate

The extension packages the same visual vocabulary as the portable skill, with a version-matched
copy under `.specify/extensions/illustrate/skill/`. It does not depend on a global skill install.
[Package reference](../extensions/illustrate/README.md).

| Command | When and example |
| --- | --- |
| `$speckit-illustrate-theme` | Configure: `set cobalt light` or `validate` for the tracked project theme. |
| `$speckit-illustrate-generate` | Explain: `Create a state diagram of refund request, approval/rejection, and settlement from the real implementation.` |
| `$speckit-illustrate-export` | Embed: `docs/refund-approval.html --svg-only` |

Expected result: self-contained editable HTML and explicitly requested SVG/PNG exports. Preserve
sources alongside exports, use the project's theme, and review rendering. Legacy Diagram Design
installs migrate to `illustrate`; PNG rendering needs Playwright and Chromium.

## Memory

Memory reconciles completed feature knowledge into `specs/memory/`, migrates required fixtures,
and removes selected spec folders only after verified, independently reviewed, recoverable commits.
Use Python 3.11+, Git, Spec Kit 1.x, the actual merge branch, and named checks that verify your code.
[Package reference](../extensions/memory/README.md).

```bash
specify extension add memory
```

| Command | When and example |
| --- | --- |
| `$speckit-memory-init` | Once: `Configure main as this sample application's merge branch and register its real test commands and covered paths.` |
| `$speckit-memory-prepare` | After implementation: `Queue specs/412-refund-approval for eligibility checking after merge.` |
| `$speckit-memory-run` | Explicit selection: `specs/412-refund-approval Archive this verified, fully completed feature.` |
| `$speckit-memory-session` | Next local session: `Inspect interrupted transactions and process approved pending archives after merge.` |
| `$speckit-memory-enable` | Once per concrete policy/implementation: `Present the configured branch, checks, hooks, and guards for owner review before enabling automatic mode.` |
| `$speckit-memory-impact` | Before a new spec: `Consult current refund constraints and settlement decisions relevant to this proposed change.` |
| `$speckit-memory-status` | Inspect: `Show policy approval, queued refund work, writer state, and recovery phase.` |

Expected result: canonical per-entry knowledge and provenance, generated index/catalog pages,
reserved feature numbers, and checkpoint/final archive commits. `specs/project-memory.md` is a
navigation stub in format 2. Checked tasks and merge status alone do not prove completion.
Automatic mode queues after implementation and processes in a local session after merge; no daemon
or remote merge execution is installed. Changed policy/implementation invalidates approval.

For retrieval and integrity checks in the sample application:

```bash
python .specify/extensions/memory/scripts/archive.py pending --gate
python .specify/extensions/memory/scripts/archive.py memory query --text refund
python .specify/extensions/memory/scripts/archive.py memory check
```

Use `memory show --id <actual-id>` for exact entries and `memory catalog --domain <actual-domain>`
for browsing. Typed `constrains`/`supersedes` links keep current limiting rules with retrieved entries.
Ordinary implementation checks pending work; load knowledge during specification and impact analysis.
For large runs, packet drafting and partitioned review preserve entry ownership and coverage.
The package reference covers explicit retirement, verification overrides, format migration, resume,
abandon, and rollback. Never delete a journal or reset Git to bypass a blocked archive.

## Internal skills and overlays

These skills ship inside extensions; they are not additional `npx skills` installs.

| Skill source | Owner and use in the refund example |
| --- | --- |
| [assure](../extensions/assure/skills/assure/SKILL.md) | Assure Analyze/Document route QA analysis and test walkthroughs. |
| [scope-analyst](../extensions/scope/skills/scope-analyst/SKILL.md) | Scope Run owns issue evidence, prerequisite checks, effort, and decomposition. |
| [github-clarification](../extensions/scope/skills/github-clarification/SKILL.md) | Clarify/Brainstorm reread issue 412's human answers and preserve binding. |
| [sanduq-workflow](../extensions/workflow/skills/workflow/SKILL.md) | Workflow commands claim stages, invoke their references, and validate receipts. |
| [speckit-scope alias](../extensions/workflow/skills/speckit-scope/SKILL.md) | The short entry routes issue 412 into the managed dispatcher. |
| [Bridge alias](../extensions/workflow/skills/speckit-superpowers-bridge/SKILL.md) | Routes continuation to its current owner and prevents a competing executor. |
| [user-manual](../extensions/user-manual/skills/user-manual/SKILL.md) | Manual commands own module discovery and incremental refund documentation. |
| [api-docs](../extensions/user-manual/skills/api-docs/SKILL.md) | Manual Update loads safe refund contracts only when API work is needed. |
| [release-docs](../extensions/user-manual/skills/release-docs/SKILL.md) | Manual Release loads actual application release/migration evidence. |
| [ui-screenshots](../extensions/user-manual/skills/ui-screenshots/SKILL.md) | Capture deterministic approved/refused refund states. |
| [preview-publishing](../extensions/user-manual/skills/preview-publishing/SKILL.md) | Use the approved provider for the private manual preview. |
| [Illustrate package skill](../extensions/illustrate/skill/SKILL.md) | Generate/export useful refund diagrams through extension commands. |

Canonical [Workflow](../presets/workflow/preset.yml), [Scope Gate](../presets/scope-gate/preset.yml),
and [Scope Brainstorm](../presets/scope-brainstorm/preset.yml) presets prepend policy to provider
commands. Installing an overlay does not install SuperSpec or Bridge. The
[worked lifecycle](skill-guide.md#core-superspec-and-bridge-overlays) covers every overlay and its
consistent prompt. [Source ownership](workflow-source-ownership.md) explains where to contribute.
