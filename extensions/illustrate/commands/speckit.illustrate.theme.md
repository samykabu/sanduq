---
description: "Initialize, select, validate, or create a project-level Illustrate color and font theme."
---

# Manage the Illustration Theme

Use the versioned Illustrate package to manage the target project's tracked theme.

## User input

$ARGUMENTS

## Required package

1. Read `.specify/extensions/illustrate/skill/references/theme-initialization.md` completely.
2. Use `.specify/extensions/illustrate/skill/scripts/illustration_theme.py` with the project root.
3. Store project policy only at `.github/illustration-theme.yml`.
4. When no file exists, ask for Cobalt (recommended), Emerald, Classic, or custom; ask for
   light/dark mode and font loading. In non-interactive automation, initialize Cobalt Light.
5. Custom themes require complete light and dark semantic palettes plus sans, serif, and mono stacks.

## Output

Report the active theme, mode, font-loading policy, validation result, and YAML path.
