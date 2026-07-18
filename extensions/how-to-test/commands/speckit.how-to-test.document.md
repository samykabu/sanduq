---
description: "Generate or update the QA-facing How-To-Test manual for a completed Spec Kit feature."
---

# Generate How-To-Test Manual

Produce or update an internal QA-facing How-To-Test manual for the completed active Spec Kit
feature. The manual is a development-only human walkthrough, not a replacement for automated tests.

Recommended lifecycle phase: `after_implement`.

Run this after implementation completion validation and the full relevant test suite. If the target
Spec Kit project has an implementation-review hook, run this command after that review. If no review
hook exists, run it at `after_implement` before PR handoff or human QA review so the reviewer gets
fresh screenshots, API examples, and manual validation steps.

## User Input

```text
$ARGUMENTS
```

Optional flags:

- `--feature <path>` - override feature directory detection, e.g. `specs/006-user-management`.
- `--project <path>` - limit manual generation to one impacted project after the workspace scan.
- `--skip-screenshots` - allowed only when the feature has no UI or screenshot tooling is missing;
  document the reason in the manual.
- `--phase after_implement|after_review|before_review|manual` - record when the command was run.

## Behavior Overview

```text
resolve feature -> scan workspace -> update project memory -> find impacted projects -> generate diagram assets -> generate manual -> capture screenshots/API samples -> update indexes -> report
```

## Instructions

### 0. Ensure the Illustrate dependency

Before resolving the feature, read `.specify/extensions/how-to-test/dependencies.yml` and enforce its
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
- Derive `feature-slug` from the final feature directory segment.

Read all available feature artifacts:

- `spec.md`
- `plan.md`
- `tasks.md`
- `quickstart.md`
- `data-model.md`
- `research.md`
- `contracts/*`
- existing docs under `docs/<feature-slug>/`
- recent git diff/log for the branch

Never invent behavior, screens, endpoints, examples, test counts, or coverage.

### 2. Verify readiness

- Confirm implementation tasks relevant to the feature are complete or clearly mark the manual as a
  draft when completion evidence is missing.
- Check for E2E, screenshot-capture, API contract/integration, and manual smoke-test tasks in
  `tasks.md` or the workspace.
- If important coverage is missing, report it and suggest running `/speckit-how-to-test-analyze`.
  Continue only if enough evidence exists to generate an honest draft.

### 3. Scan workspace and update project memory

Create or refresh `.github/memory/project-memory.md`.

Scan deeply from the workspace root while excluding generated/vendor folders such as `.git/`,
`node_modules/`, `bin/`, `obj/`, `dist/`, `build/`, `.next/`, `.nuxt/`, `.turbo/`, `.expo/`,
`coverage/`, `.cache/`, package-manager caches, and generated How-To-Test assets.

If `/speckit-how-to-test-analyze` already created `.github/memory/project-memory.md`, reuse it as
the starting point, then verify it against the current marker scan before writing manuals. Never
trust stale memory blindly.

Detect project markers:

- Workspace/package boundaries: root `package.json` workspaces, `pnpm-workspace.yaml`, `nx.json`,
  `turbo.json`, `lerna.json`, `rush.json`, solution files, and package/app folders.
- Web frontend: React, Next.js, Vite, CRA, Angular, Vue, Nuxt, Svelte, SvelteKit, Remix, Astro,
  TanStack Router, React Router, `public/`, `pages/`, `app/`, `src/routes`, `src/pages`,
  `src/main.*`, `src/App.*`, `vite.config.*`, `next.config.*`, `angular.json`,
  `astro.config.*`, `svelte.config.*`.
- Mobile frontend: React Native, Expo, `app.json`, `app.config.*`, `android/`, `ios/`,
  `metro.config.*`, `expo-router`.
- Backend/API: `*.csproj`, `*.sln`, `pyproject.toml`, `go.mod`, `Cargo.toml`, OpenAPI contracts,
  controllers, routers, API gateways.
- Deployment/infrastructure: Docker, Compose, Helm, Terraform, Pulumi, ArgoCD, GitHub Actions.
- Tooling/documentation: plugin manifests, extension manifests, docs-only packages, templates,
  scripts.

Also inspect the active feature's `spec.md`, `plan.md`, `quickstart.md`, and contracts for planned
project structure. If a frontend is described in feature artifacts but no implementation marker
exists yet, record it as `planned/spec-only`, not as detected implementation.

For each project, record name, relative path, role, stack markers, run/test commands when
discoverable, documentation root, How-To-Test output root, and screenshot runner.

The memory file must keep the same reusable shape as the analyze command:

- `Frontend Coverage Summary`.
- `Frontend Project Inventory` with one row per web or mobile frontend, including status,
  framework/build tool, public/assets directory, How-To-Test root, screenshot runner, commands, and
  evidence source paths.
- `Detected Projects`.
- `Scan Markers`.
- `Maintenance Rules`.

If no web or mobile frontend is detected, say so explicitly. If only planned/spec frontend context
exists, reference the source feature artifacts so this command can generate an honest draft without
pretending implementation files exist.

### 4. Determine impacted projects and parent feature

Map the feature to all impacted projects using `project-memory.md`, feature artifacts, changed files,
routes, menu definitions, form schemas, validators, API contracts, generated clients, mobile
navigation, deployment/config changes, and tests.

Pay special attention to:

- UI screens, dialogs, forms, menu items, navigation, empty/loading/error states, validation
  messages, permission states, and role gates.
- Mobile screens or the explicit absence of mobile access.
- Backend/API endpoints, jobs, events, integrations, data migrations, and permission checks.

