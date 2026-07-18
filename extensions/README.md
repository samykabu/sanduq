# Spec Kit Extensions

This folder hosts sanduq extensions for the `specify` CLI. The public catalog is the root
[`../catalog.json`](../catalog.json), mirrored here as [`catalog.json`](catalog.json) for
compatibility with the Resal Marketplace layout.

## Extensions

| Extension | Version | Command | Description |
| --- | ---: | --- | --- |
| [`project`](project/) | 2.0.0 | `/speckit-project-init`<br>`/speckit-project-sync` | Configures and mirrors Spec Kit features onto GitHub Projects with parent issues, sub-issues, and lifecycle status sync. |
| [`pr`](pr/) | 4.0.0 | `/speckit-pr-generate`<br>`/speckit-pr-review-feedback` | Generates or updates pull requests, enforces installed documentation gates, and processes review feedback. |
| [`qa`](qa/) | 1.0.0 | `/speckit-qa-init`<br>`/speckit-qa-analyze`<br>`/speckit-qa-document` | Configures QA lifecycle policy, analyzes test readiness, and maintains the QA test manual. |
| [`user-manual`](user-manual/) | 1.0.0 | `/speckit-user-manual-init`<br>`/speckit-user-manual-analyze`<br>`/speckit-user-manual-update`<br>`/speckit-user-manual-release` | Maintains bilingual-ready, audience-specific Markdown, Material HTML, and PDF application manuals. |
| [`illustrate`](illustrate/) | 2.0.0 | `/speckit-illustrate-generate`<br>`/speckit-illustrate-export` | Generates and exports twenty-seven technical, product, architecture, process, data, and quantitative illustration types. |

## Install

Add the catalog once:

```bash
specify extension catalog add --name sanduq --priority 10 --install-allowed \
  https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
```

Install by id:

```bash
specify extension add project
specify extension add pr
specify extension add qa
specify extension add user-manual
specify extension add illustrate
```

For an existing standalone `pr-review` installation, migrate to the consolidated extension:

```bash
specify extension remove pr-review
specify extension add pr --force
```

Local development install:

```bash
specify extension add --dev /path/to/sanduq/extensions/project --force
```

Always point `--dev` at an external clone path, not a path inside the target project's
`.specify/extensions/` directory.

If a project keeps resolving an old version, clear the project cache:

```powershell
Remove-Item -Recurse -Force .specify\extensions\.cache
specify extension add project
```

## Use

`project` requires one-time configuration in each target repo:

```text
Claude Code: /speckit-project-init
Codex:       $speckit-project-init
```

The initializer asks whether Project sync hooks should be required/automatic or
optional/manual. Non-interactive runs can pass `--hooks-mode required|optional`.

The other commands are manual or optional lifecycle-hook prompts:

```text
/speckit-pr-generate
/speckit-pr-review-feedback owner/repo#123
/speckit-qa-init
/speckit-qa-analyze
/speckit-qa-document
/speckit-user-manual-init
/speckit-user-manual-analyze
/speckit-user-manual-update
/speckit-user-manual-release
/speckit-illustrate-generate
/speckit-illustrate-export path/to/diagram.html --svg-only
```

`pr`, `qa`, and `user-manual` check the Spec Kit registry for their compatible `illustrate` version
when invoked. The default dependency policy asks before install/update; projects may opt into
automatic or manual behavior through `.specify/extension-dependencies.yml`.

## Publishing

The default path is the GitHub Actions workflow
[`Release extensions`](../.github/workflows/release-extensions.yml). On pushes to `main` that touch
`extensions/**`, it:

1. Detects changed extension folders that contain `extension.yml`.
2. Bumps versions by patch by default, unless `extension.yml` is already ahead of the catalog.
3. Updates the root catalog and this compatibility catalog.
4. Packages each extension into `dist/<id>.zip`.
5. Commits version/catalog updates back to `main` with `[skip ci]`.
6. Creates or updates the GitHub release `<id>-vX.Y.Z` and uploads the ZIP.

Manual fallback:

```bash
extensions/scripts/package.sh project
gh release create project-v1.0.1 dist/project.zip \
  --title "project extension v1.0.1" \
  --notes "GitHub Project Lifecycle Sync extension v1.0.1"
```
