# Lean execution: first delivery package

**Implemented and locally accepted on 12 October 2026.** The independent final review found three material defects; one repair batch closed them and the focused recheck passed. The corrected packages passed 123 targeted tests and an isolated Bunyan upgrade. Main Bunyan is unchanged. Publication and main-workspace adoption remain separate delivery steps.

This implements the approved first package: **P01-P06, P08 and P12**. P07, P09-P11, P13 and optional P14 remain deferred. The changes preserve model allowlists, local functional acceptance, lightweight self-hosted PR checks, Project buckets and disabled deployment. They do not restore mandatory TDD.

## What changed

| Proposal | Delivered behavior | Main source |
|---|---|---|
| P01 | One lifecycle coordinator; mechanical stages stay with it. Nested orchestration and launches without concrete deliverables are rejected. Claims and receipts remain required. | `workflow.py`, `lean_policy.py` |
| P02 | Coding review waits for all coding/testing tasks. Ready and CI still require every required task, including documentation and review. | `workflow.py`, stage references |
| P03 | Opt-in aggregate preflight checks declared source/fixture identities, command arguments, encoding/newlines and runtime/browser status. Scope selects valid initial or revalidation command syntax. | `execution_tools.py`, Scope command references |
| P04 | Bounded worker briefs retain ownership, acceptance, policy/source fingerprints and pointers to detail. | `worker_brief.py` |
| P05 | One planned corrective continuation; repeated failures require a concrete diagnosis. Comparable history informs bounded timeouts and a finalization reserve. | `delegation.py`, `delegate_dispatch.py`, `lean_policy.py` |
| P06 | Selected checks bind command, sources, fixtures, declared environment, executable identity and evidence. Only unchanged passing checks can be reused. The selected executable path remains the invocation path. | `verification_plan.py` |
| P08 | Scope regression coverage retains status/checkbox/REST/idempotency behavior. PR lint verifies the bound closing issue and prerequisites; the receipt recomputes body identity and lint. | `execution_tools.py`, `workflow.py`, PR instructions |
| P12 | Progress collects normalized runs from explicit worktrees, deduplicates run IDs and reports elapsed time, last event and next action. Harness success and task acceptance remain separate. | `execution_tools.py`, native status integration |

Source paths above are under `extensions/workflow/scripts` unless otherwise indicated. This is an opt-in Workflow refactor, not a replacement lifecycle. No portable driver was modified; its canonical source remains `samykabu/sanduq-skills`.

## Completed tasks

- [x] Implement the two coherent author batches.
- [x] Integrate native preflight, claim, verification and PR receipt paths.
- [x] Run targeted tests, documentation checks, vendor identity checks and package builds.
- [x] Complete the independent review after coding and testing.
- [x] Repair the three material findings and rerun affected checks.
- [x] Rebuild and upgrade the isolated Bunyan consumer; verify protected files.
- [x] Complete the focused reviewer continuation and retain evidence.

## Verification and review

The coordinator reran **123 tests, all passing**: lean policy 20; native integration 17; verification plans 11; execution tools 28; worker briefs 29; existing delegation launch 11 and claim 7. This run had no skips. The executable symlink regression ran on this Windows host; it does not establish Linux acceptance.

Documentation validation passed for 68 guides, 42 commands, seven vendored skills and 13 skill sources. Vendor bytes match the lock. `git diff --check` and the three package builds passed. Earlier author evidence also includes 38 Scope REST tests and 20 task-issue tests; these are carried-forward author results, outside the coordinator's 123-test count.

The final review raised three findings: Ready/CI had inherited the coding-only filter; executable resolution changed invocation semantics; claim propagation could choose another feature. Each was corrected with regression coverage. The reviewer then verified all 35 frozen source hashes and three archive hashes and returned **PASS**. Review inspected recorded execution evidence; it did not rerun tests.

Two broad legacy Workflow/delegation suite runs timed out after 180 seconds and remain unverified. They are not counted as passes. No product code, application acceptance, E2E, release suite or deployment was run for this tooling-only change.

## Packages and consumer acceptance

| Package | Version | SHA-256 |
|---|---|---|
| workflow | 1.10.0 | `a42d3ac4ba7adc3cdacc636f74979a59938150dd55857c1b0d48572e795baf59` |
| scope | 1.6.2 | `b97e4fd4eafc050644fe34737e2f056fbd9d346e68b1f216b430e2f1f6fd1e71` |
| pr | 4.2.3 | `7b1b237aac6e75522952f8bfbbb8ed316c726770a087de15306e36c010bc2d8f` |

