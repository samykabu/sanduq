---
name: pr-generate-description
description: Use when finishing a feature and preparing its pull request — generates a technical CHANGELOG, a plain-English feature-details document, and architecture/process diagram assets when relevant, then creates or updates the PR description with the feature details under the heading "What have been developed and how to review it". Trigger on "/devtools:pr-generate-description", "generate a detailed PR", "write the PR description", "document this feature for review", or when wrapping up a Spec Kit feature. Works with or without Spec Kit.
---

# Generate a Detailed PR

Turn a completed feature into two reviewer-facing artifacts and a rich pull-request description:

1. A **CHANGELOG** — a precise, technical record of what shipped.
2. A **feature-details document** — a plain-English, product-manager-friendly explanation of the
   feature, its role, and every scenario it supports, with examples and diagrams.

…then **create or update the pull request** for the current branch so the feature-details content
appears in its description under the heading **"What have been developed and how to review it"**.

This skill mirrors the Spec Kit `speckit.pr.generate` extension — same behavior — with a fallback for
repositories that don't use Spec Kit.

## When to use

- The user types `/devtools:pr-generate-description`, or asks to "generate a
  detailed PR", "write the PR description", or "document this feature for review".
- A feature/branch is implemented and you're preparing to open or finalize its PR.

## Optional arguments

- `--no-pr` — generate/refresh docs only; don't touch any PR.
- `--create-pr` — create the PR without asking if none exists.
- `--feature <path>` — override feature-directory detection.
- `--heading "<text>"` — override the PR section heading (default: _What have been developed and how to review it_).

## Process

```
resolve feature  ->  gather ground truth  ->  generate diagram assets  ->  write docs/<feature>/  ->  handle the PR  ->  report
```

### 1. Resolve the feature and its slug

- **Spec Kit projects:** if `.specify/feature.json` exists and is valid, use the
  `feature_directory` path it contains (e.g. `specs/006-finance-settlement-ledger`); the **slug**
  is the final path segment. If the override path does not exist, or if `.specify/feature.json`
  points to a missing directory, stop and ask the user for a valid feature directory instead of
  guessing.
- **Non-Spec-Kit fallback:** derive the slug from the current git branch by removing a leading
  `feature/`, `feat/`, or `bugfix/` prefix, then taking the final path segment after the last `/`;
  if the result is empty, ask the user for the feature name. Search for exactly one matching
  feature directory; if zero or multiple matches exist, ask the user for the exact feature
  directory path.

### 2. Gather ground truth (never invent)

Read whatever grounds the content so nothing is fabricated:

- Spec Kit: `<feature_dir>/spec.md`, `plan.md`, `data-model.md`, `tasks.md`, `quickstart.md`,
  `research.md`, `contracts/*`, any existing `CHANGELOG.md` / `progress.yml`.
- Otherwise: a design/spec/README for the work, plus `git log` for the branch (commit subjects).

Omit anything you can't source. Do **not** invent test counts, coverage, issue numbers, or behavior.
If the required sections cannot be supported by sourced artifacts, write only the sections that are
supported and explicitly mark the unsupported parts as "not sourced from repository artifacts"
rather than inventing them.

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

### 4. Write the two documents under `docs/<feature-slug>/`

Create the folder if needed; matching the spec/feature name keeps it wiki-ready.

**`CHANGELOG.md`** — [Keep a Changelog](https://keepachangelog.com/) style. Header (spec/branch/issue/PR
if known + what it builds on), then a dated version grouping: **Added**, **Changed**,
**Architecture & boundaries**, **Migration**, **Tests & quality**, **Scope (not in this phase)**,
**Open items**. Concrete and accurate; map requirements/acceptance to what shipped.

