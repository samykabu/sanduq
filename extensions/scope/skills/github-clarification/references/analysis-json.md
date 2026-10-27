# Clarification analysis JSON

Start from `.specify/extensions/scope/examples/clarification.json`. Top level: `version: 1`, `issue`, `snapshot_digest`
from inspect, `engine`, `coverage` (category map), `summary`, `answers`, `questions`,
`spec_edits`. Copy inspect's `suggested_answers` (a single checked option with no reply) into
`answers` and add each `explanation`, or override one when other evidence changes it.

Each answer: `question_id`, `disposition` (`answered`, `superseded` or `unresolved`),
`comment_ids` with actual human reply evidence, and `explanation`. A `superseded` disposition
needs a real explanation and comment evidence.
Correlate unmatched comments explicitly or ask a focused follow-up; never drop a hard question.

Each question: unique lowercase `key`, `question` (a standalone English interrogative), `why`,
`details`, `recommendation`, `justification`, optional single-line `options` with
`recommended_option` (1-based, required with options, matching the recommendation text),
optional integer `priority` (1 is most important), optional `diagram` (raw Mermaid, no fences), optional
`diagram_image` (`path` of a pushed, project-relative Illustrate PNG and `alt`) with the
required `diagram_text`, and optional `follows_up` question IDs. Use everyday words and explain
needed terms; do not force a fixed number of options. A diagram shows the actual alternatives,
never decoration. The runtime renders lettered, unchecked checkboxes, appends **(Recommended)**,
keeps a short reason visible and folds details and diagrams into a collapsible section. Users
tick one box or reply `C1Q1: A`; custom answers are welcome. Never edit question checkboxes for
the user.

Each spec edit: exact nonempty `before` and `after` strings, no file paths, and `question_ids`: the
prior questions whose answers justify it, each `answered` or `superseded` in this analysis (or waived
by the creator's closure; in session, this round's `C1Q<n>`). The runtime refuses an edit without a
trusted cited answer (`CLARIFICATION_EDIT_UNTRUSTED`). Update requirements, acceptance and edge
cases, remove contradictions and keep unrelated text. The runtime appends the round's review log (question, answer, evidence links) to the
spec; do not write a separate Q/A list.

## Coverage

Read the spec and any `.specify/memory/constitution.md`. Mark each category Clear, Partial or
Missing in `coverage`; leave questions that belong to planning for Plan.

Clarify:

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

Brainstorm: any focus topic in the command input first, then at least boundary conditions
(minimum and maximum values, empty states, edge-of-range input), error scenarios (a service down,
malformed input, partial failures), scale and performance (load, concurrency, rate limits),
security and privacy (injection, authorization, data exposure) and user experience (confusion
points, accessibility, unintended usage), then every other material ambiguity. Skip categories
the spec's Brainstorm Log covers unless the spec changed there.

## Applying answers

Clarify: functional ambiguity goes to Functional Requirements, actors to the user stories, data
shape to the data model, non-functional constraints to measurable success criteria, edge cases to
Edge Cases, and terminology across the whole spec.

Brainstorm: new requirements go to Functional Requirements, resolved questions to the Open
Questions table, edge cases to Edge Cases. Fold brainstorming-skill design output into the
existing `spec.md` (never `docs/superpowers/`). Append a dated summary to any Brainstorm Log.
