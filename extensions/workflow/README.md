# Sanduq Workflow

Workflow 1.4.0 adds token usage per task, phase and feature to the progress
report and makes `--preserve-ci` work on any checkout. Workflow 1.3.0 added issue
decisions and an optional evidence CI gate. Check
the repository catalog for the currently published version. See the
[Delivery implementation plan](../../docs/sanduq-delivery-implementation-plan.md),
[usage guide](../../docs/sanduq-delivery-usage.md), and
[native prototype result](../../docs/native-workflow-prototype-results.md).

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
The default `measured-only` policy continues automatically without reliable host telemetry.
Estimated, missing, stale or invalid readings never force a context pause or a new session. A strict guarantee requires a host that enforces per-call bounds; prompt
instructions alone cannot provide that guarantee. Each handoff includes completed
stages, pending task IDs, identity, evidence and a fresh-session resume prompt.

## Packaging and development

Build archives with `python extensions/scripts/package.py workflow` from Sanduq.
The archive bundles canonical presets from `presets/`, so consumer command edits
are unnecessary. Install a staged extracted package using
`specify extension add --dev <extracted/workflow>`; install its bundled presets
through `specify preset add --dev <preset-path> --priority 1` (workflow) and priority
2 (scope-gate/scope-brainstorm). The isolated native prototype was checked on
Spec Kit 1.0.11, commit 92b7cf7658a177cc417b7ddbeaa4c0a941a5f41b;
its command completion is insufficient for production receipt semantics.
Other versions require compatibility testing.

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

The project selects Disabled, Advisory, or Required CI evidence gating and
individual rules at initialization or later. Managed-only scope lets ordinary
source-only bug-fix PRs pass with an explicit `not_applicable` result. Enabled
rules distinguish committed receipts and decision evidence from live GitHub
checks and human acceptance. Disabling the job checks active branch rules so a
required check is not stranded. Finalize also verifies that each inline PR visual
loads in an authenticated private-repository view.

Before publication, run `ci_gate.py --feature specs/<feature> --base-ref <target-sha>
--check-index` after staging reviewed evidence, then repeat the gate in a clean
checkout of the candidate commit. Missing/unstaged dependencies are reported by
path; the command never stages files. Target-branch source changes invalidate old
verification even when Git merges cleanly. Configure `workflow-evidence` as a
required branch check only when this project has deliberately selected Required
mode; otherwise leave its branch rule optional.

UTF-8 text fingerprints normalize CRLF across checkout platforms. Explicit Git
`-text`, SQL, NUL-bearing and non-UTF-8 files remain byte exact; lone CR is not
normalized. Shared QA/manual hashing follows the same contract. Generated graph
files are excluded from implicit documentation input discovery but remain checked
when explicitly declared as outputs. Revalidate affected historical receipts after
adopting this changed contract; do not relabel old evidence.

The dispatcher ends at PR publication. Its `pr_open` state is not post-merge
certification. Follow the skill's post-merge protocol and retain an external-state
report of exact SHAs, checks and rollout observations. See the
[Review Home pilot findings](../../docs/workflow-pilot-review.md).
