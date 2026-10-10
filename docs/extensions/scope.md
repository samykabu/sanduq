# Scope

**Purpose:** check a GitHub issue before a specification exists. Scope verifies prerequisites,
inventories requirements, estimates effort, and publishes only the decomposition you approve. It
exports the dependency plan as a diagram.

| | |
| --- | --- |
| Lifecycle phase | Before and after `specify`, before `plan`, after `implement` |
| Hooks | Five mandatory hooks ([hooks](../reference/hooks.md)) |
| Commands | `run`, `guard`, `bind`, `reconcile`, `plan`, `after-specify`, `plan-guard` ([reference](../reference/commands.md#scope)) |
| Requires | Workflow 1.8 or later (below 2.0) |
| Standalone | No |
| License | MIT; the `scope-gate` and `scope-brainstorm` presets are MIT too |

## Setup

Install Workflow and let its installer add Scope:

```bash
specify extension add workflow
```

```text
$speckit-workflow-init Use our existing GitHub Project and an advisory managed-only evidence gate.
```

Another catalog publishes an unrelated extension with the ID `scope`. Workflow's installer resolves
Sanduq's package from its pinned source.

## Example

```text
$speckit-scope-run 412 Inspect existing refund behavior and propose the remaining feature boundary.
```

Clarification questions appear on the issue as separate comments with stable IDs, such as `C1Q1`,
and an unchecked recommendation. Answer `C1Q1: A` or tick a box, then run `$speckit-workflow-clarify`.

## How it runs

![Scope approval and required issue-binding hooks](../diagrams/extension-scope.svg)

Mandatory hooks guard Specify, bind the specification to its issue, start Brainstorm or Clarify,
and guard Plan. When the work is split, `scope.plan` refreshes the dependency plan diagram.
<!-- track-s -->
The managed Workflow runs these steps through its dispatcher.
[Editable source](../diagrams/extension-scope.html).

## Limits

- Scope does not work without Workflow.
- The plan export needs its diagram tool. Scope stops when the export fails. <!-- track-s -->
- Policy approval is recorded as project policy, never as a human approval.

Package details: [Scope README](../../extensions/scope/README.md).
