---
description: "Orchestrate implementation with TDD, subagents, and review gates. In a Sanduq workflow project it runs inside the Execute claim under the shared execution protocol; use to implement an issue-bound feature with SuperSpec. (Sanduq managed)"
---

<!-- sanduq-workflow-managed:v1 -->
If `.specify/workflow.yml` exists and there is no active matching claim, enter the dispatcher and STOP; never re-enter it from a claim. Full contract: `.specify/extensions/workflow/skills/workflow/references/dispatcher-operations.md#managed-overlay-contract`.
Inside a matching claim, follow `.specify/extensions/workflow/skills/workflow/references/stage-execute.md` (SuperSpec Execute provider) from the claim's `reference_text`, then continue with the upstream instructions below.
