# One extension

**Goal:** add one Sanduq process to a Spec Kit project. The example adds Illustrate and asks for a
diagram from the active feature.

An [extension](../reference/glossary.md#extension) adds versioned commands and, often,
[hooks](../reference/glossary.md#hook) that run at a Spec Kit phase. Every Sanduq extension except
Scope is [standalone](../reference/glossary.md#standalone): it works without Workflow.

## Prerequisites

- A Spec Kit project with the Sanduq catalog registered. See [set up Spec Kit](../start/install-speckit.md).
- The tools listed for your extension in [prerequisites](../start/prerequisites.md).

## Install

```bash
specify extension add illustrate
```

Choose a different extension from the [extension pages](../README.md#extensions). If it
[requires](../reference/glossary.md#requires) another extension, add that one first, or let
`deps.py ensure` offer to add it.

## First prompt

<details>
<summary>Codex</summary>

```text
$speckit-illustrate-generate Create a state diagram of refund request, approval, rejection and settlement from specs/412-refund-approval.
```

</details>

<details>
<summary>Claude Code</summary>

```text
/speckit-illustrate-generate Create a state diagram of refund request, approval, rejection and settlement from specs/412-refund-approval.
```

</details>

## What you will see

An editable HTML diagram in the project theme. Illustrate has no hooks, so it runs only when you ask.

Extensions with hooks behave differently. Assure, User Manual, PR and Project declare optional hooks:
the host asks before it runs them. Assure and Project have an init command that can make their hooks
mandatory. See the [hooks reference](../reference/hooks.md).

## Next step

Add a second process, such as QA or a manual, with the [à-la-carte scenario](a-la-carte.md).

## Who enforces dependencies

Spec Kit does not install `requires.extensions`. Assure, PR and User Manual run `deps.py ensure`
before they use Illustrate. It follows `.specify/extension-dependencies.yml`: `prompt` (the default)
asks you, `auto` installs, and `manual` stops.

## Limits

- Scope is not standalone. It requires Workflow.
- Installing an extension does not [enable](../reference/glossary.md#enabled) its process. Run its
  init command when it has one.
