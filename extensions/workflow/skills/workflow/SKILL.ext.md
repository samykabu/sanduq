---
name: speckit-workflow
description: "Drives an issue-bound feature through the Spec Kit lifecycle, from scope to pull request, by claiming each stage from the workflow runtime, running its command and recording an evidence receipt. Use in a project with .specify/workflow.yml to scope an issue, continue or resume a feature, show its status, reread clarification answers, run doctor, or finalize the PR."
---

# Workflow dispatcher

Runtime: `python .specify/extensions/workflow/scripts/workflow.py` (argument arrays or quoted
paths; missing dependencies only from the pinned `requirements.txt`). For the stage loop, read
this file, receipt-rules.md, dispatcher-operations.md and delegation-and-decisions.md once per
session, and delegation.md once a claim carries `delegation` or `environment`.

## Entry points

`continue`: [dispatcher-operations.md](references/dispatcher-operations.md); `status`, `doctor`,
`reconcile`: [utilities.md](references/utilities.md).
`init`, upgrades, `migrate`, `relocate`, `host`: [setup-and-updates.md](references/setup-and-updates.md).
`scope`, `clarify` and `finalize` (`--finalize`) run the stage loop.

## Stage loop

1. `next --feature specs/<f>`. Stop for missing dependencies, malformed policy, ambiguous
   binding, a foreign active executor or a changed package lock. Never skip a gate.
2. Only a reliable measured context reading can pause for context; never invent percentages
   ([context-and-telemetry](references/dispatcher-operations.md#context-and-telemetry)).
3. `claim --feature ... --usage <file>` returns `stage`, `command`, the token, `reference` and
   `reference_text`. The claim already contains the stage reference text; do not read the file
   again. Each stage reference is self-sufficient. The claim may add `mode` (`revalidate`,
   `bind-only`), `merged`, `profile`, `side_effects` and `project_sync`. Handoff and GitHub rules:
   [interruption-and-github-behavior](references/dispatcher-operations.md#interruption-and-github-behavior).
4. Invoke the command through its installed skill
   ([delegation-and-decisions.md](references/delegation-and-decisions.md)), or its delegation route
   when the claim carries one ([delegation.md](references/delegation.md));
   material choices go to the GitHub issue. `workflow:*` commands are runtime stages you run
   yourself, as their reference says. Retest after every fix.
5. Before writing any receipt, read [receipt-rules.md](references/receipt-rules.md) (once per
   session): failed, skipped or pending work cannot pass and a pending decision blocks. Start
   from the claim's `receipt_template` and set every `<...>` gating field yourself. Drift: [recovery.md](references/recovery.md).
6. `complete --feature ... --token ... --receipt <file>` prints `{ok, stage, next}`; claim the
   next stage without asking. When blocked, `pause --reason` and report the actual question or
   failure. Keep required human review and deployment gates.
7. At `ready_to_finalize`, continue to Finalize if the user already asked for a PR, otherwise
   report readiness and ask. Executor hooks never create the PR. Finalize authorizes the PR
   only; merging needs the user's separate authorization, which may be in the original request.

With `profiles.enabled`, the Scope `effort_score` fixes a tier (`lite`, `standard`, `full`) at
the first Plan claim; lite and standard merge Tasks into Plan and run Analyze as
`workflow:lint`, and lite skips the QA and manual stages. `status` lists skipped stages; never
run a skipped stage by hand.

Managed command overlays (`presets/workflow/commands/*.md`) follow the
[managed-overlay-contract](references/dispatcher-operations.md#managed-overlay-contract); the
`speckit-superpowers-bridge` overlays follow [legacy-guard.md](references/legacy-guard.md).
