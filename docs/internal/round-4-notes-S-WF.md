# Round 4 notes: S-WF (Workflow runtime)

Python for every run: `uv run --no-project --python 3.11 --with pyyaml --with packaging --with jsonschema python`.
"Fails before" means the new test was run against HEAD's scripts in a scratch `git archive` copy.

## F1

- **W10** `reconcile.py`: an owned entry that differs from its journaled `managed` copy and is enabled is a fresh
  registration (Spec Kit `register_hooks`, Memory's installer, an update with new manifest text). Apply journals it
  as the new `original` and disables it; restore keeps it and drops the journal. A disabled entry that differs is
  still refused with `HOOK_CHANGED_SINCE_RECONCILE` by apply and restore. The entry has no provenance, so a hand
  re-enable is treated the same (changelog says so). The installer's restore (`install.py`) and `hosts.switch` call
  the same function, so they get the rule without a change (S-INST confirmed with its own tests).
  Tests in `test_reconcile.py`: re-registration then apply; restore keeps a fresh registration; edited disabled
  entry refused by apply and restore; update with new description text (S-PM's request). The first two fail before.
- **W11** `recorded_sync_fields`: history blobs are hashed through `portable_content` with the file's git text
  attribute, as the receipt was. One call site serves `sync-amend` and `migrate`. Not done: the one-`git log` plus
  `cat-file --batch` rewrite (optional in R1; no behaviour change). Test
  `test_sync_binding.LegacyReceiptTests.test_w11_crlf_history_matches_the_portable_recorded_hash` (autocrlf off,
  CRLF blob in history) fails before.
- **X21** `task_issues.GitHub.api` (120 s, `GITHUB_API_FAILED: gh api <path> timed out after 120 s`) and
  `ci_evidence.GhClient._run` (300 s, artifact downloads included; `EvidenceError`). Tests `GitHubTimeoutTests`,
  `GhTimeoutTests`; both fail before.

## D4 Workflow side

`workflow.py` imports `sanduq_remote` with the dev-tree fallback (`parents[2]/scripts/shared`) and re-exports
`normalize_remote_url`, `same_github_repository`, `_strip_dotgit`, `_normalize_path_remote`. The memoised
`origin_url` wraps `sanduq_remote.origin_url`; `github_repository` keeps `GIT_ERROR: no remote.origin.url` and
`GITHUB_REMOTE_REQUIRED`. The old copies and `import urllib.parse` are gone. `test_checkpoint_identity` (58) passes
unchanged. PM21 (orchestrator request): `execution_tools.py` imports `sanduq_pr_lint` the same way and re-exports
`CLOSE_REF`, `FENCE`, `pr_lint`, `PR_LINT_SCHEMA`. `test_ci_policy`'s copied-scripts test now copies both shared
helpers, as `package.py` does (it failed with `ModuleNotFoundError: sanduq_pr_lint`, which S-INST saw).
`test_execution_tools.test_pr_generate_procedure_lints_before_any_github_write` pinned the string
`execution_tools.py pr-lint`, which S-PM's PM21 text removed; it now checks the same order with "lints its closing
references" before `gh pr edit` and `gh pr create`.

## D1

`finalize` and `status` texts from R1 §1, with finalize keeping the "open the PR" trigger (R4 §2.1). Both pass
`benchmark_instructions.describe`. Workflow's command descriptions total 2,192 characters (was 1,995). New
`test_skill_split.CommandDescriptionTests`: every manifest description equals its command frontmatter.

## D3 Workflow side (steps 1, 4, 6)

- **W13** `reconcile.managed_hook(event, hook)` is the one rule; doctor imports it lazily. The rule keeps one
  `managed = ...` assignment with inline literals, because `check_docs.py` evaluates it with only `OWNED`. The
  redundant `project and after_tasks` clause is dropped. Doctor's `DUPLICATE_STAGE_OWNER` names
  `reconcile.py --apply`. Test: for every hook in the shipped manifests, doctor's decision equals the rule.
- **Step 6** the rule adds `memory` + `speckit.memory.session` / `speckit.memory.prepare`; `impact` stays.
  `check_docs.py --write` regenerated `docs/reference/hooks.md` (two rows now "disabled; the dispatcher owns this
  step"); `check_docs.py` passes.
- **W14** `Run.memory_session`: the claim runs `memory_handoff.handoff(..., 'session', lock=False)` at Scope,
  Specify and when the usage `session_id` differs from the last recorded one. `lock=False` because the claim holds
  `dispatch.lock` and the lock is not re-entrant; standalone calls still lock. Every `blocked` result and every
  `dispatch` result is returned instead of a stage (`memory_blocked` with `ok: false`, `memory_dispatch` with
  `ok: true`, both with `memory_handoff`); nothing is saved. Otherwise `memory_session {session_id, status, at}` goes
  into the checkpoint with the claim (schema updated). Without Memory no helper runs (registry check only).
  PM24 consumer: the policy helper is skipped when `pending` carries a `policy` dict and `policy_hash`.
  Prose: `dispatcher-operations.md` and `memory-lifecycle.md` (prepare hook disabled; the handoff queues with
  `default_checks`; the session handoff runs in the claim).
  Tests `test_memory_handoff.ClaimSessionHandoffTests` (6): no helper without Memory; the claim's own lock
  (WORKFLOW_BUSY without `lock=False`); active run, malformed helper output and a missing Memory command each refuse
  and record nothing; dispatch returns the actions; one handoff per session after Specify. Plus
  `test_pending_with_policy_facts_saves_the_policy_helper`.
- **Lifecycle test** `test_memory_hook_lifecycle.py` (3 tests). It uses Spec Kit's real
  `HookExecutor.register_hooks` when `specify_cli` imports, else a stand-in with the same re-enable and purge
  behaviour. Run both ways: the workflow suite (stand-in) and with the pinned Spec Kit 8147943 via
  `--with "specify-cli @ git+https://github.com/github/spec-kit.git@8147943..."`: all pass. It covers Memory before
  and after Workflow, Memory re-init (real `install.py`), `specify extension update memory`, an edited disabled
  entry refused, `reconcile --restore`, automatic mode off (the claim's real `archive.py pending` reports pending and
  the claim goes on) and an interrupted archive (claim `memory_blocked`; `install.memory_archive_preflight` refuses).
  The update drops impact's install-only `before_specify` binding (asserted); the handoff does not read hook entries.
- **Found by the pinned run (S-PM request below):** Memory's `install.py add_hook` deletes a top-level key that
  follows `hooks:`. Spec Kit's `register_hooks` writes `settings: {auto_execute_hooks: true}` after `hooks` when the
  file had no `settings`; Memory's own-block regex then swallows the `settings:` line and leaves
  `auto_execute_hooks: true` under `hooks`, which reconcile and doctor refuse (`INVALID_HOOK_LIST`). The lifecycle
  test puts `settings` before `hooks` to avoid it.

## D5

- `scripts/progress_shim.py` deleted, and `progress_bridge.status`, `progress_version`, `_flag_unsupported` with it
  (their only caller). `progress.py`: with Progress installed and enabled every legacy subcommand prints one
  `error PROGRESS_INSTALLED: ...` line naming the replacement (stdout with `--summary`, else stderr), writes nothing
  and exits 2. Absent or disabled Progress: the legacy reporter, unchanged.
- The 35 tests in `ReportingModes`, `ProgressWiring` and `AbsentProgress` moved to `test_progress_reporting.py`
  unchanged, except one helper: `init()` now runs `progress init --feature` on the real CLI (it ran the legacy
  `init`, which forwarded). The shim-only classes (ShimMappings, ProcessCounts, CompatibilityErrors,
  WorkstreamMarker, StatusSchemaFlag; 33 tests) went with the shim.
- New: `LegacyCallsWithProgress` (3), `ProgressCliContract` (2, IP23: init, lane, block, unblock, note, refresh,
  bind and status against `extensions/progress/scripts`, each exit 0 with at most one line, plus a check that the
  verbs `reporting.md` names are exactly these seven), `StatusLine` (2), `DoubledProgressWiring` (1, IP20).
- IP23 found that `refresh` prints nothing without `--verbose`; `reporting.md` said every verb prints one line. The
  text now says "at most one line". It also said `progress lane new ...`, which would create a lane named `new`;
  now `progress lane <id> ...`.
- **W21** `progress_bridge.status_line` runs `progress status --feature <f>` (text, 10 s timeout); a failure comes
  back as its first line. `native_run_status` adds `progress_status`. `dispatcher-operations.md` no longer asks the
  model to run `progress.py status`.
- Text: `reporting.md`, `execute/reporting-legacy.md`, `README.md` (the forwarding table replaced by the
  replacement table). Old time: `test_progress_shim` 92.7 s (68 tests, parallel baseline); new module about 10 s.

## W6

`delegation.cached_health` (claim only; `doctor` still always probes). Key: host, scope, driver override, plugin
root, the sha256 of the driver copy's `SKILL_FILES`, and path, size and mtime of `node`, `codex`, `claude`. TTL
3,600 s. Red results and results with no available CLI are not kept; `delegate_dispatch` drops the file when the
driver start fails. Notices are reported by the probe that raised them, not on hits.
Measured on this machine (real node 26, codex and claude CLIs, a temp project, under load from other streams):

| Call | Time |
| --- | --- |
| uncached `doctor(install=True)` (today's claim) | 2.12 s, 2.42 s |
| first call (miss) | 2.77 s |
| hit | 0.07 s, 0.05 s, 0.05 s |
| after a driver-copy edit (invalidated) | 2.67 s |
| after a start failure (`forget_health`) | 2.19 s |

Claim the saving only for hits: about 2.1 to 2.7 s per delegated claim after the first in an hour.
Tests `test_delegation.HealthCacheTests` (4).

## W20

`recovery_recipe(..., root=None)`: with the root, an explicit drift of the Project Sync state whose receipt holds a
raw hash prints `workflow.py sync-amend --feature <f> --reason "<why>"` first. Callers in `workflow.py`,
`gate_explain.py`, `ci_gate.py`, `apply_pending.py` pass the root. The "Receipts fingerprint ..." paragraph and the
"recorded before 1.16.0" bullet moved to `recovery.md#project-sync-state`; one sentence stays.
`dispatcher-operations.md` is 7,127 B (8,152 at HEAD; W14 and W21 text included). Test
`test_w20_the_recipe_for_a_raw_hash_drift_names_sync_amend`.

## W22 and X25

New `tests/lifecycle_snapshot.py`: `reuse(test, build, reopen, key)` runs `build()` once per class, key and starting
tree (sha256 of every file under the test root, `.git` included), saves a copy, and gives later tests a fresh copy
of that tree. A test that changed anything first, or a different class, builds its own. Used by:
`test_ci_gate.ready`, `test_gate_explain.ready`, `test_receipt_contract` (`LegacyCheckpointTests.setUp`,
`AmendmentTests.ready`), `test_ci_revalidation.DriftHarness.setUp`, and `test_front_half_runtime.Base`
(`run_object` and `advance`; the one test that counts doctor calls under a patch calls `advance_fresh`). The two
slowest other modules, by the serial BEFORE run, are `test_ci_revalidation` and `test_front_half_runtime`.

Serial, one module per process, same machine and session (other streams were running too):

| Module | Tests | Before | After |
| --- | ---: | ---: | ---: |
| test_ci_gate | 29 OK | 130.6 s | 32.8 s |
| test_ci_revalidation | 37 OK | 596.1 s | 260.8 s |
| test_front_half_runtime | 47 OK | 159.2 s | 128.3 s |
| test_gate_explain | 13 OK | 107.8 s | 31.3 s |
| test_receipt_contract | 30 OK | 211.8 s | 177.3 s |
| total | 156 OK | 1,205.5 s | 630.5 s |

Same test count and results before and after. `test_receipt_contract`'s remaining time is in classes whose tests
each change the tree before their lifecycle (no reuse possible without changing what they test).

## W23 (small parts)

`clear_caches` and `scope_decision` (and its one test) deleted. `setup-and-updates.md` names the no-op values
(`updates.policy`, `execution.checkpoints: every-phase`, `context.mode: measured-with-estimated-fallback`,
`clarification.transport`). Not done: `worker_brief.project_result` / `project_usage` / `PROJECTION_SCHEMA` are
test-only too, but they carry a named schema (`sanduq.worker-result.projection.v1`); removing it needs a decision.

## IP20

`progress_wiring_warnings`: with `install-lock.json` `progress.hook_wiring: native` and a `speckit.progress.hook`
entry in any host file `progress_bridge.HOST_FILES` lists, doctor and status warn `PROGRESS_HOOKS_DOUBLE_WIRED` and
name `install.py --apply`.

## presets/workflow

- SC12: `speckit.superspec.brainstorm.md:30` now states the one limit (`clarification.max_questions_per_round`,
  with `priority`, the rest deferred), matching `clarification.py:573-578`.
- SC18: checked against S-SC's contract (`round-4-notes-S-SC.md`). The composed `specify-gate.md` names no
  after-Specify chain and sends standalone runs to `specify-standalone.md` only without `.specify/workflow.yml`, so the
  Workflow overlay keeps "then continue with the upstream instructions below". No change needed.
- S-SC's bound-issue-only parent reconcile: no Workflow text or test assumed the full sweep (grep).

## Orchestrator requests done

`README.md:36` `--priority 1`; S-INST's changelog lines and Migration lines; doctor reports `backups` (lazy
`install.backup_usage`, explicit doctor only); S-PM's Memory migration line.

## Requests to other streams

- **S-PM** (`extensions/memory/scripts/install.py`): `add_hook` must stop the own-block match at a top-level key
  (`^\S`), or it deletes `settings:` when it follows `hooks:` (see D3). Reproduced with the pinned Spec Kit.
- **S-DOC** `docs/reference/hooks.md:17` (hand-written): "Memory's hooks ... stay as they are" should say "Memory's
  impact hook". `docs/extensions/progress.md:61` says the forwarder keeps prompts working; it now exits 2 and names
  the Progress command. `docs/extensions/memory.md` / `docs/workflow/*`: the claim now runs the session handoff.
- **S-CI**: `test_progress_shim.py` is gone and `test_progress_reporting.py`, `test_memory_hook_lifecycle.py` are new
  (shard weights). The lifecycle test uses the real Spec Kit when the job has `specify-cli` installed.
- **S-IL**: `attempt record` and the legacy-attempt path in Progress have no caller left in this Workflow (keep them
  for older Workflow releases, per R1).

## Tests

Full workflow suite at the end (`scratchpad/runsuite.py`: every module in its own process, 6 in parallel):
**1,247 tests in 55 modules; 1,243 pass, 4 errors.**

- 3 errors in `test_install` (`test_dangling_delegate_skill_*`, `KeyError: '.claude/skills/delegate-task'`): in the
  baseline before any change and in S-INST's notes (dangling links on this machine).
- 1 error in `test_delegation.test_collect_summary_files_verified_only_against_worker_changed_paths`:
  `PermissionError [WinError 5]` on an `os.replace` in `.specify/workflow/runtime` (Windows file contention under
  load). It passed twice alone right after, and the whole module passed (181 tests) earlier in the session.

Count against the start-of-session baseline (1,258, taken while my first edits were landing): minus 68
(`test_progress_shim`), minus 1 (`scope_decision`), plus 43 (`test_progress_reporting`: 35 moved, 8 new), plus the
other new tests in this note (W10 4, W11 1, W20 1, X21 2, D1 1, W13 1, W14 7, PM24 1, W6 4, lifecycle 3), and the
other streams' own new tests in `test_install`, `test_hosts`.

Also run: `extensions/scripts/tests` (151, OK) and `check_docs.py` (OK). The lifecycle test also passed with the
pinned Spec Kit 8147943 installed.
