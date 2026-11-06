# Pull Request Workflow Extension

For setup and a worked example, see [Install by host](https://github.com/samykabu/sanduq/blob/main/docs/start/install-by-host.md)
and the [pr page](https://github.com/samykabu/sanduq/blob/main/docs/extensions/pr.md).
Every command and its example is in the [command reference](https://github.com/samykabu/sanduq/blob/main/docs/reference/commands.md#pr).


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

Two standard-library scripts do the mechanical parts. `scripts/pr_changelog.py --feature <dir>`
seeds `CHANGELOG.md` from `scope-source.json`, `gh pr view`, `git log <base>..HEAD`, the checked
tasks by phase, `progress.yml`, stage receipts and `evidence/` files inside a marked facts block;
a rerun regenerates only that block. `scripts/pr_publish.py --feature <dir> --explained <doc>`
splices the marked section into the PR body, writes `<dir>/evidence/pr-body.md` (UTF-8, LF) and
`pr-body.lint.json`, lints closing references (Workflow's `pr_lint` when installed, the same rule
otherwise), refuses on findings, runs `gh pr edit` or `gh pr create`, and prints the Workflow PR
receipt fragment (`pr_url`, `pr_body_file`, `pr_lint_file`, `pr_body_sha256`, `evidence`). Exit
codes: 0 published, 1 lint findings, 2 bad input, 3 `gh` or `git` failed. Diagrams follow
`references/pr-diagram-recipe.md`, which reads Illustrate's type index and one type reference
instead of the whole Illustrate skill.

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
- `python` is required: `scripts/deps.py` runs the illustrate dependency check, and
  `scripts/pr_changelog.py` and `scripts/pr_publish.py` seed the changelog and publish the PR. None
  has a third-party
  dependency — nothing in the install/upgrade path installs a package's `requirements.txt` before
  its commands run, so `deps.py` parses `dependencies.yml` with a small built-in reader instead of
  requiring PyYAML.
- PR generation still writes the documentation if `git`, `gh`, authentication, or a remote is
  unavailable, and reports why it skipped the PR step.
- Diagram generation requires `illustrate >=2.0.0,<3.0.0`. Step 0 of `speckit.pr.generate` runs
  `python .specify/extensions/pr/scripts/deps.py ensure illustrate`, which checks Spec Kit's
  registry and follows the project's `.specify/extension-dependencies.yml` policy
  (`prompt`/`auto`/`manual`) before installing or updating it, printing one line and failing closed
  when the dependency cannot be brought into range. Nothing from Illustrate is loaded at step 0.
- `assure` and `user-manual` are optional integrations. The PR command never installs them implicitly,
  but enforces their configured policies when a target project has installed them.
- The PR image-embedding rules (commit-pinned `?raw=true` links, never `raw.githubusercontent.com`,
  contents-API verification) live in `references/pr-image-embedding.md` and are loaded only when the
  generated PR actually has a diagram or screenshot to embed. `pr_publish.py` rewrites relative image
  paths to those pinned links, and relative Markdown links to the same commit's blob URLs, itself, after checking each one, before the body is linted. Verification has two tiers, recorded
  in the receipt as `image_verification`: `api` (rendered `body_html` plus the contents API, both
  hosts) and `browser` (also loading in an authenticated browser, when the host has a browser tool).
- In a managed project the Workflow guard hook refuses `gh pr create|edit --body-file` without a
  matching sibling `.lint.json`, an inline `--body`/`-b`, and `gh pr create` from the default branch.

## Migrating from `pr-review`

The standalone `pr-review` extension and `/speckit-pr-review-process` command were retired in v2.0.0.
Remove the old extension, install or update `pr`, and use `/speckit-pr-review-feedback`:

```bash
specify extension remove pr-review
specify extension add pr --force
```

The former `devtools` equivalents were retired; these two extension commands are now canonical.
