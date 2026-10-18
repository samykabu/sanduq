---
description: "Structured clarification workflow for underspecified requirements, run unattended through individual GitHub question comments on the bound issue with no question-count limit. Use to clarify an issue-bound spec or reread its answers. (Sanduq managed)"
---

<!-- scope-clarify-overlay:start -->
## Managed workflow precedence

When `.specify/workflow.yml` exists, the workflow dispatcher
(`.specify/extensions/workflow/skills/workflow/SKILL.md`) owns transitions: return to it after
the domain work, never chain Plan yourself, and let its managed rules override conflicting
status or stop instructions below. Unmanaged projects keep the flow below.

## Mandatory unattended GitHub clarification contract

This customization overrides the core skill's interactive transport, all five-question
or other question-count/answer-length limits, one-at-a-time chat questioning, and
early-completion shortcuts. Keep its ambiguity taxonomy and answer-integration
guidance as reference material. Do not execute its old interactive loop afterward.

Read `.specify/extensions/scope/skills/github-clarification/SKILL.md` and execute it
with `engine: clarify`, using the explicit issue number or the active feature's
`scope-source.json`. The runtime's status check must run before any content analysis
or other hook: only Feature Specification issues are eligible. Need Clarifications
means stop immediately, ask the user to answer on GitHub and move the card back to
Feature Specification; do not move it yourself or post duplicate questions.

Run unattended: generate all useful questions, each in its own GitHub comment tagging
the issue creator, with simple English and a highlighted justified AI recommendation.
When clarification resolves and the shared workflow returns a Plan handoff, actually
execute `$speckit-plan` automatically for the same issue and spec as instructed there.
After that shared workflow (including any Plan handoff) returns, STOP this skill. Do not continue the upstream
five-question flow or ask clarification questions in the Codex conversation.
<!-- scope-clarify-overlay:end -->
