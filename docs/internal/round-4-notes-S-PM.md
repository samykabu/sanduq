# Round 4 notes: S-PM (PR, Project, Memory)

Worktree `D:\Projects\Personal\sanduq-round4`. Python: the uv command from the contract. No git command that
changes the tree or index was run. Every fix has a regression test; each was run against the HEAD version of
the changed code (a temporary copy) and failed there.

## F5

- **PM10** `pr_publish.py`: `gh pr view` asks for `state`; a PR that is not OPEN exits 3 ("PR #n is merged;
  nothing published") before any write. A new PR's branch is pushed when its upstream is behind
  (`git rev-list --count @{u}..HEAD`), not only when it has none. Tests: merged and closed never edited; behind
  pushes, level does not.
- **PM11** `pr_changelog.py`: the base comes from `pr_publish.default_branch` (origin/HEAD, else
  `gh repo view`), tried as `origin/<name>` then `<name>`. When no `git log` resolves, the commit line is left
  out; "(no commits on ...)" is written only after a successful empty log. Tests: `master` repository without
  origin/HEAD lists commits; an unresolvable base writes no "no commits".
- **PM12** both init twins: owner type from `gh api users/<owner> --jq .type` (`Organization` -> `org`); a
  failed lookup stops with "pass --owner-type". A rerun keeps `parentIssue`, `subIssues`, `stateFile` from the
  existing `config.json`; an existing invalid `config.json` stops instead of being replaced. Bash also makes one
  `gh project view` call instead of two. Tests run both shells (Git Bash with jq, pwsh) through fake `gh`.
- **PM13** README `done` row (explicit only, never automatic), sync table `done` row, `config.default.json`
  `$comment` (no prompt) and the unread `subIssues.granularity` removed.
- **P1** `project_sync.py`: invalid JSON, a non-object state or a non-object feature entry stops with
  "restore it from git or fix it by hand" and leaves the file untouched. Before creating sub-issues the sync
  lists issues with the sub-issue labels (label filter, no search index, so no indexing delay) and adopts
  titles that match the template for that task (any description); adopted ones are linked again
  (allow-fail). The state is saved after each new sub-issue. A failed lookup creates nothing. Tests: malformed
  x3, adoption, interrupted run resumes with one create, failed lookup.

## Do items

- **D1** `pr.generate`: "Generates the feature CHANGELOG and details doc, then creates or updates the pull
  request body; never merges. Use when asked to 'write the PR description'." (155 chars) in frontmatter, the
  command entry and the hook. Project sync: "...; standalone, it also creates and closes task sub-issues..."
  (159 chars), plus the extension description, the `after_tasks` and `after_implement` hook descriptions,
  the sync table and README. Both pass `benchmark_instructions.describe`. Tests assert frontmatter == manifest.
- **D4** Project side: `import sanduq_remote` with the dev-tree fallback; `github_repo` kept as a public
  name (`sanduq_remote.github_slug`); origin through `sanduq_remote.origin_url`; the hand copy and the
  `workflow.py` exec_module are gone. S-SH's `test_sanduq_remote.py` (8 tests) passes. Measured in process,
  managed `analysis` sync with an installed Workflow, FakeGh, 7 fresh interpreters each:
  **before median 292 ms (first series 319 ms), after 152 ms** (this includes PM16a, whose `gh` call is free in
  the fake). Script: scratchpad `spm/bench_sync.py`.
- **D3 Memory side** (`archive.py`, `install.py`, `session.md`, `prepare.md`, SESSION block, README):
  - Approval hash: `memory_hooks()` reads `hooks:` > `  <event>:` > `  - extension: memory` blocks; each
    hashed as `event:\n<block>` (sorted), so the event heading is bound; command, condition, priority,
    optional, description and the rest stay bound. The `enabled:` line is dropped only for
    `speckit.memory.session` and `speckit.memory.prepare`. CRLF is folded.
  - Unparseable refuses: a Memory block without a `command:` line, or any `extension: memory` mention the
    reader did not place (another key first, indented sequences, flow style) raises ArchiveError naming
    `speckit.memory.init`. Spec Kit 8147943's `register_hooks` writes `extension` first with
    `sort_keys=False`, indentless lists, so its output parses.
  - Upgrade, defined and tested: any Memory release changes the hash (it covers the extension's files), so
    `pending` reports `enabled: false` with "needs ... renewal"; the owner runs `enable` once. Queue entries from
    before keep their `enabled_at` (never re-stamped) and `pending` reports them blocked with the fix: "archive
    it manually with speckit.memory.run --spec <dir>, or re-queue it from its implementation branch" (the text
    keeps "predates current enablement", which `test_memory_handoff` reads).
  - `install.py`: an existing own entry with `enabled: false` is kept byte for byte (and in place); enabled
    entries are rewritten as before. Code comment names the sequence for a legitimate change to a disabled
    entry: Workflow `reconcile --restore`, `speckit.memory.init`, `reconcile --apply`.
  - `session.md` honours `--run <id>` (that transaction only) and `--spec <dir>` (that feature only).
  - `prepare.md` managed branch: steps 2-4 (choose checks, read-only preflight kept, so no early failure is
    lost), then `workflow.py memory-handoff --transition execute --feature specs/<f> --check <name>` instead of
    `queue`.
  - SESSION block (still four lines): in a Workflow project the claim runs the session check.
- **PM24** `pending` shape when automatic mode is on (exact):

  ```json
  {"enabled": true, "ready": [], "needs_verification": [], "blocked": [],
   "active_run": null, "active_phase": null, "writer": null, "guard_blockers": [],
   "policy_hash": "<64 hex, equal to archive.py policy's policy_hash>",
   "policy": {"target_branch": "<branch>", "default_checks": ["<name>", "..."]}}
  ```

  `policy` is a subset (only what `memory_handoff.py` reads), to keep the session-start output small. When
  disabled, `pending` keeps today's shape without the two keys, so the handoff's `policy` fallback stays.
  `memory_handoff.py:91-92` already accepts this shape.
- **PM16** managed syncs skip `gh issue view` (Scope wrote `issueNodeId`; it stays, so the binding fingerprint
  is stable): open/in-progress 4 -> 3 calls, analysis/in-review 3 -> 2. Labels are created once per label per
  run: standalone `ready` with 10 tasks 42 -> 39 calls (9 label creates fewer, 1 identity lookup more for P1).
- **PM23** the new PR's URL is the last line of `gh pr create` (one `gh pr view` fewer).
- **PM2a** `extensions/pr/scripts/pr_feedback.py gather [<id>]`: one GraphQL query paged over review threads
  (metadata, reviews, threads with `diffHunk`) plus one paged REST call for general comments; filters
  resolved, outdated, author-only and chatter (incl. `:+1:` shortcodes) with counts. Read-only (the test fake
  refuses any mutation, `--method` or reply). `review-feedback.md` step 1 uses it: 5,518 -> 5,201 bytes, 7 ->
  3-4 `gh` calls, every thread read. Trust rules, approval gate, reply template and red flags unchanged.
- **PM19** `extensions/workflow/tests/test_project_sync_summary.py` moved to
  `extensions/project/tests/test_project_sync.py` (old file deleted). New tests: P1 x4, PM16 x2, PM12a, PM12b,
  D4 route (shared helper, workflow.py never loaded), D1 descriptions. The package-import test is S-SH's
  `test_project_normalisation_route_never_loads_workflow_py`.
- **PM20** confirmed on `test_orchestration.py` first: **184.3 s -> 30.3 s** (32 tests). Then applied to
  `test_archive_v2.py` (102.7 s -> 44.4 s); not to `test_archive.py` (no saving, see "Results"). `tests/repo_template.py` builds once in
  `setUpClass` and copies into the same fixed path before each test (state stores absolute roots).
- **PM21** text side: `pr_publish.py` imports `FENCE, PR_LINT_SCHEMA, pr_lint` from `sanduq_pr_lint` (dev-tree
  fallback); its copy and the `execution_tools.py` exec_module are gone. Test: an installed `execution_tools.py`
  that exits on import is never loaded; `pr_publish.pr_lint is sanduq_pr_lint.pr_lint`.
- **AU21** `pr.generate` QA preflight runs `assure_state.py status --kind document --gate --summary`;
  `skipped gate=off` skips. No config reading in the text. Test asserts it.
- Orchestrator requests: `sanduq_remote` and `sanduq_pr_lint` used (1, 2); Memory README `--priority 1` (3);
  Project CHANGELOG `## 2.1.0 (unreleased)` -> `## [2.1.0]` (4; `check_docs.py` OK); PR step 0 shrunk to one
  sentence after AU17.

## Results

All with the uv python, 2026-10-21, while other streams ran on the same machine (times are noisy):

- PR: 29 tests OK in 0.5 s (19 before).
- Project (`extensions/project/tests`): 24 tests OK in 42 s (15 before, 20 s; the four init tests run both
  shells and take most of it).
- Memory: 197 tests OK in 846 s (an earlier full run of the same code took 619 s; round 3 717 s; the review's run
  1,441 s). Per class, same machine, run alone: `test_orchestration` 184.3 s -> 30.3 s, `test_archive_v2`
  102.7 s -> 44.4 s. `test_archive` gained nothing (its setUp is two commits; copying `.git` costs the same:
  331 s / 57 tests before, about 358 s / 60 after), so it keeps its own setUp. The template also serves the two
  classes that borrow the v2 fixture (`test_retro_tooling.MemoryV2ToolingTests`,
  `test_migration_discovery.DeltaMigrationDiscoveryTests`).
- Also run: `extensions/workflow/tests/test_memory_handoff.py` 23 OK; `extensions/scripts/tests/test_sanduq_remote.py`
  8 OK; `check_docs.py` OK.
- No machine-only failures seen in these three suites.

## Requests

- **S-CI**: `.github/scripts/ci_matrix.py:33,94` still name `extensions/workflow/tests` /
  `test_project_sync_summary`; the Project suite is now discovered in `extensions/project/tests`. Drop the
  `SUITE_TESTS['project']`/`PROJECT_LEGACY` entry and the "Workflow already runs Project" suppression, and add
  `project -> workflow` to `DEPENDENTS` (Workflow's `sync_project` runs the script). The init tests need bash
  with jq and pwsh on the runner (they skip otherwise).
- **S-SH**: `extensions/scripts/tests/test_ci_matrix.py:96` asserts the old path; update with S-CI.
- **S-DOC**: `docs/extensions/project.md:4` "one sub-issue per task": add "in standalone use"; mention that
  `done` is explicit only. `docs/extensions/memory.md`: the approval now leaves out the `enabled:` flag of the
  two Workflow-owned hooks; upgrade needs one `enable`; old queue entries are reported, not re-stamped.
- **S-WF**: (a) PM24 shape above; your consumer already matches. (b) `prepare.md` calls
  `workflow.py memory-handoff --transition execute --feature specs/<f> --check <name>`; keep that CLI.
  (c) Project's `after_tasks` and `after_implement` hook descriptions changed (D1). In a managed project a
  Project update re-registers them with the new text and `enabled: true`; W10 must accept that like any fresh
  re-registration. (d) Spec Kit's `specify extension update memory` purges Memory's entries per event and
  re-adds only the manifest's (priority 10), so the install-only `before_specify: impact` entry disappears and
  the hash changes (pre-existing; one renewal). The lifecycle test should expect it.
- **S-INST**: Memory approval needs one renewal with this release (any release does); upgrade docs should say so.
