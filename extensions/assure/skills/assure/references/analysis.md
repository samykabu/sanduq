# QA analysis contract

Run after `tasks.md` exists and before implementation.

Record one assertion per acceptance claim in `<feature>/qa/assertions.json`, then add tasks to
`tasks.md` only for assertions whose proof is missing or too thin. Tasks live inside marker-delimited
sections so reruns replace rather than duplicate generated tasks.

## Assertion record

```json
{
  "schema": "assure-readiness/1",
  "assertions": [
    {
      "id": "A-001",
      "requirement": "FR-023",
      "risk": "critical",
      "observable": "an overlapping period is rejected and names the affected days",
      "layer": "integration",
      "boundary": "any",
      "evidence": "real",
      "disposition": "extend",
      "proof": [{"path": "tests/schedule/period.test.ts", "name": "rejects a reversed period"}],
      "tasks": ["T041"]
    }
  ]
}
```

- `requirement` must appear in `spec.md` as written. `risk`: `critical`, `major`, `minor`. `layer`: `unit`,
  `integration`, `api-contract`, `e2e`, `native`, `os-contract`, `manual`, `visual`.
- `boundary: real` means the requirement names a real boundary. Then `evidence` must be `real`;
  `fixture` and `emulated` fail the check.
- `reuse`: `proof` lists the existing test; no task. `extend`: `proof` plus the `tasks` that widen it.
  `add`: no proof, `tasks` required. `not-applicable`: `reason` and `basis` (`source` file plus a `cite`
  that appears in it), nothing else. Count, runtime or budget is not a reason.
- A proof is a repo-relative `path` and a literal test `name` found in that file. The file must sit
  outside the feature folder. The check shows the name exists, not that the test is adequate.
- Every `T###` in a row exists in `tasks.md`, and every task inside the `qa-prepare` block names at
  least one assertion id (for example "Covers A-001").
- Rows are unique by `id`, and by requirement, observable and layer together.
- `context` is optional free text for a policy exception the row relies on.

Run `python .specify/extensions/assure/scripts/assure_readiness.py check --feature <feature-path>`.
A warning `requirement-unreferenced` lists a requirement id no row cites. It does not fail the check,
because the scanner cannot tell a testable requirement from a statement of fact, so you decide. Before
recording, give each one a row or a `not-applicable` row with its basis. A critical requirement without a
row blocks recording. Do not write an artificial test name to clear a noncritical one.

A proof is a test file. The check refuses proof inside the feature folder or any sibling feature folder,
inside `.specify`, and files ending in `.md`, `.json` and similar document or data types (YAML test flows
are fine). A `not-applicable` `basis.source` is tracked for freshness like a proof file, so removing the
quoted text later makes the analysis stale.

## Task block rules

- Preserve the existing Spec Kit task format: `- [ ] T### [P?] [US#?] Description with file path`.
- Preserve existing task order and content; do not duplicate existing tasks, and do not add one for
  an assertion marked `reuse`.
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

- [ ] T123 [P] [US1] Covers A-001: add Playwright E2E test for ...

<!-- qa-prepare:end -->
```

Task wording examples:

```markdown
- [ ] T041 [P] [US1] Covers A-001: add Playwright E2E test for admin password reset happy path in frontend/e2e/user-management/password-reset.spec.ts
- [ ] T042 [P] [US1] Covers A-002: add screenshot capture for the password reset confirmation the reference requires in frontend/e2e/qa/user-management-password-reset.capture.spec.ts
- [ ] T043 [P] [US1] Covers A-003: add API request/response fixture coverage for POST /api/users/{id}/password-reset in backend/tests/contracts/user-management-password-reset.test.ts
- [ ] T044 [P] [US1] Covers A-004: generate Illustrate sequence HTML and PNG assets for the password reset interaction in frontend/public/qa/assets/user-management/diagrams/user-management-password-reset-sequence.html
- [ ] T045 [US1] Covers A-005: update User Management QA documentation index under frontend/public/qa/features/user-management/index.html
```

## Report shape

Feature path audited; the inventory summary the scan printed; impacted projects (with
`planned/spec-only` where applicable); assertion counts by disposition; then the command's own items.
