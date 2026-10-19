---
description: 'Adds missing E2E, screenshot, API sample, diagram and accessibility tasks to tasks.md. Use when asked to "check QA readiness" before implementation.'
---

# Analyze QA Coverage

Review the active Spec Kit feature before implementation and make sure `tasks.md` contains the E2E,
UI screenshot-capture, API sample, frontend, and documentation-readiness work needed for the later
QA manual.

## User Input

```text
$ARGUMENTS
```

Optional flags:

- `--feature <path>` - override feature directory detection, e.g. `specs/006-user-management`.
- `--report-only` - report missing tasks without editing `tasks.md`.

## Instructions

### 0. Load the QA contract

Read `.specify/extensions/assure/skills/assure/SKILL.md` and its `references/analysis.md` (feature
resolution, task block format, report shape). In lifecycle-integrated mode this command is a gate: do
not report success while critical acceptance scenarios lack concrete test or evidence tasks.

### 0a. Ensure the Illustrate dependency

```text
python .specify/extensions/assure/scripts/deps.py ensure illustrate
```

- Exit `0`: the dependency is ready. Load the Illustrate references only in step 3, immediately before
  adding a diagram task. Pass a "newer compatible release available" note on to the user.
- Non-zero exit: report the script's one-line result verbatim, continue the non-diagram analysis, skip
  the diagram bullet in step 3, and do not silently use another diagram system. If the line names a
  `specify extension add/update illustrate` recipe and the user approves it, re-run with `--approve`
  (under a `manual` policy the user runs the printed command themselves, then re-run this command).

### 1. Resolve the feature and scan the workspace

Resolve the active feature as the contract says. Read `spec.md`, `plan.md` and `tasks.md` (required),
then `quickstart.md`, `data-model.md`, `contracts/*`, `research.md` and the recent git diff when they
exist.

Run the workspace scan in check mode; this stage reads the inventory and must not write the memory
file (Document writes it):

```text
python .specify/extensions/assure/scripts/assure_scan.py --check
```

Read the printed inventory (one line per detected project, then the memory block) instead of walking
the tree. A frontend that the feature artifacts describe but the scan did not detect is
`planned/spec-only`, never detected implementation.

### 2. Identify impacted projects

Map the feature to projects from the inventory plus the plan, task file paths, contracts, routes, menu
names, UI screens, mobile flows, backend endpoints, changed files, and tests. Use the frontend rows to
decide where E2E, screenshot capture, QA assets, and manual index tasks go. When a feature affects a
planned frontend path that is not implemented yet, add tasks against the planned path and report the
project as `planned/spec-only`.

### 3. Build the documentation coverage matrix

For each user story and scenario in `spec.md`, determine whether the later QA manual will need:

- Web E2E test for the main user journey.
- Mobile E2E test for the main user journey.
- Screenshot-capture test for each screen, form, dialog, menu entry, validation state, permission
  state, empty state, error state, loading state, and expected result.
- An Illustrate generation/export task for every visual the feature evidence warrants. Only if step 0a
  confirmed `illustrate` is ready and the scenario warrants a visual: read
  `.specify/extensions/illustrate/skill/references/type-index.md`, choose the type, and read its
  `type-*.md`; read `SKILL.md` only when the diagram is created outside that recipe. Do not add a
  visual merely to fill a checklist.
- API contract or integration test that proves request and response bodies for API-only scenarios.
- Fixture or mock data task for deterministic screenshots and stable examples.
- Accessibility smoke test for generated manual pages and UI screenshots.
- Index/navigation update for the relevant project QA documentation.

Treat these as missing coverage when tasks are absent or too vague:

- A UI user story has no named E2E task.
- A new route, menu item, form, or validation flow has no screenshot-capture task.
- A visual the feature evidence warrants has no named Illustrate HTML + PNG export task.
- A backend/API-only scenario has no request/response sample validation task.
- A mobile-accessible scenario has only a web E2E task.
- A scenario is intentionally not available on mobile but no task records that limitation in the
  manual.
- A test task says only "add tests" without path, runner, scenario, or expected result.

### 4. Patch `tasks.md`

Unless `--report-only` was supplied, add the missing tasks following the task block rules and wording
examples in `references/analysis.md`. Ground every task in the spec, plan, contracts, or project
structure; do not invent screens, endpoints, or request/response bodies.

### 5. Record freshness and report

After all edits and validation succeed, record the analysis against the final feature and working
tree state:

```text
python .specify/extensions/assure/scripts/assure_state.py record --kind analyze --feature <feature-path> --output <feature-path>/tasks.md
```

Do not record successful evidence in `--report-only` mode or while critical gaps remain unresolved.

Report the contract's shape plus: missing coverage found; tasks added with their IDs (or, under
`--report-only`, the tasks that should be added); any unresolved ambiguity, especially parent feature
routing or mobile availability. Do not claim tests exist unless they are present in `tasks.md` or the
workspace.

## Quality Bar

After this command runs, a developer should be able to implement the feature and its E2E/API
coverage in one pass. The later `assure` documentation step should not discover that a screen,
mobile state, validation path, or API sample was never tested or captured.
