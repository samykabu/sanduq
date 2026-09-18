# Workflow implementation progress

Updated 2026-09-18. Branch: `feat/reusable-workflow`. **Implementation remains in
progress. Nothing has been released, pushed, or installed into Bunyan.**

## Implemented locally

- Migrated the canonical Scope runtime, analyst and clarification skills, 95 baseline
  tests and two presets from Bunyan into Sanduq. Managed policy adds effort-band
  decisions, configurable board/artifact paths and answer rereading without a board move.
- Added workflow commands, a stage dispatcher, explicit QA/manual selections, provider
  resolution, context checkpoints, receipt invalidation, claim recovery and branch binding.
- Added a managed preset over actual core/SuperSpec commands. Tasks-to-Issues runs the
  core command with parent/feature-scoped native issue creation. Lost-response retry,
  legacy mapping adoption and close/reopen synchronization have local fake-API tests.
- Added reversible hook reconciliation. Managed Project 2.1 delegates task issue writes
  and preserves the Scope-bound parent; duplicate automatic chaining is disabled.
- Replaced Assure's indentation-sensitive hook rewrite with YAML parsing. QA/manual
  freshness now checks input and output contents, including deleted sources, and excludes
  workflow state. Legacy freshness state must be regenerated deliberately.
- Strengthened PR instructions to inventory and embed all relevant visuals, and verify
  authenticated image loading. This is an instruction contract, not a verified live PR.
- Added deterministic archives that bundle canonical presets and shared runtime helpers,
  pending version metadata, policy schema, CI gate scaffolding and documentation.

## Verified evidence

| Check | Result | Scope |
| --- | --- | --- |
| Scope regression suite | 98 passed | Local Python; includes managed policy and clarification reread |
| Workflow/adapters/freshness/reconcile suite | 34 passed | Local Python; GitHub API effects use fakes |
| Codex + installed SuperSpec 1.0.2 | Passed | Clean install, actual preset composition, all four selections, doctor, same-version reinstall |
| Claude + core Spec Kit | Passed | Same install checks; no SuperSpec selected |
| Manifest/catalog validation | Passed | Existing CI validator with explicit pending-release support |
| Project PowerShell parser | Passed | Syntax only |
| Project Bash + package Bash parser | Passed | Syntax only |
| Archify diagrams | Previously verified | Two showcase workflows, 9/9 quality, four browser sizes; evidence in assets/workflow-plan |

Install receipts: [Codex](workflow-evidence/codex-superspec-install.json),
[Claude](workflow-evidence/claude-core-install.json). Detailed logs remain under
`dist/install-tests/`. The tested Spec Kit build is 1.0.6.dev0 at
`f21acc4a25ce3aa53ff8653357b49b9aafcf8026`; this does not certify other builds.
An initial Claude smoke command rejected Codex's `--skills` option; the host-specific
fixture was corrected and a clean rerun passed. No failure is counted as a pass.

## Required remaining work

1. Finish project Init automation: exact-source dependency installation, preset installation,
   backups and failure rollback, Scope alias migration, board mapping discovery/configuration,
   selected process initialization and policy-aware CI adoption. Never select the unrelated
   community `scope` package by bare catalog name. Test real version upgrades and rollback;
   current install evidence covers only same-version reinstall.
2. Review runtime correctness under edits, failed stages, active claims and upgrades. Add
   meaningful CI gate tests. Ensure existing features are revalidated without destructive
   regeneration when migration invalidates receipts. Tighten required input manifests and
   configuration diagnostics; complete all policy/schema and host compatibility claims.
3. Complete Scope portability audit, including remaining legacy paths in agent references,
   actual configured board names in user-facing text and Archify acceptance evidence. Verify
   no new agent execution skips an explicit human-review marker.
4. Finish coordinated release pipeline: run required checks first, publish immutable assets,
   verify them, then update both public catalogs. The old release workflow still needs this
   change and must not publish these pending packages yet. Add release/package tests and
   update pending versions/changelogs coherently. Do not claim pending URLs are downloadable.
5. Pilot actual semantic command execution and live GitHub transitions, including a real
   private PR with authenticated inline-image loading. Installation tests do not prove these.
6. Obtain the pending Bunyan selection (QA/manual/neither/both), back up its installed state,
   adopt versioned Sanduq packages, preserve current issue/feature artifacts, remove obsolete
   canonical tooling only after comparison, and verify a second project with different board
   names. Complete the source ownership inventory and report remaining third-party provenance.

## Context checkpoint

Reliable host context occupancy is unavailable. This checkpoint uses the user-approved
estimated fallback and a bounded implementation batch; it does not claim a measured 60%
guarantee. Preserve all local work and continue the remaining integration/upgrade/release work
in a fresh session using [the resume prompt](workflow-resume-prompt.md).
