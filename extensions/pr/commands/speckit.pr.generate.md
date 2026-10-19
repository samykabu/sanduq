---
description: "Generates the feature CHANGELOG and details doc, then opens or updates the pull request; never merges. Use when asked to 'open the PR'."
---

# Generate a Detailed PR

Turn the work of a completed Spec Kit feature into two reviewer-facing artifacts and a rich
pull-request description:

1. A **CHANGELOG** — a precise, technical record of what shipped.
2. A **feature-details document** — a plain-English, product-manager-friendly explanation of the
   feature, its role, the scenarios it supports (with examples and diagrams).

…then **create or update the pull request** for the current branch so the feature-details content
appears in its description under the heading **"What have been developed and how to review it"**.

This command is **idempotent and context-aware**: run it as an `after_implement` hook or manually at
PR time — it converges on the same result and never duplicates. Before the PR exists it generates
the docs and creates the PR; after, it updates the PR body with the latest feature-details content.

## User Input

$ARGUMENTS

Optional flags the user may pass:

- `--no-pr` — generate/refresh the docs only; do not touch any pull request.
- `--create-pr` — accepted for backward compatibility; PR creation is already the default.
- `--feature <path>` — override feature directory detection (e.g. `specs/006-...`).
- `--heading "<text>"` — override the PR section heading (default: _What have been developed and how to review it_).

## Behavior Overview

```text
resolve feature -> documentation preflights -> gather ground truth -> generate diagrams -> write docs -> handle PR -> report
```

## Instructions

### 0. Ensure the Illustrate dependency

```text
python .specify/extensions/pr/scripts/deps.py ensure illustrate
```

Exit 0: continue (pass on a "newer compatible release available" note if printed). Nonzero: report
the printed line verbatim, continue the non-diagram work and skip diagram generation; if the line
names a `specify extension add/update illustrate` recipe and the user approves, re-run with
`--approve` and then this command.

### 1. Resolve the active feature

- Read `.specify/feature.json` and take `feature_directory` (e.g. `specs/006-finance-settlement-ledger`).
  If `--feature` was supplied, use that instead.
- Derive the **feature slug** = the final path segment (e.g. `006-finance-settlement-ledger`).
- If `.specify/feature.json` is missing or unreadable, fall back to the current git branch name and
  the most recently modified directory under `specs/`; if still ambiguous, ask the user which feature.

### 2. Enforce project-selected documentation preflights

Skip this section only when `--no-pr` was supplied. Run it before writing PR documentation or
creating/updating the PR. When `.specify/workflow.yml` exists, its `processes.qa` and
`processes.user_manual` selections govern the two preflights; installation alone enables neither.

#### QA

If `.specify/extensions/assure/assure-config.yml` exists and contains
`require_document_before_pr: true`:

1. Run `python .specify/extensions/assure/scripts/assure_state.py status --kind document --feature <feature-dir>`.
2. If `current` is false, execute `speckit.assure.document --feature <feature-dir>` with the current
   integration and wait for it to finish.
3. Run the status command again. Stop before PR handling if it is still missing/stale or required QA
   evidence remains incomplete. Do not allow an old file to satisfy the gate.

#### User Manual

If the `user-manual` extension is installed:

1. Require `User-Manual/manual.yml`. If it is missing, stop and run the interactive
   `speckit.user-manual.init` workflow; do not invent the module map during PR generation.
2. Run `python .specify/extensions/user-manual/scripts/manual_state.py status --feature <feature-dir>`.
3. If `current` is false, execute `speckit.user-manual.update --feature <feature-dir>` and wait for it
   to finish. This update must use plain audience-appropriate English and, when enabled, Arabic.
4. Recheck freshness. Stop before PR handling if it is still missing/stale or the manual audit fails.

Report every automatically executed preflight. Never install optional QA or User Manual extensions
from this command; enforce them only when the project has installed/configured them.

### 3. Gather ground truth (never invent)

Seed the technical record from facts first:

```text
python .specify/extensions/pr/scripts/pr_changelog.py --feature <feature-dir>
```

It writes `docs/<feature-slug>/CHANGELOG.md` with the header (spec, branch, issue, PR), the commit
subjects, the checked tasks by phase, `progress.yml` entries, stage receipts and evidence files
inside a marked block; a rerun regenerates only that block. Then read `<feature_dir>/spec.md`,
`plan.md`, `data-model.md`, `quickstart.md`, `research.md` and `contracts/*` for the narrative. If
something is unknown, **omit it** — do not fabricate test counts, coverage, issue numbers, or behavior.

### 4. Select and generate useful Illustrate assets

Decide first, from the gathered evidence, whether any visual would teach the reviewer more than
prose or a table. If none is warranted, skip this step; if step 0 failed, skip it and say so. Otherwise
load `.specify/extensions/pr/references/pr-diagram-recipe.md` and follow it: it names the type index
to choose from, the one `type-*.md` to load per diagram, the output paths, the export command and the
complexity budget. Do not load the whole Illustrate `SKILL.md` or `export.md` here.

