---
description: 'Checks readiness and creates or updates the feature''s single pull request, then verifies the merge. Use when the feature is ready, or for "open the PR".'
---

# Sanduq Workflow: finalize

Input: $ARGUMENTS

Read `.specify/extensions/workflow/skills/workflow/SKILL.md` and follow the `finalize` entry point.
Use the current explicit feature or issue. Do not infer issue identity from an unrelated editor tab.
The shared skill owns orchestration; do not run a second pipeline after it returns.
