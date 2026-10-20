# Session handoff: implement issue #99

Written 2026-10-20 for a fresh Claude Code session. Read this whole file, then
`docs/internal/issue-99-plan.md`, then the issue (`gh issue view 99 --repo samykabu/sanduq`), before acting.
You are the planner, orchestrator and reviewer: Opus 5.5 subagents (`model: opus`, `effort: high`) implement;
you review every diff, run the gates, commit, open the PR, read every CI job, merge and release.

## Where things stand

- Main is at 07dc50f with Workflow 1.15.0 and the round-3 companions released (catalog promoted).
- Issue #99 is **validated** on that commit. F1 and F2 are real defects; F3 and F4 are documentation. The
  validation evidence and the design are in `docs/internal/issue-99-plan.md` (commit fdc2896). Do not
  re-litigate the verdict; implement the plan.
- Work happens in the worktree `D:\Projects\Personal\sanduq-issue99` on branch `fix/issue-99` (base 07dc50f,
  plus the plan, the notes file `issue-99-notes.md`, this handoff and one patch). Nothing is implemented yet.
- `docs/internal/issue-99-partial-stream-b.patch` holds about 50 lines of unreviewed, unfinished edits a
  stopped agent had made to `sanduq_freshness.py`, the Assure and User Manual commands and
  `docs/workflow/operating-guide.md` (design items 4 and 5). Stream B may apply it as a starting point
  (`git apply`) or ignore it; delete the file before the PR either way.

## What to do

1. Dispatch the two streams in the plan's table in parallel, with disjoint files: **A runtime** (design 1,
   2, 3 and the workflow references of design 5; regressions R1, R2, R3, R4, R8; new `test_sync_binding.py`)
   and **B freshness and docs** (design 4 and the lean adoption doc; regressions R5, R6, R7, R9). Each defect
   test must fail against HEAD before the fix; each stream appends notes under its heading in
   `issue-99-notes.md`.
2. Review each diff yourself. Hard points to check in A: status-only transitions are the only thing the
   projection forgives (issue, issueNodeId, itemId, subIssues, repository and a missing entry still fail
   closed); other features' entries do not matter; legacy raw-hash receipts stay byte-exact until `migrate`
   or `sync-amend`, which verify the binding against `scope-source.json` and `workflow/task-issues.json`
   and write an `administrative-amendment` lineage record; `project-sync` is idempotent and records
   pending/done/failed honestly. In B: declared outputs leave the implicit inputs for document kinds only,
   are still hashed as outputs, and states recorded by 1.15.0 stay current when nothing changed.
3. Run the focused suites (`test_sync_binding`, `test_workflow`, `test_receipt_contract`, `test_freshness`,
   `test_project_sync_summary`, `test_lean_execution`, `test_lean_native_integration`), the guard suites
   (`test_source_key`, `test_ci_revalidation`, `test_eol_fingerprints`, `test_upgrade`, reference and skill
   tests), the Assure and User Manual suites, both workflow halves, `smoke_install.py --host claude
   --second-host codex`, `check_docs.py`, `validate_skills.py extensions presets`, `git diff --check`.
4. Optionally ask Codex (`codex exec -m gpt-6.1-sol --sandbox read-only -C <worktree> -o <file> -`) for an
   independent review of the diff before release, as in round 3.
5. Release: `python extensions/scripts/release.py bump workflow 1.16.0`, `bump assure 2.5.1`,
   `bump user-manual 1.7.1`; package changelogs and a root CHANGELOG entry ending "(pending release)";
   `pending-releases.json` status `ready` with a note; README and `docs/start/upgrades.md` upgrade notes
   (the claim's `project_sync.command` changes; in-progress features run `migrate` or `sync-amend`).
   Open the PR, read every job with `gh run view <id> --json jobs`, merge with `gh pr merge <n> --merge`
   (no `--delete-branch` while the branch is checked out in a worktree), confirm the release run and the
   catalog, then comment on #99 with the commits, what changed per finding, and what stays the consumer's
   step (Bunyan lean policy and the live two-pass acceptance).

## Working rules learned the hard way

- No `git stash`, `checkout`, `reset`, `clean` or `switch` while agents share a tree; give each agent
  disjoint files and one notes section; commit per stream yourself after review.
- Workflow tests run from `extensions/workflow/tests`; the whole suite in two halves. On this machine 18
  workflow tests fail regardless of change: `test_verification_plan` (14), `test_execution_tools`
  PreflightTests (3), `test_memory_handoff` (1). The Memory suite fails about 57 tests under the Microsoft
  Store Python; run it with `uv run --no-project --python 3.11 --with pyyaml python -m unittest discover
  -s extensions/memory/tests -q`.
- GitHub's Windows runners resolve `bash` to the WSL launcher and hand out 8.3 short temp paths: tests that
  shell out to bash must skip the System32 launcher, and path comparisons must resolve both sides.
- The org spend limit has stopped agents mid-work several times; resume a stopped agent with SendMessage,
  or restart it with a brief that tells it to inspect its partial diff first.
- CI takes about 20 minutes per PR; check every job's conclusion, never the exit code of `gh run watch`.
