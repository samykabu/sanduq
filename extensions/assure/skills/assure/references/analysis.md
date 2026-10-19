# QA analysis contract

Run after `tasks.md` exists and before implementation.

Build a coverage matrix for every acceptance scenario. Check for applicable unit, integration, E2E,
API-contract, screenshot, accessibility, fixture, and diagram work. Add concrete tasks to `tasks.md`
inside marker-delimited sections so reruns replace rather than duplicate generated tasks.

In lifecycle-integrated mode, analysis is a gate: finish with no unexplained critical gaps, then
record freshness with the `assure_state.py record` call in the command's last step.

## Task block rules

- Preserve the existing Spec Kit task format: `- [ ] T### [P?] [US#?] Description with file path`.
- Preserve existing task order and content; do not duplicate existing E2E, screenshot, diagram, API
  sample, or documentation tasks.
- Continue numbering from the highest existing `T###`.
- Put user-story-specific gaps in that story's `### Tests` section when one exists; otherwise create
  `### QA readiness tasks` inside that story phase. Put cross-cutting gaps in the final
  Polish/Cross-Cutting phase.
- Mark tasks `[P]` only when they write different files and do not depend on each other.
- Include exact target paths. A path inferred from the plan uses the planned project root and stays
  specific.
- Refresh a previous readiness block idempotently inside these markers:

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

## Report shape

Feature path audited; the inventory summary the scan printed; impacted projects (with
`planned/spec-only` where applicable); then the command's own items.
