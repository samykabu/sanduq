# Assure

**Purpose:** make QA part of the Spec Kit lifecycle. Assure finds missing test and evidence work
before implementation, and writes a QA walkthrough for testers after it.

| | |
| --- | --- |
| Lifecycle phase | After `tasks`, before and after `implement` |
| Hooks | Three optional hooks; Assure Init can make the analysis hook mandatory ([hooks](../reference/hooks.md)) |
| Commands | `init`, `analyze`, `document` ([reference](../reference/commands.md#assure)) |
| Requires | Illustrate 2.x, enforced by `deps.py ensure` |
| Standalone | Yes |
| License | PolyForm Noncommercial 1.0.0 |

## Setup

```bash
specify extension add illustrate
specify extension add assure
```

```text
$speckit-assure-init Configure required QA analysis and tester documentation for the booking application.
```

Init asks for **integrated** or **manual** mode. Integrated mode, the recommended choice, makes the
`before_implement` analysis mandatory and tells PR to refresh QA documentation when it is stale. In
the managed Workflow, select QA through `$speckit-workflow-init` instead.

## Example

```text
$speckit-assure-analyze --feature specs/412-refund-approval Add missing duplicate settlement, rejection, permission and accessibility coverage.
$speckit-assure-document --feature specs/412-refund-approval Document runnable refund scenarios and the actual test evidence.
```

You get the missing tasks, tester steps, synthetic test data, expected results, and screenshots where
there is evidence. Freshness records are kept under `.specify/extensions/assure/state/`.

## How it runs

![QA analysis, actual project checks, and documented results](../diagrams/extension-assure.svg)

Configured hooks or the managed dispatcher call Analyze and Document. In manual mode you run them
yourself. Your project's checks supply the test results; Assure records them.
[Editable source](../diagrams/extension-assure.html).

## Limits

- Assure writes test documentation. It does not prove that tests passed.
- A walkthrough goes stale when the implementation changes. Run Document again.
- QA documentation is for testers. It is not the end-user manual.
- The old `qa` and `how-to-test` extension IDs are retired.

Package details: [Assure README](../../extensions/assure/README.md).
