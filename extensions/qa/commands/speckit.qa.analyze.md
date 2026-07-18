---
description: "Analyze Spec Kit plan/tasks for missing E2E, screenshot-capture, and API sample tasks, and create reusable project memory for QA documentation."
---

# Analyze QA Coverage

Review the active Spec Kit feature before implementation, create or refresh the reusable workspace
project memory, and make sure `tasks.md` contains the E2E, UI screenshot-capture, API sample,
frontend, and documentation-readiness work needed for the later QA manual.

Recommended lifecycle phase: `after_tasks`. At this point `spec.md`, `plan.md`, and `tasks.md`
exist, but implementation has not started, so missing tests can be added before developers begin.

Alternative phase: `before_implement` if a team prefers a final gate immediately before coding. Do
not use `after_implement` as the primary hook for this command because by then missing E2E work is
usually rework.

## User Input

```text
$ARGUMENTS
```

Optional flags:

- `--feature <path>` - override feature directory detection, e.g. `specs/006-user-management`.
- `--report-only` - report missing tasks without editing `tasks.md`.
- `--phase after_tasks|before_implement|manual` - record the user's selected lifecycle phase in the
  report. The recommendation remains `after_tasks`.

## Behavior Overview

```text
resolve feature -> load artifacts -> scan workspace -> update project memory -> map impacted projects -> audit tasks -> patch tasks.md -> report
```

## Instructions

### 0. Load the QA contract

Read `.specify/extensions/qa/skills/qa/SKILL.md` and its `references/analysis.md`. If the project
uses lifecycle-integrated mode, this command is a gate: do not report success while critical
acceptance scenarios lack concrete test or evidence tasks.

### 0a. Ensure the Illustrate dependency

Before resolving the feature, read `.specify/extensions/qa/dependencies.yml` and enforce its
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

- If `--feature` is supplied, use it.
- Otherwise read `.specify/feature.json` and use `feature_directory`.
- If feature detection fails, use the most recently modified directory under `specs/` only when it is
  unambiguous. If still ambiguous, ask the user for the feature path.

Required files:

- `<feature_dir>/spec.md`
- `<feature_dir>/plan.md`
- `<feature_dir>/tasks.md`

Optional but important files:

- `<feature_dir>/quickstart.md`
- `<feature_dir>/data-model.md`
- `<feature_dir>/contracts/*`
- `<feature_dir>/research.md`
- `.github/memory/project-memory.md` (create or refresh before impact analysis)
- Recent git diff and changed files, if available

### 2. Scan workspace and update project memory

Create or refresh `.github/memory/project-memory.md` before mapping feature impact. This command owns
the memory initialization pass; do not tell the user to run another command just to create the file.

Scan deeply from the workspace root while excluding generated/vendor folders such as `.git/`,
`node_modules/`, `bin/`, `obj/`, `dist/`, `build/`, `.next/`, `.nuxt/`, `.turbo/`, `.expo/`,
`coverage/`, `.cache/`, package-manager caches, and generated QA assets.

Use the existing memory file as a hint only. Compare it with the current marker scan, update stale
entries, add new projects, and add `Last scanned: <YYYY-MM-DD>`.

Detect project markers:

- Workspace/package boundaries: root `package.json` workspaces, `pnpm-workspace.yaml`, `nx.json`,
  `turbo.json`, `lerna.json`, `rush.json`, solution files, and package/app folders.
- Web frontend: `package.json` dependencies or scripts for React, Next.js, Vite, CRA, Angular, Vue,
  Nuxt, Svelte, SvelteKit, Remix, Astro, TanStack Router, React Router, Storybook, Playwright, or
  Cypress; plus `public/`, `pages/`, `app/`, `src/routes`, `src/pages`, `src/main.*`,
  `src/App.*`, `vite.config.*`, `next.config.*`, `angular.json`, `astro.config.*`, or
  `svelte.config.*`.
- Mobile frontend: React Native, Expo, `app.json`, `app.config.*`, `android/`, `ios/`,
  `metro.config.*`, `expo-router`, Detox, Maestro, or Appium.
- Backend/API: `*.csproj`, `*.sln`, `pyproject.toml`, `go.mod`, `Cargo.toml`, OpenAPI contracts,
  controllers, routers, API gateways, generated clients, or API test folders.
- Deployment/infrastructure: Docker, Compose, Helm, Terraform, Pulumi, ArgoCD, Kubernetes manifests,
  GitHub Actions, and deployment scripts.
- Tooling/documentation: plugin manifests, extension manifests, docs-only packages, templates,
  scripts, command specs, and generated agent/prompt files.

Also inspect `spec.md`, `plan.md`, `quickstart.md`, and contracts for planned project structure. If a
frontend is described in feature artifacts but no implementation marker exists yet, record it as
`planned/spec-only`, not as detected implementation.

The memory file must include these sections:

- `Frontend Coverage Summary`: state whether implemented web and mobile frontends were detected,
  whether only planned/spec frontend context exists, and which frontend paths are reusable for later
  documentation.
- `Frontend Project Inventory`: one row per web or mobile frontend, including project name, relative
  path, status (`implemented`, `planned/spec-only`, or `stale`), platform, framework/build tool,
  router or app shell evidence, public/assets directory, QA root, screenshot runner, key
  dev/build/test commands, and evidence source paths.
- `Detected Projects`: all other projects and workspace-level tooling, including role, stack
  markers, commands when discoverable, documentation root, QA output root, and notes.
- `Scan Markers`: marker files found or explicitly not found, especially frontend markers.
- `Maintenance Rules`: remind later commands to reuse the memory, verify it against current marker
  files, and update it when frontend markers appear or disappear.

