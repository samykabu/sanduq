---
description: "Prints the one command that moves a project from the retired Scope package to Workflow 2.0.0. Use only when asked how to migrate from Scope."
---

# Scope is part of Workflow

Scope is retired as a separate package: Workflow 2.0.0 provides it. Tell the user to run, from the
project root:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version 2.0.0 --apply
```

The upgrade installs Workflow 2.0.0, removes this package and keeps every Scope state file in
`.specify/scope/`. Then run `python .specify/extensions/workflow/scripts/workflow.py migrate --feature
specs/<feature> --reason "Scope merged into Workflow"` for each feature in progress; its Scope receipt is
kept. Every `speckit.scope.<x>` command is now `speckit.workflow.scope-<x>` (`/speckit-workflow-scope-run`,
`/speckit-workflow-scope-plan`). Do nothing else in this command.
