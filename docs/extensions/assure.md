# Assure

**Purpose:** make QA part of the Spec Kit lifecycle. Assure finds missing test and evidence work
before implementation, and writes a QA walkthrough for testers after it.

| | |
| --- | --- |
| Lifecycle phase | After `tasks`, before and after `implement` |
| Hooks | Three optional hooks; Assure Init can make the analysis hook mandatory ([hooks](../reference/hooks.md)) |
| Commands | `init`, `analyze`, `document` ([reference](../reference/commands.md#assure)) |
| Requires | Illustrate 2.x, enforced by `deps.py ensure`; Python 3.11 or later |
| Standalone | Yes |
| License | MIT |

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

![Assure sequence: assure.init sets the required or manual policy; assure.analyze checks readiness and adds missing tasks; you implement and run your project's tests; assure.document records steps and observed evidence; a freshness check flags changed code that needs an update.](../diagrams/extension-assure.animated.svg)

Configured hooks or the managed dispatcher call Analyze and Document. In manual mode you run them
yourself. Your project's checks supply the test results; Assure records them.
[Editable source](../diagrams/extension-assure.html).

Scripts do the mechanical parts. `assure_scan.py` detects the projects in the repository and keeps
`.github/memory/project-memory.md` current: Analyze only reads the result, Document writes it.
It skips the folders under `scan.exclude` in `assure-config.yml`, whose default list also covers
`.venv`, `venv`, `__pycache__`, `target`, `vendor`, `Pods` and `.gradle`. Inside a git work tree it
also skips the folders git ignores. `assure_scan.py --check`
prints the inventory and the `would write` line without writing; add `--show-block` to also print
the memory block. Init keeps an existing `assure-config.yml` and changes only its three lifecycle
values. `audit_qa.py` checks the
generated manual for image alt text and captions, broken relative links, the development-only
marker, and secret-shaped values. When Document runs again, the freshness status lists the changed
inputs and outputs, so only the affected parts are rewritten. The `documentation-gates.yml` CI
check checks out the PR head, not GitHub's merge commit, and runs `assure_state.py status --gate`,
which skips the check when `lifecycle.require_document_before_pr` is false. Init replaces an
unedited earlier `documentation-gates.yml`; for an edited one it prints the `ref:` line to add.

## Limits

- Assure writes test documentation. It does not prove that tests passed.
- A walkthrough goes stale when the implementation changes. Run Document again.
- QA documentation is for testers. It is not the end-user manual.
- The old `qa` and `how-to-test` extension IDs are retired.

Package details: [Assure README](../../extensions/assure/README.md).
