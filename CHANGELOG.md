# Changelog

All notable changes to sanduq extensions/plugins are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/). Extensions are versioned
independently via `<extension>-vX.Y.Z` tags.

## 2026-11-06 — Workflow 2.3.4, Assure 2.8.0 (pending release)

- Assure Analyze builds QA from structured assertions (`qa/assertions.json`, readiness contract 2) and adds tasks only for missing proof. Earlier analyze states report `needs-reanalysis` until rerun.
- Workflow 2.3.4 selects Assure 2.8.0 and keeps the bound-Specify revalidation fix (an existing binding stays in `revalidate` mode). Source candidates only: not published.

## 2026-11-05 — Workflow 2.3.2, Assure 2.7.5, User Manual 2.0.4

- Fixes a consumer-reported blocker: one feature's committed workflow, evidence and progress records no
  longer count as QA or manual inputs of another feature, so two completed features stop invalidating
  each other. Requirements, tasks, contracts, product source and declared outputs are still checked.
- User Manual takes the dev-tools 2.0.5 builder fix: `build_manual.py --all` builds only the audiences
  configured in `manual.yml` (all three when none are configured).
- Workflow 2.3.2 selects Assure 2.7.5 and User Manual 2.0.4. Stage contracts and receipt schemas are
  unchanged; existing features need one migration and a freshness rebind, as
  [upgrades](docs/start/upgrades.md) describes.
- Tested with the affected unit suites, packaged install, upgrade and rollback smokes, and an upgrade of
  an isolated consumer project (doctor: no errors). Live runs on Claude Code and Codex used 2.3.1 with
  the builder fix applied; no new full live run was made for 2.3.2.

## 2026-11-05 — Workflow 2.3.1, Assure 2.7.4, User Manual 2.0.3

- The CI templates these packages render into a project pin Node 24 releases of the GitHub actions
  (`checkout` v7.0.1, `setup-python` v7.1.0, `upload-artifact` v7.0.2, `github-script` v9.0.0);
  GitHub deprecated the Node 20 runtime the earlier pins used. Self-hosted runners need Actions
  Runner 2.327.1 or newer. Sanduq's own workflows use the same pins.
- An upgrade replaces an unedited render of the previous templates and keeps an edited one. Workflow
  now also re-renders unedited User Manual workflows, which no step updated before.
- Source paths: `extensions/*/assets/github`, `extensions/workflow/scripts/install.py`,
  `extensions/assure/scripts/assure_init.py`, `vendor.lock.json` and focused tests. No live run was
  made for this patch train.

## 2026-11-05 — Marketplace: dev-tools 2.0.3, agent-tools 1.9.2

- Both plugin marketplaces now pin dev-tools 2.0.3 (was 1.5.0) and agent-tools 1.9.2, and carry the
  bundles' current descriptions. The User Manual extension already vendored dev-tools 2.0.3; plugin
  users now get the same version.
- **Plugin users of dev-tools:** 2.0 folded `user-manual-api-docs`, `user-manual-release-docs`,
  `user-manual-ui-screenshots` and `user-manual-preview-publishing` into the one `user-manual` skill,
  which loads that guidance when a task needs it. Call `/dev-tools:user-manual` instead. A 1.x
  `manual.yml` with MkDocs settings keeps building with MkDocs.
- agent-tools 1.9.2 changes only the plugin description; the vendored delegate-task and progress-report
  files are unchanged.

## 2026-11-04 — Workflow 2.3.0