Route documentation under the product parent that a real user would recognize:

- New feature: `<how-to-test-root>/features/<feature-slug>/index.html`.
- Enhancement: update the existing parent feature page or add a child page, e.g.
  `features/user-management/password-reset.html`.
- Do not create a disconnected top-level feature page for a sub-feature. For example, password reset
  belongs under User Management.

If parent routing is ambiguous, inspect existing docs, route names, menu labels, and spec language.
Ask the user only when evidence conflicts.

### 5. Generate the manual

For each impacted project, write a self-contained HTML manual and update the project index. For
multi-project workspaces, update `<workspace-root>/how-to-test/index.html` as the aggregating index.

Output conventions:

- Web frontend: `<public-dir>/how-to-test/features/<parent-feature>/index.html` or child page under
  that parent, assets in `<public-dir>/how-to-test/assets/<parent-feature>/`.
- Mobile frontend: `<project-root>/how-to-test/features/<parent-feature>/index.html` or child page,
  assets in `<project-root>/how-to-test/assets/<parent-feature>/`.
- Generic/backend/tooling: `<project-root>/how-to-test/features/<parent-feature>/index.html` or
  child page, assets in `<project-root>/how-to-test/assets/<parent-feature>/`.
- Diagram sources: `<assets-dir>/diagrams/*.html` with PNG exports beside them.

Manual content, in order:

1. Cover and TOC, marked "Development-only draft".
2. Prerequisites and dev tooling: start commands, dev URLs, dashboards, environment variable names
   only, and redacted test-account guidance.
3. Illustrate visuals where applicable:
   - Use the installed `illustrate` selection guide to choose among all twenty-seven types:
     architecture, IT current-state, flowchart, sequence, state machine, ER/data model, timeline,
     swimlane, quadrant, radar, loop, nested, tree, org chart, layers, venn, pyramid, bar, line,
     Gantt, scatter, high-level, process, medallion, data flow, DP integration, and DP security
     matrix.
   - Match the visual grammar to the evidence: components/connections use architecture; branching
     logic uses flowchart; ordered messages use sequence; lifecycle transitions use state machine;
     entities/relationships use ER; dated events use timeline; cross-role handoffs use swimlane;
     containment/hierarchy uses nested or tree; ownership/escalation uses org chart; abstractions use
     layers; overlap uses venn; rank/drop-off uses pyramid/funnel; two-axis positioning uses
     quadrant; quantitative comparison/trends/distribution use bar, line, radar, or scatter;
     schedules use Gantt; reinforcing cycles use loop; legacy landscapes use IT current-state;
     platform/data topology uses high-level, medallion, data flow, DP integration, or DP security
     matrix; multi-actor data handoffs use process.
   - Save source HTML under `<assets-dir>/diagrams/`, export PNG beside it, embed the PNG in the
     manual, and link to the HTML source for inspection/export.
   - If no supported visual improves the manual, say no diagram was needed; do not invent one.
4. One plain-English section per user story or use case. Each section must include a real-life user
   scenario, preconditions, numbered tester steps, expected result after meaningful actions, and
   validation/error/empty/loading/permission states when applicable.
5. Screenshots for every form, screen, page, dialog, menu entry, and important state. Each image must
   include alt text and a one-line caption that names the scenario and expected result.
6. Request/response samples for headless API endpoints, backend-only flows, or scenarios not
   available from mobile. Include method, path, intended caller, redacted headers, request body,
   response status, response body, and field explanations.

### 6. Generate diagrams, screenshots, and API samples

Do not hand-take screenshots or diagram exports.

- Diagrams: load the relevant
  `.specify/extensions/illustrate/skill/references/type-*.md`, generate source HTML from the
  selected Illustrate template/variant, then export PNG with the installed
  `scripts/export_diagram.py` utility and `references/export.md` contract. Keep HTML sources and
  PNGs together under
  `<assets-dir>/diagrams/`, embed PNGs, and link the HTML sources.
- If diagram PNG export cannot run, keep the HTML source, mark the PNG as pending in the manual, and
  report the follow-up. Do not embed a broken image.

- Web UI: add or run a Playwright capture spec that mocks all backend endpoints the feature UI
  depends on with deterministic data. Capture full-page PNGs into the feature assets directory.
- Mobile UI: use the project's existing mobile E2E runner (`Detox`, `Maestro`, `Appium`, Expo test
  tooling) when available. If mobile is intentionally unavailable, document that explicitly.
- API-only flows: derive examples from contracts first. If contracts are missing or stale, infer from
  integration tests/dev stubs and mark examples as `(inferred)` with the source path. If running
  server behavior differs from the contract, mark `(mismatch)` and include the actual response with a
  note to update the contract.

Apply redaction rules everywhere. Never include plaintext passwords, API keys, bearer tokens,
refresh tokens, session IDs, cookies, private keys, OAuth codes, database URLs, connection strings,
or full `.env` values.

### 7. Validate

- Smoke-test the generated HTML.
- Verify every `<img>` has `alt` text and a caption.
- Verify referenced assets exist.
- Verify index links work.
- Verify production builds do not ship or link development-only How-To-Test docs.

### 8. Report

Report:

- Feature path and lifecycle phase used.
- Impacted projects.
- Manual paths written.
- Diagram HTML/PNG assets written or omitted as not applicable.
- Screenshot/API sample assets written.
- Index files updated.
- Any missing coverage, skipped screenshots, inferred API samples, mismatches, or follow-up tasks.

State clearly when the manual is a draft because implementation review, screenshots, API samples, or
tests were incomplete.
