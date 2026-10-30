# sanduq

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/sanduq-logo-dark.png">
    <img src="docs/assets/sanduq-logo.png" alt="Sanduq tools for software delivery" width="460">
  </picture>
</p>

[![Spec Kit extensions](https://img.shields.io/badge/Spec_Kit-9_extensions-233C32)](docs/README.md#extensions)
[![Portable skills](https://img.shields.io/badge/Agent_skills-8-C65B36)](https://github.com/samykabu/sanduq-skills)
[![License](https://img.shields.io/badge/license-MIT-7b2d26)](#can-i-use-this)

Sanduq adds software-delivery processes to [Spec Kit](https://github.com/github/spec-kit) projects.
Each process is an extension you install on its own: QA analysis, an application manual, pull
request generation, GitHub Project sync, diagrams, and project memory. The Workflow extension can
also run them together, taking one GitHub issue to a verified pull request and resuming after an
interruption. If you do not use Spec Kit, the same diagram, manual and delegation skills are
available as portable agent skills in [sanduq-skills](https://github.com/samykabu/sanduq-skills).
The [product brief](docs/start/product-brief.md) says who Sanduq is for and how its success is measured.

## Products

![Product map: nine Spec Kit extensions in this repository; Scope is part of Workflow, and its own package is a retired shim. Workflow, Assure, PR and User Manual require Illustrate; PR uses Assure and User Manual when installed; Workflow uses Progress when installed; Project, Memory and Progress stand alone. The sanduq-skills repository supplies the Illustrate, User Manual and Delegate Task skills, copied into extensions and listed by the sanduq marketplace.](docs/diagrams/product-map.animated.svg)

The map shows each extension and what it requires; arrows point to the dependency.
[Editable source](docs/diagrams/product-map.html) and [static version](docs/diagrams/product-map.svg).

| Product | Purpose | Lifecycle phase | Standalone | Requires | Hosts |
| --- | --- | --- | --- | --- | --- |
| [Workflow](docs/extensions/workflow.md) | Resumable issue-to-PR dispatcher | All, as 16 stages | Yes | Python 3.11+, Git, `gh`; installs the extensions it uses | Claude Code (live run); Codex (install only) |
| [Scope](docs/extensions/scope.md) | Issue scope, prerequisites and decomposition; part of Workflow from 2.0.0 | Before and after Specify, before Plan | No | Workflow (it ships Scope), Illustrate | Through Workflow (Claude Code live run) |
| [Project](docs/extensions/project.md) | GitHub Project board sync | Specify to Implement | Yes | `gh` (optional standalone; Workflow needs a mapped board in its `full` and `minimal` board modes, none in `none`) | Claude Code (live run through Workflow); Codex (unverified) |
| [Assure](docs/extensions/assure.md) | QA readiness analysis and walkthrough | After Tasks, around Implement | Yes | Illustrate | Codex, Claude Code (unverified) |
| [User Manual](docs/extensions/user-manual.md) | Audience-aware application manual; HTML and PDF, English and Arabic (Amiri font) | After Tasks and Implement; release | Yes | Illustrate | Codex, Claude Code (unverified) |
| [PR](docs/extensions/pr.md) | Feature docs, PR description, review feedback | After Implement | Yes | Illustrate | Claude Code (live run through Workflow); Codex (unverified) |
| [Illustrate](docs/extensions/illustrate.md) | Themed diagrams and charts, 44 types | Any, on request | Yes | Nothing | Codex, Claude Code (unverified) |
| [Memory](docs/extensions/memory.md) | Project memory and recoverable spec archiving | Before Specify and Analyze; after merge | Yes | Python 3.11+, Git | Claude Code (live run through Workflow); Codex (unverified) |
| [Progress](docs/extensions/progress.md) | Live feature progress report with lanes, blockers and decisions | Tasks to Implement; native host hooks | Yes | Python 3.11+, Spec Kit 1.1.1+ | Claude Code (live run through Workflow); Codex (unverified) |
| [Portable skills](https://github.com/samykabu/sanduq-skills) | Illustrate, User Manual (5 skills), Delegate Task, Progress Report | No Spec Kit needed | Yes | Per skill | Codex, Claude Code, Claude Desktop (unverified) |

"Standalone" means it works without Workflow. "Requires" lists hard dependencies; Spec Kit does not
install them for you. See [who enforces dependencies](docs/start/prerequisites.md#who-enforces-dependencies).
"Live run" means a recorded end-to-end managed run on that host. Every live run so far is on Claude Code;
Codex has no end-to-end run yet. [Compatibility](docs/reference/compatibility.md) lists the evidence.

## Choose how much to use

| Level | You get | Start here |
| --- | --- | --- |
| 1. Skills only | One task in your agent, no Spec Kit | [Skills only](docs/scenarios/skills-only.md) |
| 2. One extension | One process in a Spec Kit project | [One extension](docs/scenarios/one-extension.md) |
| 3. À-la-carte set | Several processes you choose | [À-la-carte set](docs/scenarios/a-la-carte.md) |
| 4. Managed Workflow | One issue to a verified PR, resumable | [Managed Workflow](docs/scenarios/managed-workflow.md) |

## Quick start

Install the [prerequisites](docs/start/prerequisites.md) first.

**Skill only, in Codex:**

```bash
npx skills add samykabu/sanduq-skills --skill illustrate -a codex
```

**A plugin bundle, in Codex** (not yet exercised in a Codex install; Claude Code uses `/plugin`):

```bash
codex plugin marketplace add samykabu/sanduq
codex plugin add illustration-tools@sanduq
```

**An extension, in a Spec Kit project:**

```bash
specify init --here --integration codex    # or --integration claude
specify extension catalog add --name sanduq --priority 1 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
specify extension add illustrate
```

The community catalog publishes unrelated `scope` and `memory` extensions. If you keep Spec Kit's
default catalogs, [register Sanduq's catalog ahead of them](docs/start/install-speckit.md#if-you-keep-spec-kits-default-catalogs).

**The managed Workflow** needs a GitHub Project (v2) board with seven named statuses before its first
claim. [Managed Workflow](docs/scenarios/managed-workflow.md) lists them, with a first-run checklist.

```bash
specify extension add workflow
```

```text
$speckit-workflow-init Enable QA and User Manual. Use our existing GitHub Project and an advisory managed-only evidence gate.
$speckit-workflow-doctor Check project readiness, dependencies and host commands.
$speckit-workflow-scope 412 Assess refund approval and continue through implementation. Stop before PR creation.
```

Claude Code uses `/` instead of `$`. Every host is covered in [install by host](docs/start/install-by-host.md),
including what the Workflow installer adds to each host: a guard hook, two role agents and the
optional short aliases (`--with-aliases`).

## Upgrade

Upgrade with Workflow's `upgrade.py`, which updates Workflow and the companions it pins together. The
steps and each release's migration table are in [upgrades](docs/start/upgrades.md).

## Can I use this?

Yes. Every package in this repository, its presets, and the portable skills in
[sanduq-skills](https://github.com/samykabu/sanduq-skills) are under the [MIT License](LICENSE),
including commercial use. Versions released before the MIT relicensing keep the license they were
published under. Bundled upstream material keeps its own license; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the [per-package table](docs/reference/licenses.md).

## Documentation

- [Documentation index](docs/README.md)
- [Command reference](docs/reference/commands.md), [hooks](docs/reference/hooks.md) and [glossary](docs/reference/glossary.md)
- [Troubleshooting](docs/start/troubleshooting.md) and [upgrades](docs/start/upgrades.md)
- Published versions: [catalog.json](catalog.json). Versions awaiting release: [pending releases](extensions/pending-releases.json). History: [CHANGELOG.md](CHANGELOG.md).
- [Contributing](CONTRIBUTING.md) and [security](SECURITY.md): trust assumptions, what runs automatically, how to report
