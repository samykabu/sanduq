---
name: how-to-test
description: "Use when a feature or specification implementation is complete (alongside the full-suite run and PR) and you need to produce or update an internal QA-facing How-To-Test manual for development-only use: an HTML walkthrough covering every user case, with architecture/process diagrams, Playwright screenshots (captured against mocked backend endpoints only) for web pages, and request/response samples for headless APIs. Supports single-project and multi-project workspaces."
---

# how-to-test

Produce (or update) an internal QA-facing **How-To-Test manual** intended for development and QA
staff (not external end users). Treat it as part of "done", alongside the full-suite run and the PR.
The manual is a draft QA guide a human can follow by hand to validate every user case — not a
substitute for automated tests.

If the workspace contains multiple projects (e.g. a monorepo or multi-repo workspace), generate a
separate manual per impacted project and a **workspace-level index** aggregating all of them.

## Initialization: workspace discovery and project memory

Before generating any manual, perform a workspace initialization pass. This is mandatory even when
the user points at one feature, because the feature may affect more than one project.

1. Scan the workspace root deeply, excluding generated/vendor folders such as `.git/`,
   `node_modules/`, `bin/`, `obj/`, `dist/`, `build/`, `.next/`, `.turbo/`, `.expo/`, `coverage/`,
   and package-manager caches.
2. Look for project markers:
   - Web frontend: `package.json` with React, Next.js, Vite, CRA, Angular, Vue, Svelte, Remix,
     `src/routes`, `pages`, `app`, `public`, `vite.config.*`, `next.config.*`.
   - Mobile frontend: `package.json` with React Native or Expo, `app.json`, `app.config.*`,
     `android/`, `ios/`, `metro.config.*`, `expo-router`.
   - Backend/API: `*.csproj`, `*.sln`, `pyproject.toml`, `go.mod`, `Cargo.toml`, OpenAPI contracts,
     controller/router folders, API gateway config.
   - Deployment/infrastructure: `Dockerfile`, `docker-compose*.yml`, Helm charts, Terraform,
     Pulumi, ArgoCD manifests, GitHub Actions workflows.
   - Tooling/documentation: plugin manifests, extension manifests, report templates, docs-only
     packages, scripts.
3. For every detected project, record:
   - Project name and root path, relative to the workspace root.
   - Role (`web frontend`, `mobile frontend`, `backend/API`, `shared library`, `deployment`,
     `infrastructure`, `tooling`, `documentation`, or another specific role).
   - Stack markers and key commands (`npm run dev`, `dotnet run`, `dotnet aspire run`,
     `docker compose up`, `uv run`, etc.).
   - Documentation root and How-To-Test output root.
   - Whether UI screenshots are expected, and with which runner (`Playwright`, `Detox`, `Maestro`,
     `Appium`, etc.).
4. Create or update `.github/memory/project-memory.md`. If `.github/memory/` does not exist, create
   it. The memory file must list all detected projects, their roles, stack markers, run/test
   commands when discoverable, and notes about frontend coverage. If no web or mobile frontend is
   detected, state that explicitly instead of leaving the section empty.
5. Reuse the memory file on later runs, but never trust it blindly: compare it with the current
   marker scan, update stale entries, and add a "Last scanned" date.

For multi-project workspaces:

- Generate manuals only for the impacted projects, but keep the memory file workspace-wide.
- If a shared `how-to-test/` directory already exists at the workspace root, maintain the
  workspace-level index there.
- Otherwise, each project gets its own How-To-Test root and the workspace gets an aggregating
  index at `<workspace-root>/how-to-test/index.html`.

## Feature impact analysis and documentation routing

At the start of the documentation process, analyze the implemented feature before writing files:

1. Read the feature artifacts and delivery evidence that exist: `spec.md`, `plan.md`, `tasks.md`,
   `quickstart.md`, `contracts/*`, `data-model.md`, recent commits, changed files, test files, route
   definitions, menu configuration, form schemas, validators, API contracts, and mobile navigation.
