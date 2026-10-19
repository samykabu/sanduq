# Round 3: final plan (Claude and Codex, reconciled)

Inputs: `round-3-draft-plan.md` (Claude Opus 5.5), the independent review by Codex gpt-6.1-sol
(`round-3-codex-review.md`, which verified the defects against the code), `round-3-naming.md` and the six
`round-3-review-*.md`. Where we disagreed, the resolution is stated.

## 1. Naming

Decided by the user from three presets on the report page. Default recommendation (both reviewers):

- **Display names now, ids unchanged:** Sanduq Workflow, Sanduq Issue Scope, Sanduq Assure, Sanduq User
  Manual, Sanduq Pull Requests, Sanduq GitHub Project Sync, Sanduq Illustrate, Sanduq Memory and Archive,
  Sanduq Progress Report; presets Sanduq Managed Workflow, Sanduq Scope Gate, Sanduq GitHub Brainstorm.
  Workflow's description says positively what it is (issue-to-PR orchestration).
- **One id rename, `scope` to `issue-scope`, as its own release** after the expanded migration tests pass
  (Codex's position, accepted: the optimization release must not depend on the rename).
- Full id renaming (workflow, memory, project) dropped: no Spec Kit id aliases, high risk, low gain.

Migration design for `issue-scope` (and any other id the user picks), revised per Codex:

1. Recognise the old id at every entry: `upgrade.py`, `install.py`, `doctor`, and a short
   `docs/start/upgrades.md` route for consumers who use `specify extension update` directly (Spec Kit
   refuses an id change; `replaced_by` in the catalog is ignored, so the documented route is the
   migration for standalone users).
2. Before removal, inventory the old package folder: config (`*-config.yml`, `*-config.local.yml`),
   JSON config, state directories, and files the consumer added or edited; carry them across or refuse
   with a list. Spec Kit's `remove --keep-config` preserves only top-level `*-config.yml` and
   `*-config.local.yml`; a plain `remove` only backs those files up. Everything else is deleted.
3. Remove known obsolete host outputs **before** rendering the new id, so the old command names that
   come back as Spec Kit aliases are not deleted afterwards; reconcile against the expected output set.
4. Keep old command names as aliases for an explicit support window (two minor releases or until
   1.0 of the new id, whichever is later), and read historical command names in receipts without
   rewriting evidence.
5. Record `renamed_from` in `install-lock.json`; keep consumer-owned policy keys and state paths.
   Retained aliases keep the old command namespace (and its catalog-description cost and collisions)
   until the support window ends; the id rename alone does not remove them.
6. Tests: both ids installed at once, locally edited skills, custom hook flags, both host defaults, a
   failure after removal (rollback restores the old id), skipping intermediate releases, idempotent
   re-run; against the Spec Kit commit CI pins (8147943), not the local checkout.

## 2. Fix first

1. **Assure gate (AU5).** A parsed value is authoritative; the text fallback runs only when parsing fails,
   ignores comments, and a malformed config has one tested outcome (fail closed with a clear message).
2. **QA audit (AU2).** Placeholder exclusions as in the user-manual audit; decoded and root-relative links.
3. **PR publication (PM3, PM1).** `pr_publish.py` stops treating a failed PR lookup as "no PR", rejects
   malformed markers, and resolves images to verified remote URLs before the body is linted; the guard
   also covers inline `--body`. Explicit verification failures stay.
4. **Project sync (PM4).** Remote parsing through the same normalisation Workflow uses (dots, ports,
   case), the repository scope checks, and timeouts.
5. **Stable scan output (from AU5).** `assure_scan.py` rewrites the project-memory block only when the
   inventory changes, so a rerun on another day cannot stale the manual's freshness.
6. **Diagram procedure and templates together (AU1 with IP2 and IP3).** Diagram stages follow
   Illustrate's procedure (theme and checks), and the shipped templates and examples pass the checks the
   procedure requires (technical-color gets its own check profile). Upstream illustration-tools release.
7. **Illustrate hook (IP5).** Registered only when `illustrate.hooks.self_check` is true, through an
   install and uninstall interface on the Illustrate side that Workflow calls (standalone users keep a
   path); handles Codex `apply_patch` payloads with several or moved files; removal leaves no command
   pointing at a deleted script; existing dispatcher entries are cleaned up on upgrade. The migration
   reconciles both `.codex/config.toml` and `.codex/hooks.json` and the Claude settings, preserves
   unrelated hooks, makes Codex approval and policy activation a visible upgrade step, and has rollback
   tests that cover a failure mid-migration. This is the highest-risk item of the release.
8. **Visibility and small breakages.** W5 Codex guard-approval check in `doctor` and `status`; error
   messages name the commands that exist (SC7); broken export paths are fixed; the user-manual test copy that lacks `--all` coverage is
   vendored from upstream instead of hand-copied (AU6, a sanduq vendoring change).

## 3. Do

1. **Measurement first.** Fix the benchmark scenarios the reviews found wrong (Illustrate import counts
   alternative references; conditional references), and test install and event wiring against the Spec
   Kit commit CI pins (8147943), including the `specify_cli.events` API the hook review assumed. Savings
   from different options are never added together; each is remeasured.
2. **W1** one git and fingerprint pass per command, with operation-scoped caches and invalidation tests.
3. **CI selection** (X3 without dropping project coverage, smoke jobs gated on `changes`, Windows memory
   on the same event rule), then **remeasure**, then shard the Windows workflow suite (X4) and cache (X5;
   fresh runners still install Chromium's OS dependencies, a browser cache alone is not enough).
   IP7 (no duplicated upstream Illustrate tests in sanduq CI), IP10 (browser tests out of the default
   Progress run), X6 (vendored verifiers on vendor bumps and nightly).
4. **Instruction load:** W2/W3 Execute carries only the protocol that applies; AU3 skip unchanged reruns;
   SC1 scope path trim; SC4 lighter gate with snapshot reuse; IP1 icon lookup script; IP4 export reads its
   reference only on failure; AU7 host-neutral names and lighter init; descriptions for workflow (5 of 13
   failing) and scope (6 of 7 failing) and the whole catalog under 8,000 characters including aliases.
   Worker prohibitions stay in the text regardless of the guard hook: Codex may not have approved it.
5. **Small deterministic helpers:** W4 receipt skeleton, SC5 plan waves, SC6 checkbox answers and Q/A log,
   SC9 analysis skeleton.
6. **SC3** fewer GitHub calls in publish, bind and clarification, behind dependency-completeness tests and
   a fallback.
7. **Packaging:** one exclusion list (X8, IP6, IP8; drop Progress docs and the unrunnable `live_ab.py`,
   delegate-task images), presets re-added only when changed, W7 runtime-only delegate-task install.
   Required assets stay.
8. **Release tooling:** X1 `release.py bump` writes every version copy and `promote` clears pending
   markers; X2 factual `check_docs` rules (pins, changelog headings, pending markers, extension counts);
   display names applied.
9. **AU4** one freshness CLI for both state scripts (cheap deduplication only). **PM7** drop memory's
   duplicate preflight step; **PM8** shorter memory descriptions.
10. **Investigate PM6** (memory hooks against Workflow's handoff) with one managed run; change ownership
    only if duplication is shown.

## 4. Defer

`scope` to `issue-scope` release (until the migration tests above pass; ships next), W9 split of
`workflow.py`, SC8 transport extraction, X9 shared I/O module, PM5 Python init rewrite (first pass the
existing non-interactive flags, stop forcing interactive auth, and report missing choices actionably), SC2 preset consolidation, PM2 reply and
resolve automation, X7 backup pruning (until recovery requirements for the rename are settled), PM9
fixture speed-ups pending measurement.

## 5. Drop

Full id renaming; leaving project changes without regression coverage; a documentation size cap; quoting
savings as guaranteed (all ranges are estimates until remeasured); the claim that Scope has no standalone
consumers.

## 6. Ownership

One owner per shared surface: **installer** (IP5 Workflow side, IP9, presets no-op, W7, migration),
**packaging** (X8, IP6, IP8, vendored-test mapping), **CI** (X3-X6, IP7, IP10, PM9 CI part, project-init
flags in CI), **upstream illustration-tools** (IP1, IP2, IP3, IP4 part), **upstream agent-tools and
dev-tools** (IP10 upstream part). Each extension stream edits its own manifest and descriptions; the
release stream integrates generated docs and release metadata at the end.

## 7. Disagreements resolved

Codex's final pass (`round-3-codex-final.md`) agreed with the direction; its ten amendments are applied above.


- Codex would ship display names and fixes without the rename; Claude proposed one release. Resolved:
  display names and fixes now; the rename next, with the migration tests as its gate.
- Codex deferred backup pruning; Claude had it in "do". Resolved: deferred (rollback for the rename may
  need the backups).
- Claude had PM5 as a rewrite; Codex showed both init scripts already accept non-interactive flags.
  Resolved: pass the flags now, defer the rewrite.
