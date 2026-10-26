# Compatibility

This page shows what Sanduq supports and what has been tested. A cell says **Tested** only when
recorded evidence exists, and it names that evidence. **Untested** means the combination is
supported but nobody has recorded a test. **Unsupported** means it does not work.

There are two kinds of evidence. **CI** is an automated job in [CI](../../.github/workflows/ci.yml)
that installs or upgrades the packages and runs their test suites. A **live run** is a recorded
managed run of a real issue by an agent host, from scope to an open pull request. A clean install is
not a live run.

## Hosts

| Product | Codex | Claude Code | Claude Desktop | Live run (date, versions, host) |
| --- | --- | --- | --- | --- |
| Workflow, with the dependencies its installer adds | Install tested in CI (Ubuntu, core and SuperSpec). End to end: **Untested** | Install tested in CI (Ubuntu, core and SuperSpec). End to end: **Tested** (live runs) | Unsupported | Round 4, 2026-10-21: the round-4 builds released as Workflow 1.17.0, Spec Kit 1.0.11, Claude Code 2.1.306. Round 5, 2026-10-21: Workflow 1.17.1, Scope 1.10.1, Spec Kit 1.1.4.dev0, Claude Code 2.1.306 |
| Scope | Through Workflow only. **Untested** | Through Workflow only. **Tested** (live runs) | Unsupported | Rounds 4 and 5, as Workflow |
| Memory | Untested | **Tested** through Workflow (live run) | Unsupported | Round 4 run 4 (the build released as Memory 2.5.0) and round 5 (Memory 2.5.0), 2026-10-21, Claude Code 2.1.306 |
| Progress | Untested | **Tested** through Workflow (live run, native hooks) | Unsupported | Round 5, 2026-10-21: Progress 1.5.0, Claude Code 2.1.306 |
| Project | Untested | **Tested** through Workflow (live run) | Unsupported | Round 4 (the build released as Project 2.5.0) and round 5 (Project 2.5.1), 2026-10-21, Claude Code 2.1.306 |
| PR | Untested | **Tested** through Workflow (live run, pull request opened) | Unsupported | Round 5, 2026-10-21: PR 4.5.1, Claude Code 2.1.306 |
| Assure, Illustrate, User Manual | Untested | Untested | Unsupported | None. Illustrate was installed in the live runs; QA and User Manual were not selected |
| Any extension installed alone, without Workflow | Untested | Untested | Unsupported | None |
| Portable skills (from sanduq-skills) | Untested | Untested | Untested | None |

Evidence records, in this repository: round 4 in `docs/internal/round-4-live-run.md` and round 5 in
`docs/internal/round-5-live-run.md`. Both ran in a private sandbox repository on the maintainer's
Windows machine. Codex has no end-to-end live run yet, so every Codex cell beyond installation is
untested.

opencode is deferred. Copilot is outside the supported hosts. Delegate Task can start Codex, Claude
Code, opencode, Copilot and Pi as [harnesses](glossary.md#harness); that is not host support.

## Platforms

| Platform | CI | Live run | Status |
| --- | --- | --- | --- |
| Windows | Regression suites, Memory installation and Project init on `windows-latest` | Rounds 4 and 5 (Claude Code) | **Tested** |
| Linux | Every CI job on the home-office runner, including installation and upgrade | None | **Tested** (CI only) |
| macOS | None | None | **Untested** |

The maintainer works on Windows, macOS and Linux. macOS has no CI leg and no live run, so treat it as
untested until one exists.

## In use, without a live-run record

These capabilities are in use by the maintainer, and have unit tests, but no live run has exercised
them. Report what you see if you use them.

| Capability | Where it is described |
| --- | --- |
| Host switch between Codex and Claude Code | [Operating guide](../workflow/operating-guide.md) |
| CI rule waivers | [Delivery policy](../workflow/delivery-policy.md) |
| Superpowers Bridge route | [Prerequisites](../start/prerequisites.md#superpowers-bridge-and-superpowers) |
| SuperSpec as task generator and executor | [Prerequisites](../start/prerequisites.md#superspec) (installation is tested in CI) |

## Tested versions

| Component | Tested | Where |
| --- | --- | --- |
| Spec Kit | 1.1.3, commit `0282d03eb6fc3091b3deaa3a855d4030dc40cd6c` | CI installation, upgrade and Memory jobs |
| SuperSpec | 1.0.2, commit `c20ac6c1ba069cc9a72dacb8044b7b193d3dde81` | CI installation job |
| Python | 3.13 | CI on Ubuntu and Windows. 3.11 or later is recommended for the managed path, because Memory and Progress need it |
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
| Scope, `scope-gate`, `scope-brainstorm` | `>=1.0.0` |
| Memory, Workflow, `workflow` preset | `>=1.0.0,<2.0.0` |
| Progress | `>=1.1.1.dev0,<2.0.0` |

## Limits

- "Install tested" covers installation and reinstallation, not every command.
- A live run covers the configuration it used: Assure and User Manual were off, and every run was on
  Claude Code on Windows.
- Private pull request images must load for an authenticated viewer. Workflow's Finalize checks
  this; a successful upload alone is not enough.
