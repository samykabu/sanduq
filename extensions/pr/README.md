# Detailed PR Generator Extension

Generate reviewer-facing documentation for a completed Spec Kit feature and inject it into the pull
request description — so every PR explains, in plain English, **what was developed and how to review it**.

## Overview

After a feature is implemented, this extension produces two artifacts under
`docs/<feature-slug>/` (the same name as the spec folder, so it drops cleanly into a wiki):

- **`CHANGELOG.md`** — a precise, technical record of what shipped (Keep a Changelog style).
- **`<Feature>-Explained.md`** — a plain-English, product-manager-friendly narrative covering the
  feature's purpose, role, and every scenario it supports, with examples plus architecture/process
  diagram PNGs when the implementation changed architecture or workflow.

When applicable, the command uses the `architecture-diagram` and `process-flow-diagram` skills to
generate source HTML under `docs/<feature-slug>/assets/diagrams/`, exports PNGs beside the source,
embeds the PNGs in the feature-details document, and links back to the HTML sources for
inspection/export.

It then **creates or updates the pull request** for the current branch, embedding the feature-details
narrative under the heading **"What have been developed and how to review it"** — delimited by
idempotency markers so re-runs refresh rather than duplicate.

## Command

| Command               | Invocation             | Description                                                                         |
| --------------------- | ---------------------- | ----------------------------------------------------------------------------------- |
| `speckit.pr.generate` | `/speckit-pr-generate` | Generate the CHANGELOG + feature-details doc with diagram assets when relevant, then create/update the PR description |

## Usage

```text
/speckit-pr-generate
```

If you want to generate the docs but do not want to create or update the PR:

```text
/speckit-pr-generate do not create a PR
```

Optional flags:

- `--no-pr` — generate/refresh docs only; don't touch any PR.
- `--create-pr` — create the PR without asking if none exists.
- `--feature <path>` — override feature-directory detection.
- `--heading "<text>"` — override the PR section heading.

## Lifecycle hook

Registered as an **optional** `after_implement` hook — after implementation finishes (and after any
`superspec.review`), Spec Kit prompts to run it. It is also invokable manually at any time, which is
the natural moment to run it once the PR exists.

```yaml
hooks:
  after_implement:
    command: speckit.pr.generate
    optional: true
```

Because the command is idempotent, running it both as the hook (docs first, PR maybe not yet open)
and again manually (PR now open) is safe and expected.

## Requirements

- `git` (optional) — to detect the branch and base.
- `gh` (optional, authenticated) — to create/update the PR. Without it, docs are still generated and
  PR handling is skipped with a notice.

## Portable equivalent

A standalone Claude skill with the same behavior — `/devtools:pr-generate-description` — is available
outside Spec Kit projects (it adds a fallback for repos without `.specify/`).
