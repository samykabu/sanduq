---
description: Initialize, select, validate, or create the project's tracked illustration theme.
---

# Initialize Illustration Theme

Read `references/theme-initialization.md`, then manage `.github/illustration-theme.yml` with
`scripts/illustration_theme.py`.

## User input

$ARGUMENTS

## Behavior

- With no existing project file, ask the user to choose Cobalt (recommended), Emerald, Classic, or
  a custom theme; then ask for light/dark mode and remote/local/system font loading.
- In non-interactive automation, initialize Cobalt Light.
- For `list`, `show`, `set`, `create`, or `validate` requests, run the matching script command.
- Custom themes must define complete light and dark palettes plus sans, serif, and mono stacks.
- Report the selected theme, mode, font policy, and project YAML path.
