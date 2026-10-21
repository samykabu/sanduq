# Round 4 notes: S-FIX (defects from the live run)

Source: `round-4-live-run.md`. No git command changed the tree or index.

## B1: a rendered spec can bind

- Contract: `bind-only` is the initial Specify claim on a spec Scope rendered, so it is a fresh claim for
  binding. `workflow_policy.fresh_claim` now accepts mode `bind-only` when the active stage is `specify`
  (one place; Workflow's claim is unchanged).
- Second defect on the same path, found by the end-to-end test: the fresh gate compared the analysis's raw
  `specify_prompt` with the published receipt prompt, which publish prefixes with `GitHub issue #N` and
  `Effort: S`. The approved analysis therefore always counted as "revised" and needed applied Decision
  evidence (`SCOPE_RESOLVED_ANALYSIS_EVIDENCE_MISMATCH`). A new `leaf_prompt()` builds the published form;
  publish and the gate share it. The gate still accepts the old fixture shape (analysis prompt equal to the
  published prompt).
- Test: `test_front_half_runtime.BindOnlyAndLazyIssueTests.test_bind_only_claim_binds_through_scope_with_the_printed_flags`.
  Publishes an approved root issue with Scope's fake GitHub, completes Scope through Workflow, renders the
  spec, claims Specify (lean, `bind-only`), runs `scope.main` with the claim's printed `scope_command` and
  checks `scope-source.json`. Decisions' GitHub read is stubbed. Fails before the fix (checked against the
  HEAD `workflow_policy.py`).

## B2: root issue kept whole

- `Scope.native_parent()` returns None on HTTP 404; `ancestors()` and the fresh gate use it. With no parent
  the gate skips the retained-parent checks, but refuses when the issue's approval names children
  (`child_count`), so a child whose parent link was removed is still refused.
- Scope's `FakeGitHub` answers `issues/<n>/parent` (the parent from `children`, else a 404 `ScopeError`).
- Tests: `test_fresh_binding.FreshBindingTests.test_fresh_gate_on_a_root_kept_whole_needs_no_parent` and
  `test_fresh_gate_refuses_a_child_that_lost_its_parent`. Both fail before the fix.

## B3: Project init auto-create

- Both scripts: one create entry per name (Ready was sent three times); after the update every option id is
  taken from GitHub's answer (the update replaces all options, so all ids change; the old code refreshed only
  the created ones).
- Workflow's `project-defaults` now returns `statuses` (the exact names doctor checks, through
  `scope.statuses`). In a Workflow project init maps phases and these names exactly (doctor and Scope compare
  exact names), creates the missing ones, and renames a column that differs only in case or spacing
  (GitHub's default `In Progress`) instead of creating a near-duplicate. Unmanaged projects keep exact,
  case-insensitive and fuzzy matching.
- Test: `test_project_sync.ProjectInitTests.test_managed_auto_create_makes_each_doctor_column_once_with_current_ids`
  runs both shells (bash with jq and pwsh are present here) without `--dry-run` against GitHub's default board
  (Todo, In Progress, Done). Fails before the fix (checked against the HEAD scripts).
- Not done: `updateProjectV2Field` recreates every option, so items on the board may lose their Status value
  when columns are created. That was already true; worth a check on a real board before recommending
  auto-create on a board with items.

## I1: SESSION block

- Line two now ends "in a Sanduq Workflow project Workflow's claim covers this gate too, so do not run it
  separately." Standalone text is unchanged. `test_install.test_session_block_states_the_four_standing_facts`
  asserts it. The block is part of Memory's approval hash; the existing Migration already asks for one
  re-approval. `memory-lifecycle.md` says the same.

## I2: session id

- Options checked: the Workflow guard (`hooks/guard.py`, PreToolUse on Bash) and Progress hooks receive the
  host's `session_id`, but neither stores it where the claim could read it, the guard is optional (Codex needs
  `/hooks` approval) and adding a write to the guard adds a race and a new failure mode. Chosen: the claim runs
  the session handoff on every claim; the model's `session_id` is still recorded, never trusted to skip.
- Safe on feature branches: the session transition only dispatches on the target branch; elsewhere it returns
  `pending` unless a Memory run is active or a writer or guard blocks, which should stop any claim.
- Cost measured on a copy of the live-run clone (Memory installed and enabled, uv Python 3.11): 346 to 431 ms
  per handoff over 5 runs (one `archive.py pending` subprocess, 322 ms alone). No tokens: a non-blocking result
  goes only to the checkpoint. About 5 s of wall time over a 12-claim feature.
