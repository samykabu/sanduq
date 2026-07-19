---
name: assure
description: Analyze test and documentation readiness for an active Spec Kit feature, generate or refresh a feature-scoped QA test manual, and enforce lifecycle freshness before implementation or pull-request creation. Use for QA initialization, Assure.Analyze, Assure.Document, test scenarios, screenshot evidence, API samples, accessibility checks, or QA lifecycle gates.
---

# Assure

Use this skill for feature-specific verification material. Do not turn it into an application user
manual; that belongs to the `user-manual` extension.

## Route the request

- For initialization, configure `assure-config.yml` and lifecycle hooks.
- For analysis, read [analysis.md](references/analysis.md), audit `tasks.md`, and record analyze state.
- For documentation, read [documentation.md](references/documentation.md), generate the QA test
  manual from implemented behavior, validate its evidence, and record document state.

## Rules

1. Resolve the active feature from `--feature`, then `.specify/feature.json`.
2. Ground every step, expected result, endpoint, and screenshot in specifications, contracts,
   implementation, tests, or observed development behavior. Never invent evidence.
3. Keep QA material development-only and separate from `User-Manual/`.
4. Redact credentials, tokens, cookies, connection strings, private keys, and production data.
5. Prefer plain language that a tester can follow without knowing the implementation.
6. Reuse the installed Illustrate skill only when a diagram materially improves verification.
7. Use `scripts/assure_state.py` to determine freshness; do not treat a file's existence as proof that it
   is current.
