---
description: 'Generates or refreshes the development-only QA test manual from real evidence. Use when asked to "write the QA manual" after the tests pass.'
---

# Generate QA Manual

Produce or update an internal QA test manual for the completed active Spec Kit feature. The manual is
a development-only human walkthrough, not a replacement for automated tests. Run it after
implementation, the full relevant test suite and any implementation review, before PR handoff or
human QA review.

## User Input

```text
$ARGUMENTS
```

Optional flags:

- `--feature <path>` - override feature directory detection, e.g. `specs/006-user-management`.
- `--project <path>` - limit manual generation to one impacted project after the workspace scan.
- `--skip-screenshots` - allowed only when the feature has no UI or screenshot tooling is missing;
  document the reason in the manual.

## Instructions

### 0. Load the QA contract

Read `.specify/extensions/assure/skills/assure/SKILL.md` and its `references/documentation.md`. Keep
this tester-facing artifact separate from the audience-aware application documentation under
`User-Manual/`.

### 0a. Ensure the Illustrate dependency

```text
python .specify/extensions/assure/scripts/deps.py ensure illustrate
```

- Exit `0`: the dependency is ready. Load the Illustrate references only in step 5, when a diagram is
  actually going to be generated. Pass a "newer compatible release available" note on to the user.
- Non-zero exit: report the script's one-line result verbatim, continue the non-diagram work, skip
  diagram generation, and do not silently use another diagram system. If the line names a
  `specify extension add/update illustrate` recipe and the user approves it, re-run with `--approve`
  (under a `manual` policy the user runs the printed command themselves, then re-run this command).

### 1. Resolve the feature and read its inputs

Resolve the active feature as the contract says and derive `feature-slug` from the final directory
segment. Then check for an earlier run:

```text
python .specify/extensions/assure/scripts/assure_state.py status --kind document --feature <feature-path>
```

- State missing: read the full set: `spec.md`, `plan.md`, `tasks.md`, `quickstart.md`,
  `data-model.md`, `research.md`, `contracts/*`, existing docs under `docs/<feature-slug>/`, and the
  recent git diff/log for the branch.
- State present and `current: false`: read the `changed_inputs` and `changed_outputs` it lists and
  the existing manual; update only what they affect. `current: true`: nothing changed since the last
  record; refresh only what the user asked for.

Never invent behavior, screens, endpoints, examples, test counts, or coverage.

### 2. Verify readiness

- Confirm implementation tasks relevant to the feature are complete, or clearly mark the manual as a
  draft when completion evidence is missing.
- Check for E2E, screenshot-capture, API contract/integration, and manual smoke-test tasks in
  `tasks.md` or the workspace. If important coverage is missing, report it and suggest running
  `speckit.assure.analyze`. Continue only if enough evidence exists to generate an honest draft.

### 3. Scan the workspace and refresh project memory

```text
python .specify/extensions/assure/scripts/assure_scan.py
```