If no web or mobile frontend is detected, state that explicitly in both `Frontend Coverage Summary`
and `Frontend Project Inventory` instead of leaving an empty section. If planned frontend context is
found, reference the source spec/plan/quickstart paths so the later document command can reuse that
context without guessing.

### 3. Identify impacted projects

Identify impacted projects from the freshly updated project memory plus the feature plan, task file
paths, contracts, routes, menu names, UI screens, mobile flows, backend endpoints, changed files, and
tests.

Pay special attention to web and mobile frontends. Use the `Frontend Project Inventory` to decide
where E2E, screenshot capture, QA assets, and manual index tasks should be added. When a
feature affects a planned frontend path that is not implemented yet, add tasks against the planned
path and mark the project status in the report as `planned/spec-only`.

### 4. Build the documentation coverage matrix

For each user story and scenario in `spec.md`, determine whether the later QA manual will
need one or more of the following:

- Web E2E test for the main user journey.
- Mobile E2E test for the main user journey.
- Screenshot-capture test for each screen, form, dialog, menu entry, validation state, permission
  state, empty state, error state, loading state, and expected result.
- An Illustrate generation/export task for every useful visual supported by the feature evidence:
  architecture, IT current-state, flowchart, sequence, state machine, ER/data model, timeline,
  swimlane, quadrant, radar, loop, nested, tree, org chart, layers, venn, pyramid, bar, line, Gantt,
  scatter, high-level, process, medallion, data flow, DP integration, or DP security matrix. Use the
  installed skill's selection guide and matching type reference; do not add a visual merely to fill
  a checklist.
- API contract or integration test that proves request and response bodies for API-only scenarios.
- Fixture or mock data task for deterministic screenshots and stable examples.
- Accessibility smoke test for generated manual pages and UI screenshots.
- Index/navigation update for the relevant project QA documentation.

Treat these as missing coverage when tasks are absent or too vague:

- A UI user story has no named E2E task.
- A new route, menu item, form, or validation flow has no screenshot-capture task.
- A materially useful architecture, decision, interaction, lifecycle, data-model, timeline,
  cross-role, hierarchy, ownership, layering, overlap, prioritization, funnel, quantitative,
  scheduling, loop, platform, process, or data-platform visual has no named Illustrate HTML +
  PNG export task.
- A backend/API-only scenario has no request/response sample validation task.
- A mobile-accessible scenario has only a web E2E task.
- A scenario is intentionally not available on mobile but no task records that limitation in the
  manual.
- A test task says only "add tests" without path, runner, scenario, or expected result.

### 5. Patch `tasks.md`

Unless `--report-only` was supplied, update `tasks.md`.

Rules:

- Preserve the existing Spec Kit task format:
  `- [ ] T### [P?] [US#?] Description with file path`
- Preserve existing task order and content.
- Do not duplicate existing E2E, screenshot, diagram, API sample, or documentation tasks.
- Continue numbering from the highest existing `T###`.
- Put user-story-specific gaps in that user story's `### Tests` section when one exists. If the
  story has no tests section, create `### QA readiness tasks` inside that story phase.
- Put cross-project or cross-cutting gaps in the final Polish/Cross-Cutting phase.
- Mark tasks `[P]` only when they write different files and do not depend on each other.
- Include exact target paths. If a path is inferred from plan structure, use the planned project
  root and keep it specific.
- If replacing a previous readiness block, refresh it idempotently. Prefer a markdown block with
  these markers when you create a dedicated section:

```markdown
<!-- qa-prepare:start -->
### QA readiness tasks

- [ ] T123 [P] [US1] Add Playwright E2E test for ...

<!-- qa-prepare:end -->
```

Task wording examples:

```markdown
- [ ] T041 [P] [US1] Add Playwright E2E test for admin password reset happy path in frontend/e2e/user-management/password-reset.spec.ts
- [ ] T042 [P] [US1] Add screenshot capture for User Management password reset states in frontend/e2e/qa/user-management-password-reset.capture.spec.ts
- [ ] T043 [P] [US1] Add API request/response fixture coverage for POST /api/users/{id}/password-reset in backend/tests/contracts/user-management-password-reset.test.ts
- [ ] T044 [P] [US1] Generate Illustrate sequence HTML and PNG assets for the password reset interaction in frontend/public/qa/assets/user-management/diagrams/user-management-password-reset-sequence.html
- [ ] T045 [US1] Update User Management QA documentation index under frontend/public/qa/features/user-management/index.html
```

### 6. Record freshness and report

After all edits and validation succeed, record the analysis against the final feature and working
tree state:

```text
python .specify/extensions/qa/scripts/qa_state.py record --kind analyze --feature <feature-path>
```

Do not record successful evidence in `--report-only` mode or while critical gaps remain unresolved.

Report:

- Feature path audited.
- Selected lifecycle phase and recommendation. If the user did not select a phase, state
  `after_tasks` as the recommendation.
- Project memory path written and frontend inventory summary.
- Impacted projects.
- Missing coverage found.
- Tasks added, with task IDs.
- If `--report-only` was used, list the tasks that should be added.
- Any unresolved ambiguity, especially parent feature routing or mobile availability.

Do not claim tests exist unless they are present in `tasks.md` or the workspace. Do not invent
screens, endpoints, or request/response bodies. Ground every task in the spec, plan, contracts, or
project structure.

## Quality Bar

After this command runs, a developer should be able to implement the feature and its E2E/API
coverage in one pass. The later `qa` documentation step should not discover that a screen,
mobile state, validation path, or API sample was never tested or captured.
