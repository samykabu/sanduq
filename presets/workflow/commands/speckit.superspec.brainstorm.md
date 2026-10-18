---
description: "Deep-dive edge cases and refine a spec using brainstorming skills. For an issue-bound spec it posts each material question as its own GitHub comment with a recommendation, rereads answers and folds them into the spec; use to brainstorm or stress-test a spec before planning. (Sanduq managed)"
---

<!-- sanduq-workflow-managed:v1 -->
# SuperSpec Brainstorm

Input: $ARGUMENTS

This command replaces the upstream interactive Brainstorm; there are no upstream instructions
below.

If `.specify/workflow.yml` exists and there is no active matching claim, enter the dispatcher and
STOP; never re-enter it from a claim. Full contract:
`.specify/extensions/workflow/skills/workflow/references/dispatcher-operations.md#managed-overlay-contract`.
Inside a matching claim, follow `.specify/extensions/workflow/skills/workflow/references/stage-clarify.md`
from the claim's `reference_text`, and under `required-only` checkpoints also
`.specify/extensions/workflow/skills/workflow/references/superspec-checkpoints.md`.

In every case execute `.specify/extensions/scope/skills/github-clarification/SKILL.md` with
`engine: brainstorm`, using the explicit issue number or the bound feature. That shared contract
supersedes SuperSpec's and Superpowers' one-at-a-time questioning, question quotas, chat
approvals and completion signals; an optional underlying brainstorming skill must not bring them
back. Brainstorm shares Clarify's GitHub history, question IDs, answers and round count.
SuperSpec availability decides which engine runs, never a second round.

## Coverage

Read the target spec and the constitution first. Cover at least these five categories, then
every other material ambiguity, with no question count limit:

- Boundary conditions: minimum and maximum values, empty states, edge-of-range input.
- Error scenarios: a service down, malformed input, partial failures.
- Scale and performance: load, concurrency, rate limits.
- Security and privacy: injection, authorization, data exposure.
- User experience: confusion points, accessibility, unintended usage.

Each question is a separate GitHub comment that mentions the issue creator, in plain English,
with supporting details or a diagram and a highlighted, justified recommendation.

## Applying answers

Express each accepted answer as `spec_edits`: new requirements go to Functional Requirements,
resolved questions update the Open Questions table, and new edge cases go to Edge Cases. Fold any
brainstorming-skill design output back into the existing `spec.md` (never `docs/superpowers/`).
When the spec has a Brainstorm Log, append a dated summary of what this round found; later
rounds skip categories the log already covers unless the spec changed there.
