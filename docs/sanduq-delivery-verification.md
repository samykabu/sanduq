# Sanduq Delivery verification record

Status: local implementation checks passed on 2026-09-24; remote PR and release
checks remain pending. This records local
evidence only; no live GitHub issue, Project automation, agent completion, PR
merge, or deployment is certified by these checks.

## Source checks

| Check | Result |
| --- | --- |
| Workflow unit suite, after final runtime and test edits | 174 tests passed |
| Decision parser, authority, conflict, edit and application evidence | 10 tests passed |
| Exact PR waiver authority, expiry and head SHA | 3 tests passed |
| CI policy, modes, rendering and branch-rule unit tests | 30 policy tests, 17 gate tests passed in focused runs; installer cases included in the 174-test suite |
| Isolated native Spec Kit 1.0.11 definition and mocked Claude/Codex dispatch | 3 tests passed; native scheduling no-go |
| Workflow package archive | `workflow.zip`, 65 files; SHA-256 `b514d4d9702870be0991c04a316a41bd5fc8db43b9d30d14aa227c1a420c7d61` |
| Adjacent packages | Scope 110 tests; User Manual 7 tests passed |
| Installation and upgrade smoke | Codex and Claude core installs passed with Spec Kit 1.0.11 CLI options; published 1.2.4 upgrade and injected rollback passed |

The mock CLI tests
demonstrate generated argv and native step behavior, not live model work.

## Disposable consumer paths

| Path | Observed result | Limit |
| --- | --- | --- |
| Greenfield, Spec Kit 1.0.11, Claude | `specify init --here`, local workflow 1.3.0 package install, QA/manual off, Advisory gate, dependency/preset install, basic doctor passed; gate job rendered | No Project board or live issue; `doctor --project` not claimed |
| Brownfield, existing `bugfix.py`, Codex | In-place `specify init --here --force` retained `bugfix.py`; workflow 1.3.0 package installed with Disabled gate; basic doctor passed; managed gate job absent | Disposable copy only; no custom user CI conflict exercised |
| Brownfield later process changes | `init --replace` then installer applied QA+manual on, basic doctor passed; later both off applied and retained history | Assure/User Manual Init interviews and real documents not run |
| Existing workflow 1.2.4 | Installed published 1.2.4 through trusted catalog, then previewed/applied local 1.3.0 upgrade; old no-`gate` policy still resolves to Required/all-PRs; basic doctor passed | No active feature checkpoint migration or custom Project data in this disposable copy |
| Public installer smoke | Codex and Claude core installation, four QA/manual combinations, composition, report state preservation and reinstall passed | No real semantic agent or GitHub issue run |
| Upgrade rollback smoke | Published PR extension 4.0.2 to 4.1.0, injected failure rollback, synthetic workflow self-upgrade and rollback passed | A synthetic workflow version tests outer rollback; not a published 1.3.1 release |

The isolated native workflow was accepted by `specify workflow add --dev` and
`specify workflow info` showed six command/guard steps. Its static guard failed
as intended when no feature was selected. The full native state/resume matrix
was not executed, so the production scheduler remains Sanduq's dispatcher.

## Still required before merge and release

- Check actual remote CI and branch rules on the PR. A local pass is not a
  remote check pass.
- Verify the release asset and promoted catalog after merge.
- Keep live issue/Project/agent acceptance separate from the local test result.