2. Determine every impacted project from `.github/memory/project-memory.md` plus the current changed
   files. Pay special attention to:
   - UI/UX screens, pages, dialogs, forms, empty/error/loading states, menu items, navigation routes,
     permissions, role gates, and validation messages.
   - Mobile-specific screens or flows, including whether the flow is unavailable from mobile.
   - Backend/API endpoints, events, jobs, integrations, data migrations, and permission checks.
   - Shared libraries, generated clients, deployment/config changes, and infrastructure dependencies.
3. Route the manual to the impacted project's documentation root under the relevant feature:
   - New feature: create `<project-how-to-test-root>/features/<feature-slug>/index.html`.
   - Enhancement to an existing feature: update the existing parent feature page or add a child page
     below that parent, e.g. `features/user-management/password-reset.html`.
   - Do not create a disconnected top-level feature when the work belongs under an existing parent.
     For example, "reset a user's password" belongs inside User Management documentation, not in a
     brand-new Password Reset feature group.
4. If the parent feature is ambiguous, inspect existing docs and route/menu names. Prefer the
   product parent that a real user would recognize. Ask the user only when the evidence conflicts.

## Security and redaction rules

The manual is for internal QA, but it must not collect or publish secrets. Never include plaintext
passwords, API keys, bearer tokens, refresh tokens, session IDs, cookies, private keys, OAuth codes,
database URLs, connection strings, or full `.env` values in generated HTML, screenshots, request
samples, logs, or comments.

When documenting prerequisites:
- List environment variable names and purpose only; use placeholders such as `<REDACTED>` or
  `<set locally>`.
- For seeded dev accounts, include non-secret identifiers such as usernames/emails only when they
  are already documented test identities. Do not include passwords; say to retrieve them from the
  approved secret store or existing team runbook.
- Redact `Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key`, OAuth, CSRF, and similar headers from
  every curl output and request/response sample.
- If an existing test fixture contains realistic-looking credentials, replace the value with
  `<REDACTED>` before writing it into the manual.

If a flow needs authentication, prefer mocked/stubbed auth responses with fake tokens. Do not capture
screenshots of pages that visibly show real secrets or personal data; mask or replace that data in
the Playwright route mocks first.

## Output conventions

Output paths depend on the impacted project type detected. Choose the best match, then place the
manual under the correct feature parent as described above.

### Web frontend (Vite / Next.js / CRA)

- **Manual:** `<public-dir>/how-to-test/features/<parent-feature-slug>/index.html` for a new feature,
  or `<public-dir>/how-to-test/features/<parent-feature-slug>/<child-feature-slug>.html` for an
  enhancement under an existing feature (self-contained, inline CSS).
  Use slug format `<ticket-number>-<short-name>` lowercase, hyphen-separated, ASCII only (e.g.
  `1234-plan-catalog`), max 50 chars.
- **Assets:** `<public-dir>/how-to-test/assets/<parent-feature-slug>/*.png`.
- **Diagram sources:** `<public-dir>/how-to-test/assets/<parent-feature-slug>/diagrams/*.html`
  with PNG exports beside them.
- **Stripped from production build:** add a Vite plugin or build exclusion that strips the
  whole `how-to-test/` directory so dev credentials never ship to prod.
- **In-app link (Development only):** gate on an environment variable or build flag
  (e.g. `import.meta.env.DEV`, `NODE_ENV === 'development'`, `__DEV__`). Never linked in
  production.

### Mobile frontend (React Native / Expo)

- **Manual:** `<project-root>/how-to-test/features/<parent-feature-slug>/index.html` or a child page
  under that parent.
- **Assets:** `<project-root>/how-to-test/assets/<parent-feature-slug>/*.png`.
- **Diagram sources:** `<project-root>/how-to-test/assets/<parent-feature-slug>/diagrams/*.html`
  with PNG exports beside them.
