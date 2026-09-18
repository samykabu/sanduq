# Spec Kit Extensions

This folder hosts sanduq extensions for the `specify` CLI. The public catalog is the root
[`../catalog.json`](../catalog.json), mirrored here as [`catalog.json`](catalog.json) for
compatibility with the Resal Marketplace layout.

## Extensions

| Extension | Source version | Main purpose |
| --- | --- | --- |
| [workflow](workflow/) | 1.0.0 (unreleased) | Sanduq Workflow |
| [scope](scope/) | 1.4.0 (unreleased) | Speckit Scope |
| [project](project/) | 2.1.0 (unreleased) | GitHub Project Lifecycle Sync |
| [pr](pr/) | 4.1.0 (unreleased) | Pull Request Workflow |
| [assure](assure/) | 2.1.0 (unreleased) | Assure |
| [user-manual](user-manual/) | 1.1.0 (unreleased) | User Manual |
| [illustrate](illustrate/) | 2.1.2 | Illustrate |

Published install versions remain authoritative in the two catalogs. Source versions
marked unreleased are exercised with staged archives, not assumed live URLs.

For what an extension *is* — and how it differs from a portable skill or a plugin bundle — see
[Skills, plugins, and extensions](../README.md#skills-plugins-and-extensions). For the sequenced
Scope-to-PR pipeline these extensions compose into, see
[The managed Spec Kit workflow](../README.md#the-managed-spec-kit-workflow).

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
specify extension add assure
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
/speckit-assure-init
/speckit-assure-analyze
/speckit-assure-document
/speckit-user-manual-init
/speckit-user-manual-analyze
/speckit-user-manual-update
/speckit-user-manual-release
/speckit-illustrate-generate
/speckit-illustrate-export path/to/diagram.html --svg-only
```

`pr`, `assure`, and `user-manual` check the Spec Kit registry for their compatible `illustrate` version
when invoked. The default dependency policy asks before install/update; projects may opt into
automatic or manual behavior through `.specify/extension-dependencies.yml`.

## Publishing

Maintainers set source manifest versions and `extensions/pending-releases.json` in
the reviewed change. Keep its status `implementation-in-progress` until validation
is complete; set `ready` only for release-ready packages.

After successful push CI on the current main commit, Release extensions:

1. Builds deterministic ZIPs including canonical presets and shared helpers.
2. Creates immutable versioned release assets, or verifies identical assets on retry.
3. Downloads every asset and checks SHA-256. A mismatch blocks publication; bump the
   version instead of overwriting an existing asset.
4. Promotes both catalogs only after every asset verifies, then clears released entries
   from the pending map. A failed push cannot create a catalog URL for a missing asset.

Local preparation without publication:

```bash
python extensions/scripts/release.py prepare --development
python extensions/scripts/release.py publish
```

Development plans cannot be published or promoted. The second command is a dry run.
See [the workflow guide](../docs/workflow-guide.md) for installation, resumption,
version updates, rollback and the difference between local and live acceptance.
