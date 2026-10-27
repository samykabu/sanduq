---
description: "Generate technical implementation plans from feature specifications. In a Sanduq workflow project it runs inside the Plan claim after clarification is resolved and also writes tasks.md on the lite and standard tiers; use to plan an issue-bound feature. (Sanduq managed)"
---

<!-- sanduq-workflow-managed:v1 -->
If `.specify/workflow.yml` exists and there is no active matching claim, enter the dispatcher and STOP; never re-enter it from a claim. Full contract: `.specify/extensions/workflow/skills/workflow/references/dispatcher-operations.md#managed-overlay-contract`.
Inside a matching claim, follow `.specify/extensions/workflow/skills/workflow/references/stage-plan.md` from the claim's `reference_text`, then continue with the upstream instructions below. Where the upstream text below conflicts with the claim's `reference_text`, the `reference_text` wins; upstream hook prompts are skipped inside a claim.
