# Workflow pilot review: Review Home

Reviewed 2026-09-20. The pilot exercised the managed lifecycle on
[Bunyan issue #10](https://github.com/abushanab-net/Bunyan/issues/10) through
[PR #368](https://github.com/abushanab-net/Bunyan/pull/368). It demonstrated a usable
Scope-to-PR workflow, with operational defects now addressed in the reusable
source. It did **not** establish an enforced, fully green merge-to-live workflow.

## Verified delivery state

GitHub confirms the PR merged into `develop` at `2026-09-19T21:37:59Z`.
Final PR head: `6fd8d851f598eeec44d43a88b65d2469002d274a`.
Merge commit: `ad6c3d9b4f81b0b73973251888e54c18fa59aa66`.
Issue #10 is closed as completed. See the timestamped
[GitHub snapshot](evidence/review-home-merge.json).

The final head added a merge of `develop` after the earlier verified revision
`564399416a977fe88441d7938b2d8232f618393a`. That merge changed 12 files, including
CI configuration, verification adapters and tooling tests. The final-head
[workflow check](https://github.com/abushanab-net/Bunyan/actions/runs/35470990632)
failed with `STALE_RECEIPT: verify`. This is correct rejection of changed build/test
inputs, not evidence that the freshness gate should be relaxed.

The merge's [workflow run](https://github.com/abushanab-net/Bunyan/actions/runs/35471000822)
failed with `CHECKPOINT_MISSING_OR_WRONG_FEATURE`; its comparison covers legacy
feature directories outside the managed pilot. The canonical supplied workflow is
PR-only. A consumer push adaptation needs explicit feature selection and the right
comparison base; silently skipping unbound features would hide missing evidence.

API and web build runs succeeded. Manual previews and publication succeeded.
Bootstrap verification failed, including a quick-run image-policy rejection
(`Image policy rejected the input or repository configuration`, exit 78).
These are separate consumer CI findings. No successful live application rollout
or production acceptance was established by this review.

The effective `develop` rules returned deletion protection, non-fast-forward
protection and PR review requirements, but no required-status-check rule. The
classic status-check protection endpoint returned “Branch not protected.” Review
protection exists; enforcement of `workflow-evidence` was not configured in the
effective rules observed. No branch rules were modified by this review.

## What the pilot demonstrated

- A single approved feature retained Scope identity, clarification provenance,
  planning and stable task IDs through execution and finalization.
- Native task sub-issues, completion tracking and selected QA/manual workflows
  operated together. Generated evidence remained distinct from recorded human approvals.
- The implementation ledger records 1,168 .NET unit tests, 999 web unit tests,
  818 executed integration tests, and 81 browser tests passing. Six discovered
  integration cases were explicitly not run; they are not counted as passes.
- Two local load measurements met the agreed two-second target with 50 fresh
  sessions after the documented warmup. This is local evidence, not deployment capacity.
- Finalize produced reviewer documentation and authenticated inline visuals.
- The freshness gate caught source/build drift introduced after verification.

These implementation results are historical evidence from the pilot's verified
revision, not tests rerun against the later merge by this workflow review.

## Findings and reusable changes

| Finding | Change or disposition |
| --- | --- |
| Ignored evidence existed locally but was absent from the candidate commit | Added `ci_gate.py --check-index`, reporting missing and unstaged receipt dependencies without staging them. Finalize now requires clean-checkout verification too. |
| A small suffix allowlist caused Windows/Linux hash drift in build scripts and extensionless files | One packaged hashing implementation normalizes UTF-8 CRLF; SQL, `-text`, NUL-bearing/non-UTF-8 data and lone CR remain byte sensitive. Regression tests exercise an actual CRLF clone. |
| `STALE_RECEIPT` did not identify the changed inputs | The gate now reports changed paths, without file contents. Source drift remains blocking. |
| Post-commit graph generation invalidated QA/manual input manifests | Derived `graphify-out/` files no longer enter implicit documentation inputs. Explicit graph output fingerprints remain enforced. |
| Tracking evidence late changed source inventory and forced repeated readiness passes | Finalize prepares portable evidence before its last verification/review/readiness pass; recommends the existing feature evidence directory. No blanket artifact exclusion was added. |
| Routine SuperSpec approval text conflicted with the managed overlay | The execution overlay explicitly overrides routine phase approval pauses under `required-only`, while preserving real human/deployment decisions. |
| Diagram exporter paths could be interpreted relative to the PR extension | PR generation now names the full installed Illustrate exporter and reference paths. |
| A merged PR was easily confused with fully verified delivery | Added an exact-head, merge-check and rollout reporting protocol. Runtime receipts remain historical; no fabricated post-merge passed stage. |
| Failed evidence did not prevent merge | Governance follow-up: require `workflow-evidence` on the actual merge path and refresh evidence after target changes. Not changed silently. |

## Adoption and release boundary

Reusable changes are in Sanduq, not edits to Bunyan's installed distributions.
Workflow 1.0.0 and coordinated dependency versions remain pending releases.
Publishing archives and adopting them in consumers is separate from this source PR.

Hash and implicit-input semantics changed. Existing consumers must inspect active
claims, recover only after checking prior actions, install the reviewed package
through the public CLI, migrate and revalidate affected receipts. Run
`doctor --project`, `next`, context-policy checks and clean-checkout CI. Do not
rewrite historical fingerprints or count a migration as new test execution.

Before claiming general release acceptance, finish consumer merge-time evidence
refresh, configure required-check enforcement through the authorized governance
process, and separately resolve consumer bootstrap/rollout failures. Cross-host
installation, migration and rollback evidence supports the reusable build, but
does not substitute for those delivery controls.

## Validation

Local validation:

- Workflow regression suite: **80 tests passed** in 127.261 seconds, including
  claim/recovery, migration, context policy, CI gating and new portability cases.
- Focused freshness suite: **9 tests passed**, including an actual Git clone with
  `core.autocrlf=true`, byte-sensitive SQL/binary inputs and explicit graph outputs.
- Public Spec Kit Codex installation/reinstallation: passed for neither, QA only,
  manual only and both processes, with command composition and doctor checks.
- Published PR 4.0.2 to staged 4.1.0 upgrade: passed; injected failure restored all
  managed bytes; retry and retained custom configuration passed. Outer workflow
  upgrade/rollback used a synthetic 1.0.1 fixture and passed.
- Workflow, QA, manual and PR archives built successfully. Shared hashing is
  packaged into each state-checking extension. `git diff --check` passed.

The first local
regression run exposed a misplaced assertion in a new test, which was corrected;
that failed attempt is not counted as a pass. Installation fixtures and synthetic
upgrade versions are not claims of a published release or live GitHub acceptance.
