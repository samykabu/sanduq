# Round 5 notes: S-WF (Workflow runtime)

## PR-RES

- Removed `worker_brief.PROJECTION_SCHEMA`, `USAGE_FIELDS` (local copy), `project_usage`, `project_result` and
  `test_projection_keeps_counters_apart_and_unavailable_zeros_unknown`. `execution_tools.USAGE_FIELDS` and Progress's
  `runs.USAGE_FIELDS` stay (used elsewhere). Grep over `*.py`, `*.md`, `*.json` finds no other reference.
- Files: `extensions/workflow/scripts/worker_brief.py`, `extensions/workflow/tests/test_worker_brief.py`.
- Tests: `test_worker_brief.py` 32 OK.
- Request (orchestrator, docs owner): `docs/workflow/lean-execution-delivery.md:14` (P04) says "Result projections
  preserve unknown usage honestly"; that function is gone. Drop the sentence.

## W27 (landed first, for S-SC)

- **S-SC: my only change in `extensions/scope/scripts/workflow_policy.py`** is line 97 in `bound_claim`:
  `if state.get('schema_version') != 1 or ...` became
  `if state.get('schema_version') not in (1, 2) or ...: return None  # checkpoint v1 or v2 (W27)`.
  Nothing else in that file changed. Build your policy cache on top of it.
- `workflow.py`: `SCHEMA = 1` stays the policy schema. New `CHECKPOINT_SCHEMA = 2`, `CHECKPOINT_SCHEMAS = (1, 2)`.
  The three `Run` readers (`load`, `relocate` preview and apply) accept both. `Run.save` sets version 2 and drops
  `repo_path`, so every writer (`start`, a loaded legacy checkpoint's adoption, `relocate`, `migrate`, claim and
  complete) writes version 2. `start` no longer writes `repo_path`; `load` and `relocate` no longer set it.
  The relocation reader (`_relocate_plan`) still records `legacy_repo_path` from a version-1 pre-1.8.0 checkpoint
  (it reads the raw file with `.get`).
- `ci_gate.py:95` accepts `CHECKPOINT_SCHEMAS` (imported from `workflow`).
- `schemas/checkpoint-v1.schema.json`: `schema_version` enum `[1, 2]`; `if` version 2 `then` no `repo_path`.
  File name and title kept (renaming would ripple through tests and docs for no behaviour).
- `docs/workflow/schemas.md`: version paragraph and the `repo_path` row.
- Tests (`test_checkpoint_identity.py`): new `CheckpointVersionTests` (start writes v2 without `repo_path`, policy
  `SCHEMA` still 1; a 1.17-shaped checkpoint (v1 plus `repo_path`) loads without a write and `migrate` rewrites it
  as v2 with the same identity and receipts; version 3 refused; `ci_gate.check` accepts 1 and 2 and refuses 3;
  Scope's `bound_claim` (loaded by path) accepts 1 and 2 and refuses 3). Replaced `CompatibilityTests` (which
  asserted `repo_path` is still written: a deliberate rule change, W27). Legacy-upgrade and relocate tests now assert
  `repo_path` is gone after the write. `fixture_008` (a real 1.3.0 checkpoint) unchanged.
  Result: `test_checkpoint_identity` 62 run, 1 error before the fix to my new test's setup (doctor needed
  `configure`); after it `CheckpointVersionTests` 5 OK. Full module rerun below.
- Request (orchestrator, docs owner): `docs/workflow/state-files.md:48-51` says `repo_path` is "still written by
  `start`, the legacy-upgrade path and `relocate`". Replace with: "Version 2 checkpoints no longer carry it."
- Request (S-SC, optional): `extensions/scope/tests/test_revalidation.py:38` builds a version-1 checkpoint; my
  Workflow-side test covers version 2 through `bound_claim`, so nothing is required.

## W26 (Amendment 4: equal contracts only)

- Git: `workflow.run_git(root, *args, **options)` is the package's one unchecked runner; it applies the W1 memo rule
  (`GIT_READS` plus `worktree list` keep the operation memo, anything else drops it). `git()` (checked, text,
  `GIT_ERROR`) and new `git_ok()` (exit status only) are built on it. Every raw `subprocess.run(['git', ...])` in
  `workflow.py` (`previous_branch`, root-commit walk, shallow probe, `root_commit_still_reachable`, branch-name
  check, `show-ref`, the sync-binding history walk, three `merge-base --is-ancestor` checks) and the two in
  `delegate_dispatch.py` (`--show-toplevel`, `worktree list`) now go through it. Not merged (different contracts):
  `sanduq_hash._git` (bytes, `ValueError`; injected into Assure and User Manual; file untouched, interface kept),
  `source_key._git` (bytes, `SourceKeyError`; stdlib-only for CI evidence), the diff-review `diff-tree` call (own
  environment). `GIT_READS` gained `check-ref-format`, `show-ref`, `show`: those were raw calls before, so their
  memo behaviour is unchanged, and no `git()` caller used them.
