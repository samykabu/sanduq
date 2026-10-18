---
description: "Convert tasks from tasks.md into GitHub issues. In a Sanduq workflow project it runs inside the Tasks-to-Issues claim and creates native sub-issues of the bound issue through the deduplicating adapter, optionally one phase at a time; use to publish task issues. (Sanduq managed)"
---

<!-- sanduq-workflow-managed:v1 -->
If `.specify/workflow.yml` exists and there is no active matching claim, enter the dispatcher and STOP; never re-enter it from a claim. Full contract: `.specify/extensions/workflow/skills/workflow/references/dispatcher-operations.md#managed-overlay-contract`.
Inside a matching claim, follow `.specify/extensions/workflow/skills/workflow/references/stage-taskstoissues.md` from the claim's `reference_text`, then continue with the upstream instructions below.
