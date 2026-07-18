---
name: ui-screenshots
description: Plan, capture, redact, validate, and maintain deterministic screenshots for web, responsive web, and native mobile user documentation. Use when manual pages need UI evidence across roles, interfaces, viewports, themes, languages, or happy, empty, loading, validation, error, and permission states.
---

# UI screenshots

Read [capture-matrix.md](references/capture-matrix.md), then use the project's existing automation
runner. Prefer Playwright for web and responsive web; use the existing Detox, Maestro, Appium, or
native runner for actual mobile applications.

Use deterministic synthetic fixtures. Fix locale, timezone, viewport/device, color scheme, reduced
motion, fonts, and network responses. Disable animations and mask unstable or sensitive elements.
Never capture production data.

Store screenshots under the owning module and language. Give every image descriptive alt text and a
caption that explains the task and expected result in plain audience-appropriate language. Record
the scenario, role, state, viewport, theme, locale, runner, and source test in coverage metadata.
