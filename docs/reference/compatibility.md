# Compatibility

This page shows what Sanduq supports and what has been tested. A cell says **Tested** only when
recorded evidence exists, and it names that evidence. **Untested** means the combination is
supported but nobody has recorded a test. **Unsupported** means it does not work.

There are two kinds of evidence. **CI** is an automated job in [CI](../../.github/workflows/ci.yml)
that installs or upgrades the packages and runs their test suites. A **live run** is a recorded
managed run of a real issue by an agent host, from scope to an open pull request. A clean install is
not a live run.

Workflow 1.19.2 hotfix: focused reconciler, rollback and packaged CLI checks passed with Spec Kit 1.1.3, plus an existing Windows consumer upgrade and project doctor. No new full managed live run was recorded for either host for this patch; the older live runs below retain their stated versions.
Workflow 2.0.0 train (PH-06): every suite passed on Windows with Spec Kit 1.1.3 on the merged tree, and a real consumer project upgraded from Workflow 1.18.2 with Spec Kit 1.1.3 kept every receipt of its 12 features in progress (`doctor --project` passed). No new managed live run was recorded for this train.

Workflow 1.21.0 train (PH-03): every suite passed on Windows with Spec Kit 1.1.3 on the merged tree (workflow 1391, scope 287, memory 207, shared scripts 209, project, pr, assure, user-manual, progress). No new managed live run was recorded for this train.

Workflow 1.20.0 and Scope 1.11.1 (PH-02): every suite passed on Windows with Spec Kit 1.1.3 (scripts, assure, pr, project, user-manual, progress, memory and the full workflow suite, including the new end-to-end lifecycle test). No new managed live run was recorded for this train; the older live runs below retain their stated versions.

## Hosts

| Product | Codex | Claude Code | Claude Desktop | Live run (date, versions, host) |
| --- | --- | --- | --- | --- |
| Workflow, with the dependencies its installer adds | Install tested in CI (Ubuntu, core and SuperSpec). End to end: **Tested** (one live run, [PH-04](../evidence/ph04-live-run-codex.md)) | Install tested in CI (Ubuntu, core and SuperSpec). End to end: **Tested** (live runs) | Unsupported | Round 4, 2026-10-21: the round-4 builds released as Workflow 1.17.0, Spec Kit 1.0.11, Claude Code 2.1.306. Round 5, 2026-10-21: Workflow 1.17.1, Scope 1.10.1, Spec Kit 1.1.4.dev0, Claude Code 2.1.306. [PH-04](../evidence/ph04-live-run-claude.md), 2026-10-28: Workflow 1.21.0, Scope 1.12.0, Spec Kit 1.1.3, Claude Code 2.1.312 and [Codex CLI 0.163.0](../evidence/ph04-live-run-codex.md), QA and User Manual on, advisory gate, standard tier, PR opened on each host; host switch and Bridge route exercised. The CI gate did not run (its workflow file did not load, fixed in Workflow 1.22.1); the gate passed locally |
| Scope | Through Workflow only. **Tested** (PH-04 live run) | Through Workflow only. **Tested** (live runs) | Unsupported | Rounds 4 and 5, and PH-04 (Claude Code and Codex), as Workflow |
| Memory | Untested | **Tested** through Workflow (live run) | Unsupported | Round 4 run 4 (the build released as Memory 2.5.0) and round 5 (Memory 2.5.0), 2026-10-21, Claude Code 2.1.306 |
| Progress | Untested | **Tested** through Workflow (live run, native hooks) | Unsupported | Round 5, 2026-10-21: Progress 1.5.0, Claude Code 2.1.306 |
| Project | Untested | **Tested** through Workflow (live run) | Unsupported | Round 4 (the build released as Project 2.5.0) and round 5 (Project 2.5.1), 2026-10-21, Claude Code 2.1.306 |
| PR | Untested | **Tested** through Workflow (live run, pull request opened) | Unsupported | Round 5, 2026-10-21: PR 4.5.1, Claude Code 2.1.306 |
| Assure, Illustrate, User Manual | **Tested** through Workflow (PH-04 live run) | **Tested** through Workflow (PH-04 live run) | Unsupported | PH-04, 2026-10-28: Assure 2.6.2 and User Manual 1.8.2 ran QA Analyze, QA Document, Manual Analyze and Manual Update on both hosts |
| Any extension installed alone, without Workflow | Untested | Untested | Unsupported | None |
| Portable skills (from sanduq-skills) | Untested | Untested | Untested | None |

