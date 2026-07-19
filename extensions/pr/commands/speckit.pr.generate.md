---
description: "Generate the feature CHANGELOG + plain-English feature-details doc, then create or update the PR description with the feature details under a review heading."
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
PR time — it converges on the same result and never duplicates.

- You can run it **before the PR exists**; it will generate the docs and create the PR by default.
- You can run it **after the PR exists**; it will update the PR body with the latest feature-details content.

## User Input

$ARGUMENTS

Optional flags the user may pass:

- `--no-pr` — generate/refresh the docs only; do not touch any pull request.
- `--create-pr` — accepted for backward compatibility; PR creation is already the default.
- `--feature <path>` — override feature directory detection (e.g. `specs/006-...`).
- `--heading "<text>"` — override the PR section heading (default: _What have been developed and how to review it_).

## Behavior Overview

```
resolve feature -> documentation preflights -> gather ground truth -> generate diagrams -> write docs -> handle PR -> report
```

## Instructions

### 0. Ensure the Illustrate dependency

Before resolving the feature, read `.specify/extensions/pr/dependencies.yml` and enforce its
`illustrate` requirement.

1. Read `.specify/extensions/.registry` as the installed-version source of truth.
2. Read the optional project policy at `.specify/extension-dependencies.yml`. Supported
   `update_policy` values are:
   - `prompt` (default): ask before `specify extension add illustrate` or
     `specify extension update illustrate`.
   - `auto`: the user has pre-authorized dependency installation and updates.
   - `manual`: never mutate dependencies; report the exact command the user must run.
3. If `illustrate` is absent, disabled, or outside the declared SemVer range, follow the policy
   and install/update it. Never make this extension-state change under `prompt` without explicit
   approval.
4. For an installed compatible version, use `.specify/extensions/.dependency-checks.json` to avoid
   catalog checks more often than `check_interval_hours`. When due, run
   `specify extension info illustrate` (read-only), compare the catalog version with the
   registry version, and follow the update policy if a newer compatible release exists.
5. After any add/update, re-read the registry and verify the version before continuing. Record the
   checked time and installed version in `.specify/extensions/.dependency-checks.json`.
6. Load `.specify/extensions/illustrate/skill/SKILL.md` and resolve its references/assets
   relative to that skill directory. This direct resource path works in the current run even if the
   agent only discovers newly registered skills in a new conversation.
7. If installation/update is declined or unavailable, continue the non-diagram work, explicitly skip
   diagram generation, and report the missing dependency. Do not silently use another diagram
   system.


### 1. Resolve the active feature

- Read `.specify/feature.json` and take `feature_directory` (e.g. `specs/006-finance-settlement-ledger`).
  If `--feature` was supplied, use that instead.
- Derive the **feature slug** = the final path segment (e.g. `006-finance-settlement-ledger`).
- If `.specify/feature.json` is missing or unreadable, fall back to the current git branch name and
  the most recently modified directory under `specs/`; if still ambiguous, ask the user which feature.

### 2. Enforce installed documentation preflights

Skip this section only when `--no-pr` was supplied. Run it before writing PR documentation or
creating/updating the PR.

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

Read whatever exists for the feature so all generated content traces to real artifacts:

- `<feature_dir>/spec.md` (user stories, requirements, acceptance scenarios, edge cases, scope, assumptions, open questions)
- `<feature_dir>/plan.md`, `data-model.md`, `tasks.md`, `quickstart.md`, `research.md`, `contracts/*`
- Any existing `<feature_dir>/CHANGELOG.md` or `progress.yml` (reuse delivery facts: tests, coverage, commits, issue/PR numbers)
- `git log` for the branch (commit subjects, scope)

If something is unknown, **omit it** — do not fabricate test counts, coverage, issue numbers, or behavior.

### 4. Select and generate useful Illustrate assets

Before writing the feature documents, use the installed `illustrate` skill's selection guide to
decide whether a visual teaches the reviewer more than prose or a table. Choose only types supported
by the evidence:

- **Architecture** for components, boundaries, integrations, infrastructure, security zones, or
  deployment topology.
- **Flowchart** for branching validation or decision logic.
- **Sequence** for time-ordered messages between users, services, jobs, or external systems.
- **State machine** for lifecycle states, transitions, guards, or status behavior.
- **ER/data model** for entities, important fields, and relationships.
- **Timeline** for releases, migrations, events, or phased behavior over time.
- **Swimlane** for cross-functional processes and ownership handoffs.
- **Quadrant** for two-axis prioritization or positioning grounded in feature decisions.
- **Nested** for containment, scope, tenancy, or boundary hierarchy.
- **Tree** for parent-child relationships or branching hierarchy.
- **Org chart** for human/agent/team ownership, routing, reporting, or escalation.
- **Layer stack** for abstraction levels or ordered platform layers.
- **Venn** for meaningful overlap between no more than three sets.
- **Pyramid/funnel** for ranked hierarchy, maturity, or conversion/drop-off.
- **Radar/spider** for comparing entities across three to five quantitative criteria.
- **Loop/flywheel** for reinforcing cycles around shared accumulated state.
- **Bar** for categorical quantitative comparison; **line** for continuous trends; **scatter** for
  distribution/correlation; **Gantt** for scheduled tasks and phases.
