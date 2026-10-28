# Lite card

The whole lite lifecycle on one page. When `status` or a claim prints `instructions` naming this
file, read it once per session instead of receipt-rules.md, dispatcher-operations.md and
delegation-and-decisions.md. Each claim's `reference_text` still carries its stage's rules, and
the claim's `cli` its exact `complete` and `pause` commands; no `--help` is needed.

`W` is `python .specify/extensions/workflow/scripts/workflow.py`, `S` is
`python .specify/extensions/scope/scripts/scope.py`, `F` is `specs/<feature>`, `n` the issue number.

## Loop

1. Once per session: `echo '{"session_id":"<id>"}' > .specify/workflow/runtime/usage.json`.
2. `W claim --feature F --usage .specify/workflow/runtime/usage.json`; add `--finalize` when
   `next` says `ready_to_finalize` and the user asked for the PR.
3. Do the stage. Write the receipt from the claim's `receipt_template`, run `cli.complete`, then
   the claim's `project_sync.command` when it prints one. Claim the next stage without asking.
4. Waiting on a person or blocked: `cli.pause` with the actual question or failure, report it, stop.
5. Resume: `W status --feature F`; finish a held claim with the `receipt_template` status prints.

Lean execution is on for lite: this session is the coordinator and keeps claims, integration,
receipts and publication; never create another coordinator. `claim.environment` holds
`SANDUQ_WORKFLOW_CLAIM_TOKEN` and `SANDUQ_WORKFLOW_SESSION_ID`: export both for Scope, decision
and worker commands. Read delegation.md only when a claim carries `delegation` (a model route).

## Receipts

Set every `<...>` value from what the stage produced; failed, skipped or pending work never
passes. `evidence` lists existing files that prove the work (test or lint output, publication
record). `inputs` lists other files relied on; `input_roles` may name only paths in `inputs`. No
checkpoint files. A source file Execute will change is never a Plan input. A material choice
goes to the issue: `python .specify/extensions/workflow/scripts/decisions.py --feature F ask
--question "..." --option "..." --option "..."`, then pause.

## Stages

Scope, Specify (bind-only), Clarify, Plan (with tasks and lint), Execute, Verify (with the Review
and Ready checks), PR. `status` lists the skipped ones; never run them by hand.

- **Scope, new issue**: `W prepare --issue n`, `W start --feature F --issue n`, claim, then the
  scope-analyst skill. `requirements` is a list of strings, each a stable coverage ID and its text
  (`"REV-1: Print the words in reverse order"`); `tree.covers` repeats those exact strings.
  Dry run: `S publish n --analysis F/scope-analysis.json --snapshot .specify/scope/issue-n-snapshot.json`.
  Show the proposal, ask the owner to approve it, and pause.
- **Scope, after approval**: `S approve n --analysis F/scope-analysis.json --snapshot
  .specify/scope/issue-n-snapshot.json --child-count <count> --approved-by <user>
  --approval-text "<their words>"`, the dry-run command plus `--apply`, then the gate:
  `python .specify/extensions/workflow/scripts/execution_tools.py scope-command --mode initial
  --command gate --issue n --feature F --token <token> --session <session> --analysis
  F/scope-analysis.json` prints it; run it unchanged. Receipt: `effort_score`, the analysis in `inputs`.
- **Specify** (`mode: bind-only`): `S render-spec n --analysis F/scope-analysis.json --feature F`,
  review, rerun with `--apply`; then the same scope-command with `--command bind` and the
  Specify token, run with `--apply` appended.
- **Clarify**: when the claim prints `clarification_round`, follow its steps and do not load
  the clarification skill; otherwise follow the claim's reference.
- **Plan**: one pass writes plan.md and tasks.md; `python .specify/extensions/workflow/scripts/lint.py
  --feature F` must be clean; the receipt's evidence is its `--json` output.
- **Execute**: follow the protocol the claim prints.
- **Verify**: run the tests, save the output under `F/evidence/`, list it as evidence.
- **PR**: the claim's reference; commit (and push, when the PR exists) the explainer and the files it
  links to, then build the body once with `pr_publish.py`.
