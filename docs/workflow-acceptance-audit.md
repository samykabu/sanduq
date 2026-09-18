# Workflow acceptance audit

Updated 2026-09-18. This maps the implementation plan's 17 scenarios to evidence.
Automated fixtures validate contracts and recovery; they do not prove that an agent
performed a complete live feature lifecycle. No release or Bunyan adoption is claimed.

| # | Scenario | Evidence available | Remaining acceptance |
| --- | --- | --- | --- |
| 1 | Four selections, core/SuperSpec | Runtime combinations and public-CLI host installation matrix; installed but unselected processes stay disabled | Live semantic dispatch for selected processes |
| 2 | Dependency availability and upgrades | Doctor, version/provenance checks, migration tests; published PR package upgrade and staged workflow rollback | Released workflow upgrade after first release |
| 3 | Pending/resolved/conflicting/reopened answers | Scope clarification tests, unresolved-answer gates, explicit refresh and progressed-feature revalidation | Live GitHub answer round trip |
| 4 | Enrichment, freshness, no hook recursion | Ordered stages, task freshness, hook ownership and reconciliation tests | Agent executes selected analyzers before publication |
| 5 | One executor across core/SuperSpec/Bridge | Provider selection, active Bridge guard, native presets and recognized short-alias migration | Live executor invocation |
| 6 | Context boundaries and output | Estimated/measured contracts, reserve, stale telemetry and checkpoint tests | Host enforcement and huge-output/independent-agent experiments; no hard-cap claim |
| 7 | Interruptions and remote recovery | Claims/resume tests, lost task-creation response recovery, transactional rollback | Live interruption across phases and fresh-session resume |
| 8 | Documentation evidence quality | Required outcome schemas, freshness gates and selected-process checks | No-change, missing screenshot, failed test and human-review live examples |
| 9 | PR feature resolution | Source-only and multi-feature tests, binding, new/deleted source and normalization | Shallow/merge checkout acceptance |
| 10 | Init/reconcile/rollback | Repeated public-CLI install, unrelated-hook preservation, malformed input tests, real staged upgrade rollback; PowerShell Project Init fixture | Bash Project Init CI and live board initialization |
| 11 | Explicit Finalize and PR update | Runtime refuses automatic PR stage; existing draft PR updated during delivery | Workflow-driven repeat Finalize on the authorized pilot |
| 12 | Release consistency | Deterministic archives, readiness/receipt/catalog tests and guarded main release workflow | Reviewed release, actual coordinated asset download and catalog promotion |
| 13 | Inclusive effort preference | 17/20/23 and 16/24, unit/policy and Scope tests | Pilot confirms no redundant decomposition prompt |
| 14 | Automatic stage selection | Provider-per-stage and ordered runtime checks; installed preset composition | Agent-level Specify-to-Clarify-to-Plan-to-Tasks-to-executor run |
| 15 | Re-read GitHub answers | Scope tests cover comment handling and refresh; advanced open features can revalidate under matching claims | Live edited/conflicting replies and no duplicate comments |
| 16 | Mandatory task sub-issues | Parent/feature/task identity, native mapping, lost-response recovery, adoption and state-sync tests | Actual native parent links before execution |
| 17 | Inline PR visuals | Canonical PR instructions, generated skill parity, both public PR diagrams loaded in authenticated browser | Created and updated private PR images must actually load |

The next live pilot needs an explicit issue URL and project QA/manual selections.
Neither editor tabs nor elapsed time select a feature or enable an optional process.
Private assets must stay private; public Sanduq rendering is not private-repo evidence.

See [progress and receipts](workflow-implementation-progress.md),
[compatibility boundaries](workflow-compatibility.md) and
[the implementation plan](workflow-extension-implementation-plan.md).
