Continue the active goal "implement the plan" in D:\Projects\Personal\sanduq on
feat/reusable-workflow. Read workflow-implementation-progress.md, workflow-guide.md
and workflow-extension-implementation-plan.md under docs. Preserve existing changes,
the canonical PR image contract and Archify artifacts. Do not mark the goal complete
based only on local tests or installation smoke checks.

The runtime, reusable presets, selected dependency installer, workflow self-updater,
rollback, task issue adapter, freshness gates and release sequencing are implemented
locally. Current evidence: 103 Scope tests; 62 workflow tests including schema
validation; real Codex+SuperSpec and Claude+core public-CLI installs; published PR
4.0.2 to staged 4.1.0 upgrade; synthetic staged workflow 1.0.0 to 1.0.1 self-upgrade.
Both upgrade paths recovered injected failures and succeeded on retry. See committed
receipts for exact scope; do not imply synthetic 1.0.1 was released.

Next review semantic dispatch, board initialization, revalidation of progressed
features, legacy aliases and all 17 acceptance scenarios. Run remote CI before
release. New CI jobs cover Windows/Linux regressions, Codex/Claude x core/SuperSpec
registration and actual upgrade rollback. Main release tooling refuses publication
while pending status is implementation-in-progress. Public catalogs remain unchanged.

No Bunyan feature was selected from its editor tabs. Two unanswered setup items
remain: Bunyan's independent QA/manual selections, and an explicit issue URL for
the live pilot. Do not re-ask if answers have arrived; do not treat preselected
options or elapsed time as answers. The live pilot must cover real GitHub answers,
native task links, resume and private PR inline image loading. Released-package
Bunyan adoption and a second project with different board names remain pending.

Use labelled estimated context monitoring and bounded work. Produce a handoff before
the context target; never claim reliable host telemetry or a measured hard guarantee.
Keep canonical source in Sanduq and consumer policy/evidence in the consumer repo.
