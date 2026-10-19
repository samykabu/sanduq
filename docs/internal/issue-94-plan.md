# Issue #94: plan

Fix for https://github.com/samykabu/sanduq/issues/94 on branch `fix/issue-94` (sanduq) and
`fix/pinned-actions-fork-guard` (sanduq-skills). Verdict and fix shape come from
`handoff-2026-10-19.md`; this page only assigns files, tests and versions. Streams append to
`issue-94-notes.md` under their heading and never commit; the orchestrator reviews and commits.

Target versions: workflow 1.13.1, assure 2.3.4, user-manual 1.5.4 (sanduq, `dependencies.json`
selected pins follow), dev-tools 1.1.3 (sanduq-skills). The user-manual templates are vendored
from sanduq-skills under `vendor.lock.json`, so their change is made upstream, tagged, then vendored
back with `vendor.py update`; editing them in sanduq would fail `vendor.py check` in CI.

Verified action pins (GitHub API, lightweight tags on commits):
`actions/checkout@08eba0b27e820071cde6df949e0beb9ba4906955 # v4.3.0`,
`actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0`,
`actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2`,
`actions/github-script@f28e40c7f34bde8b3046d885e986cb6290c5673b # v7.1.0`.

## Stream A1: evidence retention by ancestry (item 1)

Owns `extensions/scripts/shared/evidence_snapshot.py`, `extensions/workflow/tests/test_evidence_snapshot.py`
and one sentence in `docs/workflow/runner-policy.md`.

- In `_snapshot_plan`, a git record whose retention ref is absent or points elsewhere is accepted
  when `record['commit']` is a full object id and `git merge-base --is-ancestor <commit> HEAD`
  exits 0; any other exit code refuses with `EVIDENCE_RETENTION_MISSING`. Blob and SHA-256 checks
  are unchanged. No restore step, no new script, no descriptor rewrite.
- Two existing tests delete the ref while the recorded commit is `HEAD` and expect refusal
  (`test_missing_retention_and_missing_objects_are_refused`,
  `test_moved_repository_requires_exact_retained_ref_commit_blob_and_sha`). They keep every
  assertion but first move `HEAD` to a commit that does not descend from the recorded one
  (`git commit-tree` plus `git update-ref HEAD`, no checkout). Reason recorded in the notes.
- New test: capture, commit the snapshot, `git clone` the fixture (retention refs are not cloned),
  then `validate`, `resolve`, `workflow.validate_evidence_snapshots` and `receipt_status(...)['current']`
  succeed in the clone; a snapshot whose commit is fetched but not an ancestor of `HEAD` is refused.

## Stream A2: renderer guard, base ref, pins in sanduq (items 2 to 4)

Owns `extensions/workflow/scripts/sanduq_ci.py`, `extensions/workflow/assets/github/workflow-gates.yml`,
`extensions/assure/assets/github/documentation-gates.yml`, `extensions/workflow/tests/test_ci_policy.py`
and one paragraph in the self-hosted section of `docs/workflow/operations.md`.

- `flags(ci)` gains `self_hosted: not hosted(ci['runners']['linux'])`.
- Both PR-triggered templates get, at job level, a `# sanduq:if self_hosted` block holding
  `if: github.event.pull_request.head.repo.full_name == github.repository` (the assure gate runs
  the same checkout on the same runner, so it gets the guard too; this is the one widening from
  the issue text).
- `workflow-gates.yml`: base ref through `env: BASE_REF` and an explicit refspec fetch
  (`+refs/heads/$BASE_REF:refs/remotes/origin/$BASE_REF`); checkout and setup-python pinned.
- `documentation-gates.yml`: checkout pinned.
- Tests: guard present under the self-hosted fixture on both assets and absent under the default;
  no `${{` inside any `run:` of the gate template; pinned `uses:` lines carry a version comment;
  existing hygiene tests updated for the new `uses:` string and the env-based fetch.

## Stream A3: dev-tools 1.1.3 in sanduq-skills (item 4, user-manual templates)

Owns, under `skills/dev-tools/`: `skills/user-manual/scripts/sanduq_ci.py`,
`skills/user-manual/assets/github/user-manual-preview.yml`, `.../user-manual-release.yml`,
`skills/user-manual/tests/test_init_manual.py`, `.claude-plugin/plugin.json`, `plugin.json` and the
root `CHANGELOG.md`.

- Same `self_hosted` flag in the portable renderer; preview template gets the guard block and all
  four pins; release template (tag push, no PR) gets checkout, setup-python and upload-artifact
  pins. Version 1.1.3 in both manifests; one changelog entry; one test that renders the preview
  under a self-hosted and a hosted selection.

## Orchestrator

Review each diff; `cd extensions/workflow/tests && python -m unittest test_evidence_snapshot test_ci_policy test_install -q`;
`python extensions/scripts/smoke_install.py --host claude --second-host codex`; `check_docs.py`,
`validate_skills.py extensions presets`, `git diff --check`. Merge sanduq-skills first, tag
`dev-tools-v1.1.3`, then `vendor.py update --source ../sanduq-skills` in sanduq, bump versions,
changelogs, `dependencies.json`, `pending-releases.json` to `ready`, open the PR, read every job's
conclusion, merge, verify `gh release list`, close #94 naming the commits.
