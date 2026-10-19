# Managed workflow projects

Applies when `.specify/workflow.yml` exists; these rules override the standalone stop and Plan
handoff.

- Read the validated policy first. Use the actual board names mapped through `scope.statuses`;
  never require a differently named column.
- `clarification.resume_on_reinvoke: reread-answers` permits inspecting **Need Clarifications**
  on invocation without a manual status move. Read every page of comments and edited choices.
  With no new answer or material requirement, report still waiting and post nothing. An
  explicit managed revalidation claim may also reread an open Ready, In progress or In review
  feature; a package or policy file alone grants nothing. New unresolved questions return the
  issue to waiting.
- Return the outcome to the workflow dispatcher when it holds the clarification claim; never
  dispatch Plan yourself. Without an active claim, continue through the workflow entry point for
  the same bound feature. Never run the legacy interactive chat loop.
- Diagrams: read `.specify/extensions/scope/references/clarification-diagrams.md` only when a
  question carries one.
- Question cap: give questions an integer `priority` (1 is most important); over
  `clarification.max_questions_per_round`, move the keys `CLARIFICATION_TOO_MANY_QUESTIONS` names
  to a later round.

## In-session first round

Only when `clarification.in_session_first_round` is true, this is round 1, and the person in
this session is the issue creator (the authenticated `gh api user` login):

1. Ask the round's questions here, each with its options and recommendation, and wait for real
   answers. Never answer for the user.
2. Write `answers.json` as `[{"key", "option": <1-based> or "answer": "<text>", "answered_by":
   "<creator login>", "answered_at": "<UTC ISO time>"}]`, one entry per question, and put the
   resulting `spec_edits` in the analysis.
3. Run `clarification.py publish <issue> --analysis <file> --answers <answers.json>` to preview,
   then with `--apply`. The runtime posts one comment listing each question, the chosen answer
   and who answered, applies the edits, records `in-session` evidence and sets Ready.

Otherwise, or when the creator prefers GitHub, publish the round on GitHub as usual.
