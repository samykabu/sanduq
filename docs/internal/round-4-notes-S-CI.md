# Round 4 notes: S-CI (CI)

Files changed: `.github/scripts/ci_matrix.py`, `.github/scripts/shard_weights.json` (new),
`.github/actionlint.yaml` (new), `.github/workflows/{ci,release-extensions,vendor-update,prune-artifacts}.yml`.
Tests: `extensions/scripts/tests/test_ci_matrix.py` (see "Outside my files").

## Items

- **IP13.** `MODULE_RULES` maps `extensions/illustrate/hooks/` to the Workflow module `test_install_hooks` (a module
  list, not the whole suite) on both OSs and every event, and `INSTALL_PREFIXES` adds the folder, so the install
  smoke runs too. A whole Workflow selection wins over a module list.
- **IP14 / X13.** "Cache the Playwright browser" and "Install Playwright" run only for Illustrate on Linux when
  `illustrate_vendored` is true, the same condition as the steps that use the browser.
- **IP15.** The vendored builders, verifiers and render lint run on Linux only. `illustrate_vendored` is true on a
  vendor path change, on `workflow_dispatch`, when the changed files are unknown, and on the scheduled run on
  Sunday (UTC; `VENDORED_WEEKDAY`). Other nightly runs skip them; the Illustrate suite itself still runs nightly.
- **X15.** Windows workflow (4 jobs, by module) and Windows memory (2 jobs, by test class, found with `ast`) are
  split heaviest-first onto the lightest shard by `.github/scripts/shard_weights.json`. A unit missing from the
  table weighs its bytes times the table's seconds per byte, so it still gets a shard. See "Shard weights".
- **X16.** Lint-only: `release-extensions.yml`, `vendor-update.yml`, `prune-artifacts.yml`, `.github/actionlint.yaml`,
  `extensions/scripts/tests/**`, `test_check_docs.py`, `validate_skills.py`, `vendor.py`. `release.py` runs
  Workflow's `test_release`, `check_docs.py` runs Assure's `test_descriptions`, `benchmark_instructions.py` runs
  Scope's `test_instructions` (module lists, both OSs). Lint runs `actionlint` 1.7.12 (download checked by sha256,
  after ShellCheck so it also checks every `run:` script). `actionlint.yaml` names the `homek8-general` label.
  Fixed the one finding: the suite step now word-splits `$MODULES` with `read -ra`.
- **X24.** All 25 `uses:` refs in the four workflows are pinned by commit with the version in a comment.
  `actions/checkout` 08eba0b (v4.3.0) and `actions/setup-python` a26af69 (v5.6.0) are the SHAs from 29a4224's
  templates. The rest were read with `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` (all lightweight tags on
  commits): `actions/cache` 0057852 (v4.3.0), `actions/upload-artifact` ea165f8 (v4.6.2), `actions/github-script`
  f28e40c (v7.1.0). Note: the moving `v4` tag of checkout now points at v4.4.0 (11d5960); I kept v4.3.0 so the
  repository and the consumer templates use one version.