- Adds a supported minimum profile tier, strengthens the existing package-content guard, and links canonical evidence across managed delivery records. Source paths: `extensions/workflow/scripts`, `assets/roles`, policy schema, managed references and focused tests.
- Pins released agent-tools 1.9.1 in the delegate vendor lock and both host marketplaces. The delegate redaction fix preserves structured token counters; Progress source bytes remain unchanged.
- Live runs on Claude Code and Codex reached open pull requests with passing workflow-evidence checks; the redacted run bundles are attached to the [2.3.0 release](https://github.com/samykabu/sanduq/releases/tag/workflow-v2.3.0).

## 2026-10-29 — Workflow 2.0.4, Assure 2.7.2, Memory 2.6.3, PR 4.7.5, Project 2.7.2, User Manual 1.8.5

- Hotfix from the native and external routing live runs, where most refused completions came from running `complete` on a natively done stage before recording it. A native-first claim now prints the exact `attest-native` command ahead of `complete`, and `DELEGATION_STAGE_NOT_VERIFIED` opens with it. `ACTIVE_STAGE_MUST_BE_RESOLVED` no longer suggests `pause`, which keeps the claim: complete the stage or release it with `workflow.py recover`.
- Every shared helper a package ships from outside its own folder (`extensions/scripts/shared/*.py`, plus Workflow's `sanduq_hash.py` and `sanduq_ci.py` in Assure and User Manual) starts with an `SPDX-License-Identifier: MIT` line, and a packaging test checks it alongside each package's LICENSE and notices. No behaviour change.
- Quantitative claims in recent CHANGELOG entries, the upgrade guide and Workflow's execution-assign reference name their source, a benchmark recorded between 2026-10-27 and 2026-10-29 or the unit test that counts fake-client calls, and unit, or say estimated; a test keeps percentage and ratio claims labelled. `benchmark_compare.py` takes several runs per arm and prints n, median and spread, and says whether a comparison is like-for-like or a process change; `benchmark_instructions.py` measures Workflow and Scope by default.
- Scope's fresh gate accepts a child kept whole whose revision carries the parent's approval, by following the recorded approval chain back to the live parent approval; a consumer run had stopped on SCOPE_RETAINED_PARENT_APPROVAL_MISMATCH. No migration or re-approval is needed. A carried approval from a former parent no longer passes once the issue loses its native parent: the gate refuses it with SCOPE_CARRIED_APPROVAL_WITHOUT_PARENT and asks for the issue to be approved as its own root.
- Vendors agent-tools 1.8.2: on Windows, killing the delegate-task supervisor now ends every harness descendant; results report `process_containment`.

## 2026-10-28 — Workflow 2.0.2

- Hotfix from a live routing measurement: a claim now pins its delegation routes. `start`, `record-native`, `adopt` and `attest-native` refuse with `DELEGATION_POLICY_CHANGED_IN_CLAIM` once `.specify/workflow.yml`'s `delegation` section changes mid-claim, Ready refuses a task attempt recorded under another policy, and `NATIVE_ROUTE_DISALLOWED` no longer suggests editing the policy. Task annotations show each task's `route_kind` and `route_reason`. Claims from before 2.0.2 are not checked.

## 2026-10-28 — Workflow 2.0.1

- Hotfix from a live routing run: `adopt` no longer adopts a task whose route is external, which had let an agent implement externally routed tasks in-session and record them as adopted. `--reason` records a labelled substitution that Ready warns on; every adopted attempt records `route_kind` and `route_reason`. Delegation off and native-first routes are unchanged.

## 2026-10-28 — Workflow 2.0.0, Scope 2.0.0 (retired), Assure 2.7.1, Memory 2.6.2, PR 4.7.4, User Manual 1.8.4

- **Breaking:** Scope is part of Workflow, and every `speckit.scope.<x>` command is now `speckit.workflow.scope-<x>` (Spec Kit requires an extension's commands to start with its id). The installer removes the old Scope package and keeps `.specify/scope/` state; `migrate` treats the old command name as the new one, so features in progress keep their receipts. Scope 2.0.0 is a no-code shim marked deprecated that prints the upgrade step. Presets workflow 1.4.0, scope-gate 1.7.0, scope-brainstorm 1.6.0.
- A claim previews every receipt it would remove and why, and `recover` restores them when the claim did no work (#109, #112, #114). `adopt` is an alias of `accept --no-attempt`. Internal clean-up with no behaviour change: explicit `memory_handoff` inputs, ledger-trust helpers in one module, no script loaded by path, review-history comments rewritten as rules with a lint check, round-named test modules renamed. The upgrade preview reports the blockers apply would hit, reuses an earlier `--preserve-ci` choice, and a rolled-back upgrade restores `.specify/integrations/`. A real consumer upgrade from 1.18.2 kept every receipt of its 12 features in progress. See the 2.0.0 table in `docs/start/upgrades.md`.
