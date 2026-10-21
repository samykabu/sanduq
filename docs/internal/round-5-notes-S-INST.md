# Round 5 notes: S-INST (installer)

## IP21: native Progress wiring by default for new installs

What: `install()` resolves `progress.hook_wiring` once. An explicit key in `.specify/workflow.yml` wins. Without
one, the wiring `install-lock.json` records is kept; a project whose Progress is installed but has no lock record
keeps Spec Kit's wiring; a project with neither (no Progress wiring yet) gets `native`. The resolved value drives
`wire_progress`, the dry-run result, the lock record, and the "leaving native needs a Progress re-add" check
(`install.py:804` before). `progress_policy(policy, wiring='speckit')` keeps its default, so `wire_progress` and its
callers in `test_progress_reporting.py` are unchanged. The IP9 hint is unchanged (Spec Kit wiring whose interpreter
imports `specify_cli`).

Where the choice lives: the lock (tracked), not `workflow.yml`. The installer does not write the user's policy file
(that would drop comments); the lock's `progress.hook_wiring` is what IP20's doctor check reads.

Files: `extensions/workflow/scripts/install.py` (`progress_policy`, `install`).

Tests: `test_install_hooks.ProgressDefault` (installed layout: a real `install()` apply, Spec Kit stubbed to
register Progress and render its dispatcher entries, the real Progress CLI writing the native entries):
- first install with `--with progress` is native on both hosts, no hint, IP20 `progress_wiring_warnings` empty; the
  next apply without `--with` stays native; a re-render by Spec Kit makes IP20 warn and the next apply clears it;
- Progress installed before (no lock record) keeps Spec Kit wiring and the IP9 hint;
- explicit `speckit` on a new project is kept; then explicit `native` switches it;
- host switching: claude-only first install, then codex added (Spec Kit renders codex entries): both native;
- rollback: a late failure in the first install restores the host files byte for byte and writes no lock;
- upgrade: `upgrade.upgrade` running the new installer on a project whose lock records `speckit` and whose
  Progress 1.4.0 is updated to 1.5.0 keeps Spec Kit wiring.
Without the fix, the two native-default tests fail (checked by reverting the one resolution line, then restoring);
the four keep-tests pass either way (they guard existing behaviour).

Not done: the live gate (orchestrator, L-RUN). Docs that say "default speckit" need a line for new installs (see
Requests).

## SC8 installer side: `required_gate_checks` on `sanduq_gh`

What: the inner `api()` calls `sanduq_gh.api(endpoint, cwd=root, timeout=60)` (same `gh api <endpoint> -H Accept`
arguments). Error mapping kept: timeout `CI_BRANCH_RULE_INSPECTION_FAILED: gh api <endpoint> timed out after 60 s`;
404 / Not Found on the legacy protection endpoint returns None; other failures
`CI_BRANCH_RULE_INSPECTION_FAILED: <stderr, 400 chars>`; invalid JSON or an empty body
`CI_BRANCH_RULE_RESPONSE_INVALID`. New: gh absent now maps to `CI_BRANCH_RULE_INSPECTION_FAILED: gh CLI not
installed` (it raised a bare `FileNotFoundError` before). No retry (`retry=False`, as before); the call is a safe GET,
so `retry=True` could be turned on later. Import uses the dev-tree fallback S-SH documented. The seams stay:
tests patch `installer.subprocess.run` (the same module `sanduq_gh` calls) and `installer.github_repository`.

Files: `extensions/workflow/scripts/install.py` (import, `required_gate_checks`),
`extensions/workflow/tests/test_install.py` (new `test_branch_rule_errors_keep_their_codes_on_the_shared_gh_transport`).

## Test results (all run 2026-10-21, `uv run --no-project --python 3.11 --with pyyaml --with packaging --with jsonschema`)

- `discover -s extensions/workflow/tests -p "test_install*.py"`: 60 tests, 3 errors, the known machine-only
  dangling link/junction rollback tests (`test_dangling_delegate_skill_junction_rolls_back_as_a_junction`,
  `test_dangling_delegate_skill_link_rolls_back_as_a_folder_link`,
  `test_dangling_junction_target_with_shell_metacharacters_is_restored_exactly`). Nothing else failed.
- `test_upgrade.py`: 12 OK. `test_hosts.py`: 31 OK. `test_host_files.py`: 13 OK.
- Also `test_progress_reporting.py` (S-WF's, calls `wire_progress`): 43 OK.

## Changelog lines

For `extensions/workflow/CHANGELOG.md` under `## Unreleased`:

- `install.py --with progress` wires Progress natively (`hook_wiring: native`) on a project with no Progress wiring
  yet. An explicit `progress.hook_wiring` still wins, and a project that already has Progress keeps the wiring
  `install-lock.json` records (Spec Kit's when it records none), with the slow-dispatcher hint.
- The installer's branch-rule check (before it removes a disabled gate job) runs `gh` through the shared
  `sanduq_gh` transport; its error codes are unchanged, and a missing `gh` now reports
  `CI_BRANCH_RULE_INSPECTION_FAILED: gh CLI not installed`.

### Migration

- Existing projects: nothing changes. New Progress installs get native wiring; to keep Spec Kit's dispatcher, set
  `progress.hook_wiring: speckit` in `.specify/workflow.yml` before `install.py --apply --with progress`.

## Requests

- Docs owner: these still say Spec Kit wiring is the default; add "new installs: native" where they state it:
  `docs/workflow/delivery-policy.md:162`, `docs/start/upgrades.md:101`, `docs/extensions/progress.md:66`,
  `extensions/progress/README.md:125-129`, root `README.md:155`.
