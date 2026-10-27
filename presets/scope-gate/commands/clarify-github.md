---
description: "Structured clarification workflow for underspecified requirements, run unattended through individual GitHub question comments on the bound issue with no question-count limit. Use to clarify an issue-bound spec or reread its answers. (Sanduq managed)"
---

# Clarify

Input: $ARGUMENTS

This command replaces the upstream interactive Clarify. Execute
`.specify/extensions/scope/skills/github-clarification/SKILL.md` with `engine: clarify`, using the
explicit issue number or the active feature's `scope-source.json`. It owns the status check, the
GitHub questions (one comment each, no question or answer-length limit), the spec edits and the
Plan handoff. Never ask clarification questions in this chat unless the feature's claim says
`clarification_transport: local`; then the skill's `references/local.md` applies and nothing is
posted to GitHub. When it returns, STOP.
