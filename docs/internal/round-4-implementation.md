# Round 4: implementation contract

Approved 2026-10-20 (report db `plan/current`): every Fix-first and Do group in `round-4-final-plan.md`; every Defer
item stays deferred. Names unchanged (D1-D5 in `round-4-plan.md`). Source of each item: the review files
`round-4-review-*.md` (design and evidence) as amended by `round-4-codex-review.md`. Where they disagree, the final
plan wins.

## Rules for every stream

- Work only in `D:\Projects\Personal\sanduq-round4` (upstream stream: `D:\Projects\Personal\sanduq-skills-round4`).
- Edit only the files your stream owns (below). Need a change elsewhere? Write it under "Requests" in your notes file
  and continue; the orchestrator routes it.
- No git command that changes the tree, the index or branches (no add, commit, stash, checkout, reset, clean,
  restore). The orchestrator reviews and commits.
- Every defect fix gets a regression test that fails before the fix. Keep existing tests passing; never weaken a test
  to make it pass.
- Python: `uv run --no-project --python 3.11 --with pyyaml --with packaging --with jsonschema python ...`. Known
  machine-only failures: about 19 workflow tests (Microsoft Store python hashing; they pass under the uv python), 1
  Scope test (Illustrate PNG export, Playwright absent). Report any other failure.
- No version bumps and no catalog edits. Add changelog lines under a `## Unreleased` heading at the top of your
  extension's `CHANGELOG.md` (create the heading if missing), with a `### Migration` block where a consumer sees a
  change. The orchestrator bumps versions at release.
- Keep descriptions within the rules in `extensions/scripts/benchmark_instructions.py`.
- Notes: `docs/internal/round-4-notes-<stream>.md` (yours only): what you did per item id, tests run with results,
  anything not done and why, requests to other streams.
- Plain, short sentences in docs and changelogs. Comment only the why.

## Shared interface: `extensions/scripts/shared/sanduq_remote.py` (owner S-SH, written first)

Stdlib only. Moved from `workflow.py:360-441` without behaviour change, plus:

- `normalize_remote_url(url) -> str` (as today).
- `github_slug(url) -> str | None`: `owner/repo` when the normalised URL is `github.com[:port]/owner/repo`, else None.
  Case of owner and repo preserved.
- `same_github_repository(a, b) -> bool`: case-insensitive, None-safe (as `workflow.py:334`).
- `origin_url(root, timeout=10) -> str | None`: `git config --get remote.origin.url`; None when unset. This is the one
  origin-reading policy for Workflow, Project and Scope.

`package.py` injects it into workflow, project and scope (as `deps.py`). Consumers import it with the same dev-tree
fallback `deps.py` uses. Workflow keeps its memoised `origin_url` wrapper and re-exports the moved names, so
`workflow.normalize_remote_url` and existing tests keep working.

## Streams and ownership