**`<Feature>-Explained.md`** — the plain-English, business/PM-facing narrative. Audience: a product
manager or commercial stakeholder, **not** an engineer. Friendly and descriptive; light humor and
real-world analogies welcome when they aid understanding. Define any unavoidable term. Structure
(scale to the feature, skip what doesn't apply):

1. **Title + subtitle** and a _one-paragraph version_ (whole feature in ~4 sentences).
2. **Why we needed this ("so what")** — the business problem, with an analogy.
3. **The building blocks in human words** — table mapping each concept to "what it really is" + analogy.
4. **Architecture and process visuals** — if generated, embed the architecture PNG and/or process
   flow PNG with descriptive alt text, and add a nearby link to each source HTML file.
5. **What this feature can do — scenarios, with examples** (the heart): one numbered scenario per
   capability, each with a concrete _Story_ (named actors, real numbers reused consistently), what the
   system does, and a visual where it helps. Prefer the generated `process-flow-diagram` PNG for
   user/system workflows. Mermaid can be used only as a lightweight fallback when no exported diagram
   asset is available. Cover happy paths **and** guardrails (rejections, immutability, idempotency,
   fail-closed).
6. **Who does what** — actors and their boundaries.
7. **What this deliberately does NOT do** — scope boundaries.
8. **Caveats / pending decisions** — baselines pending sign-off, open questions.
9. **How confident should you be?** — tests/coverage/quality in plain terms (only if known).
10. **Glossary** — plain meanings of any terms used.

Footer: link to `CHANGELOG.md`, the spec/design source, and any diagram HTML sources.

> Quality bar: a reader who has never seen the code finishes the feature-details doc knowing what the
> feature is, why it exists, every scenario it supports, and exactly what's out of scope.

### 5. Handle the pull request (unless `--no-pr`)

Run this as a numbered algorithm:

1. **Detect PR:** run `gh pr view --json number,url,body` for the current branch. If that fails,
   run `gh pr list --head <branch> --json number,url,body`. If `gh pr list --head <branch>` returns
   more than one PR, stop and ask the user which PR to update; do not guess. If no PR is found,
   proceed to step 3.
2. **Update existing PR:** build the section (heading + feature-details narrative) wrapped in
   idempotency markers:

   ```
   <!-- speckit-pr:start -->
   ## What have been developed and how to review it

   …feature-details content…
   <!-- speckit-pr:end -->
   ```

   If the PR body already contains the markers, **replace what's between them** (keep the rest of
   the body). If the PR body contains multiple marker pairs or malformed markers, stop and ask the
   user to clean the PR body first; do not silently choose one block. If no markers exist, append
   the marked section to the end. Apply with `gh pr edit <number> --body-file <tmpfile>`. Never
   create a second copy. If `gh pr edit` fails, report the failure, keep the generated docs, and
   do not retry silently.

3. **Create PR (if none exists):** derive the PR title from the spec header or the feature slug in
   Title Case. If no feature title can be sourced from the spec or branch, derive the title from
   the feature slug in Title Case and ask the user to confirm it before creating the PR. With
   `--create-pr`, create it immediately (`gh pr create --base <default-branch> --head <branch>
   --title "<feature title>" --body-file <tmpfile>`); otherwise **ask** whether to create it now. If
   the user declines, write docs only and tell the user to re-run once the PR exists. If
   `gh pr create` fails, report the failure, keep the generated docs, and do not retry silently.

### 6. Report

Summarize the doc paths written, diagram HTML/PNG assets generated, whether the PR was
created/updated (with URL), and follow-ups. State test/coverage figures only if sourced from real
artifacts.

## Idempotency

Fixed doc paths + marker-delimited PR section mean repeated runs (hook then manual) converge and never
duplicate.

## Graceful degradation

- **No `gh` / not authenticated / no remote:** write docs, skip PR handling, say so.
- **Not a git repo:** still generate docs from the spec/design.
- **No source artifacts / invalid feature path:** if the requested feature path is invalid, or no
  valid source artifacts can be found under the resolved directory, stop and ask for the correct
  feature directory instead of continuing with partial data.
- **Detached/odd branch state:** report and skip PR handling rather than PR'ing the wrong base.