- **Screenshots:** capture with the project's existing mobile E2E tool when available
  (`Detox`, `Maestro`, `Appium`, Expo test tooling). If the flow is not available from mobile,
  document that explicitly and include the API or web fallback scenario instead.

### Generic (no web frontend detected)

- **Manual:** `<project-root>/how-to-test/features/<parent-feature-slug>/index.html` or a child page
  under that parent.
- **Assets:** `<project-root>/how-to-test/assets/<parent-feature-slug>/*.png`.
- **Diagram sources:** `<project-root>/how-to-test/assets/<parent-feature-slug>/diagrams/*.html`
  with PNG exports beside them.

### Screenshots & test naming

Use filenames `<feature-slug>--<scenario-slug>--<state-slug>.png` and a test file named
`<nn>-howto-<feature-slug>.spec.ts` to avoid collisions. Document naming in the manual.

### Index file

Place an `index.html` in each `how-to-test/` directory — a TOC with a brief description of each
feature/manual and a link to it. In a multi-project workspace, create a **workspace-level index** at
`<workspace-root>/how-to-test/index.html` that lists all impacted project manuals grouped by project,
plus a per-project index inside each project's how-to-test directory.

## What the manual must contain (ordered subtasks)

Proceed in the order below — each step depends on the previous one.

1. **Scaffold HTML** — Create the file with a Cover + TOC with anchor links; mark it a
   Development-only draft. Include the full HTML document structure.
2. **Prerequisites & dev tooling** — how to start the app in development, any seeded dev
   test account identifiers, required environment variable names, dev URLs / dashboards. Apply the
   redaction rules above; do not print secrets or passwords.
3. **Architecture and process visuals** where applicable:
   - Use the `architecture-diagram` skill when the feature changes or clarifies architecture,
     infrastructure, service boundaries, data flow, integrations, security zones, deployment
     topology, or major component responsibilities.
   - Use the `process-flow-diagram` skill when the feature changes or clarifies a user journey,
     approval flow, automation sequence, background job lifecycle, integration sequence, validation
     flow, or exception path.
   - Save the diagram HTML source under the feature's `diagrams/` asset folder, export a PNG beside
     it, embed the PNG in the manual, and link to the HTML source for inspection/export.
   - If no architecture or process impact exists, say that no diagram was needed; do not invent one.
4. **One section per user story / use case**, written in plain English. Each section must include:
   - A real-life user scenario with concrete actors and intent.
   - Preconditions and the user's starting point.
   - Numbered steps a tester follows.
   - Expected result after each meaningful action, not only at the end.
   - Validation, error, empty, loading, and permission-denied states when the feature includes them.
5. **Screenshots for every form, screen, page, dialog, menu entry, and important state** (see below).
   Each `<img>` must have an `alt` attribute and a one-line caption describing the scenario and
   expected result (e.g., "Admin opens User Management and sees the reset password action enabled for
   an active user"). Ensure the HTML page passes an automated a11y smoke check.
6. **Request/response samples for headless API endpoints, backend-only flows, and scenarios not
   accessible from mobile** — derive shapes from the feature's API contract (e.g.
   `contracts/openapi.yaml`, `spec/openapi.json`, `api/*.http`); show method, path, intended caller
   (e.g., web-client, mobile-client, internal-service) or OAuth `aud` claim, request headers with
   secrets redacted, request body, response status, response body, and a plain-English description
   of what each important field means. If the API contract is missing or out-of-date, generate
   samples from the server's dev stub or integration tests and mark them with "(inferred)" including
   the source file/path used. If samples differ from the running dev server, mark the sample with
   "(mismatch)" and include the actual curl response from the dev server plus a note instructing to
   update the API contract.

### Checklist