- File SHA-256: `execution_tools.sha256_file` is the one helper. `delegate_dispatch.file_sha256` is now an alias of
  it (it was a byte-identical copy); `ledger_bytes_digest`, `verification_plan.file_hash`, `delegation.py:1176` and
  both `decisions.py` evidence hashes call it. Not merged: `workflow.digest` vs `verification_plan.digest`
  (different JSON serialisation, stored), `worker_brief.digest` and `delegation.py:116` (text), portable content
  hashes. Stored digests are byte-identical (same hex of the same bytes).
- Test: `test_front_half_runtime.test_the_one_git_runner_keeps_the_memo_for_reads_and_drops_it_after_a_write`.

## W19 (Amendment 3)

- `canonical_path` keeps its label checks (`..`, absolute, drive, UNC, NUL, empty), then `_no_link_below`: one
  `os.lstat` per existing component under the root. Any symlink, any reparse point (junction, mount point, Windows
  symlink: `st_file_attributes & 0x400`), any component with `:` or a trailing dot or space, or any `lstat` error
  other than not-found falls back to the old full `inside()` resolve. A missing component ends the walk (nothing
  below it exists). Nothing is memoised: a memoised parent cannot be validated without an `lstat` of every ancestor
  (a moved directory keeps its own identity when an ancestor is swapped for a link to it), so a safe memo costs the
  same as none. The saving is `lstat` against `Path.resolve`.
- Tests: new `test_canonical_path.py` (10): symlinked leaf, symlinked directory, link inside the root still
  accepted, junction, case-differing label on Windows, Windows-rewritten names agree with the full resolve, `..` /
  absolute / drive / UNC refused, an ancestor replaced by a symlink and by a junction between two calls inside one
  `operation()`, fast check equals full resolve. With `_no_link_below` forced to True, 7 of the 10 fail.
- Measured (this machine, 400 installed package labels, mean depth 5.7, 4 alternating rounds): full resolve 0.30,
  0.22, 0.40, 0.53 s; lstat walk 0.12, 0.16, 0.26, 0.26 s.

## W18 (Amendment 2)

- `package_digest(root, cached=False)`; only the claim's `DEPENDENCY_CHANGED` check passes `cached=True`. `start`
  and `migrate` (`migration_plan`) hash fully. `complete`, `sync-amend`, `finalize`, `revalidate*`,
  `receipt_status` and `ci_gate` never compute `package_digest` and never read the cache.
- `cached_fingerprints(root, paths)` with `.specify/workflow/runtime/hash-cache.json`
  `{label: [size, mtime_ns, text_attribute, sha256]}`. A hit needs a regular file with equal size, mtime and git
  text attribute and an mtime over 2 s old. Misses go through `fingerprint_files` (portable hashing unchanged); a
  result is stored only when the stat taken before hashing still matches after it and the file is not
  byte-sensitive (its portable hash can come from the index). The cache keeps only the last call's paths; a
  malformed cache is ignored.
- Not done from the plan text: "every evidence write refreshes the cache". Those writes never compute
  `package_digest`, so there is nothing to refresh; the first claim after `start` fills it.
- Tests: new `test_hash_cache.py` (9): a hit reads nothing and equals the full hash; size or mtime change re-hashes;
  a fresh mtime is never served or stored; a changed text attribute re-hashes; byte-sensitive files never stored;
  malformed or mismatching entries ignored; full hashing ignores a forged entry; only the last call's paths kept;
  missing file.
- Measured (424 files, 4.43 MB: a nine-extension install copied from this tree; warm; alternating): full 0.45,
  0.43 s; cached 0.36, 0.38 s, so about 0.07 s per claim here. The rest is listing (`rglob` plus `is_file`, 0.21 s),
  the containment walk (0.22 s) and `check-attr` (0.06-0.08 s), which the cache cannot skip. Where `stat` is cheap
  (round 4 measured 14-29 ms to stat against 320-347 ms to hash) the saving is larger.

## W24: measured, not shipped

- The W18 cache applied to the source inventory on a large real tree (a clone of this worktree: 1,083 source files,
  17.0 MB, mtimes set 2 min old, warm cache, alternating rounds, two runs): full 1.55, 1.75, 1.52 s and 1.29, 1.06,
  1.24 s; cached 1.72, 2.69, 1.83 s and 1.50, 1.41, 1.94 s. Cached was slower: 575 of the 1,083 files are
  byte-sensitive (images, fonts, fixtures) and are never cached, the containment walk and `check-attr` stay, and
  here a `stat` costs about as much as reading a small file. Enforcing paths would also have to bypass the
  operation memo (Amendment 2), adding work to `complete`. The saving does not hold, so W24 is not shipped.
