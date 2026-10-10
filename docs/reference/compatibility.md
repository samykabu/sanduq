# Compatibility

This page shows what Sanduq supports and what has been tested. A cell says **Tested** only when
recorded evidence exists. **Unverified** means the combination is supported in principle but nobody
has recorded a test. **Unsupported** means it does not work.

## Hosts

| Product | Codex | Claude Code | Claude Desktop |
| --- | --- | --- | --- |
| Portable skills (from sanduq-skills) | Unverified | Unverified | Unverified |
| Workflow, with the dependencies its installer adds | Install tested in CI (Ubuntu, core and SuperSpec) | Install tested in CI (Ubuntu, core and SuperSpec) | Unsupported |
| Memory | Unverified | Unverified | Unsupported |
| Assure, Illustrate, PR, Project, User Manual installed alone | Unverified | Unverified | Unsupported |
| Scope | Through Workflow only | Through Workflow only | Unsupported |

CI installs Workflow from a clean project for each host, with and without SuperSpec, then
reinstalls it. A clean install is not a live feature run. Live runs on each host are planned for the
host test phase.

opencode is deferred. Copilot is outside the supported hosts. Delegate Task can start Codex, Claude
Code, opencode, Copilot and Pi as [harnesses](glossary.md#harness); that is not host support.

## Tested versions

| Component | Tested | Where |
| --- | --- | --- |
| Spec Kit | 1.0.11, commit `8147943512404afb9d99c6252cb9bf84369fd0b0` | CI installation, upgrade and Memory jobs |
| SuperSpec | 1.0.2, commit `c20ac6c1ba069cc9a72dacb8044b7b193d3dde81` | CI installation job |
| Python | 3.13 | CI on Ubuntu and Windows |
| Playwright | 1.63.0 with Chromium | CI Illustrate suite |
| `npx skills` | 1.7.2 | CI listing and named-install check |
| Superpowers Bridge, Superpowers | Unverified | |

The regression suites for Workflow, Scope, User Manual, Memory and Illustrate run on Ubuntu and
Windows. Manifest ranges allow other versions; those are not tested combinations.

## Spec Kit ranges by package

| Package | Spec Kit range |
| --- | --- |
| Assure, Illustrate, PR, Project, User Manual | `>=0.2.0` |
| Scope, `scope-gate`, `scope-brainstorm` | `>=1.0.0` |
| Memory, Workflow, `workflow` preset | `>=1.0.0,<2.0.0` |

## Limits

- "Install tested" covers installation and reinstallation, not every command.
- Private pull request images must load for an authenticated viewer. Workflow's Finalize checks
  this; a successful upload alone is not enough.
