# Sanduq Scope

Canonical source migrated from Bunyan's `tools/speckit-scope` package. Existing MIT
notices remain intact. Version 1.4.0 is a pending local release.

Build with `python extensions/scripts/package.py scope`; the archive bundles the
scope-gate and scope-brainstorm presets. Install the extracted package through
`specify extension add --dev <scope-package>` and install its presets through the
public Spec Kit preset CLI. Do not edit generated skills. The community catalog
contains an unrelated extension named scope: use explicit Sanduq package sources.

The analyst is `skills/scope-analyst/SKILL.md`; shared GitHub clarification is
`skills/github-clarification/SKILL.md`. Commands retain issue guards, prerequisites,
labels, spec-prompt, source binding and native scope decomposition. Mutations require
`--apply`. PyYAML is required for managed policy; unmanaged runtime retains its
existing behavior and approval contract.

With `.specify/workflow.yml`, an inclusive `scope.keep_together` band can settle
feature decomposition without asking again. Provide `effort_estimate.value` and
`effort_estimate.unit` in analysis JSON; the unit must match project policy. This
never suppresses implementation task sub-issues. Policy approval is recorded as
project-policy, not fabricated human approval.

Managed clarification rereads waiting issue comments, including edits. Unchanged
unanswered threads produce no new comments. Real answers update spec.md before
Plan. Questions are individual comments, mentioning the creator, with stable IDs
and unchecked recommendations. Project `scope.statuses` maps logical names such as
Backlog, Feature Specification, Need Clarifications and Ready to actual board names.

Managed default artifacts are `.specify/scope/github/` and
`docs/workflow/implementation-plan.html`; `scope.artifact_directory` and
`scope.plan_file` can preserve existing project locations. Unmanaged projects retain
legacy paths. All paths must stay inside the project. Read `references/analysis-contract.md`
for the effort rubric and approval details.
