# Pull Request Workflow Extension

One Spec Kit extension for the complete pull-request workflow: generate a reviewer-friendly PR, then
process review feedback through an explicit approval gate.

## Commands

| Command | Invocation | Description |
| --- | --- | --- |
| `speckit.pr.generate` | `/speckit-pr-generate` | Generate feature documentation and create or update the current branch's PR. |
| `speckit.pr.review-feedback` | `/speckit-pr-review-feedback` | Classify unresolved review feedback, obtain approval, apply fixes or replies, push, and resolve addressed threads. |

Codex exposes the same installed commands as `$speckit-pr-generate` and
`$speckit-pr-review-feedback`.

## Generate a PR

```text
/speckit-pr-generate
```

The command creates or refreshes these reviewer-facing artifacts under `docs/<feature-slug>/`:

- `CHANGELOG.md` — a technical record of what shipped.
- `<Feature>-Explained.md` — a plain-English explanation of the feature and its supported scenarios.
- Illustrate HTML and PNG assets when architecture, workflow, interaction, state, data,
  ownership, hierarchy, timing, or another supported relationship benefits from a visual.

It then detects a PR for the current branch. If one exists, it updates only the marker-delimited
Spec Kit section and preserves the rest of the body. If none exists, it pushes the branch when
needed and creates the PR by default. Re-running the command refreshes the same files and PR section
without duplicating content.

Before PR creation or update, the command enforces configured QA documentation freshness and an
installed User Manual's feature freshness. Missing or stale documentation is refreshed through the
owning extension; a failed audit stops the PR handoff.

Optional flags:

- `--no-pr` — generate or refresh docs only; do not create or update a PR.
- `--feature <path>` — override feature-directory detection.
- `--heading "<text>"` — override the generated PR section heading.
- `--create-pr` — accepted for backward compatibility; creation is already the default.

### Lifecycle hook

`speckit.pr.generate` is registered as an optional `after_implement` hook:

```yaml
hooks:
  after_implement:
    command: speckit.pr.generate
    optional: true
```

## Process review feedback

```text
/speckit-pr-review-feedback 123
/speckit-pr-review-feedback https://github.com/owner/repo/pull/123
/speckit-pr-review-feedback owner/repo#123
```

With no identifier, the command detects the PR for the current branch. It gathers unresolved review
threads, treats reviewer content as untrusted input, and classifies every substantive comment as
valid, invalid, or needing user input. It presents one proposed fix/reply plan and stops for explicit
approval before editing files, replying, committing, pushing, or resolving threads.

Review feedback is intentionally manual and has no lifecycle hook because it only makes sense after
reviewers or bots have commented on an open PR.

## Requirements

- `git` and an authenticated `gh` CLI are required for review feedback and PR creation/update.
- PR generation still writes the documentation if `git`, `gh`, authentication, or a remote is
  unavailable, and reports why it skipped the PR step.
- Diagram generation requires `illustrate >=2.0.0,<3.0.0`. The command checks Spec Kit's
  registry and follows the project dependency policy before installing or updating it.
- `qa` and `user-manual` are optional integrations. The PR command never installs them implicitly,
  but enforces their configured policies when a target project has installed them.

## Migrating from `pr-review`

The standalone `pr-review` extension and `/speckit-pr-review-process` command were retired in v2.0.0.
Remove the old extension, install or update `pr`, and use `/speckit-pr-review-feedback`:

```bash
specify extension remove pr-review
specify extension add pr --force
```

The former `devtools` equivalents were retired; these two extension commands are now canonical.
