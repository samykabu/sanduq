# Issue #94: stream notes

Each stream appends under its own heading only. Plan: `issue-94-plan.md`.

## A1: evidence retention by ancestry

- `_snapshot_plan` accepts a git record when the retention ref matches, or when the record's commit is a full OID and `git merge-base --is-ancestor <commit> HEAD` exits 0; otherwise `EVIDENCE_RETENTION_MISSING` (an absent ref no longer surfaces as `EVIDENCE_GIT_UNAVAILABLE`). Blob and SHA-256 checks unchanged.
- Fixture `orphan_head()` points HEAD at an empty-tree root commit (`mktree` + `commit-tree` + `update-ref`, no checkout).
- `test_missing_retention_and_missing_objects_are_refused`: HEAD moved to the orphan before deleting the ref, because the recorded commit was HEAD and is now accepted by ancestry.
- `test_moved_repository_requires_exact_retained_ref_commit_blob_and_sha`: same move before deleting the ref; after the `--allow-empty` commit `other`, HEAD moves to the orphan again, because `other` is built from the index (still holds clean.md with the recorded blob) and as HEAD it would pass ancestry in the `('commit', other)` subtest.
- New `test_fresh_clone_validates_committed_snapshot_by_ancestry`; its receipt carries a fingerprint and patches `required_inputs` like the other `current` assertions in the file (the fixture has no `specs/example`).
- The clone is made with `-c core.autocrlf=false -c commit.gpgsign=false`: a machine-global `autocrlf=true` would rewrite `before.json` at checkout and the receipt's normalized fingerprint would then differ from its byte digest.

## A2: renderer guard, base ref, pins (sanduq)

- `flags()` gains `self_hosted: not hosted(ci['runners']['linux'])`; a mixed label set counts as self-hosted, same as A3.
- workflow-gates.yml and documentation-gates.yml: job-level `# sanduq:if self_hosted` guard under `runs-on:`;
  checkout pinned to v4.3.0, setup-python to v5.6.0 (gates only). documentation-gates.yml still has
  `${{ steps.feature.outputs.path }}` inside two `run:` scripts; left alone per "nothing else" (it is a step output,
  not PR-controlled text, but a follow-up could move it to env too).
- Base-ref fetch: ci_gate.py never reads `origin/<base>` by name. It gets `--base-ref "$BASE_SHA"` (a SHA) and runs
  `git merge-base HEAD <sha>` in `resolve_features`, then forwards the same SHA to assure_state/manual_state via
  `ready_checks`. It only needs the base commit objects locally; the explicit refspec fetches the full base branch
  history (BASE_SHA is that tip or an ancestor of it), so the gate sees what it saw before, plus a named
  `refs/remotes/origin/<base>` instead of only FETCH_HEAD.
- Tests: fork guard on every job of FORK_GUARDED assets under `self_hosted()`; no job `if:` on any asset under the
  default; no `${{` in any `run:` of workflow-evidence (both selections); every `uses:` in PINNED assets is
  `@<40 hex> # vX.Y.Z`. Add user-manual-preview.yml to FORK_GUARDED (and preview/release to PINNED) after vendoring A3.

## A3: dev-tools 1.1.3 (sanduq-skills)

- Done in sanduq-skills on fix/pinned-actions-fork-guard: `flags()` gains `self_hosted`; preview template gets the
  guard block under `runs-on:` and four SHA pins; release template gets three pins; both manifests 1.1.3; root
  CHANGELOG entry dated 2026-10-19; one test in test_init_manual.py (self-hosted render has the `if:`, default render
  has none, every `uses:` is SHA-pinned with a version comment).
- `python -m unittest discover -s skills/dev-tools/skills/user-manual/tests -q`: 26 tests OK. `git diff --check` clean.
- `User-Manual/tools/` paths and `with:` blocks untouched, so the sanduq vendor rewrite rules still apply.
- Templates are LF; the guard reuses the `hosted()` regex, so a mixed hosted/self-hosted label set counts as self-hosted.

## Orchestrator

- Reviewed all three diffs; commits on `fix/issue-94`: dac91a7 (A1), 29a4224 (A2), 23d774e (release notes),
  plus the vendoring commit for dev-tools 1.1.3. sanduq-skills PR #16 merged as 1a27b56, tag `dev-tools-v1.1.3`.
- Gates run locally: `test_evidence_snapshot` + `test_ci_policy` (55 OK, then 39 OK after the vendored templates
  joined FORK_GUARDED and PINNED), `test_install` (with A2's run, 69 OK), `test_ci_evidence` + `test_ci_gate`
  (35 OK), `smoke_install.py --host claude --second-host codex` (ok), `check_docs.py`, `validate_skills.py`
  (0 errors), `git diff --check`, `release.py prepare --development` (lists workflow 1.13.1, assure 2.3.4,
  user-manual 1.5.4).
- Decisions: the user-manual templates are vendored under `vendor.lock.json`, so their change went upstream
  (dev-tools 1.1.3) and came back through `vendor.py update`; the fork guard is also emitted into the assure
  gate and the user-manual preview because they run the same checkout on the same runner (one widening from the
  issue text). `documentation-gates.yml` still interpolates `steps.feature.outputs.path` (a step output read
  from the repository's feature.json) into two `run:` scripts; left for a follow-up.
- `vendor.py check` reports 58 illustrate icon SVGs as differing on this Windows checkout: index and lock are LF,
  the working copy is CRLF (`git ls-files --eol`); CI on Linux is the authority.
