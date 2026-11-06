# Stage reference: plan

## Required work and evidence

Produce the current plan, research and contracts from the resolved spec. Keep the clarification
gate: a managed claim may recheck an open feature in progress only with resolved clarification
evidence. For a `mode: revalidate` claim, update only what changed; keep established decisions
and task history and never copy a fresh template over reviewed content. A new material choice
goes to the bound issue through `decisions.py` and pauses for an authorized GitHub answer;
apply it and record its evidence before a passed receipt.
Source files that Execute will change are not Plan `inputs`: leave them out, or give them
`{"role": "consulted", "because": "..."}`; as dependencies they fail Execute's completion with
`UPSTREAM_INPUT_CHANGED_DURING_STAGE`.

## Merged plan and tasks

When the claim returns `merged: ['tasks']` (standard and lite tiers), this one pass also writes
tasks.md. Generate tasks with the core Tasks rules: stable `T###` ids in order, one headline line
of at most 200 characters, `Covers FR-xxx` or the requirement ids inline, explicit `depends on`
and file paths, and a `## Phase` heading per phase. Keep detail lines within
`artifacts.budgets.tasks_detail_lines`. On revalidation reconcile only changed requirements and
keep ids, checkboxes and issue mappings. The receipt lists both plan.md and tasks.md in
`inputs`. On the lite tier research.md, data-model.md, quickstart.md and contracts/ are
optional: write them only when the feature needs them.

Lite has no Analyze stage: `complete` runs `workflow:lint` and records `lint`; a finding that
blocks is `PLAN_LINT_FAILED`. Run `lint.py --feature specs/<f>` first and fix the artifact, then
write the evidence file the lite `receipt_template` names: `mkdir -p specs/<f>/evidence && python
.specify/extensions/workflow/scripts/lint.py --feature specs/<f> --json >
specs/<f>/evidence/plan-lint.json`.
