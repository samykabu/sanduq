# Spec Kit Extensions

This folder hosts sanduq extensions for the `specify` CLI. The public catalog is the root
[`../catalog.json`](../catalog.json), mirrored here as [`catalog.json`](catalog.json) for
compatibility with the Resal Marketplace layout.

## Extensions

| Extension | Version | Command | Description |
| --- | ---: | --- | --- |
| [`project`](project/) | 1.0.1 | `/speckit-project-sync` | Mirrors Spec Kit features onto GitHub Projects with parent issues, sub-issues, and lifecycle status sync. |
| [`pr`](pr/) | 1.1.2 | `/speckit-pr-generate` | Generates feature changelog/details docs and creates or updates the pull request body. |
| [`how-to-test`](how-to-test/) | 1.4.1 | `/speckit-how-to-test-document` | Generates QA How-To-Test manuals, with `/speckit-how-to-test-analyze` for readiness checks after task generation. |
| [`pr-review`](pr-review/) | 1.0.4 | `/speckit-pr-review-process` | Processes GitHub pull request review comments through a classify, fix/reply, push, and resolve workflow. |

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
specify extension add how-to-test
specify extension add pr-review
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
/speckit-project-init
```

The other commands are manual or optional lifecycle-hook prompts:

```text
/speckit-pr-generate
/speckit-how-to-test-analyze
/speckit-how-to-test-document
/speckit-pr-review-process owner/repo#123
```

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
