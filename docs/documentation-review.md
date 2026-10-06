# Documentation structure and coverage

Keep a short README and split the operating documentation into focused files in this repository.
The setup, commands, and evidence rules change with the packages. Reviewing them in the same PR
keeps a documented command tied to the version that implements it.

## Table of contents

- [README, documents, or Wiki?](#readme-documents-or-wiki)
- [Coverage reviewed](#coverage-reviewed)
- [Gaps repaired](#gaps-repaired)
- [Keep it maintainable](#keep-it-maintainable)

## README, documents, or Wiki?

| Option | Fits | Cost for Sanduq |
| --- | --- | --- |
| One large README | A small tool with one setup and a few commands | Eight extensions and several audiences crowd the entry point; release detail obscures first use. |
| Short README plus repository docs | Versioned setup, examples, operations, and contributor instructions | Readers follow focused links; maintainers can validate links and coverage with the code change. |
| GitHub Wiki | Optional background or community notes | Operational content would need a second publication path and explicit version coordination. |

GitHub describes a README as a quick explanation of the project and a Wiki as a home for additional
long-form material. [GitHub's Wiki guide](https://docs.github.com/en/communities/documenting-your-project-with-wikis/about-wikis).
For this repository, the practical choice is repository docs. A future Wiki can link to those
canonical guides; moving setup or command contracts there would add maintenance work without
improving their version accuracy. No Wiki publication is required for this reorganization.

## Coverage reviewed

The review uses current source manifests, skill instructions, preset manifests, utility references,
catalogs, package scripts, and CI workflows. It covers seven portable skills, three plugin bundles,
eight extensions with **41 public commands**, sixteen dispatcher stages, extension-internal skills,
and all managed/provider overlays. Test fixture copies are historical fixtures, not extra products.

| Surface | Setup | Usage and examples | Contribution source |
| --- | --- | --- | --- |
| Seven portable skills | [Getting started](getting-started.md#portable-skills) | [Every skill](skills.md), with input, purpose, and expected output | `skills/<bundle>/skills/` |
| Three plugins | [Plugin setup](getting-started.md#claude-code-plugins) | Host namespaces in setup and skill examples | Bundle manifests and marketplace |
| Workflow: 13 commands | [Managed setup](getting-started.md#managed-workflow) | [Workflow](extensions.md#workflow), stages and utility contracts | `extensions/workflow/` |
| Scope: 7 commands | Workflow dependency installer and board policy | [Scope](extensions.md#scope), approval, prerequisites, and clarification | `extensions/scope/` |
| Project: 2 commands | Project access and board mapping | [Project](extensions.md#project), managed/unmanaged ownership | `extensions/project/` |
| Assure: 3 commands | QA process selection | [Assure](extensions.md#assure), readiness and fresh tester evidence | `extensions/assure/` |
| User Manual: 4 commands | Interview and approved module map | [User Manual](extensions.md#user-manual), analysis/update/release | `extensions/user-manual/` |
| PR: 2 commands | Git, authenticated `gh`, documentation policies | [PR](extensions.md#pr), docs-only option and feedback approval | `extensions/pr/` |
| Illustrate: 3 commands | Theme and renderer prerequisites | [Illustrate](extensions.md#illustrate), generate/theme/export | `extensions/illustrate/` and portable skill |
| Memory: 7 commands | Branch, checks, guard initialization | [Memory](extensions.md#memory), retrieval, archival, and recovery | `extensions/memory/` |
| Internal skills | Installed with their owner | [Internal skill map](extensions.md#internal-skills-and-overlays) | Owner's `skills/` or `skill/` |
| Presets/providers | Composed by the installer | [Every overlay](skill-guide.md#core-superspec-and-bridge-overlays) | Canonical `presets/` |
| Packaging and releases | [Contributor setup](../CONTRIBUTING.md) | Disposable consumer, smoke checks, immutable release promotion | `extensions/scripts/` and CI |

## Gaps repaired

- Replaced release-history introductions with purpose and navigation; package changelogs retain history.
- Corrected stale extension/plugin version tables and the eight-command Workflow claim.
- Added all Memory commands, current format-2 storage, typed links, retrieval, and safe archive boundaries.
- Added Workflow's five utility commands and their limits: local results are not CI evidence;
  evidence-only amendment does not certify changed dependencies.
- Documented internal skills and alias/overlay ownership without presenting them as portable installs.
- Standardized the reader guides in `docs/` on Codex prompts and one booking/refund scenario;
  host conversion lives in setup. Package references retain their host-specific syntax.
- Preserved worker/report, state, evidence, runner, context, and upgrade detail in the operating references.

The examples are instructional scenarios, not a live deployment test. Compatibility and prior
acceptance records retain their original dates and identifiers. No documentation change certifies
old test results or releases.

Cleanup removed 16 obsolete overview/source/export and theme-preview files after scanning tracked
documentation, scripts, tests, manifests, and templates for references. Brand masters, active
diagram sources/exports, the progress-report screenshot, and historical evidence remain. Two
Illustrate diagrams now explain dispatcher interactions and checkpoint state; their editable
HTML and SVG exports are linked from the guides. The visual expansion adds 17 editable diagrams
and five actual manual screenshots: preset/custom process themes, bounded delegation, all eight
extension workflows, and independent QA/manual paths. A checked-in synthetic manual and gallery
runner reproduce the screenshots through the real audit/build scripts. The standalone builder's
Material/CSS support is distinguished from the extension's configurable installed themes.

## Keep it maintainable

Run `python extensions/scripts/check_docs.py` after changes. It checks public-command and skill
coverage, the extension version table, and local links/anchors in the active guides. Review
illustration rendering separately. Consult package references for machine-level flags and recovery.
Keep release history in changelogs and investigations in evidence records. Add a new guide only
when it owns a distinct reader task.
