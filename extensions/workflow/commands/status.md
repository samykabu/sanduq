---
description: 'Prints the workflow record of one issue-bound feature: stage, active claim, receipts, blockers and evidence freshness; read-only. Use when asked which stage a feature is in or what blocks it, or for "where is this feature". For the live progress report use speckit.progress.status.'
---

# Sanduq Workflow: status

Input: $ARGUMENTS

Read `.specify/extensions/workflow/skills/workflow/SKILL.md` and follow the `status` entry point.
Use the current explicit feature or issue. Do not infer issue identity from an unrelated editor tab.
The shared skill owns orchestration; do not run a second pipeline after it returns.