Then: embed each PNG in `<Feature>-Explained.md` and link its HTML source; if PNG export is
unavailable, keep the HTML, add a "PNG export pending" note and report the follow-up, never a broken
image. **If this PR has any reviewer-facing diagram or screenshot** (from this step or from an
installed QA/User Manual extension), load `.specify/extensions/pr/references/pr-image-embedding.md`
before step 6 and follow it exactly; with no visuals, skip it.

### 5. Write the two documents under `docs/<feature-slug>/`

Create the folder if needed. The folder name **matches the spec folder name** so it can drop into a
wiki cleanly.

#### 5a. `docs/<feature-slug>/CHANGELOG.md`

Complete the skeleton from step 3 into a [Keep a Changelog](https://keepachangelog.com/)–style
record: leave the facts block as generated (a rerun regenerates it), and write the narrative,
**Architecture & boundaries**, **Migration** and **Scope (not in this phase)** outside it from spec
and plan. Keep **Added**, **Changed**, **Tests &
quality** and **Open items** concrete; map functional requirements / acceptance criteria to what shipped.

#### 5b. `docs/<feature-slug>/<Feature>-Explained.md`

The **plain-English, business/PM-facing narrative**. Audience: a product manager or commercial
stakeholder, _not_ an engineer. Friendly and descriptive; light humor and real-world analogies are
welcome when they aid understanding. Avoid jargon; define any unavoidable term. Use this proven
structure (scale each section to the feature — skip what doesn't apply):

1. **Title + one-line subtitle** and a _one-paragraph version_ (the whole feature in ~4 sentences).
2. **Why we needed this ("so what")** — the business problem, ideally with an analogy.
3. **The building blocks in human words** — a small table mapping each core concept to "what it
   really is" and a real-world analogy.
4. **Feature visuals** — embed every useful Illustrate PNG with descriptive alt text and add a
   nearby link to its source HTML. Explain what question each visual answers.
5. **What this feature can do — the scenarios, with examples** — the heart of the doc. One numbered
   scenario per capability, each with: a short _Story_ (concrete, named actors, real numbers reused
   consistently), what the system does, and a visual where it helps. Prefer a generated flowchart,
   sequence, state-machine, swimlane, or other fitting Illustrate asset for user/system
   workflows. Do not substitute Mermaid when the required Illustrate dependency is available.
6. **Who does what** — the cast of actors and their boundaries.
7. **What this phase deliberately does NOT do** — scope boundaries, to set expectations.
8. **Caveats / pending decisions** — anything flagged as baseline-pending-sign-off or an open question.
9. **How confident should you be?** — summarize tests/coverage/quality in plain terms (only if known).
10. **Glossary** — plain meanings of any terms that appeared.

Footer: link back to `CHANGELOG.md`, the `specs/<feature-slug>/` spec, and any diagram HTML sources.

> Quality bar: a reader who has never seen the code should finish the feature-details doc knowing
> what the feature is, why it exists, every scenario it supports, and exactly what's out of scope.

### 6. Handle the pull request

```text
python .specify/extensions/pr/scripts/pr_publish.py --feature <feature-dir> --explained docs/<feature-slug>/<Feature>-Explained.md [--heading "<text>"] [--no-pr]
```

The script detects the branch's PR, replaces the text between `<!-- speckit-pr:start -->` and
`<!-- speckit-pr:end -->` (or appends the marked section), writes the exact UTF-8/LF body to
`<feature-dir>/evidence/pr-body.md`, lints its closing references against the bound issue and its
prerequisites from `scope-source.json` with Workflow's `execution_tools.py pr-lint` rule into
`pr-body.lint.json` beside it, and only then runs `gh pr edit`, or pushes the branch and runs
`gh pr create`; it never publishes after a nonzero exit. When Workflow is absent, the script applies
the same closing-reference check on its own, so standalone PR use is unchanged and Workflow is never
required or installed merely for linting. It prints the PR receipt fragment (`pr_url`,
`pr_body_file`, `pr_lint_file`, `pr_body_sha256`, `evidence`): copy it into the receipt as printed.
Exit codes: 0 published; 1 the body closes a foreign, prerequisite or unbound issue: fix the
document and rerun; 2 bad input; 3 `gh` or `git` failed: report that the PR step was skipped and
why. With `--no-pr` it stops after the lint.

### 7. Report

Summarize: the doc paths written, diagram HTML/PNG assets generated, whether the PR was created or
updated (with its URL), and any follow-ups (for example, PR handling skipped because `gh` is not
authenticated). State test/coverage figures only if you sourced them from real artifacts.

## Idempotency

Fixed doc paths + marker-delimited PR section mean the hook-run and any manual re-run converge on the
same result. Re-running refreshes the docs and replaces (never duplicates) the PR section.

## Graceful Degradation

- **No `gh` / not authenticated / no remote:** write the docs, skip PR handling, and tell the user the
  PR step was skipped (and why).
- **Not a git repo:** still generate the docs from the spec artifacts.
- **No spec artifacts found:** ask the user for the feature directory rather than guessing content.
- **Detached/odd branch state:** report it and skip PR handling rather than creating a PR on the wrong base.
