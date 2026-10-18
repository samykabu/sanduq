---
description: "Checks the workflow's dependencies, policy, installed host commands and skills, board configuration and package lock, reporting every missing or broken item. Use after installing or upgrading, when a claim fails on setup, or when asked to diagnose the workflow."
---

# Sanduq Workflow: doctor

Input: $ARGUMENTS

Read `.specify/extensions/workflow/skills/workflow/SKILL.md` and follow the `doctor` entry point.
Use the current explicit feature or issue. Do not infer issue identity from an unrelated editor tab.
The shared skill owns orchestration; do not run a second pipeline after it returns.
