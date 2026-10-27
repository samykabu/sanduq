# Setup and updates

Entry points that run outside the stage loop: `init`, package updates, `migrate`, `relocate`
and `host`.

## init

Read existing project instructions, constitution, Scope and manual configuration. Ask once,
unless already selected explicitly:

- QA, User Manual, both or neither; `init --qa on|off --manual on|off --delegate on|off`.
- Board sync, `--board full|minimal|none`: `full` writes every phase and creates task sub-issues,
  `minimal` writes only Ready, In progress, In review and Done with no task sub-issues, `none` needs
  no board. Changing it later invalidates nothing. Project Init is needed in `full` and `minimal`.
- The evidence gate (`disabled`, `advisory` or `required`), its `managed-only` or `all-prs`
  scope and any `--gate-rule NAME=on|off`.
- Decision reviewers beyond the issue creator and collaborators (`--decision-owner LOGIN`,
  repeatable). Status stays the lifecycle field; the Decision single-select field is separate.
- Model-aware delegation (default off). Model preferences, routes, fallback order, install scope
  and per-task overrides live in `.specify/workflow.yml`; a later YAML edit opts in or out
  without reinitializing or invalidating receipts. After opting in, run `workflow.py doctor
  --project`, then `delegation.py install` when it reports `DELEGATE_SKILL_MISSING`, `_BROKEN`
  or `_INCOMPATIBLE`; report any `DELEGATE_SKILL_REPLACED` or
  `DELEGATE_SKILL_LEGACY_BACKUP_MOVED` notice. Running work keeps its route snapshot.
- Where CI runs: GitHub-hosted runners or self-hosted labels the user names. Record labels per
  platform, `sudo apt-get` ability and Python with `ci --policy ... --linux ...
  --system-packages ... --python ...`. `--policy self-hosted-required` needs a dated
  `ci.exceptions` entry for every remaining hosted runner (why, and what would remove it).
  Never edit a rendered `.github/workflows/` file; change the selection and reinstall.
- Optional, only when the user wants them: `profiles` (tiers by effort score),
  `clarification.max_questions_per_round`, `clarification.in_session_first_round`,
  `artifacts.budgets`, `project_sync.points` and `scope.board_cache_seconds`.
- Never offer these as choices; they are validated but change nothing today (doctor warns
  `POLICY_VALUE_INERT` when one is set): `updates.policy`, `execution.checkpoints` (`every-phase`
  acts as `required-only`) and `context.mode: measured-with-estimated-fallback` (acts as
  `measured-only`).
- Edit `.specify/workflow.yml` by merging keys into the section that already holds them; a second
  copy of a section is refused with `POLICY_DUPLICATE_KEY` and its line. `init` with unchanged
  choices leaves the file untouched; `--replace` prints `affected_features` to show before migrating.

Discover existing effort units and preferences and keep their meaning. No later feature asks
these questions again; show changed policy when `--replace` is needed. Then run
`scripts/install.py` for the exact dependency, preset and CI preview, and `--apply` within this
setup authorization (immutable URLs, consumer backups, rollback on failure; `--packages
<extracted-packages>` offline). Never treat a rollback as adoption. Then invoke User Manual
Init only when selected without an approved module map, Assure Init only when QA is selected
and unconfigured, and Project Init only without a valid board configuration, saving
`scope.statuses` where status names differ. Keep board identity, audience map, languages and
publication settings. Each Scope lifecycle state needs a distinct real column and every Project
phase an existing option. Waiting decisions park the issue in the mapped Need Clarifications
status; answers return it under `clarification.resume_on_reinvoke` (default `reread-answers`).
Finish with `doctor --project`; package checks alone do not prove project readiness.

## Updates

Reusable source belongs in Sanduq; installed files and generated skills are distributions.
For dependency and preset updates use `scripts/install.py` preview, then `--apply`; it
restores old hook ownership, installs, then reconciles. Never overwrite generated upstream
skills directly. For the workflow package use `scripts/upgrade.py --version X.Y.Z` preview,
then `--apply` for a reviewed exact version, with active claims resolved first. Never use a
floating version or downgrade state, and never rewrite receipts to hide stale work.

After an upgrade, run `workflow.py migrate --feature ... --preview` on the feature's bound
branch: it writes nothing and lists `invalidated`, `preserved_as_historical` and blockers.
Review them, then `migrate --feature ... --reason <review evidence>` (add
`--invalidate-from <stage>` for changed stage contracts). Confirm the saved `migrations[]`
entry matches the preview, then prove continuation with the next `claim`.

## relocate

Checkpoints identify their repository by the normalised `origin` remote and root commit, and
the bound issue must name this repository's GitHub remote. A legacy path-based checkpoint
upgrades on its next write when both checks pass and its `head` is reachable from HEAD;
otherwise use `relocate --allow-history-change`. For a real relocation (renamed remote,
migrated org, fork), run `workflow.py relocate --feature ... --preview --reason "<why>"`, then
the same without `--preview`. Never use it for an unrelated repository's checkpoint. Flags:
`--allow-branch-rebind` for a branch mismatch, `--allow-repository-rename` when the bound issue
names another repository, `--allow-history-change` for a changed root history, and on a
repository change `--keep-issue-number` (rename or transfer, never a fork) or `--issue
<owner/repo#n>`. It refuses inside delegated workers, needs no active claim, rebinds
`scope-source.json` in the same locked write, and records actor, reason and both identities in
`relocations[]` without invalidating receipts.

## host

Never run a bare `specify integration use`; it rewrites the managed aliases. Run `workflow.py
host --use codex|claude --preview`, review blockers, delegation findings and
`checkpoints_to_migrate`, then run it without `--preview` and migrate each listed checkpoint on
its branch. `host --use <current default>` re-registers a host that lost its skills.
