# Round 5 notes: S-W9 (split `workflow.py`, phases 1-2)

## W9

Pure move on the committed tree (HEAD 03c88e9). Every top-level definition moved as a whole segment, with the
comments above it, by a script; a second script checked that each of the 190 definitions of the original appears
byte-identical in exactly one module. The only text change inside moved code: `git_text_attributes` and
`prefetch_attributes` read the memo as `wf_core._OPERATION` (a `from wf_core import _OPERATION` would be a stale copy).

### Module map (as built)

| Module | Holds |
| --- | --- |
| `wf_core.py` | The constants block (`SCHEMA`, `CHECKPOINT_SCHEMA`, `CHECKPOINT_SCHEMAS`, `BASE_STAGES`, `COMMANDS`, ... `WORKFLOW_PACKAGE_PREFIX`, `HANDOFF_BEGIN`/`HANDOFF_END`); `WorkflowError` through `canonical_path`; `run_git`, `git_ok`, `git` (W26 runner); the operation memo (`_OPERATION`, `operation`, `_memo`, `_wrote`); `RACY_NS`; `default_actor`, `require_not_delegated_context`, `ensure_local_excludes`, `locked`; `ACTIVE_INDEX`, `foreign_active_claim` (W25). |
| `wf_identity.py` | `github_repository` through `prepare_issue`. |
| `wf_fingerprints.py` | Sync-state helpers (`sync_state_label`, `sync_entry`, `sync_projection`, `sync_binding`); `HASH_CACHE`, `cached_fingerprints` (W18); `normalized_text`, `text_fingerprints`, `fingerprint_files`, `git_text_attributes`, `prefetch_attributes`, `source_fingerprints`, inventories. |
| `wf_policy.py` | `default_policy` through `policy_cutoff`, including `stages`, `load_policy`, tiers, side effects. |
| `wf_health.py` | `registry` through `pr_lint_binding`, including `package_digest` (W18 caller), `cached_doctor`, `doctor`. |
| `wf_receipts.py` | Sync binding verification (`verify_sync_binding`, `same_path`, `recorded_sync_fields`), `handoff_text`, `native_run_status`, `sync_retry`, context gates, `required_inputs`, input roles, drift, CI and diff-review evidence, `receipt_status`, `recovery_recipe`, `ready_checks`. |
| `workflow.py` | Its import header (unchanged), the re-exports, `stage_reference`, `reference_text`, `execute_protocol`, `Run`, `compact_completion`, `main`, `run_command`. |

Layering: `wf_core` < `wf_identity` < `wf_fingerprints` < `wf_policy` < `wf_health` < `wf_receipts` < `workflow`;
each module imports only from lower ones (checked by the split script). Round-5 additions placed by responsibility: `run_git`/`git_ok`,
`RACY_NS`, `foreign_active_claim`/`ACTIVE_INDEX` and the checkpoint schema constants in `wf_core`; `HASH_CACHE` and
`cached_fingerprints` in `wf_fingerprints`; `package_digest` stays with `registry` in `wf_health` (it reads the registry).

