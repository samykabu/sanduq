# Contributing to Sanduq

Change the source that owns the behavior, test the package consumers will receive, and include a
usable example. Generated agent registrations and installed consumer copies are not source.

## Table of contents

- [Priority rule](#priority-rule)
- [No third-party names](#no-third-party-names)
- [Set up the checkout](#set-up-the-checkout)
- [Find the owning source](#find-the-owning-source)
- [Test a local package](#test-a-local-package)
- [Validate a change](#validate-a-change)
- [No-behaviour-change rule for cleanup PRs](#no-behaviour-change-rule-for-cleanup-prs)
- [Update documentation and assets](#update-documentation-and-assets)
- [Prepare a release](#prepare-a-release)
- [Release trains](#release-trains)
- [CI and runner policy](#ci-and-runner-policy)
- [Maintainer records](#maintainer-records)

## Priority rule

The [product brief](docs/start/product-brief.md) names the users and the outcomes. Work is ordered by it:

1. Consumer-reported data loss and broken workflows come first. Fix them before any optimization work.
2. No optimization rounds during the stabilization phases (PH-01 and PH-02 of the current plan). Fixes,
   documentation and security work continue.
3. A cleanup pull request shows that behavior does not change: the same tests pass before and after,
   and the description says which checks prove it.
4. Record the agent cost of each release train. See [release trains](#release-trains).

## No third-party names

This repository never names third-party products, customers or their hosts: not in code, tests, fixtures, documentation, evidence, changelogs, commit messages, issues or pull requests. Write "the consumer" or "a private product" instead. The `lint` job greps the tree with a pattern the maintainer keeps in the `PRIVATE_NAMES` repository secret and fails on any match.

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
| Portable skills (Illustrate, User Manual, Delegate Task, Progress Report) | [samykabu/sanduq-skills](https://github.com/samykabu/sanduq-skills); never edit their vendored copies here |
| Vendored skill copies and their pins | `vendor.lock.json`, synced by `extensions/scripts/vendor.py` |
| Claude Code marketplace entries | `.claude-plugin/marketplace.json` (pinned `git-subdir` sources); bundle versions live in sanduq-skills |
| Extension-adapted skill entrypoints | `SKILL.ext.md`; `package.py` restores `SKILL.md` in the archive |
| Extension metadata and commands | `extensions/<id>/extension.yml`, `commands/`, `skills/`, and references |
| Scope runtime, analyst and GitHub clarification | `extensions/workflow/scripts/scope/`, `extensions/workflow/skills/scope-analyst/` and `github-clarification/` (MIT); `extensions/scope/` is the retired 2.0.0 shim |
| Short Scope entry and Bridge router alias skills | `extensions/workflow/skills/speckit-scope/` and `speckit-superpowers-bridge/`; the installer replaces only a recognized legacy alias or an identical owned copy |
| PR visuals contract | `extensions/pr/commands/speckit.pr.generate.md`; generated skills inherit it after installation |
| Managed command policy | Canonical `presets/` (`workflow`, `scope-gate`, `scope-brainstorm`); bundled by package tooling |
| Shared freshness/dependency helpers | `extensions/scripts/shared/`; injected at build time |
| Workflow claims, receipts, evidence, progress, installation and self-upgrade | `extensions/workflow/scripts/` |
| Deterministic ZIPs and releases | `extensions/scripts/package.py` and `release.py` |
| Published versions | `catalog.json` and mirrored `extensions/catalog.json` |
| Reviewed versions awaiting publication | `extensions/pending-releases.json` |
| Human onboarding and examples | README and `docs/` |
| Core Spec Kit and SuperSpec | Their upstream repositories; no vendored fork, tested through installed distributions |
| Other third-party skills a workflow uses | Their upstream sources; no copying or relicensing |
| A consumer's requirements, issue IDs and board settings | That project's policy and configuration, never hardcoded in Sanduq source |

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
python extensions/scripts/smoke_project_init.py
python extensions/scripts/smoke_memory_install.py
```

CI exercises Linux/Windows regression, Codex/Claude and core/SuperSpec installs, transactional
upgrades, Project initialization on Linux and Windows, and Memory registration. Report unavailable
infrastructure and skipped checks accurately; package creation alone is not live acceptance.

## No-behaviour-change rule for cleanup PRs

A cleanup pull request (a merge, a rename, dead-code removal, a simplification) changes no behaviour a
user can reach. Its description shows all four:

1. The affected suites pass, unchanged, before and after (see [Validate a change](#validate-a-change)).
2. The fixture lifecycle gives identical outputs before and after: `test_lifecycle_e2e` passes and
   `python extensions/scripts/benchmark_front_half.py --repo . --tier <lite|standard|full> --out <file>`
   writes the same JSON for each tier once `meta.generated_at` and `meta.repo_head` are ignored.
3. No capability or code path a user can reach is removed. A renamed command keeps its old name as an
   alias with the same output; a migration stays while any released version can have left the state it reads.
4. The line counts of the changed files before and after.

## Update a vendored skill

Change and release the skill in sanduq-skills first (tag `<bundle>-vX.Y.Z`). As a step of each
release train, run the `vendor-update` workflow from the Actions tab: it vendors any newer release,
pins its marketplace entry, and opens a pull request. It opens the pull request with the
`VENDOR_PR_TOKEN` secret (a fine-grained token for this repository with contents and pull-request
write access) so CI starts on its own; renew that token before it expires. The same token opens the
release catalog pull request (`release/catalog-<run id>`) and enables auto-merge on it, because the
`main` ruleset requires a pull request and the lint check. To do the same locally:

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
python extensions/scripts/release.py bump <id> <version>   # writes every copy of the version
python extensions/scripts/release.py prepare --development
python extensions/scripts/release.py publish
python extensions/scripts/release.py check-bumps             # lint: shipped files changed without a bump
```

`check-bumps` fails when a package's shipped files differ from its catalog entry and no newer version is
pending. Edits to only `README.md`, the top-level `CHANGELOG.md`, `LICENSE` or `docs/**` need no bump.

Development preparation cannot be promoted. The publish command above is a dry run without
`--apply`. Keep pending status `implementation-in-progress` until validation is complete; marking
it `ready` authorizes publication.

The [release workflow](.github/workflows/release-extensions.yml) requires successful push CI for
the current `main` commit. It builds deterministic archives, publishes immutable `<id>-vX.Y.Z`
assets, downloads and verifies their SHA-256 bytes, and only then promotes both catalogs. A retry
must verify the same bytes. Never overwrite an existing release asset to repair a version.

## Release trains

Packages ship together in one release train per completed phase, with vendor syncs batched into
the train. The checklist (cumulative upgrade smoke, one retained live run per host, evidence assets,
agent cost and code paths touched) is in [release process](docs/start/release-process.md).

## CI and runner policy

Sanduq's own [CI](.github/workflows/ci.yml) runs on the home-office runner `homek8-general`. The
jobs that run on GitHub-hosted runners, and why, are listed in the red runner exception at the top
of the [README](README.md). Update that exception in the same pull request that changes a `runs-on`.

A consumer records its own runners and capabilities in `.specify/workflow.yml`; Sanduq renders
managed workflows from that policy. See [runner configuration](docs/workflow/operations.md#where-your-ci-actually-runs).
Do not infer consumer runner policy from this repository's CI.

## Maintainer records

Recorded evidence that user pages cite lives in `docs/evidence/`: the round 4 and round 5 live runs
behind the [compatibility matrix](docs/reference/compatibility.md) and the
[benchmarks](docs/evidence/benchmarks/README.md) behind the measured numbers in the changelogs and
upgrade notes. Their version statements describe the recorded run, not the current release.
Earlier design plans, reviews and implementation notes were removed once the work shipped; they
remain in git history.
