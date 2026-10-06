# Contributing to Sanduq

Change the source that owns the behavior, test the package consumers will receive, and include a
usable example. Generated agent registrations and installed consumer copies are not source.

## Table of contents

- [Set up the checkout](#set-up-the-checkout)
- [Find the owning source](#find-the-owning-source)
- [Test a local package](#test-a-local-package)
- [Validate a change](#validate-a-change)
- [Update documentation and assets](#update-documentation-and-assets)
- [Prepare a release](#prepare-a-release)
- [CI and runner policy](#ci-and-runner-policy)

## Set up the checkout

Clone the repository and work from its root:

```bash
git clone https://github.com/samykabu/sanduq.git
cd sanduq
python -m venv .venv
```

Activate `.venv` with your shell, then install the pinned test requirements:

```bash
python -m pip install -r extensions/workflow/test-requirements.txt
```

Use Node 18+ for Delegate Task checks. Bash and PowerShell cover separate installation paths.
Smoke installations need the Spec Kit revision pinned in [CI](.github/workflows/ci.yml), and some
need authenticated GitHub access. Use a disposable consumer for installer work.

## Find the owning source

| Change | Source |
| --- | --- |
| Portable skill instructions/scripts | `skills/<bundle>/skills/<name>/` |
| Plugin packaging | Bundle `.claude-plugin/plugin.json` and root marketplace |
| Extension metadata and commands | `extensions/<id>/extension.yml`, `commands/`, `skills/`, and references |
| Managed command policy | Canonical `presets/`; bundled by package tooling |
| Shared freshness/dependency helpers | `extensions/scripts/shared/`; injected at build time |
| Workflow claims, receipts, evidence, progress | `extensions/workflow/scripts/` |
| Deterministic ZIPs and releases | `extensions/scripts/package.py` and `release.py` |
| Published versions | `catalog.json` and mirrored `extensions/catalog.json` |
| Reviewed versions awaiting publication | `extensions/pending-releases.json` |
| Human onboarding and examples | README and `docs/` |

Consult [source ownership](docs/workflow-source-ownership.md) before editing a provider overlay.
Workflow's alias files are hash-owned; customizing an installed alias can block replacement.
Preserve project-owned CI, manual maps, board IDs, and hooks during upgrades.

## Test a local package

**Sanduq checkout:** build the affected extension and extract it outside the consumer:

```bash
python extensions/scripts/package.py workflow
python -m zipfile -e dist/workflow.zip <external-packages-directory>
```

Build and extract selected dependencies into that same directory when the dependency lock requires
new versions. The package includes canonical presets, the delegation driver, and shared helpers;
the raw source directory omits build inputs and is insufficient for Workflow acceptance.

**Disposable consumer repository:** install the extracted package:

```bash
specify extension add --dev <external-packages-directory>/workflow
```

For an existing consumer, preview and apply the upgrade using the source manifest version:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version <source-version> --packages <external-packages-directory>
python .specify/extensions/workflow/scripts/upgrade.py --version <source-version> --packages <external-packages-directory> --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

Resolve active claims first. Add `--preserve-ci` only when retaining project-owned CI is intended.
Review checkpoint migration and installer rollback. Never point `--dev` inside the consumer's
`.specify/extensions/` tree. Keep the extracted package available during development testing.

## Validate a change

Run the affected suite from the Sanduq checkout:

```bash
python -m unittest discover -s extensions/workflow/tests -q
python -m unittest discover -s extensions/scope/tests -q
python -m unittest discover -s extensions/user-manual/tests -q
python -m unittest discover -s extensions/memory/tests -q
node skills/agent-tools/skills/delegate-task/test/run.mjs
python extensions/scripts/test_check_docs.py
python extensions/scripts/check_docs.py
git diff --check
```

Choose the suites affected by the diff. Documentation-only changes need the documentation check,
link review, and rendered illustration inspection. Changed command semantics need a check that
fails when the behavior breaks, not a copy of the implementation.

Installation changes also need the relevant smoke check:

```bash
python extensions/scripts/smoke_install.py --host codex
python extensions/scripts/smoke_upgrade.py
python extensions/scripts/smoke_project_init.py --shell pwsh
python extensions/scripts/smoke_memory_install.py
```

CI exercises Linux/Windows regression, Codex/Claude and core/SuperSpec installs, transactional
upgrades, Project initialization in Bash/PowerShell, and Memory registration. Report unavailable
infrastructure and skipped checks accurately; package creation alone is not live acceptance.

## Update documentation and assets

Keep the README as the entry point. Update setup in `docs/getting-started.md`, skill examples in
`docs/skills.md`, public command examples in `docs/extensions.md`, stages/overlays in
`docs/skill-guide.md`, and operating rules in the owning workflow guide.

Use the [shared booking/refund scenario](docs/README.md#example-conventions). Preserve exact
identifiers in code, distinguish proposed behavior from verified behavior, and write for the
declared audience. Use `my-voice` for concise instructional prose and `illustrate` for useful
visuals. Do not add a summary that simply repeats a short section.

Illustration sources and exports stay together. Resolve the tracked theme, validate it, and
inspect rendering at desktop and narrow widths. Explain the same flow in adjacent text so the
image is not the only usable reference.

Before cleanup, search both the full path and basename across tracked text, scripts, tests,
templates, and manifests. A source/export pair or logo master remains useful even if only its
export is embedded. Preserve release evidence and historical design records. Delete only
enumerated obsolete files, then rerun link checks. Keep generated build output in ignored `dist/`.

## Prepare a release

For changed publishable behavior, update its manifest version and changelog. Plugin versions live
in their plugin manifests and marketplace; extension versions live in `extension.yml`. Record
reviewed extension versions in `extensions/pending-releases.json`; do not advertise an unpublished
asset through the catalogs.

```bash
python extensions/scripts/release.py prepare --development
python extensions/scripts/release.py publish
```

Development preparation cannot be promoted. The publish command above is a dry run without
`--apply`. Keep pending status `implementation-in-progress` until validation is complete; marking
it `ready` authorizes publication.

The [release workflow](.github/workflows/release-extensions.yml) requires successful push CI for
the current `main` commit. It builds deterministic archives, publishes immutable `<id>-vX.Y.Z`
assets, downloads and verifies their SHA-256 bytes, and only then promotes both catalogs. A retry
must verify the same bytes. Never overwrite an existing release asset to repair a version.

## CI and runner policy

Sanduq's own [CI](.github/workflows/ci.yml) uses `ubuntu-latest` and `windows-latest`; release runs
on Ubuntu. The repository records an exception because the organization-scoped home-office
runners belong to another account. Verify current availability before changing `runs-on`.

A consumer records its own runners and capabilities in `.specify/workflow.yml`; Sanduq renders
managed workflows from that policy. See [runner configuration](docs/workflow-operations.md#where-your-ci-actually-runs).
Do not infer consumer runner policy from this repository's CI.
