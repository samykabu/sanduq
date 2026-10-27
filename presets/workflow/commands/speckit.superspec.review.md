---
description: "Run code review against spec requirements using review skills. In a Sanduq workflow project it runs inside the Review stage with blocking findings fixed before Ready; use to review an issue-bound feature with SuperSpec. (Sanduq managed)"
---

<!-- sanduq-workflow-managed:v1 -->
If `.specify/workflow.yml` exists and there is no active matching claim, enter the dispatcher and STOP; never re-enter it from a claim. Full contract: `.specify/extensions/workflow/skills/workflow/references/dispatcher-operations.md#managed-overlay-contract`.
Inside a matching claim, follow `.specify/extensions/workflow/skills/workflow/references/stage-review.md` (SuperSpec Review provider) from the claim's `reference_text`, then continue with the upstream instructions below. Where the upstream text below conflicts with the claim's `reference_text`, the `reference_text` wins; upstream hook prompts are skipped inside a claim.
