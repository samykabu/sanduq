# Scope

**Purpose:** check a GitHub issue before a specification exists. Scope verifies prerequisites,
inventories requirements, estimates effort, and publishes only the decomposition you approve. It
exports the dependency plan as a diagram. From Workflow 2.0.0 Scope is part of Workflow: its commands are
`speckit.workflow.scope-*`, and there is no separate package to install
([upgrades](../start/upgrades.md#workflow-200-scope-is-part-of-workflow)).

An issue is ready when each prerequisite is In review or Done. The check follows prerequisites of
prerequisites through In review issues and stops at a Done one, so a Done prerequisite whose own prerequisite
was reopened does not block.

| | |
| --- | --- |
| Lifecycle phase | Before and after `specify`, before `plan`, after `implement` |
| Hooks | Five mandatory hooks, registered by Workflow ([hooks](../reference/hooks.md)) |
| Commands | `speckit.workflow.scope-` + `run`, `plan`; hook-only `guard`, `bind`, `after-specify`, `plan-guard`, `reconcile` ([reference](../reference/commands.md#scope)) |
| Requires | Workflow 2.0.0 or later, which ships Scope; Illustrate 2.2.1 or later (below 3.0); Python 3.11 or later |
| Standalone | No |
| License | MIT; the `scope-gate` and `scope-brainstorm` presets are MIT too |

## Setup

Install Workflow; it includes Scope:

```bash
specify extension add workflow
```

```text
$speckit-workflow-init Use our existing GitHub Project and an advisory managed-only evidence gate.
```

Do not install a `scope` extension. The community catalog publishes an unrelated one ("Spec Scope"), and
Sanduq's own Scope 2.0.0 is a retired shim: it has no code, and installing it only prints the upgrade command.
Workflow's installer removes any Sanduq `scope` package and keeps its state in `.specify/scope/`.

## Example

```text
$speckit-workflow-scope-run 412 Inspect existing refund behavior and propose the remaining feature boundary.
```

Clarification questions appear on the issue as separate comments with stable IDs, such as `C1Q1`,
and an unchecked recommendation. Answer `C1Q1: A` or tick a box, then run `$speckit-workflow-clarify`.

## How it runs

![Workflow sequence with Scope inside it: you run workflow.scope on an issue and the dispatcher runs Scope, Specify and Clarify; the Scope panel lists the host commands workflow.scope-run and workflow.scope-plan and the Spec Kit hooks workflow.scope-guard, scope-bind, scope-after-specify, scope-plan-guard and scope-reconcile.](../diagrams/extension-workflow.animated.svg)

The [hook lifecycle](../reference/hooks.md) shows where each hook runs.

Mandatory hooks guard Specify, bind the specification to its issue, start Brainstorm or Clarify,
and guard Plan. When the work is split, `scope-plan` accepts an [Illustrate](illustrate.md) dependency graph: it checks
that every issue is covered and reachable, renders the graph in a browser, and exports SVG and PNG.
Clarification questions embed that image when GitHub serves the pushed file, and fall back to a
text list when it cannot. A question may also carry a Mermaid diagram. With
`clarification.in_session_first_round`, the issue creator can answer the first round in the
session, and `clarification.max_questions_per_round` caps a round. In a managed project Scope can
render the spec from the approved analysis (`scope.py render-spec`), and `--snapshot` reuses an
`inspect` result across gate, approve, publish and bind.
`scope.py cancel <issue>-<hash>` marks an interrupted publish cancelled and prints what to repair by hand.
The managed Workflow runs these steps through its dispatcher.
[Editable source](../diagrams/extension-workflow.html).

## Limits

- Scope is part of Workflow and does not exist without it.
- Scope requires Illustrate. Plan acceptance needs Playwright with Chromium; without it, acceptance
  stops with the install command and keeps the previous plan.
- Policy approval is recorded as project policy, never as a human approval.

Package details: [Workflow README, Scope section](../../extensions/workflow/README.md#scope).