- Scripts (scratchpad, not in the repo): `r5wf/w24bench.py`, `r5wf/pkgbench.py`, `r5wf/w19bench.py`.

## W25 (Amendment 2)

- `foreign_active_claim(root, own)` replaces the claim's loop and runs under the dispatch lock the claim holds.
  Index `.specify/workflow/runtime/active-index.json` `{checkpoint label: [size, mtime_ns, ctime_ns, file id]}`
  holds only checkpoints read as inactive. A checkpoint is skipped only when its key equals the entry and its mtime
  is over 2 s old; every other one (new, replaced, recent, changed, malformed, unindexed) is read. An active one is
  never indexed and is returned at once (first in glob order, as before). Deleted ones drop out (the index is
  rebuilt from the glob on every call). A malformed checkpoint raises as before. Writers need no hook: a write
  changes the mtime and a replace changes the file id.
- Tests: new `test_active_index.py` (9), each asserting the indexed answer equals the unindexed scan: unchanged
  inactive not re-read; new discovered; deleted dropped; replaced with the same size and mtime re-read (file id);
  malformed refused as before; malformed index rebuilt; recent never trusted; active never indexed; own ignored.

## SC8 Workflow side (Amendment 1)

- S-SC decided Move (its notes). `decisions.scope_transport()` returns `sanduq_scope_github`: the copy next to
  `decisions.py` when packaged, else `extensions/scope/scripts/sanduq_scope_github.py` loaded by path. It no longer
  executes `scope.py`.
- `decisions.GitHub.api` uses `sanduq_gh.api(..., timeout=30, retry=method == 'GET')`; `GITHUB_DECISION_API_FAILED`
  kept (stderr, 500 characters). `task_issues.GitHub.api` uses `sanduq_gh.api(..., timeout=120, retry=GET)`;
  `GITHUB_API_FAILED` and its timeout message kept. `ci_evidence.GhClient._run` uses `sanduq_gh.run_gh(binary=True,
  timeout=300)`, never retried (downloads); `EvidenceError` messages kept. A missing `gh` now gives the error code
  instead of `FileNotFoundError`.
- Seams: `test_decisions_corrective.py:96` keeps `d.scope_transport()` and its fake runner; the patch target moved
  from `module.subprocess` (Scope's new module imports no `subprocess`) to `module.sanduq_gh.subprocess`, the same
  `subprocess.run`. `test_task_issues.py:386` and `test_ci_evidence.py:146` patch `<module>.sanduq_gh.subprocess`.
  Deliberate change: a hung GET in `task_issues` is now tried twice (asserted, sleep patched). Added: a hung POST is
  not repeated; a failed call keeps `GITHUB_API_FAILED: <stderr>`; `ci_evidence` failure message and binary
  download. `test_task_issues.py` defined its timeout class twice, identically; now once.
- Tests: `test_task_issues`, `test_ci_evidence`, `test_decisions_corrective`: 44 OK.
- Request (S-SH, from S-SC's decision): inject `extensions/scope/scripts/sanduq_scope_github.py` into the Workflow
  archive next to `decisions.py`. Without it an installed Workflow loads the installed Scope's copy, which needs the
  new Scope.

## Orchestrator follow-ups

- `test_front_half_runtime.py` (the Scope bind helper, about line 873): `reconcile` on the per-process cached
  `_decisions_module()` is now patched with `patch.object` inside the `with`, not overwritten.
- `test_ci_policy.py:421`: the comment names `project_init.py`; the copied-scripts test also copies `sanduq_gh.py`
  (package.py injects it into Workflow).
- `decisions.scope_transport()` already imports `sanduq_scope_github` with the source-tree fallback (SC8 above);
  S-SH's eb90bc8 ships it in the Workflow archive, so the request above is done.

## Test results

- Full Workflow suite (`python -m unittest discover -s extensions/workflow/tests -q`, Python 3.11, all S-WF items
  in): 1,294 tests in 1,702 s, 3 errors, 2 skipped. The 3 errors are the known machine-only `test_install` dangling
  link/junction rollback tests. That run loaded its modules before the two follow-up test edits above; rerun after
  them: `test_front_half_runtime`, `test_ci_policy`, `test_decisions_corrective`: 97 tests OK.
- Earlier partial run of `test_checkpoint_identity test_contracts test_ci_gate test_receipt_contract
  test_ci_revalidation` (machine under load from other streams) had 1 transient `PermissionError` from Windows on
  a checkpoint `os.replace`; the full suite run above had none.
- `check_docs.py` reports `docs/reference/hooks.md` stale. Not from S-WF (no hook or `extension.yml` change here).
