# Compatibility

This page shows what Sanduq supports and what has been tested. A cell says **Tested** only when
recorded evidence exists, and it names that evidence. **Untested** means the combination is
supported but nobody has recorded a test. **Unsupported** means it does not work.

There are two kinds of evidence. **CI** is an automated job in [CI](../../.github/workflows/ci.yml)
that installs or upgrades the packages and runs their test suites. A **live run** is a recorded
managed run of a real issue by an agent host, from scope to an open pull request. A clean install is
not a live run.

Workflow 2.0.2: eight managed live runs on the released 2.0.2, seven on Claude Code and one on Codex, lite tier, with delegation off, native and external tasks; all eight valid, every PR passed its own tests and the held-out tests, as recorded during the October 2026 live runs.

Workflow 1.19.2 hotfix: focused reconciler, rollback and packaged CLI checks passed with Spec Kit 1.1.3, plus an existing Windows consumer upgrade and project doctor. No new full managed live run was recorded for either host for this patch; the older live runs below retain their stated versions.
Workflow 2.0.0 train: every suite passed on Windows with Spec Kit 1.1.3 on the merged tree, and a real consumer project upgraded from Workflow 1.18.2 with Spec Kit 1.1.3 kept every receipt of its 12 features in progress (`doctor --project` passed). No new managed live run was recorded for this train.

Workflow 1.21.0 train: every suite passed on Windows with Spec Kit 1.1.3 on the merged tree (workflow 1391, scope 287, memory 207, shared scripts 209, project, pr, assure, user-manual, progress). No new managed live run was recorded for this train.

Workflow 1.20.0 and Scope 1.11.1: every suite passed on Windows with Spec Kit 1.1.3 (scripts, assure, pr, project, user-manual, progress, memory and the full workflow suite, including the new end-to-end lifecycle test). No new managed live run was recorded for this train; the older live runs below retain their stated versions.

## Hosts

