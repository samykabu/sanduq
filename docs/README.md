# Sanduq documentation

Start with your [adoption level](reference/glossary.md#adoption-level): how much of Sanduq you want
to use. Then install, and use the reference when you need an exact command or hook.

## Choose an adoption level

| Level | You get | Start here |
| --- | --- | --- |
| 1. Skills only | One task, such as a diagram or a manual, in any supported host. No Spec Kit. | [Skills only](scenarios/skills-only.md) |
| 2. One extension | One process added to a Spec Kit project | [One extension](scenarios/one-extension.md) |
| 3. À-la-carte set | Several standalone processes, such as QA, docs and board sync | [À-la-carte set](scenarios/a-la-carte.md) |
| 4. Managed Workflow | One GitHub issue taken to a verified pull request, resumable | [Managed Workflow](scenarios/managed-workflow.md) |

## Start

| Task | Page |
| --- | --- |
| Check the tools and versions you need | [Prerequisites](start/prerequisites.md) |
| Create or prepare a Spec Kit project | [Set up Spec Kit](start/install-speckit.md) |
| Install on Codex, Claude Code or Claude Desktop, and set recipes | [Install by host](start/install-by-host.md) |
| Fix a common problem | [Troubleshooting](start/troubleshooting.md) |
| Upgrade, read changelogs, find moved pages | [Upgrades](start/upgrades.md) |

## Extensions

One page per extension: purpose, lifecycle phase, hooks, dependencies, setup, an example and limits.

| Extension | Purpose |
| --- | --- |
| [Workflow](extensions/workflow.md) | Resumable issue-to-PR dispatcher |
| [Scope](extensions/scope.md) | Issue scope, prerequisites and decomposition before Specify |
| [Project](extensions/project.md) | GitHub Project board sync |
| [Assure](extensions/assure.md) | QA readiness analysis and tester walkthrough |
| [User Manual](extensions/user-manual.md) | Audience-aware application manual |
| [PR](extensions/pr.md) | Feature docs, PR description and review feedback |
| [Illustrate](extensions/illustrate.md) | Themed diagrams and charts |
| [Memory](extensions/memory.md) | Project memory and recoverable spec archiving |

## Managed Workflow in depth

| Task | Page |
| --- | --- |
| Follow a feature through every stage | [Worked lifecycle](workflow/lifecycle.md) |
| Resume, upgrade or recover | [Operating guide](workflow/operating-guide.md) |
| Inspect state, progress and runners | [State, evidence and runners](workflow/operations.md) |
| Change QA or manual selection, or the CI gate | [Delivery policy](workflow/delivery-policy.md) |
| Look up stages, state files, schemas, runner policy, utilities, delegation | [Stages](workflow/stages.md) · [State files](workflow/state-files.md) · [Schemas](workflow/schemas.md) · [Runner policy](workflow/runner-policy.md) · [Utilities](workflow/utilities.md) · [Delegation](workflow/delegation.md) · [Development](workflow/development.md) |

## Reference

| Page | Contents |
| --- | --- |
| [Commands](reference/commands.md) | All 42 commands with an example each, and host syntax |
| [Hooks](reference/hooks.md) | Every hook: manifest defaults and the managed Workflow view (generated) |
| [Compatibility](reference/compatibility.md) | Hosts, tested versions and Spec Kit ranges |
| [Licenses](reference/licenses.md) | License per package |
| [Glossary](reference/glossary.md) | Terms used in these pages |

## Examples

| Example | Page |
| --- | --- |
| Draw a process and choose preset or custom colors | [Illustrate examples](illustrate-examples.md) |
| Bound a debate, run parallel reviews, or automate delegation | [Delegate Task examples](delegate-examples.md) |
| Compare real manual themes and install your own | [User Manual theme gallery](user-manual-examples.md) |

## Example conventions

The examples describe a **synthetic booking application** with Booking, Payments, and Operations
modules. Its GitHub repository is `example-org/booking-app`; issue **412**, titled **Refund approval**,
produces `specs/412-refund-approval/`. A customer requests a refund, an operator approves or rejects
it, and the payment provider returns the settlement result. Repeated approval must not settle twice.

Replace these identifiers with your own. Issue 412, task `T012`, PR 438, and release tags `v2.4.0`
and `v3.0.0` illustrate different identities; they are not live Sanduq records or promised
application behavior. Read your real API contract and tests before documenting the application.

Prompts use **Codex `$…` syntax**. See [command names](reference/commands.md#command-names) for other hosts.
Shell commands run in the consumer repository unless a step says **Sanduq checkout**.
Replace angle-bracket placeholders before execution. Screenshots and payloads use synthetic data.

## Maintain and contribute

| Task | Page |
| --- | --- |
| Find the owning source, test packages and submit a change | [Contributing](../CONTRIBUTING.md) |
| Write or edit these pages | [Style guide](style-guide.md) |
| Find logos and editable illustrations | [Asset index](assets/README.md) |
| Look up an exact package contract | [Extension source index](../extensions/README.md) |
