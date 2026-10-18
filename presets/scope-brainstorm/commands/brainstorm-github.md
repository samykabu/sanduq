---
description: "Deep-dive edge cases and refine a spec using brainstorming skills, run unattended through individual GitHub question comments on the bound issue. Use to brainstorm or stress-test an issue-bound spec before planning. (Sanduq managed)"
---

<!-- scope-brainstorm-overlay:start -->
## Managed workflow precedence

When `.specify/workflow.yml` exists, the workflow dispatcher
(`.specify/extensions/workflow/skills/workflow/SKILL.md`) owns transitions: return to it after
the domain work, never chain Plan yourself, and let its managed rules override conflicting
status or stop instructions below. Unmanaged projects keep the flow below.

## Mandatory unattended GitHub brainstorm contract

Read `.specify/extensions/scope/skills/github-clarification/SKILL.md` and execute it
with `engine: brainstorm`. Use the explicit GitHub issue number or the current bound
feature. This shared contract supersedes Superspec's and Superpowers' one-at-a-time
interactive questioning, question quotas, chat approvals, and completion signals.
Do not allow an optional underlying brainstorming skill to reinstate those rules.

Only Feature Specification issues are eligible. Need Clarifications stops immediately
before analysis or new comments; ask the user to answer each GitHub question and move
the issue back to Feature Specification. Keep Superspec's five-category coverage
scan as a minimum, expanding to all material ambiguity categories without a question
count limit. Use the same GitHub history, IDs, answers and round count as Clarify.

Questions are separate GitHub comments mentioning the issue creator, in simple English,
with clear supporting details/diagrams and a highlighted justified AI recommendation.
On a resolved review, execute the shared workflow's `$speckit-plan` handoff automatically
for the same issue and spec. Run the shared workflow including that handoff, then STOP; do not execute the legacy interactive
process afterward. Superspec availability controls auto-selection, not a second round.
<!-- scope-brainstorm-overlay:end -->
