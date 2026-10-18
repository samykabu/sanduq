---
description: "Installs or repairs the workflow's managed hooks and presets from policy through Spec Kit, without changing unrelated integrations. Use after editing .specify/workflow.yml, after an upgrade, or when doctor reports drifted hook or preset ownership."
---

# Sanduq Workflow: reconcile

Input: $ARGUMENTS

Read `.specify/extensions/workflow/skills/workflow/SKILL.md` and follow the `reconcile` entry point.
Use the current explicit feature or issue. Do not infer issue identity from an unrelated editor tab.
The shared skill owns orchestration; do not run a second pipeline after it returns.
