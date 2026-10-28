# Standalone projects

Applies without `.specify/workflow.yml`.

## Waiting

On `CLARIFICATION_WAITING`, STOP immediately. Ask the user to answer the individual comments on
the GitHub issue (tick one option or reply with the question ID), then move the card to
**Feature Specification** and rerun. Do not post more questions, move the card, spend a round,
edit the spec or wait in chat. Diagrams:
`.specify/extensions/workflow/references/clarification-diagrams.md`, read only when a question
carries one.

## Automatic Plan handoff

When publish with `--apply` returns `next_action.command: /speckit-plan`, read and execute
`$speckit-plan` in this session once, before reporting completion; never only print or offer it.
Finish spec edits, checklist updates and mandatory after_clarify hooks first. A dry run never
triggers Plan.

Pass the returned issue number and exact spec path to Plan. Activate the returned
`feature_directory` in `.specify/feature.json` (keep other keys) and use it as
`SPECIFY_FEATURE_DIRECTORY` with `SPECIFY_FEATURE` set to the returned `feature_name` for this
invocation's scripts; restore earlier environment overrides afterwards. Never plan another
feature or switch branches implicitly. Before Plan writes, check the feature's
`scope-source.json` still names this repository and issue, and rerun `clarification.py
plan-gate <issue-number>`. Honor Plan's mandatory hooks; a missing or malformed hook
configuration, a missing Plan skill or a failed guard stops the handoff with a concrete error.
Optional hooks must not interrupt it. After Plan, return to the report; never run Tasks or
Implement.

Pending questions, a reached limit, a failed publication or a closure that waives unresolved
decisions do not trigger Plan. If Plan fails after clarification succeeded, report both and the
recovery command `/speckit-plan`; never repeat clarification to retry planning.
