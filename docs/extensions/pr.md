# PR

**Purpose:** write a feature changelog and a plain-English explanation with diagrams, then create or
update the branch's pull request. It also processes review feedback through an approval step.

| | |
| --- | --- |
| Lifecycle phase | After `implement`; after review |
| Hooks | One optional `after_implement` hook ([hooks](../reference/hooks.md)) |
| Commands | `generate`, `review-feedback` ([reference](../reference/commands.md#pr)) |
| Requires | Illustrate 2.x, enforced by `deps.py ensure`; uses Assure and User Manual when installed |
| Standalone | Yes |
| License | PolyForm Noncommercial 1.0.0 |

## Setup

```bash
specify extension add illustrate
specify extension add pr
```

Git and a signed-in `gh` are needed to push and to open the pull request.

## Example

```text
$speckit-pr-generate --feature specs/412-refund-approval Update the existing PR with behavior, verified checks and readable diagrams.
$speckit-pr-review-feedback example-org/booking-app#438 Classify unresolved feedback and present the fix and reply plan for approval.
```

Generate writes `docs/<feature-slug>/CHANGELOG.md`, a feature explanation and diagrams, then updates a
marked section of the PR description. Add `--no-pr` to write the documents only.

## How it runs

![PR sequence: pr.generate, or managed Finalize, validates fresh QA and manual evidence and then updates the PR or writes documents only; pr.review-feedback inspects unresolved review comments, you approve a concrete plan, and only then are fixes applied, verified and pushed.](../diagrams/extension-pr.animated.svg)

Before it touches the PR, Generate checks QA and manual freshness for the extensions you installed.
Review Feedback shows a plan and waits for your approval before it edits, replies, commits, pushes
or resolves threads. In the managed Workflow, Finalize runs Generate.
[Editable source](../diagrams/extension-pr.html).

## Limits

- Without `git`, `gh`, authentication or a remote, Generate still writes the documents and reports
  why it skipped the PR.
- The old `pr-review` extension is retired. Use `review-feedback`.

Package details: [PR README](../../extensions/pr/README.md).
