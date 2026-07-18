# How-To-Test Extension

Generate internal QA-facing How-To-Test manuals for completed Spec Kit features, while keeping an
optional pre-implementation readiness audit for the tests, screenshots, API samples, and diagram
assets those manuals depend on.

This extension is the canonical sanduq How-To-Test workflow.

## Commands

| Command | Invocation | Description |
|---|---|---|
| `speckit.how-to-test.document` | `/speckit-how-to-test-document` | Generate or update the QA-facing How-To-Test manual with diagram assets when relevant for the completed active feature |
| `speckit.how-to-test.analyze` | `/speckit-how-to-test-analyze` | Create/update reusable project memory, deeply inventory frontend projects, and add missing E2E/API/screenshot/diagram readiness tasks to the active feature `tasks.md` |

## Usage

```text
/speckit-how-to-test-document
/speckit-how-to-test-document --feature specs/006-user-management
/speckit-how-to-test-analyze --report-only
```

## Lifecycle Hooks

Recommended manual-generation phase: `after_implement`.

That is the best supported phase in this repo's Spec Kit lifecycle because implementation completion
validation has finished. If a target project has an implementation-review hook, run
`/speckit-how-to-test-document` after that review; otherwise run it at `after_implement` before PR handoff or
human QA review.

```yaml
hooks:
  after_implement:
    command: speckit.how-to-test.document
    optional: true
```

Recommended readiness phase: `after_tasks`.

At this point `spec.md`, `plan.md`, and `tasks.md` exist, but implementation has not started. The
analyze command first creates or refreshes `.github/memory/project-memory.md`, including a deep
frontend inventory, then adds missing E2E/API/screenshot/diagram tasks while they are still cheap to
implement with the feature.

```yaml
hooks:
  after_tasks:
    command: speckit.how-to-test.analyze
    optional: true
```

## What The Manual Generator Produces

- Workspace project memory at `.github/memory/project-memory.md`.
- A reusable frontend inventory covering implemented web/mobile frontends and planned/spec-only
  frontend paths, so later commands can route screenshots and manuals without rediscovering the
  workspace from scratch.
- One development-only HTML manual per impacted project, grouped under the correct parent feature.
- A workspace-level How-To-Test index for multi-project workspaces.
- Illustrate assets selected from all twenty-seven architecture, interaction, lifecycle,
  hierarchy, quantitative, process, and data-platform types, with PNGs embedded in the manual and
  HTML sources linked.
- Playwright or mobile E2E screenshots for every relevant screen, form, dialog, menu item, and state.
- API request/response samples for backend-only or mobile-inaccessible scenarios.
- Plain-English, real-life user scenarios with expected results.

## Grounding Rules

Both commands read real artifacts only:

- `spec.md`
- `plan.md`
- `tasks.md`
- `quickstart.md`
- `data-model.md`
- `contracts/*`
- `.github/memory/project-memory.md`
- Current changed files, when available

They must not invent screens, endpoints, request bodies, response bodies, test counts, or coverage.
When the parent feature or mobile availability is ambiguous, they report the ambiguity instead of
guessing.

## Diagram dependency management

Both commands require `illustrate >=1.0.0,<2.0.0` for diagram work. On every invocation they
read `.specify/extensions/.registry`, perform a cached catalog-version check, and follow the
project's `prompt`, `auto`, or `manual` update policy. If the dependency cannot be installed, the
commands continue non-diagram work and clearly report the skipped visuals.
