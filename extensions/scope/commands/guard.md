---
description: "Validate the explicit GitHub issue and score before any Specify side effects."
---

# Scope prerequisite guard

Input: $ARGUMENTS

Extract one explicit GitHub issue number from this Specify invocation, such as
`#8`, `GitHub issue #8`, or a same-repository issue URL. Never infer it from other
numbers, the active feature, branch, a previous invocation, or a stale local cache.
If missing or ambiguous, STOP with `SCOPE_REQUIRED: provide a GitHub issue number
and run /speckit-scope <issue> first.` Do not create or edit a specification.

Run `python .specify/extensions/scope/scripts/scope.py gate <number>`.
The issue must currently be in **Backlog**. Any other Project status is a hard
stop before branch creation or specification writes, even if its scope is valid.
Any nonzero exit is a hard stop for Specify and its remaining hooks. Surface the
error and prerequisite table without hiding it. On success retain the returned
issue number and fingerprint in this invocation, and use its returned enriched
prompt as the authoritative scoped input to Specify. Extra user requirements
outside that scope require running Scope again, not quietly expanding the spec.
This guard does not create a branch or a feature; ignore the core command's
generic assumption that every before_specify hook returns branch metadata.
