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
- [Maintainer records](#maintainer-records)

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

Bash and PowerShell cover separate installation paths.
Smoke installations need the Spec Kit revision pinned in [CI](.github/workflows/ci.yml), and some
need authenticated GitHub access. Use a disposable consumer for installer work.

## Find the owning source

| Change | Source |
| --- | --- |
| Portable skills (Illustrate, User Manual, Delegate Task) | [samykabu/sanduq-skills](https://github.com/samykabu/sanduq-skills); never edit their vendored copies here |
| Vendored skill copies and their pins | `vendor.lock.json`, synced by `extensions/scripts/vendor.py` |
| Claude Code marketplace entries | `.claude-plugin/marketplace.json` (pinned `git-subdir` sources); bundle versions live in sanduq-skills |
| Extension-adapted skill entrypoints | `SKILL.ext.md`; `package.py` restores `SKILL.md` in the archive |
| Extension metadata and commands | `extensions/<id>/extension.yml`, `commands/`, `skills/`, and references |
| Managed command policy | Canonical `presets/`; bundled by package tooling |
| Shared freshness/dependency helpers | `extensions/scripts/shared/`; injected at build time |
| Workflow claims, receipts, evidence, progress | `extensions/workflow/scripts/` |
| Deterministic ZIPs and releases | `extensions/scripts/package.py` and `release.py` |
| Published versions | `catalog.json` and mirrored `extensions/catalog.json` |
| Reviewed versions awaiting publication | `extensions/pending-releases.json` |
| Human onboarding and examples | README and `docs/` |

Consult [source ownership](docs/internal/workflow-source-ownership.md) before editing a provider overlay.
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
python extensions/scripts/vendor.py check
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

## Update a vendored skill

Change and release the skill in sanduq-skills first (tag `<bundle>-vX.Y.Z`). Every day, the
`vendor-update` workflow here vendors any newer release, pins its marketplace entry, and opens a
pull request; run it from the Actions tab to skip the wait. It opens the pull request with the
`VENDOR_PR_TOKEN` secret (a fine-grained token for this repository with contents and pull-request
write access) so CI starts on its own; renew that token before it expires. To do the same locally:

```bash
python extensions/scripts/vendor.py update --source ../sanduq-skills
python extensions/scripts/vendor.py check
```

Record a patch release for each extension that ships the vendored files. `extensions/user-manual/ADAPTER.md` lists the User Manual
files that are vendored, rewritten, or owned here.

## Update documentation and assets

Keep the README as the entry point. Follow the [style guide](docs/style-guide.md) and link new
terms to the [glossary](docs/reference/glossary.md). Update setup in `docs/start/`, adoption paths in
`docs/scenarios/`, per-extension pages in `docs/extensions/`, every command example in
`docs/reference/commands.md`, and stages, state and operating rules in `docs/workflow/`.
`docs/reference/hooks.md` is generated: run `python extensions/scripts/check_docs.py --write`
after changing a manifest hook, a preset, or Workflow's stage or hook ownership rules.
Package READMEs ship inside their archives, so they use absolute links for anything outside the package.

Use the [shared booking/refund scenario](docs/README.md#example-conventions). Preserve exact
identifiers in code, distinguish proposed behavior from verified behavior, and write for the
declared audience. Use `my-voice` for concise instructional prose and `illustrate` for useful
visuals. Do not add a summary that repeats a short section.

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
managed workflows from that policy. See [runner configuration](docs/workflow/operations.md#where-your-ci-actually-runs).
Do not infer consumer runner policy from this repository's CI.

## Maintainer records

Design plans, audits, pilot reviews and recorded evidence live in [`docs/internal/`](docs/internal/).
They explain earlier decisions; their version statements describe the recorded experiment, not the
current release. User-facing pages do not link to them; `check_docs.py` enforces this.

- [Documentation overhaul plan](docs/internal/documentation-overhaul-plan.md) and [documentation review](docs/internal/documentation-review.md)
- [Source ownership](docs/internal/workflow-source-ownership.md) and [compatibility evidence](docs/internal/workflow-compatibility.md)
- [Delivery implementation plan](docs/internal/sanduq-delivery-implementation-plan.md) and [verification](docs/internal/sanduq-delivery-verification.md)
- [Workflow implementation plan](docs/internal/workflow-extension-implementation-plan.md), [acceptance audit](docs/internal/workflow-acceptance-audit.md), [progress record](docs/internal/workflow-implementation-progress.md) and [fresh-session prompt](docs/internal/workflow-resume-prompt.md)
- [Workflow pilot review](docs/internal/workflow-pilot-review.md) and [orchestration task design](docs/internal/orchestration-tasks.md)
- [Native prototype results](docs/internal/native-workflow-prototype-results.md) and [illustration](docs/internal/sanduq-native-workflow-prototype.html)
- Recorded evidence: `docs/internal/evidence/`, `docs/internal/workflow-evidence/`, `docs/internal/assets/workflow-plan/`