The script rewrites the block between `<!-- assure-scan:start -->` and `<!-- assure-scan:end -->` in
`.github/memory/project-memory.md` (this stage's permitted side effect) and prints the inventory. Read
the printed inventory instead of walking the tree. When the feature artifacts describe a frontend the
scan did not detect, add a `planned/spec-only` row below the end marker with the source spec, plan or
quickstart path; the script keeps text outside its markers.

### 4. Determine impacted projects and parent feature

Map the feature to all impacted projects using the inventory, feature artifacts, changed files,
routes, menu definitions, form schemas, validators, API contracts, generated clients, mobile
navigation, deployment/config changes, and tests. Pay special attention to UI screens, dialogs,
forms, menu items, navigation, empty/loading/error states, validation messages, permission states and
role gates; mobile screens or the explicit absence of mobile access; backend/API endpoints, jobs,
events, integrations, data migrations, and permission checks.

Route documentation under the product parent that a real user would recognize:

- New feature: `<qa-root>/features/<feature-slug>/index.html`.
- Enhancement: update the existing parent feature page or add a child page, e.g.
  `features/user-management/password-reset.html`. Do not create a disconnected top-level page for a
  sub-feature.

If parent routing is ambiguous, inspect existing docs, route names, menu labels, and spec language.
Ask the user only when evidence conflicts.

### 5. Generate the manual

For each impacted project, write a self-contained HTML manual and update the project index. For
multi-project workspaces, update `<workspace-root>/qa/index.html` as the aggregating index.

Output conventions:

- Web frontend: `<public-dir>/qa/features/<parent-feature>/index.html` or a child page under that
  parent, assets in `<public-dir>/qa/assets/<parent-feature>/`.
- Mobile, generic, backend or tooling project: `<project-root>/qa/features/<parent-feature>/index.html`
  or a child page, assets in `<project-root>/qa/assets/<parent-feature>/`.
- Diagram sources: `<assets-dir>/diagrams/*.html` with PNG exports beside them.

Manual content, in order:

1. Cover and TOC, marked "Development-only draft".
2. Prerequisites and dev tooling: start commands, dev URLs, dashboards, environment variable names
   only, and redacted test-account guidance.
3. Illustrate visuals where applicable. Only if step 0a confirmed `illustrate` is ready and a visual
   improves verification: read `.specify/extensions/illustrate/skill/references/type-index.md`,
   choose the type, and read its `type-*.md`; read `SKILL.md` only when the diagram is created
   outside that recipe. Save source HTML under `<assets-dir>/diagrams/`, export PNG beside it, embed
   the PNG, and link the HTML source. If no visual improves the manual, say no diagram was needed.
4. One plain-English section per user story or use case: a real-life user scenario, preconditions,
   numbered tester steps, expected result after meaningful actions, and
   validation/error/empty/loading/permission states when applicable.
5. Screenshots for every form, screen, page, dialog, menu entry, and important state. Each image is
   a `<figure>` with non-empty `alt` text and a one-line `<figcaption>` naming the scenario and
   expected result.
6. Request/response samples for headless API endpoints, backend-only flows, or scenarios not
   available from mobile: method, path, intended caller, redacted headers, request body, response
   status, response body, and field explanations.

### 6. Generate diagrams, screenshots, and API samples

Do not hand-take screenshots or diagram exports.

- Diagrams: generate source HTML from the selected Illustrate type reference, then export PNG with
  the installed `scripts/export_diagram.py` and the `references/export.md` contract. If PNG export
  cannot run, keep the HTML source, mark the PNG as pending in the manual, and report the follow-up.
  Do not embed a broken image.
- Web UI: add or run a Playwright capture spec that mocks all backend endpoints the feature UI
  depends on with deterministic data. Capture full-page PNGs into the feature assets directory.
- Mobile UI: use the project's existing mobile E2E runner (`Detox`, `Maestro`, `Appium`, Expo test
  tooling) when available. If mobile is intentionally unavailable, document that explicitly.
- API-only flows: derive examples from contracts first. If contracts are missing or stale, infer from
  integration tests/dev stubs and mark examples as `(inferred)` with the source path. If running
  server behavior differs from the contract, mark `(mismatch)` and include the actual response with a
  note to update the contract.

Apply the contract's redaction rule everywhere.

### 7. Audit

```text
python .specify/extensions/assure/scripts/audit_qa.py <manual-path> [<manual-path> ...]
```

The script checks that every `<img>` has non-empty `alt` text and a `<figcaption>`, that every
relative `src` and `href` resolves, that the "Development-only draft" marker is present, and that no
secret-shaped value survived redaction. Fix every finding, then confirm production builds do not
ship or link development-only QA docs.

### 8. Record freshness and report

After the audit passes, record the document state and every generated manual path relative to the
repository root:

```text
python .specify/extensions/assure/scripts/assure_state.py record --kind document --feature <feature-path> --output <manual-path>
```

Repeat `--output` for every generated index, manual, or required evidence artifact. Do not record a
successful state while the manual remains a draft because required tests, screenshots, or API
samples are missing.

Report the contract's shape plus: diagram HTML/PNG assets written or omitted as not applicable;
screenshot/API sample assets written; index files updated; any missing coverage, skipped screenshots,
inferred API samples, mismatches, or follow-up tasks. State clearly when the manual is a draft because
implementation review, screenshots, API samples, or tests were incomplete.
