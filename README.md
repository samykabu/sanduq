# sanduq

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/sanduq-logo-dark.png">
    <img src="docs/assets/sanduq-logo.png" alt="Sanduq tools for software delivery" width="460">
  </picture>
</p>

[![Spec Kit extensions](https://img.shields.io/badge/Spec_Kit-8_extensions-233C32)](docs/README.md#extensions)
[![Portable skills](https://img.shields.io/badge/Agent_skills-7-C65B36)](https://github.com/samykabu/sanduq-skills)
[![License](https://img.shields.io/badge/license-PolyForm_NC_and_MIT-7b2d26)](#can-i-use-this)

Sanduq adds software-delivery processes to [Spec Kit](https://github.com/github/spec-kit) projects.
Each process is an extension you install on its own: QA analysis, an application manual, pull
request generation, GitHub Project sync, diagrams, and project memory. The Workflow extension can
also run them together, taking one GitHub issue to a verified pull request and resuming after an
interruption. If you do not use Spec Kit, the same diagram, manual and delegation skills are
available as portable agent skills in [sanduq-skills](https://github.com/samykabu/sanduq-skills).

## Products

| Product | Purpose | Lifecycle phase | Standalone | Requires | Hosts | License |
| --- | --- | --- | --- | --- | --- | --- |
| [Workflow](docs/extensions/workflow.md) | Resumable issue-to-PR dispatcher | All, as 16 stages | Yes | Python 3.10+, Git, `gh`; installs the extensions it uses | Codex, Claude Code (install tested) | PolyForm NC |
| [Scope](docs/extensions/scope.md) | Issue scope, prerequisites and decomposition | Before and after Specify, before Plan | No | Workflow, Illustrate | Through Workflow | MIT |
| [Project](docs/extensions/project.md) | GitHub Project board sync | Specify to Implement | Yes | `gh` (optional) | Codex, Claude Code (unverified) | PolyForm NC |
| [Assure](docs/extensions/assure.md) | QA readiness analysis and walkthrough | After Tasks, around Implement | Yes | Illustrate | Codex, Claude Code (unverified) | PolyForm NC |
| [User Manual](docs/extensions/user-manual.md) | Audience-aware application manual | After Tasks and Implement; release | Yes | Illustrate | Codex, Claude Code (unverified) | PolyForm NC |
| [PR](docs/extensions/pr.md) | Feature docs, PR description, review feedback | After Implement | Yes | Illustrate | Codex, Claude Code (unverified) | PolyForm NC |
| [Illustrate](docs/extensions/illustrate.md) | Themed diagrams and charts, 44 types | Any, on request | Yes | Nothing | Codex, Claude Code (unverified) | PolyForm NC |
| [Memory](docs/extensions/memory.md) | Project memory and recoverable spec archiving | Before Specify and Analyze; after merge | Yes | Python 3.11+, Git | Codex, Claude Code (unverified) | PolyForm NC |
| [Portable skills](https://github.com/samykabu/sanduq-skills) | Illustrate, User Manual (5 skills), Delegate Task | No Spec Kit needed | Yes | Per skill | Codex, Claude Code, Claude Desktop (unverified) | MIT |

"Standalone" means it works without Workflow. "Requires" lists hard dependencies; Spec Kit does not
install them for you. See [who enforces dependencies](docs/start/prerequisites.md#who-enforces-dependencies)
and [compatibility](docs/reference/compatibility.md).

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

**An extension, in a Spec Kit project:**

```bash
specify init --here --integration codex    # or --integration claude
specify extension catalog add --name sanduq --priority 10 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
specify extension add illustrate
```

**The managed Workflow:**

```bash
specify extension add workflow
```

```text
$speckit-workflow-init Enable QA and User Manual. Use our existing GitHub Project and an advisory managed-only evidence gate.
$speckit-workflow-doctor Check project readiness, dependencies and host commands.
$speckit-workflow-scope 412 Assess refund approval and continue through implementation. Stop before PR creation.
```

Claude Code uses `/` instead of `$`. Every host is covered in [install by host](docs/start/install-by-host.md).

## Can I use this?

| Package | License | Commercial use |
| --- | --- | --- |
| Portable skills ([sanduq-skills](https://github.com/samykabu/sanduq-skills)) | MIT | Yes |
| Scope, `scope-gate` and `scope-brainstorm` presets | MIT | Yes |
| Workflow, Project, Assure, User Manual, PR, Illustrate, Memory, `workflow` preset | [PolyForm Noncommercial 1.0.0](LICENSE) | Needs a separate written license from [Samy K. Abushanab](https://github.com/samykabu) |

PolyForm Noncommercial is source available, not an OSI-approved open-source license. Bundled upstream
material keeps its own license; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the
[per-package table](docs/reference/licenses.md).

## Documentation

- [Documentation index](docs/README.md)
- [Command reference](docs/reference/commands.md), [hooks](docs/reference/hooks.md) and [glossary](docs/reference/glossary.md)
- [Troubleshooting](docs/start/troubleshooting.md) and [upgrades](docs/start/upgrades.md)
- Published versions: [catalog.json](catalog.json). Versions awaiting release: [pending releases](extensions/pending-releases.json). History: [CHANGELOG.md](CHANGELOG.md).
- [Contributing](CONTRIBUTING.md)
