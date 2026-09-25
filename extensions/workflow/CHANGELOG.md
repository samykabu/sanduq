# Changelog

## Unreleased

- `install.py --preserve-ci` and `upgrade.py --preserve-ci` no longer roll back
  with `CI_WORKFLOW_STALE` on a clone, worktree or machine without the
  git-excluded `install-receipt.json` (#22). The installer hands the preserved
  path straight to its health check, and the tracked `install-lock.json` now
  records `preserved_ci` so every checkout treats that file as project-owned.

## 1.3.0

- Issue-bound feature identity uses the GitHub issue number and title for the
  initial branch and spec directory. Standalone non-issue Specify stays upstream.
- Material workflow decisions use stable questions and authorized answers in the
  bound GitHub issue, with a separate Project Decision field, a committed
  application ledger, conflict/edit detection, and artifact freshness checks.
- Select Disabled, Advisory, or Required evidence CI, managed-only or all-PR
  applicability, and individual rule groups during init or later. Ordinary
  non-feature bug-fix PRs return `not_applicable` under managed-only scope.
  Disabling an installed gate checks active GitHub branch rules before removing
  its managed job. Optional live-answer and candidate-merge rules are available.
  Exact, dated PR-rule waivers require an authorized GitHub reviewer and the
  current head SHA; identity checks remain mandatory.
- CI runner policy changes have a separate digest from delivery policy so they
  do not invalidate feature receipts. Reviewed migrations preserve older
  checkpoint hashes and audit invalidation.
- QA Assure and User Manual can be independently selected or deselected after
  initialization through reviewed policy and installer changes. The native
  Spec Kit workflow prototype remains isolated; Sanduq's receipt-based
  dispatcher remains the production scheduler.

## 1.2.4

- Evidence fingerprints no longer depend on how Git checked a byte-sensitive file
  out. A tracked `.sql` (or `-text`) file whose working tree differs from the
  index only by Git's checkout conversion (`core.autocrlf`, `eol` attributes) is
  fingerprinted as its committed blob, which is what a clean CI checkout holds.
  A Windows `core.autocrlf=true` checkout wrote LF-committed SQL as CRLF, so
  local receipts hashed CRLF bytes and the CI evidence gate reported
  `STALE_RECEIPT` for unchanged files. Real edits still hash the working-tree
  bytes, untracked files are unchanged, SQL committed as CRLF keeps its CRLF
  hash, and SQL content is still never normalized. Git is queried in batches
  (`ls-files --stage`, `hash-object --stdin-paths`, `cat-file --batch`), and not
  at all for files already identical to the index.
- `doctor` reports a `BYTE_SENSITIVE_EOL_DRIFT` warning (not an error) naming how
  many tracked byte-sensitive files have working-tree line endings different
  from the index (`i/lf w/crlf` or `i/crlf w/lf`) and how to re-checkout them.
  The report now always carries a `warnings` list.

## 1.2.3

- The implementation progress report is titled with the feature: `init` takes
  the plan's `# Tasks: <feature>` heading by default, `--title` renames an
  existing report without losing its evidence, and the browser tab shows the
  same title instead of a fixed "Implementation progress".
- The report shows the Sanduq logo (light and dark variants shipped under
  `assets/report/` and copied beside the page), adds a Phase column, filters
  tasks by Status and Phase, and moves the activity log to its own tab. Filters
  and the selected tab are kept in the URL fragment, so the five-second refresh
  no longer resets them; without JavaScript the page still refreshes.

## 1.2.2

- Depend on user-manual 1.3.0, which stages an edition's reachable assets so a
  strict manual build resolves every link.


## 1.2.1

- A reviewed migration now rebinds a checkpoint to the current policy. A release
  that only adds a policy section (1.2.0 added `ci:`) left every finished feature
  reading `POLICY_CHANGED` in the CI gate even though no work had changed.
  `migrate` records the policy change, invalidates exactly the stages the policy
  cutoff says a semantic change reached, and preserves the rest as historical.

## 1.2.0

- Where CI runs is a project decision recorded under `ci:` in `.specify/workflow.yml`;
  shipped workflow assets are rendered from it instead of carrying a fixed runner.

## 1.0.0 (unreleased)

- Review Home pilot hardening: shared portable UTF-8 hashes across Workflow,
  QA and manuals, respecting `-text`, binary data, SQL bytes and lone CR.
- Publication index preflight and path-level stale-receipt diagnostics; no
  automatic staging and no relaxation of source freshness after target merges.
- Exclude derived graph output from implicit documentation inputs, retain
  explicit graph output integrity, and document exact-head/post-merge verification.
- Upgrading existing pilot state can invalidate receipts where hash semantics
  or implicit inputs changed. Review drift and migrate/revalidate affected stages;
  never rewrite historical receipts as new test execution.

- Live-pilot correction: only reliable measured context can pause the default workflow.
  Unknown/estimated/stale telemetry continues automatically; explicit strict mode remains opt-in.

- Initial managed workflow runtime, presets, issue adapters and local verification. Release and live acceptance pending.
- Exact-source dependency and preset installer, host registration checks, local backups,
  symlink-preserving rollback and an outer transaction for workflow package updates.
- Required artifact/source freshness, parent-scoped task mappings, reviewed migrations,
  versioned state contracts and policy-aware CI gates.
- Explicit clarification refresh, existing-feature revalidation, owned legacy alias
  upgrades and project readiness checks before dispatch.
- Resolve PR features from the target/head common ancestor, excluding unrelated
  target-branch changes; missing shallow history blocks with a fetch instruction.
