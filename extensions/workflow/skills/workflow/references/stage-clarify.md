# Stage reference: clarify

## Entry point

**clarify**: resolve the explicit issue through `scope-source.json`, then run the stage loop.
For an external invocation, run `refresh --feature ... --from-stage clarify --reason "Explicit
clarification invocation: reread GitHub answers"` once before the loop; it archives receipts and
invalidates Clarify onward even when local files did not change. Never refresh from an active
claimed command. GitHub-discussion and handoff rules:
`references/dispatcher-operations.md#interruption-and-github-behavior`.

## Required work and evidence

A claim with `clarification_round` needs no skill: follow its `steps`. Otherwise run `.specify/extensions/workflow/skills/github-clarification/SKILL.md` with engine `clarify`, or
`brainstorm` for `speckit.superspec.brainstorm`. Read every page of current comments and edited
answers; reuse earlier answered clarification only after checking the current discussion and
spec. Unchanged unanswered discussions wait without new posts. Receipt: `unresolved: 0` and
`answers_applied: true`, with comment or snapshot evidence; asking questions is not resolution.
The claim's `side_effects` lists what this stage may edit (spec.md, project-sync-state.json,
checklists).

The skill's managed reference carries the in-session first round, the per-round question cap
and diagrams. With `clarification_transport: local` on the claim, its `references/local.md`
applies instead: ask in the conversation, record the user's replies in
`specs/<f>/clarifications.md`, list that file in the receipt inputs and post nothing to GitHub.

Return to the dispatcher; never call Plan from here. With SuperSpec Brainstorm under
`required-only` checkpoints, also follow [superspec-checkpoints.md](superspec-checkpoints.md).
