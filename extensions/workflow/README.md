# Sanduq Workflow

**Local implementation in progress; 1.0.0 is not published yet.** See the
[implementation plan](../../docs/workflow-extension-implementation-plan.md) and
[verification status](../../docs/workflow-implementation-progress.md).

Choose QA Assure and User Manual independently during project initialization.
Daily entry points are `speckit.workflow.scope`, `.clarify`, `.continue`, and
`.finalize`. They are entry points into one resumable dispatcher, not mandatory
pauses between every stage.

Scope -> Specify -> Clarify/Brainstorm -> Plan -> one task generator -> selected
QA/manual analysis -> Analyze -> core Tasks-to-Issues -> one executor -> verification
and review -> selected QA/manual documentation -> explicit Finalize -> one PR.
All workflow and clarification illustrations use Archify. The existing PR, Assure
and User Manual Illustrate dependency remains separately versioned.

The dispatcher calls actual installed agent commands. The Python runtime manages
claims, evidence, invalidation and handoffs; it does not implement semantic agent
work or launch a fresh host session by itself. Missing native invocation support
is a blocker, not an instruction to pretend a stage ran.

## Context

Target a maximum 60% context occupancy with a checkpoint at 50% and a 10% reserve.
Without host telemetry, use explicitly labelled conservative estimates and smaller
batches. A strict guarantee requires a host that enforces per-call bounds; prompt
instructions alone cannot provide that guarantee. Each handoff includes completed
stages, pending task IDs, identity, evidence and a fresh-session resume prompt.

## Packaging and development

Build archives with `python extensions/scripts/package.py workflow` from Sanduq.
The archive bundles canonical presets from `presets/`, so consumer command edits
are unnecessary. Install a staged extracted package using
`specify extension add --dev <extracted/workflow>`; install its bundled presets
through `specify preset add --dev <preset-path> --priority 1` (workflow) and priority
2 (scope-gate/scope-brainstorm). Core command composition was checked on Spec Kit
1.0.6.dev0, commit f21acc4a25ce3aa53ff8653357b49b9aafcf8026. Other versions require
compatibility testing. No claim of general host support is made yet.

For a managed project run `workflow.py init --qa on|off --manual on|off`, configure
GitHub Project status mappings, run `install.py` preview/apply and run doctor. Only explicit
selections enable processes. The dependency lock records exact intended versions;
those pending releases cannot yet be installed from public release URLs.

Scope's community catalog name is ambiguous. Always use the Sanduq archive URL or
verified staged package, never a bare `specify extension add scope` command.

## State and recovery

Policy lives in `.specify/workflow.yml`. Feature state lives under
`specs/<feature>/workflow/`. Claims prevent concurrent stage ownership. Only an
explicit Specify claim can bind a new branch after verifying scope-source.json.
Use `recover` with the recorded token after inspecting possible remote writes;
use `migrate` after reviewing a dependency upgrade. Both preserve an audit trail.
A migration backs up the checkpoint, preserves still-current historical evidence and invalidates changed command selections. Use `--invalidate-from <stage>` when an upgrade changes a stage contract.

Use `upgrade.py --version X.Y.Z` preview, then `--apply`, to update the workflow
package and its integrations with outer rollback. Local staged testing supports
`--packages <extracted-packages>`. See the [operating guide](../../docs/workflow-guide.md)
and [compatibility contract](../../docs/workflow-compatibility.md) for tested limits.

`task_issues.py` is dry-run by default. The core Tasks-to-Issues preset invokes it
with `--apply` within authorized issue work. Native sub-issues are identified by
repository, parent, feature and task ID; retries recover lost responses. Existing
Project mappings are adopted only after verifying native parent links. Unmapped
children block duplicate creation. `--sync-states` updates task issue completion
without changing the publication evidence.

The policy-aware CI workflow validates every changed feature, selected documentation
freshness, task mapping and receipts. It distinguishes committed evidence from live
GitHub checks and human acceptance. Finalize also verifies that each inline PR visual
loads in an authenticated private-repository view.
