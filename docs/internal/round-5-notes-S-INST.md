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

## D1 (live run): optional package needs a newer Spec Kit; the cause was hidden

1. Preview check. `install()` checks each optional package it is about to add or update (Progress) against the
   installed Spec Kit, in preview and before any apply step: `OPTIONAL_PACKAGE_SPECKIT_INCOMPATIBLE: progress 1.5.0
   requires spec-kit >=1.1.1.dev0,<2.0.0; installed 1.0.11. Upgrade Spec Kit or run without --with progress.`
   (the "or run without" part only when Progress was asked for with `--with`). The installer did not read the
   Spec Kit version before (it only copies `tested_spec_kit` into the lock), so `speckit_version()` runs
   `specify --version` (prints `specify <version>` on 1.0.11 and 1.1.4.dev0; checked in both sources) and returns
   None when it cannot tell; then the check is skipped and Spec Kit still checks on add. The comparison is Spec
   Kit's own (`SpecifierSet.contains(..., prereleases=True)`).
   Where the requirement comes from: with `--packages`, the staged package's `extension.yml`
   `requires.speckit_version`. A release install has no package on disk in preview, so it reads
   `dependencies.json` `optional_speckit.<name>`. That key does not exist yet; see Requests. Until it lands, the
   release path (the live run's case) is covered only by fix 2.
2. `command()` now ends `INSTALL_COMMAND_FAILED: <command>: <cause>`. The cause is the last paragraph of stderr,
   else stdout, with Rich's 80-column wrapping joined back, at most 500 characters. If that paragraph is the
   installer's JSON result, its `error` is used. Without output it says `no output, exit code N`. Upgrade wraps it,
   so the live-run case now reads `WORKFLOW_UPGRADE_ROLLED_BACK: INSTALL_COMMAND_FAILED: <python> install.py ...
   --with progress: INSTALL_ROLLED_BACK: INSTALL_COMMAND_FAILED: specify extension add progress ...: Compatibility
   Error: Extension requires spec-kit >=1.1.1.dev0,<2.0.0, but 1.0.11 is installed. Upgrade spec-kit with: ...;
   backup: ...`. The full output stays in the log and backup `result.json` as before.

`upgrade.py` needed no change: it already wraps the installer's error text.

Files: `extensions/workflow/scripts/install.py` (`command`, new `failure_message`, `speckit_version`,
`check_speckit_requirement`, the check in `install()`), `extensions/workflow/tests/test_install.py` (4 tests),
`extensions/workflow/tests/test_upgrade.py` (1 test).

Tests (all 5 failed on the committed installer at HEAD 2d4263c; checked by swapping the file in, then restoring):
- `test_preview_refuses_an_optional_package_that_needs_a_newer_spec_kit`: exact message in preview and on apply;
  no command run, no lock written; no check without Progress; a matching (1.1.4.dev0) or unknown Spec Kit goes ahead.
- `test_preview_reads_a_staged_optional_package_requirement`: the `--packages` path reads the staged manifest.
- `test_spec_kit_version_comes_from_specify_version`: `specify 1.0.11`, `specify 1.1.4.dev0`, a failing command,
  a missing `specify`.
- `test_a_failed_command_reports_its_own_error`: the live run's real stdout (wrapped), an installer JSON error, a
  stderr traceback, no output.
- `test_upgrade.test_a_failed_installer_run_names_its_cause_at_the_top`: `WORKFLOW_UPGRADE_ROLLED_BACK` carries
  the Compatibility Error.

## Test results (all run 2026-10-21, `uv run --no-project --python 3.11 --with pyyaml --with packaging --with jsonschema`)

- `discover -s extensions/workflow/tests -p "test_install*.py"`: 60 tests, 3 errors, the known machine-only
  dangling link/junction rollback tests (`test_dangling_delegate_skill_junction_rolls_back_as_a_junction`,
  `test_dangling_delegate_skill_link_rolls_back_as_a_folder_link`,
  `test_dangling_junction_target_with_shell_metacharacters_is_restored_exactly`). Nothing else failed.
- `test_upgrade.py`: 12 OK. `test_hosts.py`: 31 OK. `test_host_files.py`: 13 OK.
- Also `test_progress_reporting.py` (S-WF's, calls `wire_progress`): 43 OK.

After D1 (same command):
- `test_install*.py`: 64 tests, 3 errors, the same three machine-only link/junction tests. Nothing else failed.
- `test_upgrade.py`: 13 OK. `test_hosts.py`: 31 OK. `test_host_files.py`: 13 OK.
- `test_progress_integration.py` (S-WF's, previews `--with progress`): 7 OK.
- `speckit_version()` against this machine's Spec Kit: `1.1.4.dev0`.

## Changelog lines

For `extensions/workflow/CHANGELOG.md` under `## Unreleased`:

- `install.py --with progress` wires Progress natively (`hook_wiring: native`) on a project with no Progress wiring
  yet. An explicit `progress.hook_wiring` still wins, and a project that already has Progress keeps the wiring
  `install-lock.json` records (Spec Kit's when it records none), with the slow-dispatcher hint.
- The installer's branch-rule check (before it removes a disabled gate job) runs `gh` through the shared
  `sanduq_gh` transport; its error codes are unchanged, and a missing `gh` now reports
  `CI_BRANCH_RULE_INSPECTION_FAILED: gh CLI not installed`.

- Before it changes anything, `install.py` refuses an optional package (Progress) whose `requires.speckit_version`
  excludes the installed Spec Kit: `OPTIONAL_PACKAGE_SPECKIT_INCOMPATIBLE` names both versions and the fix. Before,
  Spec Kit refused it during the apply and the installer rolled back.
- A failed Spec Kit or installer command reports its own error after the command line in `INSTALL_COMMAND_FAILED`
  (and so in `WORKFLOW_UPGRADE_ROLLED_BACK`), for example Spec Kit's `Compatibility Error: ...`. Before, the cause
  was only in the backup's `result.json`.

### Migration

- Existing projects: nothing changes. New Progress installs get native wiring; to keep Spec Kit's dispatcher, set
  `progress.hook_wiring: speckit` in `.specify/workflow.yml` before `install.py --apply --with progress`.

## Requests

- D1, dependencies.json owner (orchestrator or S-WF; `tested_spec_kit` untouched): add
  `"optional_speckit": {"progress": ">=1.1.1.dev0,<2.0.0"}` to `extensions/workflow/dependencies.json`, and a test
  next to `test_progress_integration.test_dependencies_offer_progress_at_the_version_in_its_manifest` that keeps it
  equal to `extensions/progress/extension.yml` `requires.speckit_version`. Without the key, the release-path
  preview check does nothing; the `--packages` path and the error message fix work now.

- Docs owner: these still say Spec Kit wiring is the default; add "new installs: native" where they state it:
  `docs/workflow/delivery-policy.md:162`, `docs/start/upgrades.md:101`, `docs/extensions/progress.md:66`,
  `extensions/progress/README.md:125-129`, root `README.md:155`.
