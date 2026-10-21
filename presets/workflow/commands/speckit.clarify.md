---
description: "Structured clarification workflow for underspecified requirements. Posts each material question about an issue-bound spec as its own GitHub comment with a recommendation, rereads the answers and applies them to the spec; use to clarify a spec, collect or apply clarification answers. (Sanduq managed)"
---

<!-- sanduq-workflow-managed:v1 -->
# Clarify

Input: $ARGUMENTS

This command replaces the upstream interactive Clarify; there are no upstream instructions below.

If `.specify/workflow.yml` exists and there is no active matching claim, enter the dispatcher and
STOP; never re-enter it from a claim. Full contract:
`.specify/extensions/workflow/skills/workflow/references/dispatcher-operations.md#managed-overlay-contract`.
Inside a matching claim, follow `.specify/extensions/workflow/skills/workflow/references/stage-clarify.md`
from the claim's `reference_text`.

In every case execute `.specify/extensions/scope/skills/github-clarification/SKILL.md` with
`engine: clarify`, using the explicit issue number or the active feature's `scope-source.json`.
Questions go to GitHub, one comment each, not to this chat (the managed in-session first round
is the one exception). There is no five-question cap and no answer-length limit.

