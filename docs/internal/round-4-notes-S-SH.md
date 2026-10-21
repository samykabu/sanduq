# Round 4 notes: S-SH (shared code and packaging)

## D4 `sanduq_remote.py` (review, injection, tests)

- Reviewed against `workflow.py:360-441` at HEAD: `_strip_dotgit`, `_normalize_path_remote` and
  `normalize_remote_url` are the same code. `github_slug` is the old `github_repository` regex. Two intended
  differences from Workflow's old `origin_url`: a `timeout` (X21 style) and an empty value reads as None.
- One change: `github_slug(None)` and `github_slug('')` return None, so `github_slug(origin_url(root))` works
  without a guard.
- `package.py`: one `SHARED` table ships `sanduq_remote.py` to workflow, project and scope (and
  `sanduq_pr_lint.py`, below) before the inventory is written. Fixture roots without the shared folder skip it.
- Tests, `extensions/scripts/tests/test_sanduq_remote.py`:
  - 20 GitHub forms and 14 non-GitHub forms (look-alike path, userinfo trick, bad port, scp to another host,
    deep path, local paths, `file://`, empty, None), normalisation and `same_github_repository` cases,
    `origin_url` on a temp repo.
  - Archive bytes equal the source and the inventory hash matches, for every consumer of both helpers.
  - Installed-layout import from each archive alone with PyYAML and packaging blocked.
  - Project route only: `project_sync.github_repo` from the project archive alone, with a `workflow.py` that
    leaves a mark when loaded. Scope is not pinned (it loads `workflow.py` for checkpoint identity).
  - One definition: an AST scan of `extensions/*/scripts` finds the moved names only in the shared files.

## X17 promote returns what it wrote

- `release.promote` returns `written` (the two catalogs, `pending-releases.json`, and `CHANGELOG.md` when it
  cleared a heading). `test_release_promote.py` checks `written` equals `git status` after promote, with and
  without a changelog, and that the `git add` line in `.github/workflows/release-extensions.yml` covers every path.
  The yml already stages all four; no S-CI change needed.

## X18 three `check_docs.py` rules

`version_drift()`: (1) the `| Requires |` row in `docs/extensions/<id>.md` names every required extension and any
version it gives equals the manifest lower bound (`2.x` reads as 2.0.0; Spec Kit and Python are checked when the
row gives a version); (2) `extensions/<id>/README.md` "describes <Name> X.Y.Z" equals the manifest version;
(3) no heading containing "unreleased" at or below the manifest version's entry. A `## Unreleased` heading above
it is allowed (tested). Five failing fixtures and one passing fixture in `test_check_docs.py`.

Current violations (run on the tree, 2026-10-21), for the owners:

| Where | Owner |
| --- | --- |
| `extensions/scope/README.md:8` describes 1.8.0; manifest 1.9.0 | S-SC |
| `extensions/assure/CHANGELOG.md:102` "2.1.0 (unreleased)" | S-AU |
| `extensions/user-manual/CHANGELOG.md:149` "1.1.0 (unreleased)" | S-AU |
| `extensions/project/CHANGELOG.md:50` "2.1.0 (unreleased)" | S-PM |
| `docs/reference/hooks.md` stale (not a new rule; some manifest change; run `check_docs.py --write`) | S-DOC / orchestrator |

`docs/extensions/scope.md` already reads 1.13.0 (S-DOC fixed it).

## X20 changelogs out of packages, LF for LICENSE and `*.txt`

- `package.excluded` drops each top-level `<ext>/CHANGELOG.md`; the README link rewrite now covers it
  (links go to the GitHub blob URL). Nested files named CHANGELOG.md still ship.
- `.gitattributes`: `*.txt text eol=lf` and `LICENSE text eol=lf`. The index is already LF; this checkout's
  working tree still has CRLF in 13 files (LICENSEs and requirements files) until they are checked out again.
  Orchestrator: after committing, `git checkout -- LICENSE '*.txt' '**/LICENSE'` (or a fresh clone) before
  building local archives.
- `test_package_exclusions.py`: changelogs absent, README links point at GitHub, `git check-attr` gives LF.
- `extensions/user-manual/ADAPTER.md:60` still lists `CHANGELOG.md` as package documentation (S-AU, text only).

## PM21 one `pr_lint` source (injection side)

- New `extensions/scripts/shared/sanduq_pr_lint.py`: `PR_LINT_SCHEMA`, `CLOSE_REF`, `FENCE`, `pr_lint`, moved
  unchanged from `execution_tools.py:299-326`. Injected into `pr` and `workflow`.

## Tests run

- `extensions/scripts/tests`: 136 tests, 134 pass, 2 fail by design until consumers land (below).
- `extensions/scripts/test_check_docs.py`: passes. `extensions/workflow/tests/test_release.py`: 6 OK.

## Requests

- **S-PM** (`project_sync.py`): import `sanduq_remote` with the `deps.py` dev-tree fallback; keep
  `github_repo(remote)` as the name (or `github_repo = sanduq_remote.github_slug`); delete the copy (`:65-103`),
  `WORKFLOW` and the `exec_module`. Turns `test_project_normalisation_route_never_loads_workflow_py` and part of
  `test_moved_names_are_defined_only_in_the_shared_files` green.
- **S-PM** (`pr_publish.py`): `lint()` calls `sanduq_pr_lint.pr_lint` (same fallback import), drop the
  `exec_module` of `execution_tools.py` and the `CLOSE_REF` copy; `FENCE` can come from the module too.
- **S-WF** (`execution_tools.py`): `from sanduq_pr_lint import PR_LINT_SCHEMA, CLOSE_REF, FENCE, pr_lint` with the
  same fallback, and delete the local definitions.
- **S-CI**: CI runs `check_docs.py`; it will fail on the violations above until the owners fix them.
