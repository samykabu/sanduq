Continue the active goal "implement the plan" in D:\Projects\Personal\sanduq on
feat/reusable-workflow. Read workflow-implementation-progress.md, workflow-guide.md
and workflow-extension-implementation-plan.md under docs. Preserve existing changes,
the canonical PR image contract and Archify artifacts. Do not mark the goal complete
based only on local tests or installation smoke checks.

Draft PR: https://github.com/samykabu/sanduq/pull/3. The branch is pushed. Both inline
public diagrams loaded in the authenticated browser; private rendering is still pending.
First CI run 35369374493 passed 10/11 jobs and exposed Windows TEMP path aliases in
two Scope test expectations. Fixture canonicalization was corrected and run
35369636370 at 5aa6a76 passed all 11 jobs. Follow-up implementation 6e8223d passed
all 13 jobs in run 35372199271, including both Project Init scripts. Later documentation
commits do not change that tested implementation; inspect PR checks for latest head.

The runtime, reusable presets, selected dependency installer, workflow self-updater,
rollback, task issue adapter, freshness gates and release sequencing are implemented
locally. Current evidence: 110 Scope tests; 72 workflow tests including schema
validation; real Codex+SuperSpec and Claude+core public-CLI installs; published PR
4.0.2 to staged 4.1.0 upgrade; synthetic staged workflow 1.0.0 to 1.0.1 self-upgrade.
Both upgrade paths recovered injected failures and succeeded on retry. See committed
receipts for exact scope; do not imply synthetic 1.0.1 was released.

Follow-up fixes cover explicit clarification refresh, revalidation of progressed
features, owned legacy alias upgrades and preservation of managed setup hooks.
Real PowerShell and Bash Project Init passed with fake custom board names in CI.
Read workflow-acceptance-audit.md for all 17 scenarios and remaining
semantic/live gaps. Run remote CI before release. CI covers Windows/Linux regressions, Codex/Claude x core/SuperSpec
registration and actual upgrade rollback. Main release tooling refuses publication
while pending status is implementation-in-progress. Public catalogs remain unchanged.

No Bunyan feature was selected from its editor tabs. Two unanswered setup items
remain: Bunyan's independent QA/manual selections, and an explicit issue URL for
the live pilot. Do not re-ask if answers have arrived; do not treat preselected
options or elapsed time as answers. The live pilot must cover real GitHub answers,
native task links, resume and private PR inline image loading. Released-package
Bunyan adoption and a second project with different board names remain pending.

Owner correction 2026-09-19: continue automatically without reliable context telemetry.
Do not stop on estimates, stale readings or inability to estimate. Only reliable measured
usage can trigger the default limit; explicit strict mode remains opt-in.
Keep canonical source in Sanduq and consumer policy/evidence in the consumer repo.

Follow-up acceptance closed a Git comparison gap: CI feature detection now uses the
common ancestor, matching QA/manual freshness. Nine targeted CI-gate tests passed,
including diverged target/head, detached merge and depth-1 clone failure/recovery.
Consult PR checks for the follow-up commit's full cross-platform result.
