# Round 5 notes: S-CI

## SHARD (Amendment 15)

- New `.github/scripts/shard_times.py` (stdlib).
  - `shard_times.py run NAME...` behaves like `python -m unittest -q NAME...`: it uses `unittest.main` with a
    loader that runs each name as its own top-level suite, so tests, output and exit codes are unittest's own
    (checked against `python -m unittest` for pass, fail and a missing module). After the tests it prints one
    `shard-unit-seconds <name> <seconds>` line per name: a module for workflow, `module.Class` for memory, the
    same keys as `shard_weights.json`. Class fixtures are counted with their unit. No test folder uses module
    fixtures, so ending each unit as a top-level run changes nothing else.
  - `shard_times.py rebuild --source TEXT LOG...` reads those lines from downloaded logs
    (`gh run view <id> --log > run.log`, or per-job logs), averages a unit seen more than once, keeps only units
    that `ci_matrix.shard_units()` still lists, replaces each suite's table it measured, and keeps a suite's
    table when no unit of it was measured. Exits 2 without writing when the logs have no timing lines.
- `.github/workflows/ci.yml` "Run the suite": the module-list branch (shards and module lists) calls
  `python .github/scripts/shard_times.py run "${names[@]}"` instead of `python -m unittest -q`; the discover
  branch is unchanged.
- `shard_weights.json` unchanged, as asked. To rebuild after the first run with the lines:
  `gh run view <run-id> --log > run.log` then
  `python .github/scripts/shard_times.py rebuild --source "Seconds per unit on the Windows runners, from CI run <id>" run.log`.
  Only Windows shard lines should go in (Linux partial runs also print lines for their module lists; give
  `rebuild` only the Windows shard job logs, or a run where no partial Linux list ran).
- Tests (`extensions/scripts/tests/test_ci_matrix.py`, class `Round5ShardTimes`): run vs `python -m unittest`
  (exit code, `Ran N tests`, class setUp/tearDown counts, one line per name), log parsing with GitHub prefixes,
  CRLF and noise, averaging, rebuild per suite, CLI write and refusal, the ci.yml step. Regression check: with the
  `_previousTestClass` reset removed, the fixture test fails (`A-down` printed twice).

## X22 / SC8: injected helpers in `ci_matrix.py`

- `INJECTED` gains `extensions/scripts/shared/sanduq_gh.py: [scope, workflow, project, pr]` (S-SH request; it
  is already injected by `package.py`) and `extensions/scope/scripts/sanduq_scope_github.py: [scope, workflow]`
  (S-SC's decision: the file moves to Scope and is injected into the Workflow archive). The second entry selects
  the same suites as before; it is there so `test_injected_table_covers_every_built_archive` passes once S-SH
  injects the file.
- Test: `test_sanduq_gh_runs_every_suite_that_ships_it` (selection and install smoke). The archive-coverage test
  passes with `sanduq_gh.py` injected.

## X23 lint step

- `ci.yml` lint job: new step "Packages changed without a version bump" running
  `python3 extensions/scripts/release.py check-bumps`, right after "Check documentation links and command
  coverage". `check_bumps` calls no git, so the shallow checkout is enough; lint already installs pyyaml and
  packaging. Locally it exits 0 with the bootstrap notices.
- `ci_matrix.py` unchanged for this: `release.py` still runs workflow `test_release` on both OSes, `package.py`
  still runs everything.
- Tests (class `Round5Lint`): the lint job has the step after the documentation step; release.py and package.py
  keep their selection.

## PM5 project-init job

- `ci.yml` job `project-init`, as S-PM's notes asked: matrix `os: [ubuntu-latest, windows-latest]` instead of
  `shell: [pwsh, bash]`; `runs-on` uses the regression jobs' pattern (Linux leg on `homek8-general`, fork PRs on
  `ubuntu-latest`); the step is `python extensions/scripts/smoke_project_init.py` (its default `--shell python`);
  artifact `project-init-${{ matrix.os }}`. Checkout, setup-python (pip, which the Windows fake `gh.exe` needs) and
  the pip install are unchanged, actions still pinned by SHA.
- Nothing in `ci_matrix.py` or its tests named the per-shell matrix. `test_ci_policy.py:421` only has a comment
  naming `project-init.sh`; S-PM already filed that with S-WF (optional), so no request from S-CI.
- Test (class `Round5ProjectInit`): the job's OS matrix, runner pattern, setup-python, the smoke step without
  `--shell`, and the artifact name.
- Not run here: `smoke_project_init.py` itself (S-PM's); it first runs in CI on both OSes.

## Pending

- None.

## Test results

- `python -m unittest discover -s extensions/scripts/tests -p test_ci_matrix.py -q`: 54 tests OK (after X23), 55 OK (after PM5).
- `python -m unittest discover -s extensions/scripts/tests -q`: first pass 185 tests, 10 errors, all in
  `test_release_check_bumps` (S-SH's X23 work then in progress); after S-SH landed, 187 tests OK.
- actionlint 1.7.12 (`go run`): no findings after each change (SHARD, X23, PM5). ShellCheck is not installed here, so its pass over `run:` scripts
  was not run locally.
