---
description: "Runs as the before_specify hook: blocks Specify unless the issue has a fresh approved scope. Use when asked to specify an issue."
---

# Scope prerequisite guard

Input: $ARGUMENTS

Extract one explicit GitHub issue number from this Specify invocation, such as
`#8`, `GitHub issue #8`, or a same-repository issue URL. Never infer it from other
numbers, the active feature, branch, a previous invocation, or a stale local cache.
If missing or ambiguous, STOP with `SCOPE_REQUIRED: provide a GitHub issue number
and run /speckit-workflow-scope-run <issue> first.` Do not create or edit a specification.

Run `python .specify/extensions/workflow/scripts/scope/scope.py gate <number>`.
Standalone work requires **Backlog** before branch creation or specification writes.
The fresh managed clarification-return path is the narrow exception; a historical
feature pointer or workflow policy alone does not authorize it.
Any nonzero exit is a hard stop for Specify and its remaining hooks. Surface the
error and prerequisite table without hiding it. On success retain the returned
issue number and fingerprint in this invocation, and use its returned enriched
prompt as the authoritative scoped input to Specify. Extra user requirements
outside that scope require running Scope again, not quietly expanding the spec.
This guard does not create a branch or a feature; ignore the core command's
generic assumption that every before_specify hook returns branch metadata.

In a managed workflow claim, take the exact command and flags from
`.specify/extensions/workflow/skills/workflow/references/scope-binding.md`.
