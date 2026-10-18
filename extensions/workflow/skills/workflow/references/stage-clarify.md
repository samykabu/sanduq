# Stage reference: clarify

## Entry point

**clarify**: resolve the explicit issue through `scope-source.json`, then run the stage loop.
For an external invocation, run `refresh --feature ... --from-stage clarify --reason "Explicit
clarification invocation: reread GitHub answers"` once before the loop; it archives receipts and
invalidates Clarify onward even when local files did not change. Never refresh from an active
claimed command. GitHub-discussion and handoff rules:
`references/dispatcher-operations.md#interruption-and-github-behavior`.

## Required work and evidence

Run `.specify/extensions/scope/skills/github-clarification/SKILL.md` with engine `clarify`, or
`brainstorm` for `speckit.superspec.brainstorm`. Read every page of current comments and edited
answers; reuse earlier answered clarification only after checking the current discussion and
spec. Unchanged unanswered discussions wait without new posts. Receipt: `unresolved: 0` and
`answers_applied: true`, with comment or snapshot evidence; asking questions is not resolution.
The claim's `side_effects` lists what this stage may edit (spec.md, project-sync-state.json,
checklists).

- In-session first round: when `clarification.in_session_first_round` is true and this is round
  1, the skill may ask the issue creator in this session and publish the answers with
  `clarification.py publish <issue> --analysis <file> --answers <answers.json> --apply`; the
  issue goes straight to Ready.
- `clarification.max_questions_per_round` caps one round; give questions a `priority` (1 is most
  important) and defer the keys `CLARIFICATION_TOO_MANY_QUESTIONS` names.
- A Mermaid `diagram` is allowed in managed projects; an Illustrate `diagram_image` is optional.

Return to the dispatcher; never call Plan from here. With SuperSpec Brainstorm under
`required-only` checkpoints, also follow [superspec-checkpoints.md](superspec-checkpoints.md).
