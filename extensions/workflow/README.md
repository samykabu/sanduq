# Sanduq Workflow

Workflow runs one GitHub issue from Scope to a verified pull request. It is a single resumable
dispatcher. It claims each stage, calls the installed agent command that does the work, and records
a receipt with fingerprinted evidence. When a session ends, the next session resumes from the
recorded checkpoint. The Python runtime manages claims, evidence, invalidation and handoffs. It does
not do the semantic work itself.

Release changes are in [CHANGELOG.md](CHANGELOG.md). Published versions are in the
[catalog](https://github.com/samykabu/sanduq/blob/main/catalog.json).

## When to use it

Use Workflow when you want:

- one issue-bound feature to move through Specify, Plan, Tasks, implementation, verification and
  review without you calling each Spec Kit command by hand;
- a run that survives an interrupted or out-of-context session;
- evidence that a reviewer or CI can check against the exact files that changed;
- optional QA Assure and User Manual processes in the same run.

Use the individual Spec Kit commands instead when you only need one stage, or when the work is not
tied to a GitHub issue.

Workflow and clarification illustrations use Illustrate, which Scope 1.6.0 and newer also requires
for its dependency plan and clarification images.

## Install

You need Spec Kit, Python 3.10 or later, Git and the GitHub CLI. See
[prerequisites](https://github.com/samykabu/sanduq/blob/main/docs/start/prerequisites.md).

Add the Sanduq catalog, then add Workflow from your repository root:

```bash
specify extension catalog add --name sanduq --priority 10 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
specify extension add workflow
```

Workflow's installer then installs the Sanduq dependencies it needs at the versions recorded in
`dependencies.json`. You do not add Scope, Project, PR or Illustrate yourself. Always let the
installer resolve Scope, because other catalogs use the same ID.

Host-specific steps are in
[install by host](https://github.com/samykabu/sanduq/blob/main/docs/start/install-by-host.md).

## Initialize and check

Run init once per project. It records your choices for QA, User Manual, the decision authority and
the CI evidence gate. Only the processes you select are enabled.

```text
$speckit-workflow-init Enable QA and User Manual. Use our existing GitHub Project and an advisory managed-only evidence gate.
$speckit-workflow-doctor Verify project readiness and installed host commands.
```

The script equivalent is:

```bash
python .specify/extensions/workflow/scripts/workflow.py init --qa on --manual on --delegate off
python .specify/extensions/workflow/scripts/install.py
python .specify/extensions/workflow/scripts/install.py --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

The first `install.py` call previews. The second backs up, applies and rolls back on failure. Run
doctor after any install or upgrade. Doctor is read-only and names the next command when something
is missing.

## Daily use

You use four entry points. Each one enters the same dispatcher, which then runs every stage it can.
They are not pauses between stages.

1. **Scope** binds an issue and scopes it. If no decision is open, it continues.
2. **Clarify** reads the answers posted on GitHub and continues to tasks and implementation.
3. **Continue** resumes the earliest unfinished or stale stage.
4. **Finalize** checks completion and opens or updates one pull request.

```text
$speckit-workflow-scope #412 Add refund approval for orders over the limit.
$speckit-workflow-clarify #412
$speckit-workflow-continue #412
$speckit-workflow-finalize #412
```

The stage chain is: Scope, Specify, Clarify or Brainstorm, Plan, one task generator, selected
QA/manual analysis, Analyze, Tasks-to-Issues, one executor, verification and review, selected
QA/manual documentation, Finalize, one PR.

## Commands

In Codex, call each command as `$speckit-workflow-<cmd>`. In Claude Code, use
`/speckit-workflow-<cmd>`.

| Command | Purpose |
| --- | --- |
| `init` | Select QA, User Manual, decision authority and CI evidence policy. |
| `scope` | Scope the explicit issue and continue when decisions are resolved. |
| `clarify` | Read GitHub answers and prepare tasks and implementation. |
| `continue` | Resume the earliest unfinished or stale stage from its checkpoint. |
| `finalize` | Verify completion and create or update one PR with inline visuals. |
| `status` | Show the current stage, active claim and evidence freshness. |
| `doctor` | Check selected dependencies and available host commands. |
| `reconcile` | Install managed hooks and presets without changing unrelated integrations. |
| `verify-affected` | Run this feature's affected test lanes locally. |
| `ci-report` | Summarize the last N CI runs of a workflow. |
| `gate-explain` | Explain a gate failure and fix evidence-only drift. |
| `worker-brief` | Generate a short brief for one task. |
| `apply-pending` | Apply proposed contract, data-model and research updates. |

Worked examples for every command are in the
[commands reference](https://github.com/samykabu/sanduq/blob/main/docs/reference/commands.md).

## Where state lives

- Policy is in `.specify/workflow.yml`.
- Feature state is in `specs/<feature>/workflow/`. This includes the checkpoint, the receipts and,
  when delegation is on, the `delegations.json` ledger.
- Install locks, backups and runtime locks are under `.specify/workflow/`.

Commit the feature state with the feature. Do not edit checkpoints by hand. Use `recover`,
`migrate`, `amend`, `revalidate` and `relocate` instead. Details are in
[state files](https://github.com/samykabu/sanduq/blob/main/docs/workflow/state-files.md).

## Upgrades

Preview an upgrade, then apply it:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version X.Y.Z
python .specify/extensions/workflow/scripts/upgrade.py --version X.Y.Z --apply
```

The upgrade rolls back on failure. After an upgrade that changes dependencies, run `migrate` on each
in-progress feature before you continue it. See
[upgrades](https://github.com/samykabu/sanduq/blob/main/docs/start/upgrades.md).

To change the default host between Codex and Claude Code, use `workflow.py host --use <host>`.
Do not run `specify integration use` directly. See
[switching hosts](https://github.com/samykabu/sanduq/blob/main/docs/workflow/utilities.md#switching-hosts).

## Limits

- The dispatcher ends at PR publication. It never merges, and `pr_open` is not post-merge
  certification.
- The runtime does not start a new host session by itself. Missing native command support is a
  blocker, not a stage that ran.
- A context limit is a target, not a guarantee. A strict guarantee needs a host that enforces
  per-call bounds.
- The checkpoint identity check catches accidental mix-ups. It does not defend against a process
  that can already edit your working tree.
- Delegation is off by default. A successful delegated run is candidate evidence, never a passed
  stage.
- `verify-affected` results are local. They never count as CI evidence.
- The tested Spec Kit baseline is in `dependencies.json`. Other versions need compatibility
  testing. See [compatibility](https://github.com/samykabu/sanduq/blob/main/docs/reference/compatibility.md).
- Never install Scope with a bare `specify extension add scope`.

## Reference

- [Stages and dispatcher](https://github.com/samykabu/sanduq/blob/main/docs/workflow/stages.md): stage chain, context budget, per-stage references and the execution protocol.
- [Utilities](https://github.com/samykabu/sanduq/blob/main/docs/workflow/utilities.md): the five utility entry points, switching hosts and the skill inventory.
- [State files](https://github.com/samykabu/sanduq/blob/main/docs/workflow/state-files.md): state and recovery, checkpoint identity, relocation and the receipt contract.
- [CI evidence and runner policy](https://github.com/samykabu/sanduq/blob/main/docs/workflow/runner-policy.md): source drift, CI runs as Verify evidence, the evidence gate and task issue sync.
- [Schemas](https://github.com/samykabu/sanduq/blob/main/docs/workflow/schemas.md): the policy, checkpoint and receipt JSON schemas.
- [Delegation](https://github.com/samykabu/sanduq/blob/main/docs/workflow/delegation.md): model-aware routing, recovery, light-tier evidence and ledger trust.
- [Development](https://github.com/samykabu/sanduq/blob/main/docs/workflow/development.md): building and testing the package.
- [Lifecycle walkthrough](https://github.com/samykabu/sanduq/blob/main/docs/workflow/lifecycle.md)
- [Operating guide](https://github.com/samykabu/sanduq/blob/main/docs/workflow/operating-guide.md)
- [Operations](https://github.com/samykabu/sanduq/blob/main/docs/workflow/operations.md)
- [Delivery policy](https://github.com/samykabu/sanduq/blob/main/docs/workflow/delivery-policy.md)
- [Workflow extension overview](https://github.com/samykabu/sanduq/blob/main/docs/extensions/workflow.md)
- [Glossary](https://github.com/samykabu/sanduq/blob/main/docs/reference/glossary.md)
- [Troubleshooting](https://github.com/samykabu/sanduq/blob/main/docs/start/troubleshooting.md)
