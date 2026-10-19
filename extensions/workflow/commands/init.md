---
description: 'Sets up the Sanduq workflow in a Spec Kit project: processes, decision reviewers, delegation, CI runners and evidence gate. Use when configuring a project, or for "initialize the workflow".'
---

# Sanduq Workflow: init

Input: $ARGUMENTS

Read `.specify/extensions/workflow/skills/workflow/SKILL.md` and follow the `init` entry point.
Use the current explicit feature or issue. Do not infer issue identity from an unrelated editor tab.
The shared skill owns orchestration; do not run a second pipeline after it returns.