- [ ] Cover + TOC present and marked Development-only draft
- [ ] Prerequisites section complete (dev start command, redacted test-account/env-var guidance, URLs)
- [ ] Architecture/process diagrams included as PNGs with HTML source links, or explicitly omitted as not applicable
- [ ] User story sections present with real-life scenarios, numbered step lists, and expected results
- [ ] Screenshots for each form/page/dialog/menu/state — each has `alt` text and caption; HTML passes a11y smoke check
- [ ] API samples include request and response bodies derived from API contract (or marked "(inferred)"/"(mismatch)" if not)
- [ ] Feature is routed under the correct project and parent feature documentation
- [ ] `.github/memory/project-memory.md` exists and reflects the current workspace scan
- [ ] Index file updated (project-level and, for multi-project workspaces, workspace-level)

## Generating architecture and process diagrams

Use the illustration skills before writing the final manual content:

1. From the implemented feature artifacts and changed files, decide whether architecture and/or
   process flow documentation is needed.
2. Generate architecture diagrams with `architecture-diagram` and process visuals with
   `process-flow-diagram`.
3. Write source HTML files to `<assets-dir>/diagrams/`, using names such as
   `<feature-slug>-architecture.html` and `<feature-slug>-process-flow.html`.
4. Export PNG images beside the HTML files. Prefer the built-in html2canvas export path; otherwise
   use Playwright/Puppeteer to screenshot `#report-container`.
5. Embed the PNG in the manual with descriptive `alt` text and a caption, and link to the HTML source.
6. If PNG export cannot run, keep the HTML source, mark the PNG as pending in the manual, and report
   the follow-up. Never embed a missing image.

## Generating screenshots (do NOT hand-take them)

Add a Playwright spec that **mocks all backend endpoints the feature's UI depends on** with
`page.route(...)` and captures full-page PNGs into the assets dir — frontend-only, no backend, fast.
Do **not** mock unrelated analytics/telemetry endpoints unless they affect layout. Reuse the mock
shapes from the feature's existing render specs.

For mobile projects, use the project's existing mobile E2E runner to capture equivalent screenshots.
If no mobile runner exists, document the gap and add a follow-up task instead of silently omitting the
mobile state. If the feature is intentionally unavailable on mobile, say so in the scenario and
include the API or web path the tester should use.

Ensure mocks provide stable, deterministic data (fixed timestamps, deterministic IDs). Document any
dynamic regions and how to normalize them (CSS masks, fixed data in mocks).

If the page requires third-party interactive auth (OAuth), mock the auth exchange or provide a
stubbed dev auth flow; include exact Playwright steps to bypass interactive popups (e.g., stub token
endpoints or use pre-authenticated state).

```ts
const ASSETS = "<assets-directory>"; // e.g. "frontend/public/how-to-test/assets"
test("capture: <page>", async ({ page }) => {
  await page.route("**/api/<endpoint>", (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SAMPLE),
    }),
  );
  await page.goto("/<route>");
  await page.getByTestId("<stable-testid>").waitFor();
  await page.screenshot({ path: `${ASSETS}/<name>.png`, fullPage: true });
});
```

Run to (re)generate, then add a smoke test asserting the HTML page renders with its `<img>`s.

If the Playwright capture fails (e.g., filesystem permissions or invalid paths), abort CI with an
explicit error message. Include a retry step and write logs to a known location
(e.g. `<project-root>/how-to-test/capture.log`). If write permission is unavailable, write to a
temp directory and fail the build with instructions to fix the path.

## Common mistakes

- Asking the user to manually verify what Playwright can check — automate it; the manual is for
  humans to _re-walk_ flows, not to replace E2E.
- Creating a new top-level manual for a sub-feature that belongs under an existing product parent.
- Linking the manual in production — gate the in-app link on a DEV flag; strip the directory from
  production builds.
- Stale screenshots — re-run the capture spec whenever the UI changes; never edit PNGs by hand.
- Documenting headless endpoints without real request/response shapes — pull them from the API
  contract, not memory.
- Skipping mobile impact analysis just because the first changed project is web or backend.
- Writing it before the full suite passes — the manual ships _with_ the delivery, after green.
- Forgetting to update the workspace-level index after adding a new project's manual.
