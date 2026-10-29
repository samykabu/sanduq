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

Workflow illustrations use Illustrate, which Scope also requires for its dependency plan.
Clarification questions may use Mermaid diagrams, which GitHub renders without hosting.

## Install

You need Spec Kit, Python 3.11 or later, Git and the GitHub CLI. See
[prerequisites](https://github.com/samykabu/sanduq/blob/main/docs/start/prerequisites.md).

Add the Sanduq catalog, then add Workflow from your repository root:

```bash
specify extension catalog add --name sanduq --priority 1 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
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
python .specify/extensions/workflow/scripts/workflow.py init --qa on --manual on --delegate off --board full
python .specify/extensions/workflow/scripts/install.py
python .specify/extensions/workflow/scripts/install.py --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

The first `install.py` call previews. The second backs up, applies and rolls back on failure. Run
doctor after any install or upgrade. Doctor is read-only and names the next command when something
is missing.

`--board` picks the GitHub Project board sync: `full` (every phase, task sub-issues), `minimal`
(only Ready, In progress, In review and Done; no task sub-issues) or `none` (no board). Omitted,
a new policy is `full` and an existing one keeps its mode. You can change it at any time; it never
invalidates a feature in flight. Running `init` again with the same choices leaves `workflow.yml`
untouched (`written: false`); a rewrite first backs up the file's bytes under
`.specify/workflow/backups/`, and `--replace` lists `affected_features` with the stage each one
restarts from.

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

With `profiles.enabled: true` in `.specify/workflow.yml`, the effort score Scope records selects a
tier at the first Plan claim. The `standard` tier (score 5 to 8 by default) writes plan and tasks in
one pass and runs Analyze as the deterministic `workflow:lint`; the `lite` tier (score 3 or less)
also skips the QA and User Manual stages and makes research, data model, quickstart and contracts
optional. Scores above 8 run the full chain. Skipped stages appear in `status`. Three more options
shorten the front half: Scope 1.8.0 can render spec.md from the approved analysis so Specify only
binds, the first clarification round can be answered in the session by the issue creator, and
`revalidate-upstream` re-records every stale upstream receipt in one operation after a mid-run
change. See the [changelog](CHANGELOG.md) for the policy keys.

## Commands

In Codex, call each command as `$speckit-workflow-<cmd>`. In Claude Code, use
`/speckit-workflow-<cmd>`.

| Command | Purpose |
| --- | --- |
| `init` | Select QA, User Manual, decision authority and CI evidence policy. |
| `scope` | Scope the explicit issue and continue when decisions are resolved. |
| `scope-run` | Scope one issue: prerequisites, effort and an approved decomposition (the Scope stage runs it). |
| `scope-plan` | Redraw and accept the dependency plan with Illustrate after a split. |
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

## Scope

Scope is part of Workflow from 2.0.0 (it was the separate `scope` extension before). Its scripts are in
`scripts/scope/` (`scope.py`, `clarification.py`, `accept_plan.py`), its commands are
`speckit.workflow.scope-run` and `speckit.workflow.scope-plan`, and its five hook commands
(`speckit.workflow.scope-guard`, `-bind`, `-after-specify`, `-plan-guard`, `-reconcile`) are found by the event
dispatcher by file name and are never host skills. Its state stays in `.specify/scope/`.

In a managed project `scope.py render-spec` writes spec.md from an approved single-leaf analysis so
Specify only binds; `clarification.py publish --answers` records a first round the issue creator
answered in the session as one GitHub comment and moves the issue to Ready;
`clarification.max_questions_per_round` caps a round; Mermaid diagrams are allowed in questions.
The analysis schema and effort rubric are in [references/analysis-contract.md](references/analysis-contract.md).

The `scope-gate` and `scope-brainstorm` presets ship in this package. The community catalog contains an
unrelated extension named scope; Workflow does not need or install any `scope` package.

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

From 1.7.0 each published clarification round also writes `specs/<feature>/workflow/clarifications.json`,
so a report can show the questions without calling GitHub. It lists every question with its options,
answer, state (`pending`, `conflict`, `answered`, `applied`, `waived` or `superseded`), comment URL and the
evidence behind the answer. The file is written only after the specification is replaced and the board
transition succeeds, and before the publication journal is marked complete. Dry runs and failed or stale
publications write nothing. A changed question becomes the next `revision`; earlier revisions stay.
A checkbox answer has no recorded author or time, so `editor` and `answered_at` stay `null`.

Each `evidence` entry is `{kind, url, comment_id, explanation}` with `kind` one of `comment`, `disposition`,
`selection` or `closure`, and `null` for what does not apply. `applied` is `{at, evidence: [string, ...]}`,
always a list. The [shared test vector](https://github.com/samykabu/sanduq/blob/main/extensions/workflow/tests/fixtures/clarifications-vector.json) shows every state. If an
existing `clarifications.json` cannot be read, it is moved to `clarifications.json.unreadable-<batch>` and a
new one is written, so a rerun after the board transition still finishes.

After a split, `/speckit-workflow-scope-plan` redraws the implementation dependency plan as an
Illustrate dependency graph and `scripts/scope/accept_plan.py` accepts it only after issue
coverage, dependency reachability, Illustrate's own checks, SVG/PNG export and a headless
Chromium render check pass. Scope requires Illustrate 2.2.1 or newer (Workflow installs it); PNG export and the
render check need Playwright with Chromium. Clarification questions embed Illustrate PNGs
through verified commit-pinned GitHub URLs, which work in private repositories, and post
a text version with the reason when an image cannot be hosted. See
[the Illustrate plan reference](https://github.com/samykabu/sanduq/blob/main/extensions/workflow/references/illustrate-plan.md).

Managed default artifacts are `.specify/scope/github/` and
`docs/workflow/implementation-plan.html`; `scope.artifact_directory` and
`scope.plan_file` can preserve existing project locations. Unmanaged projects retain
legacy paths. All paths must stay inside the project. Read `references/analysis-contract.md`
for the effort rubric and approval details.

A revision of an already approved decomposition runs unattended: `publish` carries the approval
forward and records the difference against the approved baseline (`.specify/scope/approvals/<issue>-baseline.json`).
A published child whose body changed has no baseline of its own; when it is re-scoped as a single
leaf at its receipt's score, and its receipt still carries the parent's approval that the parent's
receipt lists it under, the parent's approval is carried forward instead (the owner's statement
comes from the parent's local approval record) and becomes the child's baseline. A different score,
a split, a missing retained approval or no local record still stops with `APPROVAL_REQUIRED`.
The fresh read gate accepts such a child when its receipt's `revision_of` chain, followed through
this issue's local approval records, leads to the live parent's current approval; otherwise it
stops with `SCOPE_RETAINED_PARENT_APPROVAL_MISMATCH`.

### Readiness

An issue is ready when each of its prerequisites is In review or Done (status aliases from
`scope.statuses` apply). The check follows prerequisites of prerequisites through In review
issues and stops at a Done one, so a Done prerequisite whose own prerequisite was reopened
does not block. A cancelled issue, or one closed without Done, is not Done. A full inspect
reads pull-request timelines for the direct prerequisites only.

### Snapshots, board cache and spec rendering

`scope.py inspect <issue> --output <file>` saves the snapshot and prints only a summary (issue,
fingerprint, readiness, prerequisites and counts); read the file for the issue, comments and
prerequisite bodies. `gate`, `approve`, `publish` and `bind` accept `--snapshot <file>` and reuse it
when the file is younger than `scope.board_cache_seconds` (default 300; 0 disables) and its
`fingerprint` matches one fresh fetch of the issue; the receipt and labels still come from that
fresh fetch. Otherwise they inspect again (`gate` and `bind` read prerequisites only). Without
`--snapshot`, `gate` and `bind` use `.specify/scope/issue-<number>-snapshot.json` when it exists.
The output says which with `snapshot_reused`.

Project board reads are cached in `.specify/scope/board-cache.json` (`{fetched_at, repo, items}`)
for the same TTL. Every Scope or clarification write to the board or an issue removes the cache,
and a gate that would refuse because of a cached status rereads the live board first.

For an approved single-leaf analysis, `scope.py render-spec <issue> --analysis <file> --feature
specs/<feature>` prints the Spec Kit spec (`text` in the JSON output); `--apply` writes
`specs/<feature>/spec.md` with a `<!-- sanduq-scope:rendered <sha256> -->` first line. It refuses
with `SCOPE_RENDER_UNAPPROVED`, `SCOPE_RENDER_LEAF_REQUIRED` or `SCOPE_RENDER_EXISTS` (replace an
unmarked spec only with `--force`).

`scope.py reconcile <issue> --apply` (the after_implement hook) rolls status up through that issue's
Scope ancestors only; `scope.py reconcile --apply` sweeps every Scope parent.

## Guard hook

The installer registers `hooks/guard.py` as a PreToolUse hook on the shell tools (`Bash`,
`PowerShell` and Codex's shell tool) for Claude Code and Codex (Codex runs it after you approve it in
`/hooks`). It refuses, with a one-line reason:

- `git add -A`, `git add -u`, `git add .`, `git commit -a` and `git stash`; the refusal says to stage
  owned paths by name. `SANDUQ_ROLE=coordinator`, set in the environment that launches the host,
  turns these git rules off for the whole session, including every subagent;
- `delegate_dispatch.py trust-reset|accept|reassign|adopt` in a worker or subagent context;
- `delegate_dispatch.py collect --confirm-fallback` and `delegate_dispatch.py attest-native` in a worker,
  subagent or delegated orchestrator context: both are the top-level session's own word;
- in a managed project (`.specify/workflow.yml` present), `gh pr create|edit --body-file <f>` when the
  sibling `<f without extension>.lint.json` that `pr_publish.py` writes is missing or its
  `body_sha256` is not the hash of `<f>`;
- `gh pr create` when its head (`--head`, else the current branch) is the repository default branch
  (`origin/HEAD`). A branch the guard cannot resolve allows the call.

The guard is advisory: it sees only commands sent through the host's shell tools, so a script, an
alias or another tool bypasses it, and a hook error allows the call. It is a hygiene control, not a
security boundary; see [SECURITY.md](https://github.com/samykabu/sanduq/blob/main/SECURITY.md).

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
`python3 .specify/events.py speckit.progress.hook <event> 10`: SessionStart, PreToolUse (matcher
`Task|Agent|spawn_agent`), PostToolUse, Stop and SessionEnd. The bridge counts a Codex hook as active only when
`[projects."<path>"] trust_level = "trusted"` and a `[hooks.state."<config file>:<event>:<group>:<hook>"]` entry with a
`trusted_hash` exist in `$CODEX_HOME/config.toml` (or `~/.codex/config.toml`). Without them it selects `refresh` and prints
`reporting: refresh (codex hooks not approved)`; `--json` adds `reason`. The hash is not verified: a hook that changed after
approval may need approving again, and the bridge cannot detect that.

**Never spawn, retain, message or poll an agent only to maintain the report.** This holds in every mode. The coordinator
makes the few calls in its mode table as part of its own turn. Opening the report once for a person is fine; reopening it,
re-verifying it or waiting to see it refresh is not. Waiting for a worker to finish is different and stays.

### Old calls while Progress is installed

When Progress is installed and enabled, `scripts/progress.py` writes nothing and exits 2 with one line that names the
Progress command to use (on stdout with `--summary`, else on stderr), for example
`error PROGRESS_INSTALLED: Sanduq Progress maintains the report; instead of "progress.py sync", run "python
.specify/extensions/progress/scripts/progress.py refresh". Do not retry this call.` Without Progress, or with it
disabled, the legacy reporter runs as before.

| Legacy call | Use instead |
| --- | --- |
| `init` | `progress init` |
| `task` | check the task box in `tasks.md` |
| `usage` | nothing: hooks and delegate results record usage |
| `sync` | `progress refresh` |
| `phase` | nothing: Progress reads phases from `tasks.md` |
| `pr` | `progress note "PR open: <url>"` |
| `event` | `progress note "<text>"` |

`workflow.status` carries Progress's one status line as `progress_status`. Lean run status
(`workflow.py status --runs`) reads Progress's `runs --json` when available. The rules are in
`skills/workflow/references/reporting.md`. The full Progress reference is
[here](https://github.com/samykabu/sanduq/blob/main/extensions/progress/docs/commands.md).

## Where state lives

- Policy is in `.specify/workflow.yml`.
- Feature state is in `specs/<feature>/workflow/`. This includes the checkpoint, the receipts and,
  when delegation is on, the `delegations.json` ledger. From 1.12.0 it also holds `lifecycle.jsonl`,
  the event log of claims, completions, recoveries and invalidations.
- Install locks, backups and runtime locks are under `.specify/workflow/`. Each apply's `before.zip`
  holds the exact bytes of every file the installer may change, including `.claude/settings.json`,
  `.codex/config.toml` and `.codex/hooks.json`, which can carry MCP server keys. Backups are excluded
  from git in that clone only; they travel with any copy or archive of the project folder.

Commit the feature state with the feature. Do not edit checkpoints by hand. Use `recover`,
`migrate`, `amend`, `sync-amend`, `revalidate` and `relocate` instead. Details are in
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
- Workflow provides Scope. Do not install a `scope` extension: Sanduq's Scope 2.0.0 is a retired shim, and the
  community catalog's `scope` is another package.

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
