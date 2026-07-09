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

This command is **idempotent and context-aware**: run it as an `after_implement` hook (when the PR
may not exist yet) or manually at PR time — it converges on the same result and never duplicates.

- You can run it **before the PR exists**; it will generate the docs and ask whether to create the PR.
- You can run it **after the PR exists**; it will update the PR body with the latest feature-details content.

## User Input

$ARGUMENTS

Optional flags the user may pass:

- `--no-pr` — generate/refresh the docs only; do not touch any pull request.
- `--create-pr` — if no PR exists for the branch, create one without asking first.
- `--feature <path>` — override feature directory detection (e.g. `specs/006-...`).
- `--heading "<text>"` — override the PR section heading (default: _What have been developed and how to review it_).

## Behavior Overview

```
resolve feature  ->  gather ground truth  ->  generate diagram assets  ->  write docs/<feature>/  ->  handle the PR  ->  report
```

## Instructions

### 1. Resolve the active feature

- Read `.specify/feature.json` and take `feature_directory` (e.g. `specs/006-finance-settlement-ledger`).
  If `--feature` was supplied, use that instead.
- Derive the **feature slug** = the final path segment (e.g. `006-finance-settlement-ledger`).
- If `.specify/feature.json` is missing or unreadable, fall back to the current git branch name and
  the most recently modified directory under `specs/`; if still ambiguous, ask the user which feature.

### 2. Gather ground truth (never invent)

Read whatever exists for the feature so all generated content traces to real artifacts:

- `<feature_dir>/spec.md` (user stories, requirements, acceptance scenarios, edge cases, scope, assumptions, open questions)
- `<feature_dir>/plan.md`, `data-model.md`, `tasks.md`, `quickstart.md`, `research.md`, `contracts/*`
- Any existing `<feature_dir>/CHANGELOG.md` or `progress.yml` (reuse delivery facts: tests, coverage, commits, issue/PR numbers)
- `git log` for the branch (commit subjects, scope)

If something is unknown, **omit it** — do not fabricate test counts, coverage, issue numbers, or behavior.

### 3. Generate diagram assets when the implementation changed architecture or process flow

Before writing the feature documents, decide whether the implementation has architecture or process
flow impact:

- Use the `architecture-diagram` skill when the feature changes or clarifies architecture,
  infrastructure, service boundaries, data flow, integrations, security zones, deployment topology,
  or major component responsibilities.
- Use the `process-flow-diagram` skill when the feature changes or clarifies a user journey,
  approval flow, automation sequence, background job lifecycle, integration sequence, validation
  flow, or exception path.

For each applicable diagram:

1. Generate the source HTML using the corresponding illustration skill's design system.
2. Write source files under `docs/<feature-slug>/assets/diagrams/`, using names such as
   `<feature-slug>-architecture.html` and `<feature-slug>-process-flow.html`.
3. Export a PNG beside each HTML file, using the built-in html2canvas export path or an equivalent
   Playwright/Puppeteer screenshot of `#report-container`, with names such as
   `<feature-slug>-architecture.png` and `<feature-slug>-process-flow.png`.
4. Embed the PNG in `<Feature>-Explained.md` and link to the HTML source for inspection/export.
5. If no architecture or process impact exists, explicitly omit that diagram type. Do not invent one.
6. If PNG export is unavailable, keep the HTML source, add a clear "PNG export pending" note in the
   doc, and report the follow-up. Do not embed a broken image.
7. **Private-repo rule — PR descriptions cannot resolve repo-relative paths.** For any image that
   must appear _in the PR description_, reference it by its **raw branch URL**:
   `https://raw.githubusercontent.com/<account>/<repo>/<branch>/docs/<feature-slug>/assets/<name>.png`.
   This requires the PNG to be **committed and pushed on the feature branch first** (see step 5).
   Inside the `.md` docs (which are browsed in-repo) a relative path is fine; only the PR-body copy
   needs the absolute raw URL.

### 4. Write the two documents under `docs/<feature-slug>/`

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
4. **Architecture and process visuals** — if generated, embed the architecture PNG and/or process
   flow PNG with descriptive alt text, and add a nearby link to each source HTML file.
5. **What this feature can do — the scenarios, with examples** — the heart of the doc. One numbered
   scenario per capability, each with: a short _Story_ (concrete, named actors, real numbers reused
   consistently), what the system does, and a visual where it helps. Prefer the generated
   `process-flow-diagram` PNG for user/system workflows. Mermaid can be used only as a lightweight
   fallback when no exported diagram asset is available.
6. **Who does what** — the cast of actors and their boundaries.
7. **What this phase deliberately does NOT do** — scope boundaries, to set expectations.
8. **Caveats / pending decisions** — anything flagged as baseline-pending-sign-off or an open question.
9. **How confident should you be?** — summarize tests/coverage/quality in plain terms (only if known).
10. **Glossary** — plain meanings of any terms that appeared.

Footer: link back to `CHANGELOG.md`, the `specs/<feature-slug>/` spec, and any diagram HTML sources.

> Quality bar: a reader who has never seen the code should finish the feature-details doc knowing
> what the feature is, why it exists, every scenario it supports, and exactly what's out of scope.

### 5. Handle the pull request

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
  - With `--create-pr`, create it: `gh pr create --base <default-branch> --head <branch>
--title "<feature title>" --body-file <tmpfile>` (body = a short summary + the marked section).
  - Without `--create-pr`, **ask** the user whether to create the PR now. If they decline, write the
    docs only and tell them to re-run (or run `/speckit-pr-generate`) once the PR exists.

### 6. Report

Summarize: the doc paths written, diagram HTML/PNG assets generated, whether the PR was created or
updated (with its URL), and any follow-ups (e.g. "no PR yet — re-run after opening one"). State
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
