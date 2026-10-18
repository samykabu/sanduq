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

## Coverage taxonomy

Mark each category Clear, Partial or Missing for the spec, and ask only where an answer would
change implementation or validation; leave questions that belong to planning for Plan.

- Functional scope and behavior: user goals, success criteria, out-of-scope declarations, roles.
- Domain and data: entities, identity and uniqueness, lifecycle and state transitions, volume.
- Interaction and UX: critical journeys, error, empty and loading states, accessibility, locales.
- Non-functional: performance, scalability, reliability and recovery, observability, security
  and privacy, compliance.
- Integrations: external services and their failure modes, import and export formats, versioning.
- Edge cases: negative scenarios, rate limiting, conflict resolution such as concurrent edits.
- Constraints and tradeoffs: technical constraints, rejected alternatives.
- Terminology: canonical terms, avoided synonyms.
- Completion signals: testable acceptance criteria, measurable definition of done.
- Placeholders: TODOs, unresolved decisions, vague adjectives with no measure.

## Applying answers

Express each accepted answer as `spec_edits`. Keep a `## Clarifications` section with a
`### Session YYYY-MM-DD` subheading and one `- Q: <question> → A: <answer>` bullet per answer.
Apply each answer where it belongs: functional ambiguity to Functional Requirements, actors to
the user stories, data shape to the data model, non-functional constraints to measurable success
criteria, edge cases to Edge Cases, and terminology across the whole spec. Replace an invalidated
statement instead of adding a contradicting one, and keep headings and unrelated text unchanged.
