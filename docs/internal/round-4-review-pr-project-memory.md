# Round 4 review: PR, Project and Memory (stream R4, read-only)

Measured on `D:\Projects\Personal\sanduq-round4` (branch `feat/round-4`, fb17f52) on 2026-10-20. Versions:
PR 4.4.0, Project 2.4.0, Memory 2.4.0. Python: `uv run --no-project --python 3.11 --with pyyaml --with packaging`.
Scratch scripts and logs are in the session scratchpad (`r4pm/`). Nothing in the tree was changed except this file.
Round 3 ended at PM9; options here start at PM10. Round 3's deferred PM2, PM5 and PM9 are re-assessed in §4.

Test runs: PR 19 tests in 0.92 s. Project (`extensions/workflow/tests/test_project_sync_summary.py`) 15 tests in
16.3 s. Memory: 192 tests in 1,441 s, with 1 error: `os.replace` hit `PermissionError` [WinError 5] on `candidate.json` under
`.git/sanduq-memory/runs` (`git_state.py:31`, in `test_retro_tooling`). That looks like a Windows file-lock flake, and
other measurements ran in parallel, so the time is inflated (round 3: 717 s).

## 1. Summary

1. **D4 cost, measured.** Loading `workflow.py` through `exec_module` inside `github_repo` costs **286 to 420 ms
   per sync** (3 runs, against 0.5 to 0.8 ms for the local copy; `r4pm/time_repo.py`). A managed feature runs 7 syncs
   (6 points plus `done`), so about 2 to 3 s per feature. A managed sync makes 3 or 4 `gh` calls of about 0.7 to
   0.8 s each (`gh auth status` timed at 720 and 829 ms). The load is about 10% of a sync.
2. **D3 has two hidden breaks.** (a) Memory's approval hash covers its own hook entries in `.specify/extensions.yml`,
   including the `enabled:` line (`archive.py:119-122`; README:130 "Changes invalidate it"). When `reconcile --apply`
   disables `session` and `prepare`, automatic archiving silently stops until the owner runs `enable` again. (b)
   Memory's `install.py` rewrites its hook entries with `enabled: true` (reproduced, §2.3). After a Memory re-init,
   Workflow's next install or upgrade fails `HOOK_CHANGED_SINCE_RECONCILE` (`reconcile.py:42,46`, called first with
   `restore=True` at `install.py:829-830`). Both must be fixed in Memory before D3 ships.
