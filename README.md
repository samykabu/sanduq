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

> $${\color{red}\text{CI runner exception: every job runs on the home office runner homek8-general except two cases. The windows-latest legs of the regression and memory-installation matrices in .github/workflows/ci.yml run on GitHub-hosted Windows, and every ci.yml job of a pull request from a fork runs on ubuntu-latest.}}$$
>
> $${\color{red}\text{Why: Windows legs: the home office runners are Linux pods. Fork pull requests: this repository is public, and code from a fork must not run inside the home office cluster, so jobs of pull requests from forks run on ubuntu-latest.}}$$
>
> $${\color{red}\text{Removal: Windows legs: register a self-hosted Windows runner for samykabu/sanduq and point the windows-latest legs at it. Fork pull requests: none planned; this exception is a security boundary, not a missing runner.}}$$

## Products

![Product map: eight Spec Kit extensions in this repository. Scope requires Workflow and Illustrate; Assure, PR and User Manual require Illustrate; PR uses Assure and User Manual when installed; Project and Memory stand alone. The sanduq-skills repository supplies the Illustrate, User Manual and Delegate Task skills, copied into extensions and listed by the sanduq marketplace.](docs/diagrams/product-map.animated.svg)

The map shows each extension and what it requires; arrows point to the dependency.
[Editable source](docs/diagrams/product-map.html) and [static version](docs/diagrams/product-map.svg).

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
| [Progress](docs/extensions/progress.md) | Live feature progress report with lanes, blockers and decisions | Tasks to Implement; native host hooks | Yes | Python 3.11+ | Codex, Claude Code (unverified) | PolyForm NC |
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

**A plugin bundle, in Codex** (not yet exercised in a Codex install; Claude Code uses `/plugin`):

```bash
codex plugin marketplace add samykabu/sanduq
codex plugin add illustration-tools@sanduq
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

Claude Code uses `/` instead of `$`. Every host is covered in [install by host](docs/start/install-by-host.md),
including what the Workflow installer adds to each host: a guard hook, two role agents and the
optional short aliases (`--with-aliases`).

## Adopt Workflow 1.13.0 in an existing project

Workflow 1.13.0 and Scope 1.8.0 shorten the front half of the lifecycle. Every new behaviour is
opt-in; an absent policy key keeps the previous behaviour. To adopt it in a consumer:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version 1.13.0
python .specify/extensions/workflow/scripts/upgrade.py --version 1.13.0 --apply
python .specify/extensions/workflow/scripts/workflow.py migrate --feature specs/<feature> --reason "Reviewed 1.13.0"   # each feature in progress
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

Then add the profile policy to `.specify/workflow.yml` and run the next real issue through it:

```yaml
profiles:
  enabled: true           # lite: score <= 3, standard: score <= 8, full above
clarification:
  in_session_first_round: true
  max_questions_per_round: 6
issue_sync:
  taskstoissues: phase-lazy
```

```text
$speckit-workflow-scope 412 Scope this issue and continue through implementation.
```

Scope records the effort score, the first Plan claim fixes the tier, and `status` lists the stages
the tier skips. On Codex, approve the new guard hook once in `/hooks`. The benchmark that motivated
these defaults, and how to rerun it, is in `docs/internal/benchmarks/` in this repository;
a live run is the confirmation of token spend, because the benchmark measures runtime cost and
instruction load, not generated tokens. Codex installs of the portable plugin bundles from the
marketplace are published but not yet exercised. See [upgrades](docs/start/upgrades.md#adopt-workflow-1130-profiles)
for the details and the [workflow changelog](extensions/workflow/CHANGELOG.md) for every policy key.

## Adopt the round-2 releases (Workflow 1.14.0 and the companion extensions)

Workflow 1.14.0 ships with Assure 2.4.0, User Manual 1.6.0, PR 4.3.0, Project 2.3.0, Illustrate
2.5.0, Memory 2.3.0, Progress 1.3.0 and Scope 1.8.1. The commands read less (about 41 percent fewer
instruction bytes per invocation in the repository benchmark) and hand deterministic work to scripts:
the QA inventory, the PR body and lint receipt, the project sync command, the memory hashes. Receipts,
gates and GitHub decisions are unchanged. Upgrade the same way, substituting 1.14.0:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version 1.14.0 --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

Nothing new is switched on by the upgrade. The opt-in keys are listed in
[upgrades](docs/start/upgrades.md#adopt-the-round-2-releases); the one most projects want is
`progress.hook_wiring: native`, which roughly halves the Progress hook's cost on every tool call. On
Codex, approve the changed guard hook once in `/hooks`.

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
