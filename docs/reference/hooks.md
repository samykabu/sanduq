# Hooks and the lifecycle

A [hook](glossary.md#hook) runs an extension command before or after a Spec Kit phase. This page
shows every hook in two views: what the manifests declare, and what the
[managed Workflow](glossary.md#managed-workflow) does with them. The tables are generated; do not
edit them by hand.

## How a hook's mode changes

- **Manifest default.** A **mandatory** hook (`optional: false`) runs automatically. An **optional**
  hook (`optional: true`) asks you before it runs.
- **Init can change the mode.** Assure Init and Project Init rewrite their hooks in
  `.specify/extensions.yml`. Integrated QA makes Assure's `before_implement` analysis mandatory.
  Required Project sync makes every Project hook run automatically.
- **Workflow takes over.** `speckit.workflow.reconcile` disables the hooks Workflow owns and runs
  those commands as dispatcher stages instead. It keeps a journal so the change can be reversed.
  Scope's guard, bind, plan-guard and reconcile hooks, Memory's hooks and unrelated hooks stay as they are.

## Hooks at a glance

![Lifecycle overlay: Specify, Clarify, Plan, Tasks, Analyze and Implement, with the mandatory and optional extension hooks before and after each phase, then the Memory archive and User Manual release commands you run after merge and at release.](../diagrams/lifecycle-overlay.animated.svg)

Mandatory hooks (solid) run without asking: every Scope hook, and Memory's
session, impact and prepare. Optional hooks (dashed) ask first: Project sync, Assure, User Manual
and PR. Clarify has no hooks. The diagram shows manifest defaults, as in the first table below.
[Editable source](../diagrams/lifecycle-overlay.html).

<!-- generated:hooks:start -->
## Manifest defaults

Generated from each `extensions/*/extension.yml`. This is what Spec Kit registers when you
install an extension, before any init command changes it. Lower priority runs first.

| Phase | When | Extension | Command | Mode | Priority |
| --- | --- | --- | --- | --- | ---: |
| specify | before | scope | `speckit.scope.guard` | mandatory | 1 |
| specify | before | memory | `speckit.memory.session` | mandatory |  |
| specify | after | scope | `speckit.scope.bind` | mandatory | 1 |
| specify | after | project | `speckit.project.sync` | optional |  |
| specify | after | scope | `speckit.scope.after-specify` | mandatory | 30 |
| plan | before | scope | `speckit.scope.plan-guard` | mandatory | 1 |
| plan | after | project | `speckit.project.sync` | optional |  |
| tasks | after | assure | `speckit.assure.analyze` | optional |  |
| tasks | after | project | `speckit.project.sync` | optional |  |
| tasks | after | user-manual | `speckit.user-manual.analyze` | optional |  |
| analyze | before | memory | `speckit.memory.impact` | mandatory |  |
| analyze | after | project | `speckit.project.sync` | optional |  |
| implement | before | assure | `speckit.assure.analyze` | optional |  |
| implement | before | project | `speckit.project.sync` | optional |  |
| implement | after | assure | `speckit.assure.document` | optional |  |
| implement | after | memory | `speckit.memory.prepare` | mandatory |  |
| implement | after | pr | `speckit.pr.generate` | optional |  |
| implement | after | project | `speckit.project.sync` | optional |  |
| implement | after | user-manual | `speckit.user-manual.update` | optional |  |
| implement | after | scope | `speckit.scope.reconcile` | mandatory | 30 |

## Preset overlays

Generated from `presets/*/preset.yml`. An overlay runs Sanduq policy before the upstream command.

| Preset | Command | Strategy |
| --- | --- | --- |
| scope-brainstorm | `speckit.superspec.brainstorm` | prepend |
| scope-gate | `speckit.specify` | prepend |
| scope-gate | `speckit.clarify` | prepend |
| workflow | `speckit.scope.run` | prepend |
| workflow | `speckit.specify` | prepend |
| workflow | `speckit.clarify` | prepend |
| workflow | `speckit.plan` | prepend |
| workflow | `speckit.tasks` | prepend |
| workflow | `speckit.analyze` | prepend |
| workflow | `speckit.taskstoissues` | prepend |
| workflow | `speckit.implement` | prepend |
| workflow | `speckit.superspec.brainstorm` | prepend |
| workflow | `speckit.superspec.tasks` | prepend |
| workflow | `speckit.superspec.execute` | prepend |
| workflow | `speckit.superspec.review` | prepend |
| workflow | `speckit.speckit-superpowers-bridge.execute` | prepend |
| workflow | `speckit.speckit-superpowers-bridge.handoff` | prepend |
| workflow | `speckit.speckit-superpowers-bridge.guard` | prepend |

## Managed Workflow

Generated from `BASE_STAGES`, `COMMANDS` and `stages()` in `extensions/workflow/scripts/workflow.py`,
and from the hook-ownership rule in `extensions/workflow/scripts/reconcile.py`. The dispatcher runs
these stages in order. A stage named `workflow:…` is performed by Workflow itself.

| # | Stage | Command | Runs when |
| ---: | --- | --- | --- |
| 1 | `scope` | `speckit.scope.run` | always |
| 2 | `specify` | `speckit.specify` | always |
| 3 | `clarify` | `speckit.clarify` | always |
| 4 | `plan` | `speckit.plan` | always |
| 5 | `tasks` | `speckit.tasks` | always |
| 6 | `qa_analyze` | `speckit.assure.analyze` | QA selected |
| 7 | `manual_analyze` | `speckit.user-manual.analyze` | User Manual selected |
| 8 | `analyze` | `speckit.analyze` | always |
| 9 | `taskstoissues` | `speckit.taskstoissues` | always |
| 10 | `execute` | `speckit.implement` | always |
| 11 | `verify` | `workflow:verification` | always |
| 12 | `review` | `workflow:review` | always |
| 13 | `qa_document` | `speckit.assure.document` | QA selected |
| 14 | `manual_update` | `speckit.user-manual.update` | User Manual selected |
| 15 | `ready` | `workflow:gates` | always |
| 16 | `pr` | `speckit.pr.generate` | always |

When `speckit.workflow.reconcile` runs, it sets `enabled: false` on each extension hook it owns.
The dispatcher then runs that command as a stage, so it never runs twice. Other hooks keep
their manifest mode.

| Phase | When | Extension | Command | Under Workflow |
| --- | --- | --- | --- | --- |
| specify | before | scope | `speckit.scope.guard` | kept |
| specify | before | memory | `speckit.memory.session` | kept |
| specify | after | scope | `speckit.scope.bind` | kept |
| specify | after | project | `speckit.project.sync` | disabled; the dispatcher owns this step |
| specify | after | scope | `speckit.scope.after-specify` | disabled; the dispatcher owns this step |
| plan | before | scope | `speckit.scope.plan-guard` | kept |
| plan | after | project | `speckit.project.sync` | disabled; the dispatcher owns this step |
| tasks | after | assure | `speckit.assure.analyze` | disabled; runs as stage `qa_analyze` |
| tasks | after | project | `speckit.project.sync` | disabled; the dispatcher owns this step |
| tasks | after | user-manual | `speckit.user-manual.analyze` | disabled; runs as stage `manual_analyze` |
| analyze | before | memory | `speckit.memory.impact` | kept |
| analyze | after | project | `speckit.project.sync` | disabled; the dispatcher owns this step |
| implement | before | assure | `speckit.assure.analyze` | disabled; runs as stage `qa_analyze` |
| implement | before | project | `speckit.project.sync` | disabled; the dispatcher owns this step |
| implement | after | assure | `speckit.assure.document` | disabled; runs as stage `qa_document` |
| implement | after | memory | `speckit.memory.prepare` | kept |
| implement | after | pr | `speckit.pr.generate` | disabled; runs as stage `pr` |
| implement | after | project | `speckit.project.sync` | disabled; the dispatcher owns this step |
| implement | after | user-manual | `speckit.user-manual.update` | disabled; runs as stage `manual_update` |
| implement | after | scope | `speckit.scope.reconcile` | kept |
<!-- generated:hooks:end -->

## Limits

- The Managed Workflow view shows hook ownership from `reconcile.py`. Whether a hook is actually
  disabled in your project depends on `speckit.workflow.reconcile` having run; `doctor` reports a
  `DUPLICATE_STAGE_OWNER` error when it has not.
- Init-time changes by Assure and Project depend on the answers you give. The manifest view shows the
  defaults before init.