- Test: `test_memory_handoff.test_every_claim_runs_the_handoff_whatever_session_id_it_supplies` (replaces
  `test_one_handoff_per_session_after_specify`, which pinned the skip). Fails before the fix.

## Minor: /tmp

- `dispatcher-operations.md` now says to write the usage JSON under `.specify/workflow/runtime/`, since
  Windows Python cannot open Git Bash's `/tmp`. No instruction named `/tmp`; the model chose it.

## Tests run

uv Python 3.11, `unittest discover` per suite:

- scope: 265 tests, OK (1 skipped).
- project: 25 tests, OK (both init shells ran).
- memory: 198 tests, OK.
- workflow: 1248 tests, 3 errors, 2 skipped. All three errors are `test_install` dangling-junction tests
  (`KeyError: '.claude/skills/delegate-task'`). They fail the same way in the main checkout
  (`D:\Projects\Personal\sanduq`), so they depend on this machine and not on these changes. They are not in
  the known list; S-INST should look at them.

# Round 2 (after live run 2, on 32ffcc4)

## B4: Memory refused Workflow's feature directories below issue 100

- Workflow has no feature-name definition of its own (only "inside `specs/`"), so Memory's `Archive.spec()` is
  the one place. It now accepts `\d+[a-z]?(?:-\w+)+`: Spec Kit's `001-name` and `20260101-120000-name`
  (pin 8147943 has both; `numbering.py` already knew the timestamp form) and Workflow's unpadded
  `<issue>-<slug>`, whose slug keeps Unicode word characters and underscores. `specs/memory`, `specs/2`,
  nested and out-of-`specs` paths are still refused. The numbering high-water rules (`\d{3,}`) are unchanged.
