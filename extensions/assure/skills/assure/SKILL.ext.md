---
name: assure
description: Analyze test and documentation readiness for an active Spec Kit feature, generate or refresh a feature-scoped QA test manual, and enforce lifecycle freshness before implementation or pull-request creation. Use for QA initialization, speckit.assure.analyze, speckit.assure.document, test scenarios, screenshot evidence, API samples, accessibility checks, or QA lifecycle gates.
---

# Assure

Use this skill for feature-specific verification material. Do not turn it into an application user
manual; that belongs to the `user-manual` extension.

## Rules

1. Resolve the active feature from `--feature`, then `feature_directory` in `.specify/feature.json`,
   then the most recently modified directory under `specs/` only when it is unambiguous; otherwise
   ask the user for the feature path.
2. Ground every step, expected result, endpoint, and screenshot in specifications, contracts,
   implementation, tests, or observed development behavior. Never invent evidence.
3. Keep QA material development-only and separate from `User-Manual/`.
4. Redact credentials, tokens, cookies, connection strings, private keys, and production data: never
   include plaintext passwords, API keys, bearer or refresh tokens, session IDs, OAuth codes, database
   URLs, or full `.env` values.
5. Prefer plain language that a tester can follow without knowing the implementation.
6. Reuse the installed Illustrate skill only when a diagram materially improves verification.
7. Use `.specify/extensions/assure/scripts/assure_state.py` to determine freshness; do not treat a
   file's existence as proof that it is current.
8. Generate QA from the assertion record, not from a list of screens. A task exists only for an
   assertion whose existing proof is missing or too thin. A file that exists is not proof until you
   have read the test and it checks the assertion.
9. Fixture or emulated evidence never closes a requirement that names a real boundary. Count,
   runtime or budget never waives a critical assertion.
10. `.specify/extensions/assure/scripts/assure_readiness.py` checks the record mechanically. It cannot
    judge whether a test covers an assertion; that judgment stays with you and the reviewer.