Deviations from the round-4 map, both forced by import cycles:
- The constants block moved to `wf_core`, not kept in `workflow.py`: `wf_policy`, `wf_health`, `wf_receipts` and
  `wf_fingerprints` need `BASE_STAGES`, `COMMANDS` and the rest, and a module cannot import from `workflow.py`
  (it runs as `__main__` or is loaded by path under other names). `stages()` lives in `wf_policy.py`.
  So `check_docs.py`'s AST reader now reads `wf_core.py` and `wf_policy.py` (8 lines). It reads identical values
  (checked: `BASE_STAGES`, `COMMANDS` and `stages(policy)` equal the original's). Its generated text still says
  "in `extensions/workflow/scripts/workflow.py`" (the names are still importable there); changing it would make a
  generated doc stale, so I left it.
- `required_inputs` is in `wf_receipts`, not `wf_fingerprints`: it needs `wf_policy.tier`/`feature_tier`, and `wf_policy`
  needs `wf_fingerprints.sync_state_label`.

### Re-exports and module state

- `workflow.py` re-exports every top-level name of the six modules except `_OPERATION`, by explicit import lists.
  `test_runtime_modules.py` asserts each one is the same object and that `_OPERATION` is absent from `workflow`.
- `workflow.py`'s import header is unchanged, so `w.os`, `w.time`, `w.skill_inventory`, `w.execution_tools` and
  `from workflow import sanduq_ci` (install.py) keep working. Some of those imports are now unused in the file
  itself (pyflakes); removing them could break external `w.<module>` access, so they stay.
- Verified importers: every `from workflow import ...` and `workflow.<name>` in `extensions/workflow/scripts/*.py`
  (14 importers including `delegate_dispatch`, `lint`, `hosts`, `install`, `upgrade`), `smoke_project_init.py`,
  `smoke_upgrade.py`, Scope's `workflow_policy.py` (uses `Run`, `read`, `verify_checkpoint_identity`) and
  `scope.py` resolve (AST check, none missing). `memory_handoff`'s `SimpleNamespace(**globals())`: every `w.<name>`
  it reads is a `workflow` global (test).
- Shared module state across runtime copies. Before, each loaded copy of `workflow.py` (`__main__`, `workflow`
  imported by decisions/apply_pending/reconcile, Scope's `sanduq_workflow_for_scope`) had its own `_OPERATION` and
  its own `WorkflowError` class. Now the copies share the sibling modules from `sys.modules`, so they share one memo
  and one `WorkflowError`. Effects: a write through another copy now invalidates the running command's memo
  (before it did not), and `__main__`'s `except WorkflowError` now also catches errors raised through the
  `workflow` copy. Both are the round-4 design's accepted hazard ("a process that loads two runtimes reuses the
  first submodules"); neither changes a tested outcome. The by-name check in `Run`
  (`type(exc).__name__ != 'WorkflowError'`, around `ready_checks`) still works.
- Module names: first built as `identity`, `fingerprints`, `policy`, `health`, `receipts` (the round-4 map); renamed
  to `wf_*` at the orchestrator's request so a consumer process that already imported a top-level module of a
  generic name (a `policy` or `health` package) cannot shadow them. Regenerated by the same script (the 190
  definitions again byte-identical) and every gate rerun on the renamed tree.

### Patch sites

`patch.object(w, name)` reaches only callers in `workflow.py`. The first full suite run after the split, with the
tests unchanged, failed 30 tests beyond the 3 known (22 failures, 8 errors) in exactly the patched modules, so the
retargets are needed. New helper `extensions/workflow/tests/runtime_patch.py`: `patch_runtime(name, ...)` patches
every runtime module that binds the same object and yields one mock, which is what a patch on the single-file
`workflow.py` did. Retargeted 55 sites, names with a caller outside `workflow.py`: `doctor`, `required_inputs`,
`github_repository`, `fingerprint_files`, `active_host`, `package_digest`, `git`, `read`, `source_fingerprints`,
`resolve_commands`, `compatible`, `command_exists`, `ci_errors`, `host_warnings`, `eol_drift`.

| File | Sites |
| --- | ---: |
| `test_delegation.py` | 16 |
| `test_lean_native_integration.py` | 17 |
| `test_lean_execution.py` | 10 |
| `test_verification_plan.py` | 5 |
| `test_front_half_runtime.py` | 3 |
| `test_evidence_snapshot.py` | 3 |
| `test_hash_cache.py` | 1 |
| `test_active_index.py` | 1 |

Left as `patch.object(w, ...)` because every caller looks the name up in `workflow.py` (or through the `workflow`
module, as `delegate_dispatch` does): `load_policy`, `context_gate`, `reference_text`, and the `Run` methods.

### Benchmark

`benchmark_front_half.py` wrapped `w.<name>`; on the split tree that undercounts (measured with the old wrapper:
`doctor` 0 instead of 1, `fingerprint_files` 39 instead of 251). It now wraps every binding of each counted function
in `workflow` and the runtime modules present in `sys.modules` (none before the split, so it still measures an older
tree the old way).

`benchmark_front_half.py --repo D:/Projects/Personal/sanduq-round5 --tier lite`, BEFORE (HEAD 03c88e9, HEAD
benchmark) and AFTER (split tree, new benchmark): all 30 commands have equal counters and equal stdout bytes.

| Counter | Before | After |
| --- | ---: | ---: |
| doctor | 1 | 1 |
| fingerprint_files | 251 | 251 |
| source_fingerprints | 18 | 18 |
| git | 66 | 66 |
| git_subprocess | 226 | 226 |

### Sizes

| File | Lines | KB |
| --- | ---: | ---: |
| `workflow.py` before | 4,216 | 249.6 |
| `workflow.py` after | 1,798 | 122.2 |
| `wf_core.py` | 412 | 18.7 |
| `wf_identity.py` | 360 | 19.4 |
| `wf_fingerprints.py` | 239 | 11.6 |
| `wf_policy.py` | 328 | 18.1 |
| `wf_health.py` | 418 | 24.1 |
| `wf_receipts.py` | 808 | 43.6 |

KB = bytes / 1024. Total 4,363 lines after, 147 more than before: module docstrings, imports and re-export
lists. `Run` (about 1,380 lines) stays in `workflow.py`: phase 3 is out of scope.

### Files changed

- `extensions/workflow/scripts/workflow.py`; new `wf_core.py`, `wf_identity.py`, `wf_fingerprints.py`, `wf_policy.py`,
  `wf_health.py`, `wf_receipts.py` beside it.
- `extensions/workflow/tests/runtime_patch.py` (new helper), `test_runtime_modules.py` (new, 5 tests), and the 8
  retargeted test files above (`test_active_index.py` and `test_hash_cache.py` also drop their now-unused
  `from unittest import mock`).
- `extensions/scripts/benchmark_front_half.py` (wrappers), `extensions/scripts/check_docs.py` (AST reader).
- `extensions/workflow/CHANGELOG.md`: one `## Unreleased` line ("Internal: `workflow.py` is split into modules
  ..."); no Migration block, nothing an installed consumer runs changes.
- `package.py` unchanged: the package ships the whole `scripts/` folder (checked: `package_files('workflow')` lists
  the six modules; the test helper is excluded with `tests/`). CI: `ci_matrix.py` maps `extensions/workflow/**` to the
  workflow and scope suites, and shards only `test*.py`, so `runtime_patch.py` is never a shard.

### Tests

All with `uv run --no-project --python 3.11 --with pyyaml --with packaging --with jsonschema`. Final (renamed `wf_*`)
tree:

- Workflow suite (`unittest discover -s extensions/workflow/tests -q`): 1305 tests, errors=3 (the three known
  `test_install` dangling link/junction rollback tests), skipped=2, no failures.
- Scope suite (loads `workflow.py` by path): 283 tests OK (skipped=1).
- `extensions/scripts/tests`: 189 tests OK.
- `check_docs.py`: Documentation OK (the stale `hooks.md` failure is gone on this tree).
- `smoke_install.py --host claude` and `--host codex`: both `"ok": true`.
- Lite benchmark: counters and stdout bytes equal per command against BEFORE (table above).
- pyflakes on the six new modules: clean (no undefined or unused names).

Earlier evidence (pre-rename names): the same suite right after the split, with the tests not yet retargeted, had
1300 tests, failures=22, errors=11 (3 known), all in the 8 retargeted files, so the retargets are needed. The
pre-rename tree also passed every gate above.

### Requests

None.
