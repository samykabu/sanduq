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

## Progress reporting

Workflow works without any report extension. If you install the optional
[Progress](https://github.com/samykabu/sanduq/blob/main/docs/extensions/progress.md) extension, the report
becomes a projection of `tasks.md`, the delegation ledger and the host's hooks:

```bash
python .specify/extensions/workflow/scripts/install.py --with progress          # preview
python .specify/extensions/workflow/scripts/install.py --with progress --apply
```

The instructions pick one of three modes. Ask the bridge once per Execute claim or resume:

```bash
python .specify/extensions/workflow/scripts/progress_bridge.py mode [--host claude|codex] [--json]
```

```text
reporting: projection
```

The bridge reads the spec-kit registry and the host's hook configuration. It never starts Progress. The host is detected
from the environment when `--host` is omitted. A Codex coordinator passes `--host codex`, because Codex is not always
detectable. `--json` adds `script`, `automatic`, `host` and the `source` of the decision.

| Mode | When | What the coordinator does |
| --- | --- | --- |
| `projection` | Progress is installed and enabled, and its hooks are registered and enabled for the active host | Records only lanes, blockers and notes. Task state, retries, usage and run history are collected. |
| `refresh` | Progress is installed and enabled, but the active host does not collect automatically (or the host is unknown) | The same, plus an explicit `progress refresh` after each attempt and phase. |
| `legacy` | Progress is absent or disabled in the spec-kit registry | The `progress.py` calls it has always made. |

Hooks count as disabled when the host's own switch is off: Claude Code's `disableAllHooks`, or a Codex `[features]`
entry (`hooks` or `codex_hooks`) set to `false`. A config that cannot be read is not evidence of collection.

**Codex approval.** Codex runs a project hook only when the project is `trusted` in the user config and the hook
definition was approved. Review and approve the five Progress hooks in Codex (its hooks review prompt), each running
`python3 .specify/events.py speckit.progress.hook-<event> <event> 10`: SessionStart, PreToolUse (matcher
`Task|Agent|spawn_agent`), PostToolUse, Stop and SessionEnd. The bridge counts a Codex hook as active only when
`[projects."<path>"] trust_level = "trusted"` and a `[hooks.state."<config file>:<event>:<group>:<hook>"]` entry with a
`trusted_hash` exist in `$CODEX_HOME/config.toml` (or `~/.codex/config.toml`). Without them it selects `refresh` and prints
`reporting: refresh (codex hooks not approved)`; `--json` adds `reason`. The hash is not verified: a hook that changed after
approval may need approving again, and the bridge cannot detect that.

**Never spawn, retain, message or poll an agent only to maintain the report.** This holds in every mode. The coordinator
makes the few calls in its mode table as part of its own turn. Opening the report once for a person is fine; reopening it,
re-verifying it or waiting to see it refresh is not. Waiting for a worker to finish is different and stays.

### Old calls while Progress is installed

When Progress is installed, `scripts/progress.py` forwards every subcommand to the Progress CLI and writes no legacy
state, so older instructions keep working. Each call prints what it always did: the report path, or one `--summary`
line such as `ok done=0 total=6 pending=4 running=1 blocked=1`.

| Legacy call | Progress verbs it runs |
| --- | --- |
| `init --tasks T --output O [--open]` | `init`; `--open` then opens `index.html`. `--title` is refused |
| `task --id T --status running [--agent A] [--note N]` | A lane owned by `A` is found or made (`lane new --tasks T --owner A`), `T` is moved into it, then `unblock --all-for T`, `note` when a note is given and `attempt record --lane L --run legacy-T-A --status running` |
| `task --id T --status done` | The same lane step, `unblock --all-for T`, `attempt record ... --status done --ended <now>` |
| `task --id T --status blocked --note N` | `block T --by L2` when the note is a lane, task, W or C id such as `L2`, else `block T --by ext:"N"`; plus `attempt record ... --status blocked` |
| `task --id T --status pending` | `unblock --all-for T`, then `note "T pending" --target T` |
| `event --message M` | `note M` |
| `phase --name N --status S [--commit C]` | `note "Phase N: S (C)"` |
| `pr --url U --status open\|merged` | `note "PR S: U"` |
| `sync` | `refresh` |
| `usage --id T` or `--overhead LABEL` | `attempt record ... --usage-json` with the counters Workflow's own usage reader produced, and a `note` when usage is unavailable |
| any call with `--json` | Refused with a compatibility error and exit 2. Use `progress.py status --json` |
| `--summary` | Kept |

An unknown task id prints `error Unknown task ID: T099` and exits 2. A legacy request with no faithful mapping fails
with a compatibility error; it never succeeds silently. Do not retry it. Use the Progress verb named above.

Legacy attempts carry origin `legacy` and never override the delegation ledger. Lean run status
(`workflow.py status --runs`) reads Progress's `runs --json` when available. The rules are in
`skills/workflow/references/reporting.md`. The full Progress reference is
[here](https://github.com/samykabu/sanduq/blob/main/extensions/progress/docs/commands.md).

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
