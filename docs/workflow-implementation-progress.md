# Workflow implementation progress

Updated 2026-09-18. Branch: `feat/reusable-workflow`. **Local implementation and
validation remain in progress. No release or Bunyan adoption has occurred.**

Review: [draft PR #3](https://github.com/samykabu/sanduq/pull/3). Both diagrams in
its description loaded at 1440x900 in the authenticated browser. Sanduq is public;
this does not prove private-repository attachment behavior.

## Implemented locally

- Canonical Scope runtime, analyst/GitHub clarification skills and reusable presets
  live in Sanduq, with MIT migration provenance. Managed policy supports inclusive
  effort bands, configurable board names/artifact paths and rereading waiting answers.
- Workflow commands dispatch Scope, Specify, Clarify/Brainstorm, Plan, one task
  generator, selected QA/manual analysis, Analyze, core Tasks-to-Issues and one executor.
  Verification/review and selected documentation precede explicit Finalize.
- Parent/feature/task-scoped native sub-issue creation, lost-response recovery,
  existing mapping adoption and close/reopen synchronization have fake-API coverage.
  Project sync owns board updates and cannot create a duplicate set of task issues.
- Context checks, checkpoint/resume prompts, claims, explicit feature/branch binding,
  source/artifact freshness and reviewed package migration are implemented. Estimated
  context is labelled; no measured hard-cap guarantee is claimed for this host.
- Managed presets compose with upstream commands through the public CLI. Legacy
  native Bridge commands respect the managed owner. Hooks reconcile reversibly.
- Init installs exact-source selected dependencies, presets, the owned Scope alias
  and policy-aware CI. Consumer configuration is preserved; backups and runtime
  files are locally excluded from Git. Internal command symlinks survive rollback.
- Workflow self-upgrade wraps package replacement and the new integration installer
  in an outer rollback transaction. An installation lock records provenance and the
  tested baseline outside replaceable packages. Newer compatible dependencies remain.
- QA/manual freshness checks inputs, outputs, new sources and deleted files. CI
  resolves every changed feature plus explicit source-only mappings. Required feature
  artifacts and source inventories cannot be omitted from an agent receipt.
- Deterministic packaging bundles canonical presets/shared helpers. Release tooling
  requires successful main CI, reviewed versions, downloaded asset verification and
  matching source before catalog promotion. Public catalogs still name released versions.
- Root/extension documentation, operational guide, compatibility decisions and v1
  policy/checkpoint/receipt schemas are present. Archify diagrams remain included.
- PR instructions require every relevant visual inline and actual authenticated
  loading evidence. This contract is implemented; private PR rendering is unverified.

## Verified evidence

| Check | Result | Limits |
| --- | --- | --- |
| Scope suite | 110 passed | Local Python; includes progressed-feature revalidation and clarification freshness |
| Workflow suite | 72 passed | Local Python, including runtime/schema consistency, alias upgrades, setup ownership and real Git checkout cases; GitHub effects use fakes |
| Codex + SuperSpec | Passed | Clean public-CLI install, four selections, composition, doctor, reinstall |
| Claude + core | Passed | Same checks, including real CLI command symlinks |
| PR 4.0.2 to staged 4.1.0 | Passed | Published old archive, real upgrade, injected failure, exact rollback, retry |
| Workflow 1.0.0 to synthetic staged 1.0.1 | Passed | Outer transaction failure after integration install, rollback and retry; no 1.0.1 release |
| Archify diagrams | 9/9 showcase checks and four desktop sizes | Existing delivery/browser/review receipts; no private PR claim |
| Project Init, PowerShell and Bash | Both passed in CI against a fake board with custom columns | Real scripts; preserve all Scope statuses and managed hooks; no live board mutation |
| Remote CI at 6e8223d | All 13 jobs passed | [Verified implementation run](https://github.com/samykabu/sanduq/actions/runs/35372199271); live semantic acceptance remains separate |
| Manifest/catalog validation and CI YAML | Passed in that remote run | Release metadata remains unpublished |

Receipts: [Codex](workflow-evidence/codex-superspec-install.json),
[Claude](workflow-evidence/claude-core-install.json),
[upgrade/rollback](workflow-evidence/upgrade-rollback.json). These record progressive
local candidate checks; logs and package snapshots remain in their `dist/install-tests`
directories. See [compatibility](workflow-compatibility.md) for pinned upstream commits.

The first Claude attempt in this batch rejected Spec Kit's internal command symlinks.
Backup/restore was corrected, a regression test added, and a fresh installation passed.
The failed attempt is retained under `dist/install-tests/claude-065x6h8p`.

The first remote run passed all four installation combinations, the actual upgrade
job, both workflow regression platforms, Linux Scope, lint and dry-run checks.
Windows Scope exposed `RUNNER~1` versus `runneradmin` aliases in two test expectations.
The fixture now canonicalizes its temporary path, matching runtime behavior. The
failed run remains [available](https://github.com/samykabu/sanduq/actions/runs/35369374493).

## Required remaining work

1. Complete live semantic acceptance of the follow-up fixes. Existing-feature revalidation, explicit
   clarification refresh, legacy alias migration and setup hook ownership now have
   regression coverage. Real PowerShell Project Init passed locally against a fake
   board; both shells passed CI. Installation does not prove semantic agent
   dispatch. See the [17-scenario acceptance audit](workflow-acceptance-audit.md).
2. Pilot live GitHub answers, task links, interrupted resume and Finalize on an explicit
   authorized issue. A pilot issue URL has been requested; none is selected implicitly.
   Verify authenticated inline loading on a private PR, including an update to the PR.
3. Publish the reviewed coordinated versions only after the required acceptance and
   CI results, then verify clean release downloads before promoting catalogs. Pending
   metadata remains `implementation-in-progress`; no pending URL is claimed live.
4. Obtain the pending Bunyan QA/manual selection, back up its existing installation,
   adopt released Sanduq packages and verify existing feature/manual continuity.
   Remove obsolete canonical tooling only after parity and rollback checks. Complete
   a second project with different board names and the scoped ownership audit.

## Context checkpoint

Reliable host occupancy is unavailable. Use the approved estimated fallback and small
batches. This file is a durable progress checkpoint, not proof of a measured 60% cap.
Continue from [the resume prompt](workflow-resume-prompt.md), preserving all changes.
