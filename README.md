# sanduq

**sanduq** is a shared toolbox for AI-agent workflows: Spec Kit extensions, Claude Code plugins,
and portable skills.

## What is included

### Spec Kit extensions

Install these with the `specify` CLI from the public catalog at [`catalog.json`](catalog.json).

| Extension | Version | Command | Use it for |
| --- | ---: | --- | --- |
| [`project`](extensions/project/) | 1.0.1 | `/speckit-project-sync` | Keep a GitHub Project in sync with a Spec Kit feature, parent issue, task sub-issues, and lifecycle status. |
| [`pr`](extensions/pr/) | 1.1.2 | `/speckit-pr-generate` | Generate feature changelog/details docs and update the pull request body. |
| [`how-to-test`](extensions/how-to-test/) | 1.4.1 | `/speckit-how-to-test-document` | Generate QA-facing How-To-Test manuals and run readiness analysis after task generation. |
| [`pr-review`](extensions/pr-review/) | 1.0.4 | `/speckit-pr-review-process` | Process GitHub PR review comments through an approval-gated fix/reply workflow. |

### Claude Code plugins

Install these from the marketplace at [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json).

| Plugin | Version | Use it for |
| --- | ---: | --- |
| [`devtools`](skills/devtools/) | 1.7.1 | PR review handling, standards review, How-To-Test generation, and PR description generation outside Spec Kit. |
| [`illustration-tools`](skills/illustration-tools/) | 1.3.1 | Architecture and process-flow diagrams as standalone HTML+SVG files with export controls. |

## Install

### Spec Kit catalog

Add the sanduq catalog to a Spec Kit project:

```bash
specify extension catalog add --name sanduq --priority 10 --install-allowed \
  https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
```

Or add it manually to `.specify/extension-catalogs.yml`:

```yaml
catalogs:
  - name: sanduq
    url: https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
    priority: 10
    install_allowed: true
```

Install extensions by id:

```bash
specify extension add project
specify extension add pr
specify extension add how-to-test
specify extension add pr-review
```

Local development install from a clone:

```bash
specify extension add --dev /path/to/sanduq/extensions/project --force
```

If a target project resolves an old release, clear the project-level Spec Kit cache and retry:

```powershell
Remove-Item -Recurse -Force .specify\extensions\.cache
specify extension add project
```

### Claude Code marketplace

Inside Claude Code:

```text
/plugin marketplace add samykabu/sanduq
/plugin install devtools@sanduq
/plugin install illustration-tools@sanduq
```

## Use

`project` needs one-time setup in each target repo:

```bash
gh auth refresh -h github.com -s project,read:project
```

Then invoke the rendered skill using your assistant's syntax:

```text
Claude Code: /speckit-project-init
Codex:       $speckit-project-init
```

After that, lifecycle hooks prompt for `/speckit-project-sync` in Claude Code or
`$speckit-project-sync` in Codex at each phase.

The `pr`, `how-to-test`, and `pr-review` extensions can be run manually:

```text
/speckit-pr-generate
/speckit-how-to-test-analyze
/speckit-how-to-test-document
/speckit-pr-review-process owner/repo#123
```

Plugin skills are available outside Spec Kit:

```text
/devtools:pr-review
/devtools:how-to-test
/devtools:pr-generate-description
/illustration-tools:architecture-diagram
/illustration-tools:process-flow-diagram
```

## Release pipeline

The Resal-style automated release flow lives in
[`.github/workflows/release-extensions.yml`](.github/workflows/release-extensions.yml). On pushes to
`main` that change `extensions/**`, it detects changed extension directories, bumps versions when
needed, updates [`catalog.json`](catalog.json) and [`extensions/catalog.json`](extensions/catalog.json),
builds release ZIPs, commits catalog/version changes back to `main` with `[skip ci]`, and creates
GitHub releases tagged `<extension>-vX.Y.Z`.

When changing a plugin or extension, bump its manifest version and add a changelog entry in the same
change. CI validates catalog/version alignment and plugin marketplace sources.

## Repository layout

```text
sanduq/
  .claude-plugin/marketplace.json
  catalog.json
  extensions/
    catalog.json
    scripts/
    project/
    pr/
    how-to-test/
    pr-review/
  skills/
    devtools/
    illustration-tools/
    diagrams/
```

## License

MIT © Samy K. Abushanab
