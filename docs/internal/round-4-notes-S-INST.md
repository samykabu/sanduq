# Round 4 notes: S-INST (Workflow installer)

Files changed: `extensions/workflow/scripts/install.py`, `upgrade.py`, `hosts.py`; tests in `test_install.py`,
`test_upgrade.py`, `test_hosts.py`. No other file touched.

## X19 keep the three newest install backups

- `install.py`: `backup_zips`, `backup_usage(root) -> {'zips', 'bytes'}`, `prune_backups(root, keep=3)`.
  Newest by `before.zip` mtime across `backups/installs`, `upgrades`, `hosts`. Only `before.zip` is deleted;
  `before.json`, `result.json` and `unrecognized-aliases/` stay. Pruning never raises (an OS error comes back as
  `{'error': 'BACKUP_PRUNE_FAILED: ...'}`), since the apply has already succeeded.
- Pruning runs after `result.json` is written as ok: in `install` (only when not run by an upgrade), at the end of
  `upgrade`, and at the end of `hosts.switch`. A failed apply prunes nothing. The install inside an upgrade leaves
  pruning to the upgrade, so a failed upgrade prunes nothing either.
- The apply result (install receipt as printed, upgrade result, switch result) carries `backups: {zips, bytes}`.
- The first upgrade into this release runs the old `upgrade.py`, which does not prune; pruning starts with the next
  apply.
- Tests: four applies leave three zips, four results and the alias backup; a failed install, upgrade and switch
  prune nothing; the next success keeps the newest three; an install under an upgrade does not prune.

## X21 install timeout

- `required_gate_checks`: `timeout=60` on `gh api`; `TimeoutExpired` maps to the existing
  `CI_BRANCH_RULE_INSPECTION_FAILED` with "timed out after 60 s". Test: a fake `run` that raises `TimeoutExpired`
  and records the timeout.

## W10 installer side

- No code change needed: S-WF's `reconcile.py` change (fresh registration accepted) already covers the restore at
  `install.py` and the apply in `hosts.switch`. Tests reproduce the R1 scenario: reconcile, re-register the owned hook
  enabled, then install and `host --use`. Both pass now and both failed with `HOOK_CHANGED_SINCE_RECONCILE` against
  HEAD's `reconcile.py` (checked in a scratch copy). The install test also checks an edited disabled entry is still
  refused.

## D3 step 5 upgrade refuses during an active Memory archive

- Memory records the active run in `<git common dir>/sanduq-memory/active.json` (`archive.py` `active_id`).
- `install.memory_archive_preflight(root)`: when `.specify/extensions/memory/scripts/archive.py` exists and
  `active.json` names a run, refuse with `MEMORY_ARCHIVE_ACTIVE: archive run <id> is not finished; resume or roll it
  back with "/speckit.memory.session --run <id>" (or see "python .specify/extensions/memory/scripts/archive.py
  status"), then run this again`. Called in `upgrade` and in `install` apply, under the locks, before the snapshot.
  Nothing runs and no backup is made. An idle Memory never blocks. `--run` support in `session.md` is S-PM's.
- `host --use` does not check it (not asked for; it runs reconcile, which may flip Memory hooks after S-WF step 6).
  Say if it should.

## AU8 consumer side

- Fact: in a managed project Workflow never renders `documentation-gates.yml`; the installer deletes an unedited one
  (`install.py`, "policy-aware gate replaces it"), and Workflow's own gate already checks out the head SHA (unless
  `candidate_merge` is selected). So the head checkout reaches managed consumers through `sanduq-workflow-gates.yml`;
  standalone consumers get it from S-AU's `assure_init.update_gate`.
- The real consumer break: the installer called the old render "local edits" once the Assure template changed.
  Installing Workflow over a standalone Assure updates Assure in the same transaction, so the old render no longer
  matched and the install rolled back with `LEGACY_CI_HAS_LOCAL_EDITS`. Now unedited means a render of the current
  template, of the template before this transaction (from the snapshot), or of either without the AU8 head-checkout
  lines (`install.ASSURE_HEAD_CHECKOUT`, equal to `assure_init.HEAD_CHECKOUT`). An edited file is still refused.
- Tests: old render removed after the Assure update; a pre-AU8 render removed when Assure is already new (also pins
  that the constant is in the template); an edited file refused.

## Tests

`uv run --no-project --python 3.11 --with pyyaml --with packaging --with jsonschema python -m unittest test_install
test_install_hooks test_upgrade test_hosts test_host_files`: 109 tests, 3 errors. The 3 errors are pre-existing and
were in the baseline before my edits (94 tests, same 3): `test_dangling_delegate_skill_link_rolls_back_as_a_folder_link`,
`test_dangling_delegate_skill_junction_rolls_back_as_a_junction`,
`test_dangling_junction_target_with_shell_metacharacters_is_restored_exactly` (`KeyError: '.claude/skills/delegate-task'`,
dangling links on this machine). 15 new tests, all pass; 14 fail or error against HEAD's scripts (scratch copy);
the edited-file guard passes on both, as it should.

Also seen, not mine: `test_ci_policy.test_the_runtime_works_from_a_copied_scripts_directory` fails with
`ModuleNotFoundError: sanduq_pr_lint` from `execution_tools.py` (PM21 in progress).

## Requests

- S-WF (doctor in `workflow.py`): show the backup count and bytes. Call `from install import backup_usage` lazily
  inside `doctor` (explicit mode is enough) and report `backups: {zips, bytes}`, for example as an info line
  "Install backups: 3 zips, N bytes (the three newest are kept)".
- S-WF: Workflow CHANGELOG lines below.
- S-AU: keep `assure_init.HEAD_CHECKOUT` byte-equal to `install.ASSURE_HEAD_CHECKOUT`; a test asserts the constant is
  in the template.
- S-DOC: `docs/workflow/operations.md:172` and `docs/workflow/operating-guide.md:236` say a backup ZIP is kept for every
  install and upgrade. New text: "Only the three newest `before.zip` across `installs/`, `upgrades/` and `hosts/` are
  kept; every `before.json` and `result.json` stays." `docs/workflow/utilities.md:137` is still right.

## Changelog lines

Under `## Unreleased` in `extensions/workflow/CHANGELOG.md`:

- Install, upgrade and `host --use` keep only the three newest backup zips across `installs/`, `upgrades/` and
  `hosts/` after a successful apply. `before.json`, `result.json` and alias backups stay. A failed apply deletes
  nothing. The apply result reports `backups: {zips, bytes}`.
- The branch-rule check in the installer times out after 60 s with `CI_BRANCH_RULE_INSPECTION_FAILED`.
- Install and upgrade refuse while a Memory archive run is active (`MEMORY_ARCHIVE_ACTIVE`) and name the command
  that resumes it.
- Install no longer refuses an unedited `documentation-gates.yml` rendered from an earlier Assure template
  (`LEGACY_CI_HAS_LOCAL_EDITS`); it is removed as before.
- Install and `host --use` no longer fail after Spec Kit or Memory registered an owned hook again (with S-WF's W10).

`### Migration`:

- Older backup zips are deleted on the next successful apply after this release (not on the upgrade into it). Copy
  any you still want out of `.specify/workflow/backups/` first.
- Finish or roll back an active Memory archive run before upgrading.
