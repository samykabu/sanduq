---
name: user-manual-ui-screenshots
description: Plan, capture, redact, validate, and maintain deterministic screenshots for standalone web, responsive web, and native mobile documentation. Use when manuals need UI evidence across roles, interfaces, viewports, themes, languages, or happy, empty, loading, validation, error, and permission states.
---

# User Manual UI Screenshots

Read [capture-matrix.md](references/capture-matrix.md), then use the project's existing automation
runner. Prefer Playwright for web; use the existing Detox, Maestro, Appium, or native runner for a
real mobile application.

Use deterministic synthetic fixtures. Fix locale, timezone, viewport/device, color scheme, reduced
motion, fonts, and network responses. Disable animations and mask unstable or sensitive elements.
Never capture production data. Store images under the owning module and language, with descriptive
alt text and a caption that explains the task and expected result in plain audience-appropriate
language. Record the scenario, role, state, viewport, theme, locale, runner, and source test in
coverage metadata.

For “reset a password,” capture the sign-in page, request confirmation, and successful reset states
in English and Arabic mobile widths, while masking email addresses and tokens.
