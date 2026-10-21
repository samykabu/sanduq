---
description: 'Runs the managed Ready and PR stages of an issue-bound feature: readiness checks, its one pull request, then the merge check. Use when every earlier stage has passed in a project with .specify/workflow.yml, or for "open the PR".'
---

# Sanduq Workflow: finalize

Input: $ARGUMENTS

Read `.specify/extensions/workflow/skills/workflow/SKILL.md` and follow the `finalize` entry point.
Use the current explicit feature or issue. Do not infer issue identity from an unrelated editor tab.
The shared skill owns orchestration; do not run a second pipeline after it returns.
