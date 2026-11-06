# sanduq

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/sanduq-logo-dark.png">
    <img src="docs/assets/sanduq-logo.png" alt="Sanduq tools for software delivery" width="460">
  </picture>
</p>

[![Spec Kit extensions](https://img.shields.io/badge/Spec_Kit-9_extensions-233C32)](docs/README.md#extensions)
[![Portable skills](https://img.shields.io/badge/Agent_skills-6-C65B36)](https://github.com/samykabu/sanduq-skills)
[![License](https://img.shields.io/badge/license-MIT-7b2d26)](#can-i-use-this)

Sanduq adds software-delivery processes to [Spec Kit](https://github.com/github/spec-kit) projects.
Each process is an extension you install on its own: QA analysis, an application manual, pull
request generation, GitHub Project sync, diagrams, and project memory. The Workflow extension can
also run them together, taking one GitHub issue to a verified pull request and resuming after an
interruption. If you do not use Spec Kit, the same diagram, manual and delegation skills are
available as portable agent skills in [sanduq-skills](https://github.com/samykabu/sanduq-skills).
The [product brief](docs/start/product-brief.md) says who Sanduq is for and how its success is measured.

## Products

![Product map: the nine Spec Kit packages in this repository, where Scope is part of Workflow and its own package is a retired shim. Workflow, Assure, PR and User Manual require Illustrate; PR uses Assure and User Manual when installed; Workflow uses Progress when installed; Project, Memory and Progress stand alone. The sanduq-skills repository supplies four vendored inputs, the Illustrate, User Manual, Delegate Task and Progress Report skills, copied into extensions and listed by the sanduq marketplace.](docs/diagrams/product-map.animated.svg)

The map shows each extension and what it requires; arrows point to the dependency.
[Editable source](docs/diagrams/product-map.html) and [static version](docs/diagrams/product-map.svg).

| Job | Product | Purpose | Runs at | Requires | Live-run hosts |
| --- | --- | --- | --- | --- | --- |
| Managed delivery | [Workflow](docs/extensions/workflow.md) | Takes one GitHub issue to a verified PR and resumes after an interruption. Includes Scope: issue scope, prerequisites and decomposition. | Every stage, Scope to PR | Python 3.11+, Git, `gh`; installs the extensions it uses | Claude Code, Codex |
| Checks and pull requests | [QA](docs/extensions/assure.md) (`assure`) | Finds missing test work before implementation; writes the tester walkthrough after it | After Tasks, around Implement | Illustrate | Claude Code, Codex (through Workflow) |
| Checks and pull requests | [Pull requests](docs/extensions/pr.md) (`pr`) | Writes the PR from the feature's files and checks; works through review feedback | After Implement | Illustrate | Claude Code (through Workflow) |
| Documentation | [User Manual](docs/extensions/user-manual.md) | Manuals for the audiences and languages you choose, in Markdown; HTML and PDF through a renderer | After Tasks and Implement; at release | Illustrate | Claude Code, Codex (through Workflow) |
| Documentation | [Illustrate](docs/extensions/illustrate.md) | Themed diagrams and charts, 44 types | When you ask | Nothing | Claude Code, Codex (through Workflow) |
| Tracking and context | [Project sync](docs/extensions/project.md) (`project`) | Mirrors each feature onto a GitHub Project (v2) board | Specify to Implement | `gh` | Claude Code (through Workflow) |
| Tracking and context | [Progress](docs/extensions/progress.md) | Live HTML progress report with lanes, blockers and decisions | Tasks to Implement | Python 3.11+, Spec Kit 1.1.1+ | Claude Code (through Workflow) |
| Tracking and context | [Memory](docs/extensions/memory.md) | Project memory and recoverable spec archiving | Before Specify and Analyze; after merge | Python 3.11+, Git | Claude Code (through Workflow) |
| No Spec Kit | [Portable skills](https://github.com/samykabu/sanduq-skills) | illustrate, user-manual, github-wiki-publish, delegate-task, planning-majlis, progress-report | Whenever you call them | Per skill | Per skill |

Every extension works without Workflow. "Requires" lists hard dependencies; Spec Kit does
not install them for you, see [who enforces dependencies](docs/start/prerequisites.md#who-enforces-dependencies).
A live run is a recorded managed run of a real issue, from scope to an open pull request. Workflow has
live runs on both hosts; Project sync, Pull requests, Progress and Memory have run end to end only on
Claude Code so far. [Compatibility](docs/reference/compatibility.md) lists the evidence.

## How it runs

![Managed Workflow stages from Scope to After merge, each with the command or extension that does its work, and seven numbered paths that send work back: Clarify waits for answers, Analyze returns a gap to Plan, a mid-build spec edit is revalidated, failed checks and review findings return to Execute, failed CI and PR comments are fixed on the branch and revalidated from Verify, and a change after Verify revalidates Verify, Review and Ready.](docs/diagrams/workflow-stages.svg)

On a plain Spec Kit project each extension runs from a hook on its phase. Under the managed Workflow
the same commands run as stages, and a stage passes only on recorded evidence. When something changes
later, the numbered paths above are how work goes back. [When each extension runs](docs/start/how-it-runs.md)
shows both views and follows one made-up feature from issue to merge.

## Choose how much to use

| Level | You get | Start here |
| --- | --- | --- |
| 1. Skills only | One task in your agent, no Spec Kit | [Skills only](docs/scenarios/skills-only.md) |
| 2. One extension | One process in a Spec Kit project | [One extension](docs/scenarios/one-extension.md) |
| 3. Pick your extensions | Several processes you choose, each running from its own hooks, with no Workflow | [Pick your extensions](docs/scenarios/pick-your-extensions.md) |
| 4. Managed Workflow | One issue to a verified PR, resumable | [Managed Workflow](docs/scenarios/managed-workflow.md) |

## Quick start

Install the [prerequisites](docs/start/prerequisites.md) first.

**A plugin bundle, in Claude Code:**

```text
/plugin marketplace add samykabu/sanduq
/plugin install illustration-tools@sanduq
```

**A skill only, in Codex:**

```bash
npx skills add samykabu/sanduq-skills --skill illustrate -a codex
```

**An extension, in a Spec Kit project:**

```bash
specify init --here --integration claude    # or --integration codex
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
/speckit-workflow-init Enable QA and User Manual. Use our existing GitHub Project and an advisory managed-only evidence gate.
/speckit-workflow-doctor Check project readiness, dependencies and host commands.
/speckit-workflow-scope 412 Assess refund approval and continue through implementation. Stop before PR creation.
```

Codex uses `$` instead of `/`. Every host is covered in [install by host](docs/start/install-by-host.md),
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

The guides live in [`docs/`](docs/README.md) and are published to the [wiki](https://github.com/samykabu/sanduq/wiki).

- [Documentation index](docs/README.md)
- [When each extension runs](docs/start/how-it-runs.md): hooks, managed stages, what sends work back, and one feature traced from issue to merge
- [Command reference](docs/reference/commands.md), [hooks](docs/reference/hooks.md) and [glossary](docs/reference/glossary.md)
- [Troubleshooting](docs/start/troubleshooting.md) and [upgrades](docs/start/upgrades.md)
- Published versions: [catalog.json](catalog.json). Versions awaiting release: [pending releases](extensions/pending-releases.json). History: [CHANGELOG.md](CHANGELOG.md).
- [Contributing](CONTRIBUTING.md) and [security](SECURITY.md): trust assumptions, what runs automatically, how to report
