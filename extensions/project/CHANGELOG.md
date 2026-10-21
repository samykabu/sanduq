# Changelog

## Unreleased

Round 4.

- A malformed `.specify/project-sync-state.json` stops the sync with a message that names the fix; it is no longer reset to empty (which made the next run create duplicate issues).
- Before creating task sub-issues, the sync looks for existing ones with the sub-issue labels and adopts them, and it saves the state after each new sub-issue, so a rerun after an interrupted run never duplicates. A failed lookup creates nothing.
- Remotes are read and parsed through the shared `sanduq_remote` helper bundled in the archive. The sync no longer loads an installed Workflow's `workflow.py` (about 0.14 s faster per sync, measured in process).
- Managed syncs skip the `gh issue view` node lookup (only standalone sub-issues use it), and each label is created once per run instead of once per sub-issue.
- Init asks GitHub for the owner's account type, so an organization board is recorded as `org` (`gh project list` accepts both). A rerun keeps the existing `parentIssue`, `subIssues` and `stateFile` settings. One `gh project view` call fewer (bash).
- Docs: sub-issues are standalone only; `done` runs only when passed explicitly (the README promised an automatic move no code made). `config.default.json` drops the unread `subIssues.granularity`.
- Tests moved to `extensions/project/tests/`.
- Init with auto-create makes each column once (Ready was created three times), writes the option ids GitHub returns after the update (all ids change), and in a Workflow project also creates the columns doctor requires (Backlog, Need Clarifications). There it matches names exactly and renames a column that differs only in case or spacing, such as GitHub's default `In Progress`, to Workflow's `In progress`.

### Migration

- A sync that now stops on a malformed state file: restore `.specify/project-sync-state.json` from git or fix it, then rerun.
- A config written by an older init for an organization board says `ownerType: user`; rerun `speckit.project.init` (or set `"ownerType": "org"`), otherwise the REST fallback uses the wrong path when GraphQL is exhausted.
- A Workflow project whose `config.json` came from auto-create may hold stale option ids: rerun `speckit.project.init` and check `workflow.py doctor --project`. In a Workflow project init now asks before renaming a near-match column (auto-create renames it).

## [2.4.0] - 2026-10-20

Optimization round 3 (fixes to 2.3.0).

- `project_sync.py` normalises remotes like Workflow (dots in names, ports, case, ssh and https), checks the full `project` scope, times out `gh` and `git` after 120 s, and makes one gh call fewer per sync.
- Init runs the scripts non-interactively, no longer forces an interactive `gh auth refresh`, and names each missing choice with its flag.

## [2.3.0] - 2026-10-19

Optimization round 2.

- `scripts/project_sync.py` (Python, standard library) replaces the bash and PowerShell sync scripts with the same flags, summary lines and GraphQL-to-REST fallback. Python is now a required tool; init keeps its shell pair.
- Workflow 1.14.0's claim prints the exact sync command, and the sync command file is 1.4 KB instead of 2.7 KB.
- Both commands have frontmatter descriptions; hosts listed them as "Extension command: ..." before. Init no longer asks to record the owner in a memory file.

## [2.2.2] - 2026-10-10

- README links point to the new extension page, install-by-host page and command reference.
- The fallback install script note is replaced by the local `specify extension add --dev` path; `install.sh` and `install.ps1` are retired.

## [2.2.1] - 2026-10-06

- Link setup and complete usage examples from the package README; links work in installed copies.

## 2.2.0

- **B7 — quiet output.** `project-sync` (Bash and PowerShell) gains
  `-Summary`/`--summary`: exactly one stdout line (`ok issue=<n>
  status=<status> created=<n> closed=<n>` on success; `skipped
  reason=<reason>` on a graceful degradation; `error reason=<message>` on
  a usage error or a mid-run failure, with Bash additionally carrying
  `exit=<rc>` and, when known, `line=<n>`) as an alternative to the
  `-Json`/`--json` summary, which is unchanged. Under `-Summary`/`--summary`
  the run log moves off stdout so it never breaks the one-line contract,
  and an unrecognised argument is always a stderr diagnostic. A genuine
  mid-run failure is caught and reported as that one `error` line instead
  of a raw shell trace or uncaught exception. `-Summary`/`--summary` and
  `-Json`/`--json` together is rejected. Default (no flag) behaviour and
  every exit code are unchanged.
- `project-sync` (Bash and PowerShell) falls back to the GitHub REST API
  when the GraphQL budget is exhausted: Project item add/lookup and Status
  edits, parent issue lookup/creation, sub-issue creation and linking,
  sub-issue closing and the open-PR check. The real budget is checked,
  since `gh project` can misreport exhaustion (for example "unknown owner
  type"). The run log and the `-Json`/`--json` summary report the
  `transport` used (`graphql` or `rest`).

## [2.1.0]

- Managed mode preserves the bound parent and delegates task issue creation and state changes to the workflow adapter.
- Both setup scripts preserve managed hooks, map workflow phases from project policy
  and retain Scope-only board columns. Managed sync is required.

All notable changes to the GitHub Project Lifecycle Sync extension.

## [2.0.0] - 2026-07-18

### Changed

- Use PolyForm Noncommercial 1.0.0 for Sanduq original contributions.

## [1.1.0] - 2026-07-18

### Added

- Ask during project initialization whether lifecycle sync hooks should be required/automatic or
  optional/manual.
- Support non-interactive selection through `-HooksMode` (PowerShell) and `--hooks-mode` (Bash).

### Changed

- Persist the selected hook policy in `config.json` and apply it to every `project` hook in
  `.specify/extensions.yml`.

## [1.0.1] - 2026-07-09

### Changed

- Aligned release metadata with the sanduq automated extension pipeline and public catalog.

## [1.0.0] - 2026-07-09

### Added

- Initial release of the `project` Spec Kit extension for GitHub Project (v2) lifecycle sync.
- Parent feature issues, native task sub-issues, lifecycle status movement, and graceful skips when
  GitHub CLI or project configuration is unavailable.
