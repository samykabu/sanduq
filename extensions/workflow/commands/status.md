---
description: "Shows an issue-bound feature's current stage, active claim, receipts, profile, skipped stages, blockers and evidence freshness without changing anything. Use when asked where a feature is, what is blocking it, or what the workflow will do next."
---

# Sanduq Workflow: status

Input: $ARGUMENTS

Read `.specify/extensions/workflow/skills/workflow/SKILL.md` and follow the `status` entry point.
Use the current explicit feature or issue. Do not infer issue identity from an unrelated editor tab.
The shared skill owns orchestration; do not run a second pipeline after it returns.
