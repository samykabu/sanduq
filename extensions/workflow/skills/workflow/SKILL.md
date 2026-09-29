---
name: sanduq-workflow
description: Run the project-selected Scope-to-PR lifecycle with GitHub clarification, native task sub-issues, optional QA/manuals and fresh-session checkpoints.
---

# Sanduq workflow dispatcher

This skill dispatches semantic work to the installed commands and verifies their evidence.
Use the installed runtime at `.specify/extensions/workflow/scripts/workflow.py`.
Run Python with argument arrays or properly quoted paths. Install runtime dependencies from
the package's pinned `requirements.txt` when missing. Never install a floating tool version.

## Entry points

`init`, `continue`, `status`, `doctor`, `reconcile`: see
[dispatcher-operations.md](references/dispatcher-operations.md). `scope`, `clarify`
enter the stage loop below; see `references/stage-scope.md`,
`references/stage-clarify.md`. `finalize` runs the same loop with `--finalize`; see
[stage-pr.md](references/stage-pr.md).

## Stage loop

1. Read `next --feature ...` and run doctor. Stop for missing dependencies, malformed policy,
   ambiguous binding, active foreign executor, or a changed package lock. Never skip a gate.
2. Only reliable measured host context usage can trigger a context pause; without it,
   continue automatically in bounded batches. Never invent percentages or a stop estimate.
   Full rule: [context-and-telemetry](references/dispatcher-operations.md#context-and-telemetry-stage-loop-step-2).
3. `claim --feature ... --usage <file>` returns the stage, command and claim token. It also
   returns a `reference`: the exact `references/stage-<stage>.md` to read before acting on
   this claim. If it checkpoints based on a fresh reliable measurement, save the handoff and
   use a supported host continuation mechanism when available; otherwise return the
   fresh-session prompt. Handoff contents and GitHub-discussion rules:
   [interruption-and-github-behavior](references/dispatcher-operations.md#interruption-and-github-behavior).
   Unknown, estimated, stale or unreliable measurements do not justify
   a context pause. Continue ordinary stage transitions automatically and keep durable
   progress notes.
4. Invoke the selected command in this host using its installed skill/command registration,
   or its delegation route when `delegation.enabled` is true. Full rule, including decision
   escalation: [delegation-and-decisions.md](references/delegation-and-decisions.md).
5. Before writing any receipt, read
   [receipt-rules.md](references/receipt-rules.md): it holds the rules for what
   makes a receipt honest (failed/skipped/pending work cannot pass, a pending or conflicted
   issue decision blocks a passed receipt and must be in the stage inputs, checkpoint files
   never belong in the input manifest), declaring `input_roles`, `amend`, and the recovery
   recipes after source drift or a `STALE_RECEIPT` gate failure; never revalidate on a note
   alone. Record an honest receipt JSON: `stage`, `outcome: passed`, `summary`, `inputs`,
   `evidence`, and the optional `input_roles` map. A receipt without `input_roles` is read as
   all-dependency. A changed dependency stales the receipt and fails a later stage with
   `UPSTREAM_INPUT_CHANGED_DURING_STAGE`; a changed consulted input is reported by `next` as
   `advisory_drift`. If only a completed stage's evidence file changed afterwards, do not
   re-record the stage and do not copy hashes forward: use `amend`. Add the stage-specific
   fields in this stage's own reference.
6. Run `complete --feature ... --token ... --receipt <file>`. Re-read the next stage.
   Continue automatically without asking about routine transitions. If blocked, use
   `pause --reason` and report the actual question or failure. Preserve required human
   review/deployment gates. Project Sync and native task-issue sync timing:
   [project-sync](references/dispatcher-operations.md#project-sync-and-task-issue-sync-stage-loop-step-6).
7. When `ready_to_finalize` is reached, honor the existing publication authorization.
   If the user already requested a PR, continue with Finalize automatically. Otherwise
   report readiness and obtain the missing PR authorization. Executor hooks never
   create the PR. Finalize authorizes PR creation only; merging requires the user's
   separate authorization, which may already be present in the original request.

Runtime `workflow:*` stages are this skill's built-in operations, not missing slash commands:
**verification** runs the relevant real tests/checks; **review** reviews against spec/constitution
and fixes blocking findings; **gates** validates readiness, selected documentation audits,
freshness and task mapping. Preserve their distinct evidence and run necessary retests after fixes.

## Stage reference map

`claim`'s `reference` field always names the row below for the claimed `stage`; load
exactly that file, never guess from the stage name alone.

| Stage | Reference | Stage | Reference |
| --- | --- | --- | --- |
| scope | stage-scope.md | taskstoissues | stage-taskstoissues.md |
| specify | stage-specify.md | execute | stage-execute.md |
| clarify | stage-clarify.md | verify | stage-verify.md |
| plan | stage-plan.md | review | stage-review.md |
| tasks | stage-tasks.md | qa_document | stage-qa_document.md |
| qa_analyze | stage-qa_analyze.md | manual_update | stage-manual_update.md |
| manual_analyze | stage-manual_analyze.md | ready | stage-ready.md |
| analyze | stage-analyze.md | pr | stage-pr.md |

Paths are relative to `references/`. A managed command overlay
(`presets/workflow/commands/*.md`) is a short pointer into this skill and its
claimed reference; the contract it points to (enter/stop/never-recurse) is
[managed-overlay-contract](references/dispatcher-operations.md#managed-overlay-contract).
The `speckit-superpowers-bridge` legacy overlays instead point to
[legacy-guard.md](references/legacy-guard.md).

## Updates

Package, upgrade and host-switch procedures:
[updates](references/dispatcher-operations.md#updates).
