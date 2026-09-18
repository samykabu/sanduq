---
name: speckit-scope
description: Scope an explicit GitHub issue and automatically continue the configured Sanduq workflow.
---

<!-- sanduq-workflow-scope-alias:v1 -->
Read `.specify/extensions/workflow/skills/workflow/SKILL.md` and execute its scope
entry point with the current invocation's explicit issue number or exact title.
If project policy is missing, perform Init once, then continue with the same issue.
Use the installed native Scope command through the dispatcher. Do not create a
second scope run, bypass its issue guards, or select a feature from editor context.
