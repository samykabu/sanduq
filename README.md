# sanduq

**sanduq** is a shared toolbox for AI-agent workflows: Spec Kit extensions, Claude Code plugins,
and portable skills.

## What is included

### Spec Kit extensions

Install these with the `specify` CLI from the public catalog at [`catalog.json`](catalog.json).

| Extension | Version | Command | Use it for |
| --- | ---: | --- | --- |
| [`project`](extensions/project/) | 1.1.0 | `/speckit-project-init`<br>`/speckit-project-sync` | Configure and keep a GitHub Project in sync with a Spec Kit feature, parent issue, task sub-issues, and lifecycle status. |
| [`pr`](extensions/pr/) | 3.0.0 | `/speckit-pr-generate`<br>`/speckit-pr-review-feedback` | Generate or update a pull request, then process its review feedback through an approval-gated workflow. |
| [`how-to-test`](extensions/how-to-test/) | 2.0.0 | `/speckit-how-to-test-document` | Generate QA-facing How-To-Test manuals and run readiness analysis after task generation. |
| [`illustrate`](extensions/illustrate/) | 1.0.0 | `/speckit-illustrate-generate`<br>`/speckit-illustrate-export` | Generate and export twenty-seven technical, product, architecture, and process illustration types. |

### Claude Code plugins

Install these from the marketplace at [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json).

| Plugin | Version | Use it for |
| --- | ---: | --- |
| [`illustration-tools`](skills/illustration-tools/) | 2.0.0 | One unified `illustrate` skill with editorial and technical-color families plus export controls. |

### Portable skills

| Skill | Version | Use it for |
| --- | ---: | --- |
| [`illustrate`](skills/illustration-tools/skills/illustrate/) | 3.0.0 | Twenty-seven visual types, hand variants, technical-color architecture/process packs, icons, terminal styling, and SVG/PNG/PDF export. |

The `illustrate` Spec Kit extension packages the same capability for managed, versioned installation.

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
specify extension add illustrate
```

If upgrading from the former standalone `pr-review` extension, remove it and force-refresh `pr`:

```bash
specify extension remove pr-review
specify extension add pr --force
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

Initialization asks whether lifecycle sync hooks should be `required` (automatic) or
`optional` (manual/user-approved). For automation, pass `--hooks-mode required|optional`.

After that, `optional` lifecycle hooks offer `/speckit-project-sync` in Claude Code or
`$speckit-project-sync` in Codex for manual approval; `required` hooks invoke sync as part of each
configured lifecycle phase.

The `pr` and `how-to-test` extensions can be run manually:

```text
/speckit-pr-generate
/speckit-pr-review-feedback owner/repo#123
/speckit-how-to-test-analyze
/speckit-how-to-test-document
/speckit-illustrate-generate
/speckit-illustrate-export path/to/diagram.html --svg-only
```

The PR and How-To-Test commands declare `illustrate` as a versioned dependency. On use they
inspect `.specify/extensions/.registry`, ask before installing/updating by default, and cache catalog
checks for 24 hours. Set project-wide behavior in `.specify/extension-dependencies.yml`:

```yaml
schema_version: "1.0"
update_policy: auto # prompt | auto | manual
check_interval_hours: 24
```

The remaining Claude plugin skills are available outside Spec Kit:

```text
/illustration-tools:illustrate
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
    illustrate/
  skills/
    illustration-tools/
```

## License

MIT © Samy K. Abushanab