Evidence records, in this repository: [round 4](../evidence/round-4-live-run.md),
[round 5](../evidence/round-5-live-run.md) and PH-04 on [Claude Code](../evidence/ph04-live-run-claude.md) and
[Codex](../evidence/ph04-live-run-codex.md), with its [findings](../evidence/ph04-live-run-findings.md). All ran
in a private sandbox repository on the maintainer's Windows machine. The PH-04 redacted bundles are assets of the
[Workflow 1.21.0 release](https://github.com/samykabu/sanduq/releases/tag/workflow-v1.21.0). Codex has one
end-to-end live run (PH-04); Memory and Progress on Codex are untested.

opencode is deferred. Copilot is outside the supported hosts. Delegate Task can start Codex, Claude
Code, opencode, Copilot and Pi as [harnesses](glossary.md#harness); that is not host support.

## Platforms

| Platform | CI | Live run | Status |
| --- | --- | --- | --- |
| Windows | Regression suites, Memory installation and Project init on `windows-latest` | Rounds 4 and 5 (Claude Code); PH-04 (Claude Code and Codex) | **Tested** |
| Linux | Every CI job on the home-office runner, including installation and upgrade | None | **Tested** (CI only) |
| macOS | None | None | **Untested** |

The maintainer works on Windows, macOS and Linux. macOS has no CI leg and no live run, so treat it as
untested until one exists.

## In use, without a live-run record

These capabilities are in use by the maintainer, and have unit tests, but no live run has exercised
them. Report what you see if you use them.

| Capability | Where it is described |
| --- | --- |
| CI rule waivers (posted in the PH-04 run but refused: a waiver cannot be verified when the owner and the agent share one GitHub account) | [Delivery policy](../workflow/delivery-policy.md) |
| SuperSpec as task generator and executor | [Prerequisites](../start/prerequisites.md#superspec) (installation is tested in CI) |

## Tested versions

| Component | Tested | Where |
| --- | --- | --- |
| Spec Kit | 1.1.3, commit `0282d03eb6fc3091b3deaa3a855d4030dc40cd6c` | CI installation, upgrade and Memory jobs |
| SuperSpec | 1.0.2, commit `c20ac6c1ba069cc9a72dacb8044b7b193d3dde81` | CI installation job |
| Python | 3.11, 3.13 | Every package declares 3.11 or later. CI runs the Linux regression suites on 3.11 and the Windows suites, lint and installation smokes on 3.13 |
| Playwright | 1.63.0 with Chromium | CI Illustrate suite |
| `npx skills` | 1.7.2 | CI listing and named-install check |
| Superpowers Bridge, Superpowers | Untested | |

The live runs used other Spec Kit versions (1.0.11 in round 4, 1.1.4.dev0 in round 5); the table
above is what CI pins. The regression suites for Workflow, Scope, User Manual, Memory and Illustrate
run on Ubuntu and Windows. Manifest ranges allow other versions; those are not tested combinations.

## Spec Kit ranges by package

| Package | Spec Kit range |
| --- | --- |
| Assure, Illustrate, PR, Project, User Manual | `>=0.2.0` |
| Scope 2.0.0 (retired shim), `scope-gate`, `scope-brainstorm` | `>=1.0.0` |
| Memory, Workflow, `workflow` preset | `>=1.0.0,<2.0.0` |
| Progress | `>=1.1.1.dev0,<2.0.0` |

## Limits

- "Install tested" covers installation and reinstallation, not every command.
- A live run covers the configuration it used: Assure and User Manual were off, and every run was on
  Claude Code on Windows.
- Private pull request images must load for an authenticated viewer. Workflow's Finalize checks
  this; a successful upload alone is not enough.
