# Sanduq documentation

Start with the task you need to finish. Setup lives in one guide; examples and operating details
live in the guides that own them. Package READMEs hold the detailed integration contracts.

## Learn and use

| Task | Guide |
| --- | --- |
| Install a skill, plugin, or managed workflow | [Getting started](getting-started.md) |
| Pick a standalone skill and see its output | [Portable skills](skills.md) |
| Draw a process and select preset or custom colors | [Illustrate examples](illustrate-examples.md) |
| Bound a debate, run parallel reviews, or automate delegation | [Delegate Task examples](delegate-examples.md) |
| Compare real manual themes and install your own | [User Manual theme gallery](user-manual-examples.md) |
| Configure an extension and use every public command | [Spec Kit extensions](extensions.md) |
| See user commands, hooks, states, and optional paths | [Extension workflow gallery](extension-workflows.md) |
| Follow a feature through every recorded stage | [Worked lifecycle](skill-guide.md) |
| Resume, upgrade, or diagnose evidence | [Workflow operating guide](workflow-guide.md) |
| Inspect state, delegation usage, and runner policy | [Workflow operations reference](workflow-operations.md) |
| Change QA/manual selection or CI gate policy | [Delivery setup and policy](sanduq-delivery-usage.md) |
| Look up an exact package contract | [Extension source index](../extensions/README.md) |

## Maintain and contribute

| Task | Guide |
| --- | --- |
| Find canonical source, test packages, and submit a change | [Contributing](../CONTRIBUTING.md) |
| Understand provider and command ownership | [Source ownership](workflow-source-ownership.md) |
| Check tested hosts and providers | [Compatibility](workflow-compatibility.md) |
| Review documentation coverage and placement | [Documentation review](documentation-review.md) |
| Find logos and editable illustrations | [Asset index](assets/README.md) |

## Example conventions

The examples describe a **synthetic booking application** with Booking, Payments, and Operations
modules. Its GitHub repository is `example-org/booking-app`; issue **412**, titled **Refund approval**,
produces `specs/412-refund-approval/`. A customer requests a refund, an operator approves or rejects
it, and the payment provider returns the settlement result. Repeated approval must not settle twice.

Replace these identifiers with your own. Issue 412, task `T012`, PR 438, and release tags `v2.4.0`
and `v3.0.0` illustrate different identities; they are not live Sanduq records or promised
application behavior. Read your real API contract and tests before documenting the application.

Prompts use **Codex `$…` syntax**. See [command names](getting-started.md#command-names) for other hosts.
Shell commands run in the consumer repository unless a step says **Sanduq checkout**.
Replace angle-bracket placeholders before execution. Screenshots and payloads use synthetic data.

## Design and verification records

These records explain prior decisions and tests. Their version statements describe the recorded
experiment; use the catalog and current guides for installation.

- [Delivery implementation plan](sanduq-delivery-implementation-plan.md)
- [Delivery verification](sanduq-delivery-verification.md)
- [Workflow implementation plan](workflow-extension-implementation-plan.md)
- [Workflow acceptance audit](workflow-acceptance-audit.md)
- [Workflow pilot review](workflow-pilot-review.md)
- [Native prototype results](native-workflow-prototype-results.md)
- [Native prototype illustration](sanduq-native-workflow-prototype.html)
- [Orchestration task design](orchestration-tasks.md)
- [Implementation progress record](workflow-implementation-progress.md)
- [Fresh-session prompt](workflow-resume-prompt.md)
