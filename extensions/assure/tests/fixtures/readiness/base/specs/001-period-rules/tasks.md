# Tasks: Period scheduling

## Phase 1: Rules

- [ ] T001 Implement period overlap validation in src/periods/rules.ts
- [ ] T002 Implement capacity bounds in src/periods/capacity.ts
- [ ] T003 Implement sign-out in src/session/sign_out.ts

<!-- qa-prepare:start -->
### QA readiness tasks

- [ ] T004 [US1] Add the overlap rejection test in tests/unit/period_rules.spec.ts (covers A-001; owner layer unit)
- [ ] T005 [US3] Extend sign-out with keyring and server revocation readback in tests/native/sign_out.native.ts (covers A-003; owner layer native)

<!-- qa-prepare:end -->
