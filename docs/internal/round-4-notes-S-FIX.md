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
