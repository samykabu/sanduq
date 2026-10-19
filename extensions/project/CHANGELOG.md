# Changelog

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

## 2.1.0 (unreleased)

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