- **PM19.** `suite_tests('project')` uses `extensions/project/tests` (discover) once it holds a `test*.py`, else the
  old `extensions/workflow/tests/test_project_sync_summary`. The "Workflow already runs Project" suppression is
  gone, and `project -> workflow` is a dependent (Workflow's `sync_project` runs `project_sync.py`). `ci.yml` no
  longer discovers the project folder as a special case. Works before and after S-PM's move.
- **AU23.** `INJECTED` lists every file `package.py` injects with every suite that ships or tests it
  (`sanduq_remote.py` -> workflow, project, scope; `sanduq_pr_lint.py` -> pr, workflow; `deps.py` -> pr, assure,
  user-manual; `check_inputs.py`, `bounded_json.py` -> memory, workflow; `evidence_snapshot.py` -> workflow;
  `sanduq_freshness.py` -> assure, user-manual, workflow; `workflow/scripts/sanduq_{hash,ci}.py` -> workflow,
  assure, user-manual), plus their dependents. A shared file not in the table still runs everything. A test builds
  every archive with `package.py` and fails when a package ships an injected file the table does not name.

## Shard weights

Source (also in the table's `source` key): Windows CI runs 39411311648 (PR #100, 7fe964f) and 39359728801
(nightly, 07dc50f), both 2026-10-20. The logs (`unittest -q`) print one "Ran N tests in X s" per job and no
per-module times, so each job's total is split over its units by their bytes at that run's commit, then averaged
over the two runs. The two runs had different workflow shard contents, which is the only per-module signal.
Built by a scratch script (read-only `gh run view --json jobs`, job logs, `git cat-file`).

- Workflow: 1,290 s in the table; new shards 319 / 309 / 319 / 319 s (CI shards were 96-609 s in run
  39411311648). `test_memory_hook_lifecycle` (new this round) is not in the table and falls back to bytes.
- Memory: one CI job only, so the table is bytes-proportional (582 s); shards 290 / 293 s. The local numbers in
  R6's review say `test_archive` alone is about 66%, so the first sharded run will likely show shard 1 slower.
  Rebuild the table from the two memory shard times then.
- Not used: a local per-module timing run (stopped on the orchestrator's instruction; the machine was loaded).

Rebuild after a large test change, or from a run that prints per-module times.

## New job names (branch protection)

`main` has no branch protection and no rulesets today (`gh api .../branches/main/protection`: 404; rulesets: `[]`),
so nothing breaks. If required checks are added, Windows memory is now two jobs:

- `regression (windows-latest, memory, 1/2)`
- `regression (windows-latest, memory, 2/2)`

They replace `regression (windows-latest, memory)`. Workflow shard names are unchanged (`..., workflow, 1/4` to
`4/4`). A module-list run (for example after an Illustrate hook change) is named like the full job,
`regression (<os>, workflow)`.

## Outside my files

- `extensions/scripts/tests/test_ci_matrix.py` is in S-SH's folder but only tests `ci_matrix.py`. I updated it (the
  rules say every `ci_matrix.py` change needs tests): `ALL` now includes project, `vendor.py` is lint-only, the
  project tests accept either folder, the nightly vendored rule is weekly, the setup-python regex allows the pin
  comment, plus the classes `Round4Selection` and `Round4WorkflowFiles`. Please route to S-SH as a no-conflict edit.

## Owner actions

- Runner cluster (X14, unchanged): keep CPython 3.13 in the `homek8-general` tool cache.
- `actionlint` downloads the linux_amd64 build; the self-hosted runners are x64 (setup-python logs). An arm64
  runner would need the other archive.

## Tests

- `extensions/scripts/tests` (the lint job's "Repository tooling tests", uv python 3.11): 151 tests, OK.
  `test_ci_matrix.py` alone: 46 tests, OK (was 27).
- `actionlint` 1.7.12 with ShellCheck 0.11.0 over the four workflows: no findings.
- New tests that fail on the old `ci_matrix.py`: the Illustrate hook case (IP13), the injected-file cases (AU23),
  project with workflow (PM19), the weekly vendored rule (IP15), lint-only tooling (X16), class shards (X15),
  the pin and actionlint checks (X24, X16), the Playwright gating (IP14).

## Follow-up after 0026d8c (weights refresh)

`shard_weights.json` now matches the round-4 test tree. Dropped `test_progress_shim` and `test_project_sync_summary`.
Scaled by local after/before ratios from the S-WF and S-PM notes: `test_ci_gate`, `test_ci_revalidation`,
`test_front_half_runtime`, `test_gate_explain`, `test_receipt_contract`, memory `test_orchestration` and
`test_archive_v2`. `test_progress_reporting` = the old shim weight x 10/92.7 s. `test_memory_hook_lifecycle` uses the
byte fallback. No stale entries. `test_ci_matrix.py`: 46 tests, OK.
