# Getting started

Install only what your task needs. A portable skill works without Spec Kit; the managed workflow
adds issue binding, stage ownership, and evidence checks to a Spec Kit project.

## Table of contents

- [Prerequisites](#prerequisites)
- [Portable skills](#portable-skills)
- [Claude Code plugins](#claude-code-plugins)
- [Managed workflow](#managed-workflow)
- [Individual extensions](#individual-extensions)
- [Command names](#command-names)
- [Existing projects and upgrades](#existing-projects-and-upgrades)
- [Troubleshooting](#troubleshooting)

## Prerequisites

| Path | You need |
| --- | --- |
| Portable installation | A supported agent and Node/npm for `npx skills` |
| Illustrate | Python for themes/SVG export; Playwright plus Chromium for PNG export |
| User Manual builds | Python and the skill's pinned renderer requirements; PDF builds also need system libraries |
| Delegate Task | Node 18+, Git for measured changes, and an authenticated target agent CLI |
| Managed workflow | Spec Kit 1.x, Python 3.10+, Git, authenticated `gh`, and a configured GitHub Project |
| Memory | Spec Kit 1.x, Python 3.11+, Git, and real project verification commands |

Use [Spec Kit's installation instructions](https://github.com/github/spec-kit#installation).
Check the local tools before configuring a consumer:

```bash
specify --version
python --version
git --version
gh auth status
```

Sanduq's [CI](../.github/workflows/ci.yml) pins the tested Spec Kit revision. A newer CLI is not
automatically a tested combination; see [compatibility](workflow-compatibility.md).

## Portable skills

In the booking application's repository:

```bash
npx skills add samykabu/sanduq-skills --list
npx skills add samykabu/sanduq-skills --skill user-manual -a codex
npx skills add samykabu/sanduq-skills --skill user-manual-api-docs --skill user-manual-ui-screenshots -a codex
```

Add `-g` for a user-wide installation or `-y` for non-interactive selection. Check the agent's
installed-skill list and start a new session when required. Codex normally uses `.agents/skills/`;
Claude Code uses `.claude/skills/`. Resolve script paths from the actual installed directory.

```text
$user-manual Create a manual for our booking application. Propose Booking, Payments, and
Operations modules from repository evidence. Ask for module-map approval before scaffolding.
```

Expected result: an approved `User-Manual/manual.yml`, canonical Markdown, an audit, and buildable
audience editions. See [all seven skills](skills.md) for focused examples.

## Claude Code plugins

In Claude Code, choose the bundles you need:

```text
/plugin marketplace add samykabu/sanduq
/plugin install dev-tools@sanduq
/plugin install illustration-tools@sanduq
/plugin install agent-tools@sanduq
```

They expose `/dev-tools:user-manual`, `/illustration-tools:illustrate`, and
`/agent-tools:delegate-task`. Plugin versions are independent of extension versions.

## Managed workflow

For a new Spec Kit consumer, initialize from its repository root:

```bash
specify init --here --integration codex
specify extension catalog add --name sanduq --priority 10 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
specify extension add workflow
```

For Claude Code, use `--integration claude`. Verify that the package comes from `samykabu/sanduq`.
Scope is also an ID in other catalogs; let Workflow's versioned installer resolve Sanduq Scope.

```text
$speckit-workflow-init Enable QA and User Manual for the booking application. Use our existing
GitHub Project, approve the module map through its interview, and select an advisory managed-only
evidence gate. Keep our existing CI and board settings.
$speckit-workflow-doctor Verify project readiness and installed host commands.
```

Init records independent QA/manual choices, installs selected dependencies, and reconciles hooks.
A valid Project configuration needs real board IDs, Scope statuses, and lifecycle mappings.
If the board is not configured:

```bash
gh auth refresh -h github.com -s project,read:project
```

```text
$speckit-project-init Discover our booking application's existing Project and map the lifecycle
to its actual columns. Preserve the managed workflow's hook ownership.
```

The script equivalent after choosing policy is:

```bash
python .specify/extensions/workflow/scripts/workflow.py init --qa on --manual on --gate-mode advisory --gate-scope managed-only
python .specify/extensions/workflow/scripts/install.py
python .specify/extensions/workflow/scripts/install.py --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

The first installer command previews; the second backs up and applies, with rollback on failure.
Finish the manual interview separately if its module map is still unapproved.
You are ready when `doctor --project` passes, not merely when the package downloads.

```text
$speckit-workflow-scope 412 Assess refund approval using our project policy and continue through
implementation. Preserve the booking and payment contracts. Stop before PR creation.
```

Answer real scope or clarification questions, then follow the [worked lifecycle](skill-guide.md).

## Individual extensions

After registering the catalog, install the bounded capability you need:

```bash
specify extension add illustrate
specify extension add assure
```

Initialize stateful packages using the [extension guide](extensions.md). Outside managed Workflow,
Assure and Project choose required/automatic or optional/manual hooks. `pr`, `assure`, and
`user-manual` require compatible Illustrate and follow `.specify/extension-dependencies.yml`:
`prompt`, `auto`, or `manual`. Installing a package and selecting its process are separate steps.

## Command names

| Host | Refund QA example |
| --- | --- |
| Codex | `$speckit-assure-analyze --feature specs/412-refund-approval` |
| Claude Code | `/speckit-assure-analyze --feature specs/412-refund-approval` |
| Copilot, where registered | `/speckit.assure.analyze --feature specs/412-refund-approval` |
| Manifest identifier | `speckit.assure.analyze` |

Use the host's actual registration. Agent prompts are not shell commands. See the
[Spec Kit integration reference](https://github.com/github/spec-kit/blob/main/docs/reference/integrations.md).

## Existing projects and upgrades

Inspect Git status and back up project-owned `.specify/`, agent configuration, and CI before
initializing an existing application. Review overwrite scope before using `specify init --force`.
Preserve its constitution, manual, board IDs, features, and workflows.

Resolve active claims and preview a transactional upgrade. Read the published version in
`catalog.json`; substitute it for `<version>`:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version <version>
python .specify/extensions/workflow/scripts/upgrade.py --version <version> --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

Add `--preserve-ci` to retain a project-owned evidence workflow. Installation does not certify
old feature receipts; review checkpoint migration. Test staged packages through
[Contributing](../CONTRIBUTING.md#test-a-local-package).

## Troubleshooting

| Symptom | Check and recovery |
| --- | --- |
| Command absent | Check the intended integration/directory, reinstall, then restart discovery. Workflow's `host` operation can repair/switch Codex or Claude registrations. |
| Wrong Scope package | Inspect its origin and the dependency lock; install the verified Sanduq archive. |
| QA/manual stage absent | Check `.specify/workflow.yml`; installation alone does not enable a process. |
| Board/auth failure | Check `gh auth status`, Project scopes and real mappings, then rerun `doctor --project`. |
| Old extension resolves | Inspect catalog/cache. Clear only the consumer's extension cache after confirming its absolute path, then reinstall. |
| PNG/PDF build fails | Check pinned renderer requirements and system libraries; report failed or unavailable builds accurately. |
| Stale receipt or interrupted claim | Use [workflow operations](workflow-guide.md); inspect remote effects before recovery or redispatch. |