The supported upgrade installed these packages in `D:/Projects/abushanab-net/Bunyan/.claude/worktrees/lean-workflow-pilot`, branch `chore/workflow-lean-pilot`, using `--preserve-ci`. Workflow doctor passes with lean mode enabled. The installed progress CLI reconciles all 121 historical normalized runs. Five protected policy/CI file hashes match their baseline; all seven snapshot hashes in the original main checkout remain unchanged.

The pilot explicitly enables lean execution with a 300-second minimum timeout, 7200-second maximum and 120-second finalization reserve. `.specify/lean-preflight.json` paths resolve relative to the manifest directory. Feature verification plans must still declare actual inputs and commands before evidence reuse. This pilot does not manufacture future product acceptance.

The pilot includes copied pre-existing installed toolchain state from the main workspace, so its whole Git diff must not be staged as this change. Illustrate, Memory and portable-driver differences against its base are not all attributable to this package. The source worktree is the bounded, reviewable implementation.

## Delegation and cost evidence

Seven actual invocations: two authors, one continuation for each, one repair worker, and one reviewer with one focused continuation. Six finished successfully; one author continuation timed out. No worker was launched solely to write a status report. There were no nested agents. Coding/testing completed before both review runs.

| Run | Purpose | Requested model | Outcome | Elapsed |
|---|---|---|---|---|
| `codex-20261012162952-1e7e06` | A: lifecycle and verification | gpt-6.1-sol | successful | 22.86 min |
| `claude-20261012162953-7d61a5` | B: preflight, context and progress | claude-sonnet-5-5 | successful | 4.98 min |
| `claude-20261012163728-0b3685` | B-C1: native Scope/PR/progress completion | claude-sonnet-5-5 | successful | 4.83 min |
| `codex-20261012165455-bf4c76` | A-C1: native integration | gpt-6.1-sol | abandoned | 12.21 min |
| `codex-20261012171236-1b7c2e` | R: independent final review | gpt-6-astra | successful | 3.29 min |
| `claude-20261012171914-f5fd12` | F: three-finding repair | claude-sonnet-5-5 | successful | 2.98 min |
| `codex-20261012173153-0ba48e` | R-C1: focused closure review | gpt-6-astra | successful | 1.58 min |

Claude reported Sonnet5.5 for all three of its invocations. Codex did not report actual serving-model identity; requested models are shown above without treating them as confirmed actual models. The timed-out continuation has no terminal usage record. Its zero placeholders are excluded. Exact reported usage and available cost estimates are retained separately by harness in the [evidence file](lean-execution-evidence.json); cross-harness token totals are not added together.

This batch still incurred author integration continuations and one timeout. The changes provide controls and measurable evidence for the next feature; they do not demonstrate a percentage reduction in implementation time or tokens yet. Timeout/finalization guidance uses the existing watchdog. A new mid-run signal in the portable driver is not implemented.

## Handoff

Source: `D:/Projects/Personal/sanduq-lean-execution`, branch `fix/workflow-lean-execution`, based on `35959c5`. It includes the retained PR77 prerequisites, verified open and unmerged through GitHub REST during this task. Do not drop that dependency when preparing publication. Workflow/Scope/PR release entries remain `pending-review`; the public catalog was not changed.

There are no remaining implementation blockers within the approved package. No PR, remote release, merge or deployment was created by this work. Main-workspace adoption should use the supported package upgrade after its existing changes are reconciled, preserving CI and the approved Memory/Project/constitution files. Do not copy the pilot's entire dirty tree.

To verify the retained pilot:

```powershell
Set-Location D:/Projects/abushanab-net/Bunyan/.claude/worktrees/lean-workflow-pilot
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

The next product feature must enter through Sanduq Workflow with its actual issue and declared verification plan. Deferred proposal IDs remain in the original Bunyan retrospective decision report; they are not silently included in this delivery.

[Machine-readable evidence](lean-execution-evidence.json) contains the selected test outputs, protected-file checks, package and source hashes, review outcomes and seven-run ledger. Raw prompts and harness logs remain ignored in `.delegate/`.

## Changes after this evidence

The hashes and pilot results above describe the packages built before the 2026-10-15 merge review. That review rebased the work onto Workflow 1.9.5 and changed it: claim credentials reach workers only when lean mode is on, artifact-analysis routing and claim environment output are lean-gated, Scope became 1.6.2 requiring Workflow 1.10.0, and PR 4.2.3 runs the lint step only when `execution_tools.py` exists. The release packages will differ from the recorded hashes. Their own release checks replace this evidence.