- **High-level** for an end-to-end platform or data stack on a cluster.
- **IT current-state** for a legacy landscape grouped by phase or department.
- **Process** for multi-actor sequential work with data handoffs.
- **Medallion** for tiered data storage, quality levels, and access policy.
- **Data flow** for role-scoped pipeline steps; **DP integration** for source-to-core-to-consumer
  topology; **DP security matrix** for per-role or per-component access permissions.

For each applicable diagram:

1. Load the matching `.specify/extensions/illustrate/skill/references/type-*.md` and generate
   the source HTML using the selected Illustrate template/variant.
2. Write source files under `docs/<feature-slug>/assets/diagrams/`, using names such as
   `<feature-slug>-architecture.html`, `<feature-slug>-sequence.html`, or
   `<feature-slug>-state-machine.html`.
3. Export a PNG beside each HTML file with the installed Illustrate
   `scripts/export_diagram.py` utility and its `references/export.md` contract.
4. Embed the PNG in `<Feature>-Explained.md` and link to the HTML source for inspection/export.
5. Follow the skill's complexity budget and split an overloaded diagram into overview/detail assets.
6. If no supported visual materially improves comprehension, omit diagrams. Do not invent one.
7. If PNG export is unavailable, keep the HTML source, add a clear "PNG export pending" note in the
   doc, and report the follow-up. Do not embed a broken image.
8. **Private-repo rule — PR descriptions cannot resolve repo-relative paths.** For any image that
   must appear _in the PR description_, reference it by its **raw branch URL**:
   `https://raw.githubusercontent.com/<account>/<repo>/<branch>/docs/<feature-slug>/assets/<name>.png`.
   This requires the PNG to be **committed and pushed on the feature branch before PR handling**.
   Inside the `.md` docs (which are browsed in-repo) a relative path is fine; only the PR-body copy
   needs the absolute raw URL.

### 5. Write the two documents under `docs/<feature-slug>/`

Create the folder if needed. The folder name **matches the spec folder name** so it can drop into a
wiki cleanly.

#### 4a. `docs/<feature-slug>/CHANGELOG.md`

A [Keep a Changelog](https://keepachangelog.com/)–style technical record. Header block with spec
path, branch, tracking issue/PR (if known), and what it builds on. Then a single dated version
section grouping changes under: **Added**, **Changed**, **Architecture & boundaries** (if relevant),
**Migration** (if relevant), **Tests & quality**, **Scope (not in this phase)**, **Open items**.
Be concrete and accurate; map functional requirements / acceptance criteria to what shipped.

#### 4b. `docs/<feature-slug>/<Feature>-Explained.md`

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

Unless `--no-pr` was passed:

- Detect the PR for the current branch:
  `gh pr view --json number,url,body` (or `gh pr list --head <branch> --json number,url,body`).
- Build the **section content**: the heading (default **`## What have been developed and how to
review it`**), then the full feature-details narrative (the body of `<Feature>-Explained.md`),
  wrapped in idempotency markers:

  ```
  <!-- speckit-pr:start -->
  ## What have been developed and how to review it

  …feature-details content…
  <!-- speckit-pr:end -->
  ```

- **If a PR exists:**
  - If the body already contains `<!-- speckit-pr:start -->`…`<!-- speckit-pr:end -->`, **replace
    everything between the markers** (preserve all other PR body content above/below). Never append
    a second copy.
  - Otherwise, append the marked section to the end of the existing body (keep the existing body intact).
  - Apply with `gh pr edit <number> --body-file <tmpfile>`.
- **If no PR exists:**
  - Resolve the repository's default branch. Never create a PR from the default branch itself.
  - If the current branch has no upstream or remote head, push it with
    `git push --set-upstream origin <branch>` so GitHub can use it as the PR head.
  - Create the PR without asking: `gh pr create --base <default-branch> --head <branch>
--title "<feature title>" --body-file <tmpfile>` (body = a short summary + the marked section).
  - `--create-pr` may still be supplied by existing callers, but does not change this default.

### 7. Report

Summarize: the doc paths written, diagram HTML/PNG assets generated, whether the PR was created or
updated (with its URL), and any follow-ups (for example, PR handling skipped because `gh` is not
authenticated). State
test/coverage figures only if you sourced them from real artifacts.

## Idempotency

Fixed doc paths + marker-delimited PR section mean the hook-run and any manual re-run converge on the
same result. Re-running refreshes the docs and replaces (never duplicates) the PR section.

## Graceful Degradation

- **No `gh` / not authenticated / no remote:** write the docs, skip PR handling, and tell the user the
  PR step was skipped (and why).
- **Not a git repo:** still generate the docs from the spec artifacts.
- **No spec artifacts found:** ask the user for the feature directory rather than guessing content.
- **Detached/odd branch state:** report it and skip PR handling rather than creating a PR on the wrong base.