3. **Defects.** `pr_changelog.py` falls back to `main` and writes "(no commits on `main..HEAD`)" on a `master`
   repository (reproduced). Both Project init scripts detect every owner as `user` and reset `parentIssue`,
   `subIssues` and `stateFile` to defaults on rerun. `pr_publish.py` edits a merged PR's body when the branch has no
   open PR (from gh's branch lookup; not reproduced live). The Project README promises a `done` move that no code makes.
4. **Cheap runtime wins.** In managed mode `project_sync.py` calls `gh issue view` on every sync for a node id that
   only sub-issues use (1 of 3 or 4 calls, `r4pm/count_calls.py`). Standalone `ready` with 10 tasks makes 42 `gh`
   calls; 9 are repeated `label create`.
5. **Memory tests.** The three heavy classes spend most of their time in `setUp` (1.8 s, 6.6 s and 7.0 s per test,
   106 tests). A per-class template restored into a fixed path is the PM9 shape that works (§4, PM20).
6. **Project tests exist** (339 lines), but in Workflow's folder. The structure report counted 0. CI already runs them
   as suite `project` through `SUITE_TESTS` (`.github/scripts/ci_matrix.py:31`). The minimum suite is a move plus five
   tests (PM19).

## 2. Design input for the decided items

### 2.1 D1: descriptions (Project and `pr.generate`)

Rules: `benchmark_instructions.describe` (third-person lead, at least 5 words, a when clause, a trigger in double
quotes or "asked to", under 1,024 characters). Every proposal below passes `describe` with no failures (checked).

**Project.** Managed mode forces `--no-sub-issues` (`project_sync.py:461-463`), and `sync_progress` returns early
(`:383-385`). The texts that claim sub-issues without the condition:

| Where | Today | Proposed |
| --- | --- | --- |
| `speckit.project.sync` frontmatter and `extension.yml:29` | "Moves the feature issue to a lifecycle phase on the GitHub Project and creates or closes task sub-issues. Use when asked to 'sync the board'." (141 chars) | "Moves the feature issue to a lifecycle phase on the GitHub Project; standalone, it also creates and closes task sub-issues. Use when asked to 'sync the board'." (159 chars) |
| `extension.yml:7` extension description | "...create one native sub-issue per task, and close sub-issues..." | "...and, in standalone use, one native sub-issue per task (under Sanduq Workflow, Workflow owns task issues)..." |
| `extension.yml` `after_tasks` hook description | "Create native task sub-issues and move..." | "Move the parent issue to the ready column; standalone, also create native task sub-issues" |
| `speckit.project.sync.md` table, `ready` and `in-progress` rows | sub-issue side effects, no condition | add "(standalone only)" to both rows; the `done` row also closes checked tasks' sub-issues (`:493`), so say so |
| `extensions/project/README.md:12,26` and `docs/extensions/project.md:4` | "one sub-issue per task" | the same condition, one clause each |

`docs/extensions/project.md:44` already says Workflow's adapter owns task sub-issues. Keep it.

**`pr.generate` vs `workflow.finalize`.** Both use the trigger "open the PR" (`pr.generate.md:2`, `finalize.md:2`).
The two meet only when Workflow is installed, and there `finalize` owns the PR (`COMMANDS['pr']`, `workflow.py:52`;
PR's hook is disabled, `reconcile.py:35`). So `finalize` keeps "open the PR" and `pr.generate` takes the narrower job
it actually does on its own: the documents and the body.

- `pr.generate` (frontmatter, `extension.yml:36` and the hook description `:47`): "Generates the feature CHANGELOG and
  details doc, then creates or updates the pull request body; never merges. Use when asked to 'write the PR
  description'." (155 chars, +20). Standalone users who say "open the PR" still reach it, because it is the only
  PR command they have.
- Run `check_docs.py --write` for `docs/reference/commands.md`, and remeasure the catalog column.

### 2.2 D4: one shared remote normaliser; no `workflow.py` load

Today: a hand copy (`project_sync.py:65-103`, 39 lines) and a load of the whole 4,137-line `workflow.py`
(`:106-119`). The load also inserts Workflow's scripts folder into `sys.path` for the rest of the process (`:113`) and
needs `yaml` and `packaging` (`workflow.py:37-39`). If they are missing, the `except Exception` falls back to the copy
without a word. Measured cost: 286 to 420 ms per sync (§1).

Shape (smallest single source; it follows the `deps.py` and `check_inputs.py` pattern):

1. New `extensions/scripts/shared/sanduq_remote.py`, stdlib only: `_strip_dotgit`, `_normalize_path_remote`,
   `normalize_remote_url` (the docstrings from `workflow.py:360-441`), and
   `github_repo(remote) -> 'owner/repo' | None` (the regex at `project_sync.py:118` and `workflow.py:329`).
2. `package.py:79-84`: inject it into `project` and `workflow`, next to `check_inputs.py`.
3. `project_sync.py`: `try: import sanduq_remote` / `except ModuleNotFoundError:` insert
   `parents[2]/'scripts'/'shared'` and import again. This is the dev-tree fallback `execution_tools.py:32-36` uses.
   Delete `:65-119`, `WORKFLOW` (`:32`) and `import importlib.util`.
4. `workflow.py`: `from sanduq_remote import normalize_remote_url, _normalize_path_remote, _strip_dotgit`. The names
   stay importable, so `test_checkpoint_identity.py` keeps working. `github_repository` calls
   `sanduq_remote.github_repo`. This file is R1's: one owner.
5. Optional (R2): `scope.py:525-528` still uses the old regex `github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$`. It fails on
   `ssh://git@github.com:443/acme/app` and on a trailing slash. Scope could call the same helper, but it is not
   injected there today. That is R2's decision.

Version skew: Project and Workflow archives may carry different copies after a partial upgrade. That is acceptable:
the repository test pins one source, and Workflow's `dependencies.json` pins the Project range.

Tests: `test_remote_parsing_matches_workflow_and_keeps_dots_and_ports` (`test_project_sync_summary.py:225-234`)
loses its second half (an installed Workflow's parser is used). Replace it with: `project_sync.github_repo is
sanduq_remote.github_repo`, the 9 remotes through the helper, and a package test. The package test builds
`project.zip`, extracts it into a temp folder without `extensions/scripts`, and imports `project_sync`. Without that
test, the dev-tree fallback hides a missing injection.

Saving: 286 to 420 ms per sync, about 2 to 3 s per managed feature. 39 duplicate lines. One `sys.path` side effect
and one silent fallback removed. Effort S, risk low. Consumer impact: none (one more file in the archive).

### 2.3 D3: Memory side of Workflow owning `session` and `prepare`

What happens today in a managed project: the `before_specify: speckit.memory.session` and `after_implement:
speckit.memory.prepare` hooks are mandatory (`extension.yml:44-53`, `install.py:19-22`). Workflow then runs
`memory-handoff` for the same transitions (`memory-lifecycle.md:11-14,30-34`). The handoff tolerates the duplicate
(`memory_handoff.py:113-115`).

**Preconditions in Memory (must ship first or together):**

1. **Approval hash.** `policy_hash` hashes the memory hook text from `extensions.yml`, with its `enabled:` line
   (`archive.py:119-122`). Reconcile flips it to `false`, so the hash changes. Then `approval()` raises (`:134-137`),
   and the handoff returns pending "Automatic mode is disabled or needs ... renewal" (`memory_handoff.py:98-99`). The
   same happens again on `reconcile --restore` (Workflow uninstall). Options:
   - (a) Strip the `enabled:` line from each hashed hook block before hashing. Disabling a mandatory hook only
     reduces what Memory runs, and the owner approved those commands. Change README:130 to say the enabled flag is not
     bound. **Recommended.**
   - (b) Keep the binding and document a one-time `speckit.memory.enable` after `reconcile --apply`. This one is
     fragile, because `upgrade.py` reruns reconcile.
   Every Memory release changes the hash anyway: the hash covers every file under `.specify/extensions/memory`
   (`:108-111`). So ship (a) in the same Memory release as the text changes below, and owners re-approve once.
2. **Re-init keeps the flag.** `add_hook` replaces an existing entry with `enabled: true` (`install.py:96-114`). I
   reproduced this on a disabled `session` entry (scratch run, output `enabled: true`). After that, Workflow's next
   `install.py` restore fails `HOOK_CHANGED_SINCE_RECONCILE`. Fix: when the own entry for that command exists with
   `enabled: false`, write `false` and leave every other field byte-identical. Reconcile compares the whole dict
   (`reconcile.py:42,46`), so the descriptions in `install.py:19-22` must not change while a journal exists. Say so
   in a code comment next to `HOOKS`.

**What `session.md` and `prepare.md` should still say** (both stay registered; the handoff dispatches them):

- `session.md` gets an Arguments paragraph. The handoff passes `--run <id>` (recovery,
  `memory_handoff.py:82`) and `--spec <dir>` (needs verification, `:178-179`). The body has no `$ARGUMENTS` and treats
  every call as "process all pending". Proposed: "With `--run <id>`, recover only that transaction. With
  `--spec <dir>`, verify and run only that feature, then return to the caller." The rest stays: the stale-lock rule,
  the recovery pointer, the gate and the processing loop. Size: about +200 B on 2,135 B.
- `prepare.md` gets one managed branch. The handoff returns `speckit.memory.prepare --spec <f>` only for
  `MEMORY_CHECK_SELECTION_REQUIRED` (`memory_handoff.py:120-122`), and `memory-lifecycle.md:15-20` then says "choose
  checks and retry the handoff". `prepare.md` instead runs `archive.py queue` directly (steps 4-5), which skips the
  handoff's intent record (`:125`). Proposed: "When `.specify/workflow.yml` exists, do steps 2-3 only, then run
  `workflow.py memory-handoff --transition execute --feature <f> --check <name>`." Standalone steps stay the same.
- **SESSION block** (`install.py:28-34`, loaded in every session through AGENTS.md and CLAUDE.md): add one fixed
  sentence: "In a Sanduq Workflow project, run `workflow.py memory-handoff --transition session` instead." It does not
  branch on install order, it is in the hash (one re-approval with the release), and it removes the second `pending`
  per session start.

**What Memory's `install.py` and the doctor must accept:**

- `install.py`: an existing `enabled: false` on `session` or `prepare` (above). It still adds the entries when absent,
  so standalone installs are unchanged. `test_install.py` gets one test: reinstall over a disabled entry keeps
  `false`, and the hook block bytes are unchanged.
- Workflow doctor (`workflow.py:1470`) and `reconcile.py:35`: add `extension == 'memory' and command in
  {speckit.memory.session, speckit.memory.prepare}`. `impact` stays enabled. Memory has no doctor of its own.
  `archive.py status` and `pending` do not read hook state, so nothing else in Memory needs to accept the change.

**Standalone Memory:** no `.specify/workflow.yml` means no reconcile, no `enabled: false`, and the same hash inputs
except the stripped flag line. Behaviour is unchanged.

Saving (round 3's PM6 estimate holds): one prepare body read (1,680 B) and one model step per Execute, and one
`pending` per Specify. Helper processes start in about 0.6 s each here (`archive.py --help`, 3 runs, 591-654 ms).
Effort S (Memory part), risk low with the two preconditions and high without them.

## 3. Correctness defects (verified)

| Id | Defect | Evidence | Fix |
| --- | --- | --- | --- |
| PM11 | `pr_changelog.py` uses `main` when `origin/HEAD` is absent (`:70`). On a `master` repository, the reviewer CHANGELOG states "(no commits on `main..HEAD`)" although commits exist. | Reproduced: `git init -b master`, a feature commit, run the script, and `### Added` shows `- (no commits on \`main..HEAD\`)`. | Use `pr_publish.branches`' rule (origin/HEAD, else `gh repo view`), else leave the line out. Same scripts folder, so import it. |
| PM12a | Project init detects owner type with `gh project list --owner X` and calls it `user` when that succeeds (`project-init.sh:80`, `.ps1:95-98`). `gh project list` accepts org logins too, so an org board is recorded as `user`. `project_sync.py:449` then builds `users/<org>/projectsV2/N`, and the REST fallback fails exactly when GraphQL is exhausted. | Code. The probe cannot tell the two apart. Not run against a live org. | `gh api users/<owner> --jq .type` gives `User` or `Organization` in one call. |
| PM12b | Init rerun resets `parentIssue`, `subIssues` and `stateFile` from `config.default.json` (`project-init.sh:199-200`, `.ps1:235-237`). A rerun to remap columns drops custom labels, title templates, `maxCount` and `subIssues.enabled`. | Code, both twins. | Keep these keys from the existing `config.json`. Defaults only on the first run. |
| PM10 | `pr_publish.py` treats any PR that `gh pr view` returns as the one to edit (`:177-180,206-207`). Without an open PR, gh returns the branch's latest closed or merged PR. A rerun after merge then rewrites a merged PR's body. Workflow forbids a replacement PR but expects post-merge verification (`stage-pr.md` entry point). | gh's branch finder puts open PRs first and otherwise returns the newest (gh source, `pr/shared/finder.go`). Not reproduced live. | Ask for `state` as well. When it is not OPEN, exit 3: "PR #n is merged or closed; nothing published". |
| PM13 | Project README:29 says "all sub-issues closed → `done`". No code does that: `resolve_auto` stops at `in-review` (`project_sync.py:411-417`), and `done` runs only when passed explicitly. The sync table's `done` row also omits the closing of sub-issues (`:493`). | Code. | Doc fix, together with D1. |
| PM14 | D3 preconditions (approval hash, re-init flag). | §2.3; `add_hook` reproduction. | §2.3. |

Low, not separate options: `pr_publish.ensure_branch` pushes only when there is no upstream (`:153-156`). A new PR
from an upstream-tracked branch with unpushed commits is created at the remote head. The contents check catches it
only when images exist. Fix with PM10: push when `git rev-list @{u}..HEAD` is not empty. The review-feedback thread
query is still unpaged (100 threads, 50 comments, `review-feedback.md:49-50`). That is PM2.

## 4. Options

`tok` and `time` bases: `pr.generate` 19,012 B of instructions; `review-feedback` 5,518 B and about 35 calls; managed
sync 3 or 4 `gh` calls and about 3 s; standalone `ready` with 10 tasks 42 calls; Memory lifecycle reads 6,472 B
(round 3 base).

### PM10. `pr_publish.py`: no edit of a closed or merged PR; push when ahead
- what: Add `state` to the `gh pr view` fields. When it is not OPEN, exit 3 with the PR number. Push a new PR's branch
  when the local branch is ahead of its upstream.
- evidence: §3. saving: none (correctness). effort S. risk low. consumer impact: a rerun after merge reports instead
  of editing.
- tests: `test_pr_publish.py`, with a fake `gh pr view` returning MERGED (no `pr edit` call recorded) and an ahead
  branch (one `git push` recorded).
- verdict: **fix-first**. It mutates a merged PR, and the fix is 4 lines.

### PM11. `pr_changelog.py`: one default-branch rule
- what: Import `branches` (or a small `default_branch`) from `pr_publish.py`. Without a resolvable base, leave out
  the commits line instead of saying "no commits".
- evidence: reproduced (§3). effort S. risk low. tests: `test_pr_changelog.py` on a `master` repository with no
  `origin/HEAD` and a fake `gh`.
- verdict: **fix-first**. It writes a false fact into a reviewer document.

### PM12. Project init: owner type and rerun preservation
- what: §3 PM12a and PM12b, in both shells, or once in PM5.
- effort S (twice in shell) or inside PM5. risk low. consumer impact: an org board config written by an older init
  keeps `ownerType: user` until rerun. Doctor could flag `ownerType` against `gh api users/<owner>` (R1, optional).
- tests: `ProjectInitTests` (`test_project_sync_summary.py:288-339`): an org owner gives `org`; a rerun keeps a
  custom `subIssues.labels`.
- verdict: **fix-first**, through PM5 if PM5 is done this round.

### PM13. Project docs and config truth
- what: README:29 `done` row. `sync.md` `done` row. `config.default.json`: drop `subIssues.granularity`, which is read
  nowhere (grep: only the default file), and fix `$comment`, which still says "prompt" although init is
  non-interactive. Land with D1.
- effort S. risk none. verdict: **do**.

### PM15 (= D4). Shared remote normaliser
- §2.2. Saves 286-420 ms per sync (measured), about 2-3 s per managed feature, and 39 duplicate lines. effort S. risk low.
- verdict: **do**.

### PM16. `project_sync.py`: fewer `gh` calls
- what: (a) In managed mode, skip `issue_node` in `ensure_parent` (`:236`). The node id feeds only `sync_sub_issues`,
  which is off in managed mode, and an existing value is kept, so the binding fingerprint (which includes
  `issueNodeId`, `workflow.py:88-89`) does not change mid-feature. (b) Create each label once per run (cache in
  `Sync`) instead of once per sub-issue (`:205-206`).
- evidence: `r4pm/count_calls.py` with FakeGh. Managed `open` makes 4 calls, `analysis` and `in-review` 3,
  `in-progress` 4, and each includes `issue view`. Standalone `ready` with 10 tasks makes 42 calls, 10 of them
  `label create`.
- saving: managed, 1 of 3-4 calls per sync ([0.25, 0.33] of `gh` time, about 0.7 s each, about 5 s per feature);
  standalone `ready`, 9 of 42 calls ([0.20, 0.22]).
- effort S. risk low. tests: call-count asserts in the Project suite (no `issue view` in managed mode; one `label create`
  per label per run).
- verdict: **do**.

### PM17 (= D1). Descriptions
- §2.1. Catalog: +18 chars (Project) and +20 chars (PR). effort S. verdict: **do**.

### PM18 (= D3, Memory side)
- §2.3, including PM14's preconditions. Memory files: `archive.py` (hash), `install.py` (flag), `session.md`,
  `prepare.md`, the SESSION block, `README.md:130`, CHANGELOG ("re-approve once"). Workflow files are R1's.
- tests: `test_install.py`: reinstall keeps `enabled: false`. A hash test: flipping `enabled` keeps `policy_hash`, and
  changing `priority` changes it. A Workflow reconcile test disables and restores the two Memory entries.
- verdict: **do**, with the gate D3 already names (one managed run).

### PM19. Project tests: a home and the minimum suite
- what: Move `extensions/workflow/tests/test_project_sync_summary.py` to `extensions/project/tests/test_project_sync.py`.
  `ci.yml:243-244` already discovers that folder. Drop `SUITE_TESTS['project']` (`ci_matrix.py:31`), and add
  `project -> workflow` to `DEPENDENTS`, because Workflow's `sync_project` runs the script. Add five tests: PM16a's
  call count, PM16b's label count, PM12a, PM12b, and D4's package-import test.
- evidence: the file has 15 tests (16.3 s), and 0 of them sit under `extensions/project/` (structure report §2).
- effort S. risk low (CI wiring is R6's; coordinate). verdict: **do**.

### PM20 (= PM9 revised). Memory fixture template
- what: In `test_archive.py`, `test_archive_v2.py` and `test_orchestration.py`, build the repository once in
  `setUpClass` (git init, config, commits, and for v2 and orchestration also `migrate()` and `prepare()`). Save it as a
  template. Before each test, `rmtree` and `copytree` it into **the same fixed path**. The state stores absolute roots:
  approval `root` (`archive.py:150`), queue entries (`memory_handoff.py:110`) and journals. A copy to a new path would
  break them.
- evidence: per-test `setUp` measured (`r4pm/setup_time.py`, while the full suite ran in parallel): 1.83 s × 57,
  6.58 s × 17 and 6.95 s × 32. That is about 438 s of `setUp` for 106 tests, and copying a small tree costs well
  under 0.2 s. That is
  about 30% of the 1,441 s run.
- saving: memory suite [0.35, 0.55] of wall time (estimate; confirm on `test_orchestration.py` first). Also shortens
  the 14-16 min Windows memory job (`ci_matrix.py:24`).
- risk: tests that mutate `.git` state stay isolated, because each restores a fresh copy. A test that asserts
  timestamps from `setUp` must read them after the restore. effort M.
- verdict: **do**. It makes the PM18 and D3 tests affordable, and they touch `test_install` and the hash.

### PM21. One `pr_lint` source
- what: `pr_publish.py:40-44,91-102` is an identical copy of `execution_tools.py:299-326`. And when Workflow is
  installed, `pr_publish.py` loads `execution_tools.py` by `exec_module`, which imports `evidence_snapshot` and
  `check_inputs` (`:82-90`). Move `CLOSE_REF`, `FENCE` and `pr_lint` to `extensions/scripts/shared/sanduq_pr_lint.py`,
  inject it into `pr` and `workflow` the same way as D4, and have `execution_tools` re-export it.
- saving: about 25 duplicate lines and one module load per publish (not measured; it runs once per PR). effort S.
  risk low. The guard and completion recompute through the same function.
- verdict: **do** if PM15 lands, since it is the same mechanism. Otherwise **defer**.

### PM2 (revisited). Review-feedback automation
- Today: unchanged, 5,518 B. Gather is 7 calls (`auth`, view, diff, three REST lists, GraphQL), and the REST inline
  comments duplicate the GraphQL thread comments. The thread query is unpaged.
- what: PM2a, `pr_feedback.py gather`: one paged GraphQL query plus issue comments, the filters from step 1.4, and
  compact JSON per thread (thread id, comment id, author, path, line, body, `diffHunk`). Step 1 becomes one line.
  PM2b, reply and resolve from an approved plan file, with resolve refused until the head contains the pushed commit.
- saving: PM2a [0.15, 0.20] of calls and [0.15, 0.25] of the command's bytes; PM2b another [0.10, 0.20] of calls.
- effort: PM2a M-, PM2b M. risk: PM2b moves the approval-gated writes into a script, and the trust rules must stay
  verbatim.
- verdict: PM2a **do**: it fixes paging and is read-only. PM2b **defer**: the writes are approval-gated, so the
  model's per-item calls are the audit trail.

### PM5 (revisited). Python init
- Today: 207 + 260 lines, `jq`, two interactive branches that agents never reach (the command always passes
  `--non-interactive`, `init.md:26-34`), one wasted `gh project view` (`project-init.sh:99-100`), and PM12's two
  defects in both twins. The CI `project-init` job runs per shell (`ci.yml:402-425`).
- what: round 3's PM5. A stdlib `project_init.py` with the same flags and `config.json`, no prompts, and exit 4 with
  JSON `needs` for a missing choice. The shells become one-release stubs that call it. `init.md` shrinks to one
  invocation (2,676 B to about 1,600 B).
- saving: init.md [0.35, 0.45] of bytes. One code path instead of two. `jq` no longer needed. effort M. risk:
  medium-low (`gh project` mocks; `smoke_project_init.py` drives both OSes).
- verdict: **do** this round. D1 and D4 already force a Project release, and PM12 would otherwise be fixed twice. If
  the round is full, **defer** and land PM12 in both shells.

### PM22. Shared GitHub transport: what PR and Project need (input for R2 and R6)
- Already shared by D4: remote normalisation and `github_repo`.
- Common needs: a `gh` runner with a 120 s timeout that returns `(rc, stdout, stderr)` and maps a missing binary to
  127 (Project `gh_raw:41-51`; PR `run:56-61`, which raises instead). `token_scopes(auth_text)` as a whole-token set
  (`project_sync.py:122-124`; the init twins grep it). One default-branch rule (PR `branches:135-144`; PM11).
- Project only, so keep it out of a shared module: the GraphQL-first, REST-on-exhaustion switch (`call`,
  `use_rest`), dry-run of mutations, and REST database-id lookup. PR only: `Failure(3)` exit mapping.
- The contracts differ (raise vs return code, 120 vs 60 s), as round 3 found. Share the semantics (remote, scopes,
  default branch), not a client class.
- verdict: **defer** the transport module. Do D4 and PM11 now.

### PM23. `pr_publish.py`: take the URL from `gh pr create`
- what: `gh pr create` prints the URL. Use it instead of the second `gh pr view` (`:211-212`). This is the part of
  round 3's PM3 that was not done.
- saving: 1 call per new PR. effort S. verdict: **do** (with PM10).

### PM24. Memory `pending` carries the policy facts the handoff needs
- what: The handoff calls `archive.py pending`, then `archive.py policy` for `target_branch` and `policy_hash`
  (`memory_handoff.py:68,88`). Add both fields to `pending`'s data (an additive interface change), so the handoff
  drops one helper process per transition (R1's side).
- saving: 1 of 2-3 helper processes per transition, about 0.6 s each (measured start). effort S. risk low (additive;
  the handoff checks types).
- verdict: **do** if D3 touches `memory_handoff.py` anyway. Otherwise **defer**.

### Dropped or not proposed
- **Split `archive.py`** (1,498 lines): no agent reads it. Revisit after PM20 makes the suite cheap.
- **Memory instruction trims**: the commands are 658-4,463 B. `run.md` already reads references per step. The
  prohibition density (1.8-2.0 per 100 words) guards destructive git verbs. **Drop**.
- **Reply template and red flags in review-feedback**: cheap text that guards the approval gate. Keep.

## 5. Not verified

- PM10's gh behaviour for a merged PR was read from gh's finder, not run against GitHub.
- PM12a was not run against a live org owner.
- PM16's per-call time uses `gh auth status` (720-829 ms) as a proxy for the other calls.
- The D3 savings depend on the one managed run that round 3 and D3 both require.
- PM20's saving is an estimate from `setUp` timings taken while the full suite ran in parallel. Confirm on one class.
- The `atomic_write` `PermissionError` was seen once. A short retry on Windows (`git_state.py:31`) is a candidate if it
  recurs in CI.