| Stream | Owns | Items |
| --- | --- | --- |
| **S-WF** Workflow runtime | `extensions/workflow/scripts/` except `install.py`, `upgrade.py`, `hosts.py`; `extensions/workflow/{references,commands,skills,schemas}`; workflow tests except `test_install*.py`, `test_upgrade.py`, `test_hosts.py`, `test_host_files.py`, `test_project_sync_summary.py` (moves to S-PM, see PM19); `presets/workflow/` | F1 (W10, W11, X21 in `task_issues.py`, `ci_evidence.py`); D4 Workflow side (import and re-export); D1 (`finalize`, `status`); D3 Workflow side (W13, W14, reconcile step 6, doctor, `memory_handoff.py`, PM24 consumer side); D5 (W16 with the 35 bridge tests kept, IP23, W21); W6 (measure first call, hit, invalidation); W20; W22 and X25 (`test_gate_explain`, `test_ci_gate`, `test_receipt_contract`); W23; IP20 (doctor: doubled Progress wiring); `presets/workflow` text for SC12 (`speckit.superspec.brainstorm.md:30`) and SC18 (`speckit.specify.md`) as agreed with S-SC |
| **S-INST** installer | `install.py`, `upgrade.py`, `hosts.py`, `test_install*.py`, `test_upgrade.py`, `test_hosts.py`, `test_host_files.py` | X19 (keep the three newest `before.zip`, doctor-visible count and bytes; a failed apply prunes nothing); X21 install timeout (`install.py:307`); D3 installer side: upgrade refuses while a Memory archive run is active; W10 restore path at `install.py:829` and `hosts.py:562` uses S-WF's reconcile rule; AU8 consumer side: the upgrade re-renders Assure's `documentation-gates.yml` |
| **S-SH** shared and packaging | `extensions/scripts/` (except benchmarks owned by nobody: leave them), `extensions/scripts/shared/` except `sanduq_freshness.py` and `deps.py`, `extensions/scripts/tests/`, `.gitattributes` | `sanduq_remote.py` (already written by the orchestrator; review it) and its injection plus tests (archive bytes equal the source, inventory membership, installed-layout import without Workflow or PyYAML, all remote and look-alike cases); X17 promote returns what it wrote, plus a test that the release job's `git add` covers it; X18 three `check_docs.py` rules; X20 changelogs out of packages and `text eol=lf` for `LICENSE` and `*.txt`; PM21 one `pr_lint` source (injection side, with S-PM) |
| **S-SC** Scope and the two scope presets | `extensions/scope/`, `presets/scope-gate/`, `presets/scope-brainstorm/` | F2 Scope side (use `sanduq_remote`, casefold comparisons at `scope.py:553,564,674`, missing origin as `ScopeError`, look-alike refused); F3 (SC10, SC12, SC18, SC20); SC13, SC14, SC15, SC19; Scope README and docs version drift |
| **S-AU** Assure and User Manual | `extensions/assure/`, `extensions/user-manual/`, `extensions/scripts/shared/sanduq_freshness.py`, `extensions/scripts/shared/deps.py` | F4 (AU8, AU9, AU10 sanduq copy, AU11, AU12, AU13a); AU13b, AU14, AU16 (input and output hash of `tasks.md`, per Codex), AU17, AU18, AU19, AU20 (sanduq side) |
| **S-PM** PR, Project, Memory | `extensions/pr/`, `extensions/project/`, `extensions/memory/`; the moved Project tests | F5 (PM10, PM11, PM12 in both init scripts, PM13, P1 malformed state and task identity recovery); D1 (`pr.generate`, Project); D4 Project side (use `sanduq_remote`, no `workflow.py` load); D3 Memory side (approval hash binds event, command, condition, priority and leaves out `enabled:` only for the two owned hooks; unparseable blocks refuse; `install.py` keeps `enabled: false`; `session.md` honours `--run`/`--spec`; `prepare.md` managed branch returns selected checks; PM24 `pending` facts); PM16, PM23, PM2a, PM19 (move `test_project_sync_summary.py` into `extensions/project/tests/` plus five tests; S-CI updates `SUITE_TESTS`), PM20 (confirm on one class first), PM21 text side, AU21 |
| **S-IL** Illustrate and Progress | `extensions/illustrate/` except the vendored tree, `extensions/progress/` | F6 (IP11 fail closed with an actionable message, no partial YAML fallback; IP12 command side); IP16; IP22 deprecation notice only (changelog and docs; no removal) |
| **S-CI** CI | `.github/` | IP13, IP14 / X13, IP15, X15 (measured shard weights, memory sharded), X16 (tooling path filter, `actionlint` in lint), X24 (pin actions by SHA, at least the two write workflows), PM19 `ci_matrix.py` (drop the "Workflow already runs Project" suppression), AU23 |
| **S-DOC** docs | `README.md`, `extensions/README.md`, `docs/` except `docs/internal/` | F7 X12 (reverse the priority sentence in `docs/start/install-speckit.md:39-40`, the community `scope` and `memory` note in the README, `docs/extensions/scope.md`, `docs/extensions/memory.md`, `docs/start/upgrades.md`); docs drift R6 found; later the round's migration table in `docs/start/upgrades.md` (after the streams report) |
| **U-UP** upstream sanduq-skills | `D:\Projects\Personal\sanduq-skills-round4` (branch `feat/round-4`) | dev-tools: AU10 portable `init_manual.py`, AU15 quiet builds, AU20 template removal; illustration-tools: IP12 references, IP17, IP18a. Version bumps there follow that repo's conventions; no tags |

## D3 order (one integration, two owners)

S-PM steps 2-3 and the Memory command texts; S-WF steps 1, 4 and 6; S-INST step 5. Code them in parallel against
this contract. S-WF writes the scripted lifecycle test (pinned Spec Kit 8147943 if available locally, else the
current fixtures; say which): Memory installed before and after Workflow, Memory re-init, `specify extension update
memory` re-registration, `reconcile --restore`, automatic mode off, an interrupted archive. Release is gated on that
test plus one live managed run, which the orchestrator runs.

## Order and dependencies

1. S-SH writes `sanduq_remote.py` and its injection first and says so in its notes; S-WF, S-SC and S-PM import it.
2. F-items before Do-items inside each stream.
3. S-DOC writes the migration table last, from the streams' changelog Migration blocks.
4. After review: upstream release and vendoring, AFTER measurement with the same harness, version bumps, release.
