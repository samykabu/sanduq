# À-la-carte set

**Goal:** combine several standalone extensions without the managed Workflow. You choose which
phases get QA, documentation, board updates or PR generation.

## Prerequisites

- A Spec Kit project with the Sanduq catalog registered. See [set up Spec Kit](../start/install-speckit.md).
- `gh` with Project scopes if you add Project or want PR to open pull requests.

## Install

Start from a [set recipe](../start/install-by-host.md#set-recipes), or pick your own extensions.
This example combines the QA and docs packs with Project:

```bash
specify extension add illustrate
specify extension add assure
specify extension add user-manual
specify extension add pr
specify extension add project
```

Then initialize the extensions that have an init command:

<details>
<summary>Codex</summary>

```text
$speckit-assure-init Configure required QA analysis and tester documentation.
$speckit-user-manual-init Discover our modules, interview me about audiences, and propose the module map.
$speckit-project-init Discover our GitHub Project and map the lifecycle to its columns. Use optional sync.
```

</details>

<details>
<summary>Claude Code</summary>

```text
/speckit-assure-init Configure required QA analysis and tester documentation.
/speckit-user-manual-init Discover our modules, interview me about audiences, and propose the module map.
/speckit-project-init Discover our GitHub Project and map the lifecycle to its columns. Use optional sync.
```

</details>

## First prompt

Use the ordinary Spec Kit commands. The hooks run at their phases.

```text
$speckit-specify Add refund approval for orders over the limit.
```

## What you will see

After `tasks`, Assure and User Manual add missing test and documentation tasks. After `implement`,
they refresh the QA walkthrough and the manual, and PR offers to open the pull request. Project moves
the feature's card at each phase. The [hooks reference](../reference/hooks.md) lists every hook in
order.

## Next step

When you want one command to run the whole lifecycle from a GitHub issue, use the
[managed Workflow](managed-workflow.md).

![Lifecycle overlay: Specify, Clarify, Plan, Tasks, Analyze and Implement, with the mandatory and optional extension hooks before and after each phase, then the Memory archive and User Manual release commands you run after merge and at release.](../diagrams/lifecycle-overlay.animated.svg)

Solid boxes are mandatory hooks; dashed boxes are optional hooks that ask first.
[Editable source](../diagrams/lifecycle-overlay.html).

## Who enforces dependencies

Spec Kit does not install `requires.extensions`. Assure, PR and User Manual run `deps.py ensure`
for Illustrate. PR enforces the QA and manual freshness policies of Assure and User Manual only when
you have installed them.

## Limits

- Init changes hook optionality. Assure Init and Project Init can make their hooks mandatory.
- Do not add Workflow on top of this set without running its init. Workflow takes over the hooks it
  owns and runs them through its dispatcher.
