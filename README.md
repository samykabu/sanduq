# sanduq

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/sanduq-logo-dark.png">
    <img src="docs/assets/sanduq-logo.png" alt="Sanduq tools for software delivery" width="460">
  </picture>
</p>

[![Spec Kit extensions](https://img.shields.io/badge/Spec_Kit-8_extensions-233C32)](docs/extensions.md)
[![Portable skills](https://img.shields.io/badge/Agent_skills-7-C65B36)](docs/skills.md)
[![License](https://img.shields.io/badge/license-PolyForm_Noncommercial_1.0.0-7b2d26)](#license)

Sanduq supplies agent skills and Spec Kit extensions for software delivery. Use a skill for a
bounded task, such as writing a manual or drawing a sequence diagram. Use the managed workflow
to take a GitHub issue through specification, implementation, verification, documentation, and
one pull request, with a checkpoint you can resume in a fresh session.

## Table of contents

- [Choose your path](#choose-your-path)
- [Quick start](#quick-start)
- [Skills, plugins, and extensions](#skills-plugins-and-extensions)
- [The managed Spec Kit workflow](#the-managed-spec-kit-workflow)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Choose your path

| You need to… | Start with |
| --- | --- |
| Create or update an application manual | [User Manual](docs/skills.md#user-manual) |
| Document APIs, releases, screenshots, or previews | [Focused manual skills](docs/skills.md) |
| Explain an interaction, architecture, or workflow | [Illustrate](docs/skills.md#illustrate) |
| Give another agent a bounded task or independent review | [Delegate Task](docs/skills.md#delegate-task) |
| Add QA, manuals, or PR support to Spec Kit | [Extension guide](docs/extensions.md) |
| Run the issue-to-PR lifecycle | [Managed setup](docs/getting-started.md#managed-workflow) |
| Retain current knowledge and archive completed specs | [Memory](docs/extensions.md#memory) |

## Quick start

Run installation commands in the repository that will use Sanduq. For a standalone manual in Codex:

```bash
npx skills add samykabu/sanduq --skill user-manual -a codex
```

Then ask your agent:

```text
$user-manual Create a manual for our booking application. Inspect the repository, interview me
about audiences, and propose the module map before scaffolding. Require English, offer Arabic,
and use synthetic data.
```

For an existing Spec Kit project:

```bash
specify extension catalog add --name sanduq --priority 10 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
specify extension add workflow
```

```text
$speckit-workflow-init Enable QA and User Manual. Use our existing GitHub Project. Select an
advisory evidence gate with managed-only scope and verify the board mappings.
$speckit-workflow-doctor Check project readiness, dependencies, and host commands.
```

See [Getting started](docs/getting-started.md) for prerequisites, a new Spec Kit project,
Claude Code plugins, upgrades, and troubleshooting. Installation alone does not enable QA or manuals.

## Skills, plugins, and extensions

| Format | What it adds | Needs Spec Kit | Installation |
| --- | --- | --- | --- |
| Portable skill | Instructions and focused tooling for one task | No | `npx skills add samykabu/sanduq --skill <name>` |
| Claude Code plugin | A bundle of portable skills | No | `/plugin install <bundle>@sanduq` |
| Spec Kit extension | Versioned commands and lifecycle hooks | Yes | `specify extension add <id>` |

Codex uses `$name` for skills and `$speckit-<extension>-<command>` for extension commands.
Claude Code uses the corresponding `/speckit-…` command or a plugin namespace such as
`/dev-tools:user-manual`. See [command names](docs/getting-started.md#command-names).

The [catalog](catalog.json) records published versions. Source manifests describe this checkout;
[pending releases](extensions/pending-releases.json) record versions awaiting publication.
Release history lives in [CHANGELOG.md](CHANGELOG.md) and each package's changelog.

## The managed Spec Kit workflow

Start with an explicit GitHub issue. Sanduq checks scope and prerequisites, binds a specification,
reads clarification answers, plans tasks, and coordinates implementation. Verification and review
use actual results. Selected QA and manual processes then prepare the feature for Finalize.

```text
$speckit-workflow-scope 412 Assess refund approval using our project policy and continue through
implementation. Preserve the existing booking and payment contracts. Stop before PR creation.
```

Use **Clarify** after answering issue questions, **Continue** after interruption, and **Finalize**
when you want the PR created or updated. Merge and deployment need their own authorization.
See the [worked lifecycle](docs/skill-guide.md) and [operating guide](docs/workflow-guide.md).

## Documentation

See the [visual examples](docs/README.md#learn-and-use) for process themes, a bounded Claude/Codex
debate, real manual screenshots, and extension workflows with user and automated actions.

The [documentation index](docs/README.md) routes setup, examples, command reference, and operations.
All examples use the same synthetic booking application and refund feature.

| Guide | What you will find |
| --- | --- |
| [Getting started](docs/getting-started.md) | Prerequisites, installation, initialization, and recovery |
| [Portable skills](docs/skills.md) | When to use each skill, example prompts, and expected outputs |
| [Spec Kit extensions](docs/extensions.md) | Setup and examples for all eight extensions and their commands |
| [Worked lifecycle](docs/skill-guide.md) | Every managed stage, provider overlays, and worker coordination |
| [Workflow operating guide](docs/workflow-guide.md) | Continuation, upgrades, and evidence recovery |
| [State and runner reference](docs/workflow-operations.md) | Claims, worker reports, context telemetry, and runner policy |
| [Contributing](CONTRIBUTING.md) | Source ownership, local package testing, validation, and releases |

We keep operational documentation beside the code so a PR can review both. The
[documentation review](docs/documentation-review.md) explains the README/docs/Wiki decision and coverage.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md), change the owning source, and validate the affected package.
Include a practical example when a command or behavior changes. Keep illustration HTML editable
and check the rendered result before linking an export.

## License

Original Sanduq contributions are source available under
[PolyForm Noncommercial 1.0.0](LICENSE). Commercial use requires a separate written license from
[Samy K. Abushanab](https://github.com/samykabu). This is not an OSI-approved open-source license.
Earlier MIT distributions retain their accompanying terms; bundled upstream material retains its
original license. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
