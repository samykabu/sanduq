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

Each spec edit: exact nonempty `before` and `after` strings, no file paths. Update requirements,
acceptance and edge cases, remove contradictions, keep unrelated text, and cite the human answer
comment IDs. The runtime appends the round's review log (question, answer, evidence links) to the
spec; do not write a separate Q/A list.