Workflow 2.3.0 was published on 2026-11-05 ([release](https://github.com/samykabu/sanduq/releases/tag/workflow-v2.3.0)). Its row covers three separate pieces of evidence: a clean managed run on each host from 2026-11-04 to 2026-11-05, on an earlier staged build; supported upgrades and migrations of those two consumers onto the first corrected candidate, with its checks; and the same upgrades onto the final candidate, with the checks its two contract fixes affected. The corrective upgrades are not a clean replay of the final build. The redacted evidence bundles are attached to the release.

| Product | Codex | Claude Code | Claude Desktop | Live run (date, versions, host) |
| --- | --- | --- | --- | --- |
| Workflow 2.3.0, selected QA and User Manual | **Tested: clean run on a staged build, then supported upgrades to the first and final candidates** ([redacted bundle](https://github.com/samykabu/sanduq/releases/download/workflow-v2.3.0/workflow-230-live-codex.zip)) | **Tested: clean run on a staged build, then supported upgrades to the first and final candidates** ([redacted bundle](https://github.com/samykabu/sanduq/releases/download/workflow-v2.3.0/workflow-230-live-claude.zip)) | Unsupported | 2026-11-04–05, Windows, Spec Kit 1.1.3, isolated Python 3.13.15. Both clean runs reached open PRs with exact-head workflow-evidence success; standard floor, score 2, eight shared task issues, QA and two bilingual manual editions. On the first corrected candidate, the doctor, role, route, content and status checks and the affected freshness, indexed and clean-candidate checks passed after a supported upgrade and migration. The final candidate fixes two contracts that source CI caught; its full local Workflow suite ran 1,834 tests with zero failures/errors and three skips, and all 18 installed-contract checks passed. Supported corrections do not establish a full clean replay. |
| Workflow, with the dependencies its installer adds | Install tested in CI (Ubuntu, core and SuperSpec). End to end: **Tested** (live runs, the 2026-10-28 QA run and routing fixture with one native and one external task) | Install tested in CI (Ubuntu, core and SuperSpec). End to end: **Tested** (live runs, including the 2026-10-28 routing runs with in-session, native and external tasks) | Unsupported | 2026-10-21: the builds released as Workflow 1.17.0, Spec Kit 1.0.11, Claude Code 2.1.306. 2026-10-21: Workflow 1.17.1, Scope 1.10.1, Spec Kit 1.1.4.dev0, Claude Code 2.1.306. 2026-10-28: Workflow 1.21.0, Scope 1.12.0, Spec Kit 1.1.3, Claude Code 2.1.312 and Codex CLI 0.163.0, QA and User Manual on, advisory gate, standard tier, PR opened on each host; host switch and Bridge route exercised. The CI gate did not run (its workflow file did not load, fixed in Workflow 1.22.1); the gate passed locally. Routing runs, 2026-10-28: Workflow 2.0.2, Spec Kit 1.1.3 (the Codex fixture's host switch ran 1.2.3), Claude Code 2.1.312 (seven runs) and Codex CLI 0.163.0 (one run), QA and User Manual selected, advisory gate, lite tier, delegation off or on; native and external tasks on both hosts, PR opened on each, not merged |
| Scope | Through Workflow only. **Tested** (2026-10-28 live runs) | Through Workflow only. **Tested** (live runs) | Unsupported | Live runs on 2026-10-21 and 2026-10-28 (Claude Code and Codex), as Workflow |
| Memory | Untested | **Tested** through Workflow (live run) | Unsupported | Two live runs on 2026-10-21 (Memory 2.5.0), Claude Code 2.1.306 |
| Progress | Untested | **Tested** through Workflow (live run, native hooks) | Unsupported | 2026-10-21: Progress 1.5.0, Claude Code 2.1.306 |
| Project | Untested | **Tested** through Workflow (live run) | Unsupported | Two live runs on 2026-10-21 (Project 2.5.0 and 2.5.1), Claude Code 2.1.306 |
| PR | Untested | **Tested** through Workflow (live run, pull request opened) | Unsupported | 2026-10-21: PR 4.5.1, Claude Code 2.1.306 |
| Assure, Illustrate, User Manual | **Tested** through Workflow (2026-10-28 live run) | **Tested** through Workflow (2026-10-28 live run) | Unsupported | 2026-10-28: Assure 2.6.2 and User Manual 1.8.2 ran QA Analyze, QA Document, Manual Analyze and Manual Update on both hosts |
| Any extension installed alone, without Workflow | Untested | Untested | Unsupported | None |
| Portable skills (from sanduq-skills) | Untested | Untested | Untested | None |

The 2026-10-21 runs, the 2026-10-28 QA run on Claude Code and Codex with its findings, and the 2026-10-28
native and external routing runs were recorded during the October 2026 live runs. All ran
in a private sandbox repository on the maintainer's Windows machine. The 2026-10-28 redacted bundles are assets of the
[Workflow 1.21.0 release](https://github.com/samykabu/sanduq/releases/tag/workflow-v1.21.0). Codex has two
end-to-end live runs (the 2026-10-28 QA run and routing fixture); Memory and Progress on Codex are untested.

opencode is deferred. Copilot is outside the supported hosts. Delegate Task can start Codex, Claude
Code, opencode, Copilot and Pi as [harnesses](glossary.md#harness); that is not host support.

## Workflow 2.3.2 hotfix

Workflow 2.3.2, Assure 2.7.5 and User Manual 2.0.4 were tested with their affected unit suites, the
packaged install, upgrade and rollback smokes, and an upgrade of an isolated consumer project, where
doctor reported no errors. The live runs behind this hotfix used Workflow 2.3.1 on Claude Code and
Codex on Windows: both reached an open pull request through all 15 stages with passing evidence checks,
and the builder fix was then applied to them. No new full live run was made on 2.3.2 itself, so its
host rows stay as tested for 2.3.1.

## Platforms

| Platform | CI | Live run | Status |
| --- | --- | --- | --- |
| Windows | Regression suites, Memory installation and Project init on `windows-latest` | 2026-10-21 (Claude Code); 2026-10-28 (Claude Code and Codex) | **Tested** |
| Linux | Every CI job on the self-hosted runner, including installation and upgrade | None | **Tested** (CI only) |
| macOS | None | None | **Untested** |

The maintainer works on Windows, macOS and Linux. macOS has no CI leg and no live run, so treat it as
untested until one exists.

## In use, without a live-run record

These capabilities are in use by the maintainer, and have unit tests, but no live run has exercised
them. Report what you see if you use them.

| Capability | Where it is described |
| --- | --- |
| CI rule waivers (posted in the 2026-10-28 run but refused: a waiver cannot be verified when the owner and the agent share one GitHub account) | [Delivery policy](../workflow/delivery-policy.md) |
| SuperSpec as task generator and executor | [Prerequisites](../start/prerequisites.md#superspec) (installation is tested in CI) |

## Tested versions

| Component | Tested | Where |
| --- | --- | --- |
| Spec Kit | 1.1.3, commit `0282d03eb6fc3091b3deaa3a855d4030dc40cd6c` | CI installation, upgrade and Memory jobs |
| SuperSpec | 1.0.2, commit `c20ac6c1ba069cc9a72dacb8044b7b193d3dde81` | CI installation job |
| Python | 3.11, 3.13 | Every package declares 3.11 or later. CI runs the Linux regression suites on 3.11 and the Windows suites, lint and installation smokes on 3.13 |
| Playwright | 1.63.0 with Chromium | sanduq-skills CI, at the vendored Illustrate release |
| `npx skills` | 1.7.2 | CI listing and named-install check |
| Superpowers Bridge, Superpowers | Untested | |

The live runs used other Spec Kit versions (1.0.11 and 1.1.4.dev0 on 2026-10-21); the table
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
- A live run covers the configuration it used, as its row states: host (Claude Code or Codex), tier,
  whether QA and User Manual were selected, and delegation. Every live run was on Windows.
- Private pull request images must load for an authenticated viewer. Workflow's Finalize checks
  this; a successful upload alone is not enough.
