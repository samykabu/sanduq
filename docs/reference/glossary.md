# Glossary

These are the terms Sanduq pages use. Each page links a term here the first time it uses it.

## Adoption level

How much of Sanduq you use. There are four: skills only, one extension, an à-la-carte set of
extensions, and the managed Workflow. See the [scenarios](../README.md#choose-an-adoption-level).

## Catalog

A JSON file that lists published extensions, their versions and download URLs. Spec Kit reads it
when you run `specify extension add`. Sanduq's catalog is `catalog.json` at the repository root.

## Checkpoint

A saved point in a managed feature's run. It holds the completed stages, pending tasks and the
active claim, so a new session can continue where the last one stopped. Workflow writes it to
`specs/<feature>/workflow/checkpoint.json`.

## Claim

A lock that gives one stage of one feature to one agent at a time. A second agent cannot start a
competing stage while the claim is held. Workflow records a token for each claim, which you need to
recover an interrupted one.

## Dispatcher

The part of Workflow that decides which stage runs next, takes the claim, calls the host command
that does the work, and checks the receipt. Only Workflow has a dispatcher.

## Enabled

A process that your project has selected. Installing an extension does not enable its process.
For example, QA runs in the managed Workflow only after `speckit.workflow.init` selects it.

## Evidence gate

A CI check that reads a feature's receipts and fails or warns when evidence is missing or stale.
Its mode is `disabled`, `advisory` or `required`. It does not run your application's tests.

## Extension

A versioned Spec Kit package that adds commands and, often, hooks. You install it with
`specify extension add <id>`. Sanduq has eight extensions.

## Feature

One unit of work in a Spec Kit project, stored in `specs/<number>-<name>/`. In the managed Workflow
a feature is bound to one GitHub issue.

## Freshness

Whether a piece of evidence still matches the files it describes. Evidence becomes stale when the
files it covers change.

## Harness

An agent command-line tool that the Delegate Task skill can start, such as Codex or Claude Code.
A harness is a target for delegated work. It is different from a [host](#host).

## Hook

An instruction in an extension's manifest that runs a command before or after a Spec Kit phase, for
example `after_tasks`. A **mandatory** hook (`optional: false`) runs automatically. An **optional**
hook (`optional: true`) asks you first. See the [hooks reference](hooks.md).

## Host

The agent application you work in: Codex, Claude Code or Claude Desktop. Spec Kit calls the host
an integration.

## Installed

An extension or skill whose files are present in your project. Installed is not the same as
[enabled](#enabled).

## Managed Workflow

The Workflow extension running a feature from Scope to a pull request through its
[dispatcher](#dispatcher).

## Orchestrator

The agent that coordinates implementation. It hands tasks to [workers](#worker), checks their
results, and commits each verified phase.

## Overlay

A preset command that Sanduq places in front of an upstream Spec Kit command. The upstream command
still runs; the overlay adds Sanduq's rules first. Overlays come from the `presets/` packages.

## Plugin bundle

A Claude Code plugin that installs one or more portable skills. Sanduq's marketplace offers three:
`illustration-tools`, `dev-tools` and `agent-tools`.

## Portable skill

Agent instructions and scripts for one task that work without Spec Kit. Sanduq's seven portable
skills live in [sanduq-skills](https://github.com/samykabu/sanduq-skills).

## Preset

A Spec Kit package that changes existing commands rather than adding new ones. Sanduq ships three:
`workflow`, `scope-gate` and `scope-brainstorm`.

## Receipt

A record that a stage finished. It lists the inputs, the outputs and fingerprints of the evidence.
Workflow checks receipts before it moves on.

## Requires

A hard dependency. If extension A requires B, A does not work without B. Spec Kit records
`requires.extensions` but does not install or enforce it. Workflow's installer and each package's
`deps.py ensure` do.

## Stage

One step of the managed Workflow, such as `plan`, `tasks` or `verify`. There are sixteen. See
[stages](../workflow/stages.md).

## Standalone

An extension that works without Workflow. Every Sanduq extension except Scope is standalone.

## Worker

An agent that receives one bounded task from the [orchestrator](#orchestrator) and reports its
changed files and check results.