- Tests: `test_memory_handoff.test_an_issue_numbered_feature_below_100_queues` (real Memory CLI through
  `complete`'s Execute handoff, `specs/2-add-a-name-flag-to-greet`; failed before) and
  `test_archive_v2.test_spec_accepts_spec_kit_and_workflow_feature_directories_only`.

## B5: `scope-source.json` had no `dependencies`

- History: `pr_lint_binding` has required `dependencies` since `1272a4c` (2026-10-12, first in workflow 1.10.0),
  and `pr_publish` defaults its prerequisites from the same key. No Scope release ever put it there: the gate
  result has been `{issue, score, prompt, fingerprint}` (plus fresh-path fields) since `445bcc6`, and the key
  lived only in the scope receipt. Workflow's test fixtures wrote it by hand. The consumer side is right, so
  the fix is in Scope: `gate()` returns `dependencies` (the receipt's list, already checked equal to the live
  prerequisites), and `bind` writes it.
- Released Workflow 1.16.0: not every consumer. The check runs only for a lean PR stage: `lean_execution.enabled`
  true, or (since 1.13.0) profiles on with a lite or standard feature and lean not set false. Every such PR
  stage fails, in every release since 1.10.0. Full-tier features and projects without lean are unaffected.
- Test: `test_front_half_runtime.BindOnlyAndLazyIssueTests.test_scope_bind_gives_the_pr_lint_its_prerequisites`
  (Scope publish with a done prerequisite #9, Workflow claim, the printed bind, then `pr_lint_binding`: lint
  passes and a body that closes #9 is refused). The B1 test now shares its setup (`bind_rendered_issue`).
- Migration: features bound earlier need `dependencies` added by hand from the issue's scope receipt.

## Board guard: column changes cleared every item's Status

- Both init scripts, only when columns are created or renamed (no mutation, no item reads otherwise): before
  `updateProjectV2Field`, read every item with `gh project item-list --limit 100000` (gh paginates; issues, PRs
  and draft issues all appear, and `item-edit --id` works for each). After the update, set each item's Status
  again by option name with the new ids; an item in a renamed column gets the new name. Every item that could
  not be set is named with its old Status and the run exits 1 (after writing `config.json`, whose ids are
  current). If the items cannot be read, init refuses before changing anything unless
  `--allow-status-reset` / `-AllowStatusReset` is passed.
- In passing: bash init's last line `[ "$JSON" = 1 ] && ...` made a run without `--json` exit 1; fixed.
- Tests (both shells, fake `gh`): `test_a_column_change_sets_every_item_status_again_by_name`,
  `test_unreadable_items_refuse_the_column_change_unless_allowed`,
  `test_an_item_whose_status_cannot_be_set_again_is_reported_and_fails_the_run`. The fake refuses an item read
  after the mutation, so the order is checked too.
- Not verified live: whether `gh project item-list` lists archived items. If it does not, an archived item's
  Status is still cleared. Check on board #13 before release.

## Round 2 tests run

uv Python 3.11, `unittest discover` per suite: scope 265 OK (1 skipped); project 28 OK (both shells); memory
199 OK; pr 29 OK; workflow 1250, 3 errors (the same three `test_install` dangling-junction tests as round 1,
which also fail on the main checkout), 2 skipped.

# Round 3 (after live run 3, on e112a09)

## B6: Memory refused Workflow's and Progress's runtime files in a feature folder

- What Memory protects: archiving deletes `specs/<feature>/` after merge, and the checkpoint commit is the only
  way back. An ignored file is not in that commit, so deleting it is permanent; `spec_files` refuses instead.
- Since when: the Execute queue handoff shipped in workflow 1.11.2, and Workflow's excludes
  `/specs/*/workflow/backups/` (1.0.0) and `/specs/*/workflow/progress/` (1.2.0) predate it. The legacy reporter
  writes `specs/<f>/workflow/progress/` and Progress writes `specs/<f>/progress/.view/` and `.host/` (also
  ignored, through its own exclude lines) during every reported Execute; `refresh`, `migrate` and
  `revalidate-upstream` write checkpoint backups. So in practice the handoff has never queued a managed
  feature whose Execute reported progress; run 2 never got that far because of B4.
- Fix (kept in `specs/<feature>/`; moving the folders would change the legacy reporter, Progress's report
  location, `delegation.py` and every consumer's links for no extra safety): each owner records the exact
  exclude lines it writes in `<git-dir>/info/sanduq-runtime.json` (`{"workflow": [...], "progress": [...]}`),
  beside `info/exclude`. Workflow writes it in `ensure_local_excludes` (install, upgrade, init, the recovery
  commands) and at every Memory handoff; Progress in `git_exclude`. Memory's `Repository.local_runtime()` asks
  git (`check-ignore -v`) which rule decides each ignored path and accepts it only when that rule is a line of
  `info/exclude` and is declared. Those files are dropped from the queued, prepared and archived feature hashes
  (so a report rewrite never stales a queue entry) and deleted with the folder at publication. Any other
  ignored file still refuses, including one matched by a declared pattern that a `.gitignore` line decides.
- Tests: `test_memory_handoff.test_workflow_runtime_files_in_the_feature_do_not_block_queueing` (real Memory CLI
  through `complete`: backups, legacy report and Progress `.view` files; fails before the fix, checked against
  the HEAD `archive.py`), `test_other_ignored_files_in_the_feature_still_refuse`,
  `test_git_state.LocalRuntimeTests.test_only_declared_exclude_lines_make_a_file_runtime`.
- Not tested: the publication-time delete of runtime leftovers runs only in a full archive on the target
  branch; no existing archive test has runtime files, and I did not add one.
- Known limit: Workflow and Progress rewrite the same JSON file without a lock; a lost key is rebuilt on that
  owner's next run, and until then Memory refuses (fails closed).

## G1: archived items

- Introspection on GitHub: `ProjectV2.items` takes `archivedStates: [ARCHIVED, NOT_ARCHIVED]`. On board #14 it
  returned all 4 items, #4 with `isArchived: true`. `gh project item-edit` on an archived item fails with "The
  item is archived and cannot be updated"; `unarchiveProjectV2Item`, then the edit, then `archiveProjectV2Item`
  works. I ran that once on board #14's item #4: it is archived again, with Status Done (its value before run
  3's init), so that board is repaired.
- Both scripts now read items through that GraphQL query (paginated by `endCursor`, 100 per page) instead of
  `gh project item-list`, and restore an archived item by unarchive, edit, archive. A failure at any step names
  the item (and "left unarchived" when re-archiving failed) and the run exits 1.
- The fake `gh` now answers the items query two per page, refuses to edit an archived item until it is
  unarchived, and logs the order. Project README documents the behaviour.

## Round 3 tests run

uv Python 3.11, `unittest discover` per suite: project 28 OK (both shells); memory 200 OK; progress 14 OK
(7 skipped); workflow 1252, 3 errors (the same three `test_install` dangling-junction tests, machine-only), 2
skipped.
