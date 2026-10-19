---
description: 'Repairs the workflow''s managed hooks and presets from policy through Spec Kit. Use when doctor reports drift or after editing workflow.yml, or for "reconcile the workflow".'
---

# Sanduq Workflow: reconcile

Input: $ARGUMENTS

Read `.specify/extensions/workflow/skills/workflow/SKILL.md` and follow the `reconcile` entry point.
Use the current explicit feature or issue. Do not infer issue identity from an unrelated editor tab.
The shared skill owns orchestration; do not run a second pipeline after it returns.
