# Round 3 review: cross-cutting (stream R6)

Read-only review of what spans the extensions on `feat/round-3` (HEAD 446db34): shared scripts and their
packaged copies, packaging, the installer and upgrade path, CI, docs, and release tooling. Measured on
2026-10-19. Archives were built with `package.package(name, output=<scratch>)` (no `dist/` write);
`smoke_install.py --host claude` ran once (workspace `dist/install-tests/claude-knebwkqx`, ignored by
git); CI numbers come from `gh run view --json jobs` on runs 39299790767 and 39272474099 (pull
requests) and 39306374690 (push to main). Nothing in the tree was changed except this file.

## Summary

- CI wall time per pull request is 46 to 47 minutes and is set by one job: the Windows workflow suite (35.0 and 42.1 min; the same suite takes 5.3 to 5.5 min on Linux). Windows memory takes 14 to 16 min against 1.6 min on Linux.
- An edit to root `CHANGELOG.md`, `README.md`, `extensions/README.md` or `extensions/pending-releases.json`, or to anything under `extensions/project/`, runs all 16 regression jobs plus both memory installs (`ci_matrix.py:57-59`; `project` is not in `SUITES`, line 19), so a release-notes commit costs a full 46-minute run.
- The installer never prunes `.specify/workflow/backups/installs/` (`install.py:737`, one 5.1 to 5.3 MB `before.zip` per apply, 74% of it Illustrate bytes), and it removes and re-adds all three presets on every apply even when nothing changed (6 `specify preset` calls, 9.4 s, on the smoke's fourth apply).
- A release still fans one version out by hand to about five files per extension plus four shared files (round 2's release-notes commit e8f24dc touched 55 files); only some of those copies are checked, and the checks that exist run in different places (check_docs, an inline CI script, the installation smoke).
- Docs carry almost no copied text (5 shared sentences, 831 bytes, across 58 user pages). What they do carry is stale facts that no rule catches: "eight extensions" in three places with Progress missing from the install block, and three root CHANGELOG headings still marked "(pending release)" for versions that are already published.

## Findings per lens

### 1. Shared code and its copies

`package.py` injects five shared files through four hard-coded rules (`package.py:38-57`):

| Injected file | Source | Shipped to | Rule |
| --- | --- | --- | --- |
| `sanduq_freshness.py` | `extensions/scripts/shared/` | assure, user-manual | `:38-40` |
| `sanduq_hash.py` | `extensions/workflow/scripts/` | assure, user-manual | `:41` |
| `sanduq_ci.py` | `extensions/workflow/scripts/` | assure, user-manual | `:44-46` |
| `deps.py` | `extensions/scripts/shared/` | pr, assure, user-manual | `:49-51` |
| `check_inputs.py`, `bounded_json.py` (+ `evidence_snapshot.py` for workflow) | `extensions/scripts/shared/` | memory, workflow | `:52-57` |

No checked-in duplicate of an injected file exists. The only same-named, different-content files are
unrelated modules (`install.py`, `progress.py`, `workflow.py`, `hosts.py`, `lifecycle.py`, `guard.py`
in workflow, memory and progress).

The upstream portable copy, `sanduq-skills/skills/dev-tools/skills/user-manual/scripts/sanduq_ci.py`
(208 lines), differs from `extensions/workflow/scripts/sanduq_ci.py` (328 lines) by 142 diff lines.
Upstream lacks `gate_config`, `validate_gate`, `affected_command`, `verify_command` and
`verification_check` and the `candidate_merge` template flag (workflow `:257`), and
`load_ci(policy_path)` there versus `load_ci(root)` here (workflow `:312-324`). Each copy is called
only by its own `init_manual.py`, so nothing is broken today. The two copies share render logic with
no test that pins them together.

Helpers re-implemented per extension (definitions outside tests, vendored Illustrate excluded):

| Helper | Count | Where |
| --- | ---: | --- |
| `git(...)` subprocess wrapper | 7 runtime + 1 tooling | `memory/git_state.py:52`, `project/project_sync.py:47`, `shared/evidence_snapshot.py:25`, `shared/sanduq_freshness.py:19`, `workflow/sanduq_hash.py:14`, `workflow/source_key.py:88`, `workflow/workflow.py:216`; `scripts/vendor.py:52` |
| atomic or JSON write | 8 | `memory/git_state.py:23,37`, `progress/util.py:83,93,202`, `progress/theme.py:212`, `scope/scope.py:108`, `shared/deps.py:335`, plus `workflow/workflow.py:182` (`write`) |
| `read_json` | 4 + `workflow.read` | `progress/util.py:195`, `project/project_sync.py:59`, `scope/scope.py:104`, `shared/deps.py:324` |
| `digest`/`sha` | 9 | `memory/git_state.py:19`, `scope/accept_plan.py:25`, `scope/clarification.py:23`, `shared/check_inputs.py:44`, `workflow/execution_tools.py:80`, `workflow/verification_plan.py:38`, `workflow/worker_brief.py:184`, `workflow/workflow.py:137`, `scripts/release.py:25` |
| frontmatter parser | 5 | `memory/install.py:37`, `scripts/validate_skills.py:32`, `user-manual/audit_manual.py:24`, `user-manual/manual_impact.py:27`, `workflow/skill_inventory.py:114` |
| YAML reader | `yaml.safe_load` at 26 runtime sites (workflow 16, user-manual 7, assure 3) and a 135-line YAML subset parser in `shared/deps.py:187-322` (deps.py runs where PyYAML may be absent) |

The copies are not equivalent:

- `git` raises five different error types and messages; `project_sync.git` swallows failures and returns `''`.
- Only memory and progress `theme` fsync before replace. Only progress `util` and scope retry the replace for Windows handle locks.
- `scope.write_json` uses a fixed `<file>.tmp` name (`scope.py:110`), where workflow uses a uuid suffix (`workflow.py:184`).

All of these copies together come to about 100 to 150 lines. Merging them would save little code, and
it would change error contracts that tests pin (see X9).

### 2. Packaging

Archives built from this tree (zip size, unpacked size, files):

| Extension | Zip | Unpacked | Files | Largest parts (unpacked) |
| --- | ---: | ---: | ---: | --- |
| illustrate | 3,532 KB | 10,450 KB | 515 | `skill/assets` 7,340 KB (280 files, 267 `example-*.html`), `skill/scripts` 1,041 KB, `skill/references` 709 KB |
| workflow | 741 KB | 1,728 KB | 158 | `scripts` 863 KB, `assets/delegate-task` 470 KB (of which README images 251 KB: two PNG 195 KB, two SVG, two HTML), `CHANGELOG.md` 70 KB |
| progress | 211 KB | 594 KB | 53 | `scripts` 339 KB, `docs` 130 KB, `assets/ui` 72 KB |
| memory | 106 KB | 324 KB | 34 | `scripts` 252 KB |
| scope | 95 KB | 257 KB | 42 | `scripts` 172 KB |
| user-manual | 69 KB | 155 KB | 46 | `scripts` 91 KB |
| assure | 48 KB | 116 KB | 22 | `scripts` 77 KB |
| pr | 33 KB | 79 KB | 12 | `scripts` 41 KB |
| project | 24 KB | 63 KB | 10 | `scripts` 46 KB |

Tests and caches are excluded (`package.py:12-15`). Content that ships but that no consumer process
reads:

- `progress/docs/` (130 KB). `skills/progress/references/verbs.md:4` says `docs/contracts.md` and `docs/commands.md` are "human references, not needed to run a verb".
- The delegate-task README images in workflow (251 KB). Delegation needs only `delegate.mjs`, `SKILL.md` and `contracts/result-schema-v2.md` (`delegation.py:813`).
- The nine `CHANGELOG.md` files (134 KB in total, workflow 72.7 KB). The catalog entry already links the changelog URL (`release.py:73`).
- Illustrate: `SKILL.md:55` tells the model to copy "the closest template or example", so examples are runtime inputs. But each diagram type ships five variants (`-dark`, `-full`, `-hand`, `-animated`, base), and the `example-*.html` files total 7.3 MB. That is an upstream decision for sanduq-skills (stream R5), noted here only because it dominates install size and backups (lens 3).

### 3. Installer and upgrade path

`smoke_install.py --host claude` passed in 44.3 s on this machine (Windows 11, `specify 1.1.4.dev0`).
It ran 18 commands; per-command times come from log mtimes:

| Step | Time |
| --- | ---: |
| `specify init` | 0.8 s |
| `specify extension add --dev workflow` | 1.7 s |
| `install.py --apply`, policy off/off (4 extension adds, 3 preset adds) | 7.8 s |
| `install.py --apply`, qa on (1 add, 3 preset remove + 3 add) | 9.9 s |
| `install.py --apply`, manual on (1 add, 3 preset remove + 3 add) | 10.5 s |
| `install.py --apply`, both on, **no extension change** (3 preset remove + 3 add) | 9.4 s |
| 4 x `workflow.py init`, 4 x `doctor`, 3 x `progress.py`, reinstall | about 5 s |

The four installer applies take 37.6 of the 44.3 s. Presets are always removed and re-added
(`install.py:690-694` builds `preset_ops` unconditionally, and the apply loop runs remove and add for
each). The extension loop does skip same-version extensions (`install.py:670`). One `snapshot()` of the
smoke project measured 0.64 s, 953 files, 14.4 MB raw, 5.29 MB zipped, 10.7 MB of the raw bytes from
Illustrate.

What a full install writes into a consumer (the smoke project after four applies): 976 files and
31.1 MB, of which:

- `.specify/workflow/backups`: 15 files, 16.8 MB (four `before.zip` of 1.2 to 5.2 MB)
- `.specify/extensions/illustrate`: 519 files, 10.5 MB
- `.specify/extensions/workflow`: 173 files, 1.8 MB
- `.claude/skills`: 46 skill folders, 206 KB

Without the backups, a full install is about 961 files and 14.3 MB. Backups are never pruned:
`install.py` creates `backups/installs/<uuid>` on every apply (`:737`), and no `rmtree` or unlink
touches that folder (the only `rmtree` is `:423`, a temp dir). `RENDER_SKIP` (`:350`) only keeps them
out of rendering.

Separate `specify extension add` calls:

- **Manual path:** 8 in the documented block (`docs/start/install-by-host.md:98-111`), 9 with Progress, which the block omits.
- **Workflow path:** the user runs 1 (`workflow`). The installer then runs 4 for the required extensions (`illustrate`, `project`, `scope`, `pr`), 1 per selected process (assure, user-manual) and 1 for Progress with `--with`.
- **Memory:** outside the workflow installer (`extensions/workflow/dependencies.json` has no `memory` key). It needs its own `specify extension add memory` plus its own init.

`smoke_install.py:30` packages eight extensions and never memory; memory has its own smoke
(`smoke_memory_install.py`, CI job `memory-installation`).

Three sources hold the compatible-version ranges: `requires` in each `extension.yml`, the pins in
`workflow/dependencies.json`, and `RANGES` in `workflow.py:42-43`. Illustrate is missing from `RANGES`
and falls back to the default `'>=2.1.2,<3'` (`install.py:674`).

### 4. CI

Jobs per pull request: 24 to 28.

- `changes`, `lint`, `dryrun`
- 4 `installation` (host x provider)
- `upgrade`
- 2 `project-init`
- 2 `memory-installation`
- up to 16 `regression` jobs: 8 suites x 2 OS, with Windows workflow on pull requests and nightly only (`ci_matrix.py:23`)

| Run | Event | Wall | Runner-minutes (job sum) | Critical path |
| --- | --- | ---: | ---: | --- |
| 39299790767 | PR, round 2 | 46.1 min | 122.4 | Windows workflow 42.1 (unittest step 41.6) |
| 39272474099 | PR, issue 94 | 47.3 min | 112.6 | Windows workflow 35.0 (33.2) |
| 39306374690 | push main | 20.2 min | 75.4 | Linux illustrate 15.2 (lint-render 10.4), Windows memory 14.4 (14.1) |

Other measured points:

- **Windows against Linux, same suite.** Workflow: 33.2 to 41.6 min against 5.3 to 5.5 min. Memory: 14.1 to 15.6 min against 1.6 min. The workflow suite has 1,183 test methods, 59 `git init` sites, 146 subprocess call sites and 91 temp-dir sites; `test_delegation.py` alone is 234 KB. Process and git spawn cost on Windows is the likely cause; it was not profiled here.
- **Illustrate.** Rendered-layout lint takes 10.4 to 10.8 min on Linux and 4.9 to 6.7 min on Windows; Playwright install adds 1.1 to 3.8 min. 504 of Illustrate's 556 files are vendored, byte-checked against `vendor.lock.json`, and upstream CI already runs the same builders, verifiers and `lint-render.py --all` on Ubuntu and Windows (`sanduq-skills/.github/workflows/ci.yml:70-108`).
- **Setup steps** (checkout, setup-python, pip, Playwright, Spec Kit) add up to 23.7 and 21.9 runner-minutes per run (20% to 30% of step time). No `setup-python` step sets `cache: pip`, and Playwright's browser is downloaded on every illustrate job (`ci.yml:207-212`). Spec Kit is pip-installed from git seven times per pull request (`ci.yml:257,281,330`: installation x4, upgrade, memory-installation x2).
- **Path filter.**
  - Simulated with `ci_matrix.py --files`: root `CHANGELOG.md`, `README.md`, `extensions/README.md` and `extensions/pending-releases.json` each give 16 regression jobs and `memory_install=true`. So does `extensions/project/scripts/project_sync.py`, because `project` is not a suite.
  - `extensions/workflow/CHANGELOG.md` alone gives 4 jobs, including the 35 to 42 min Windows workflow suite.
  - `docs/start/upgrades.md` gives 0 regression jobs. Even then, `installation`, `upgrade`, `project-init` and `dryrun` have no `needs: changes` gate and always run, about 13 runner-minutes.
- **Action pinning.** Repository CI uses tag refs (`actions/checkout@v4`, `ci.yml:22` and every job). The consumer templates this repo ships pin SHAs (`workflow-gates.yml:20`, `documentation-gates.yml:17`).

### 5. Docs

- **Duplication.** Across 58 user-facing pages (nine extension READMEs, `docs/extensions/*`, `docs/workflow/*`, `docs/start/*`, `docs/reference/*`, `docs/*.md` and the root README, 416 KB), only one 25-word paragraph and five 12-word sentences are shared, 831 bytes in total. Most of that is between `docs/workflow/operations.md` and `extensions/workflow/README.md`. Extension READMEs and `docs/extensions/<id>.md` pages share at most two section headings (progress: "limits", "plans outside spec kit"). The documentation overhaul already removed the copies.
- **Install command.** `specify extension add` appears 46 times across those pages, 14 of them in `install-by-host.md`. That repetition is by design (one line per recipe). None of them pins a version.
- **Pages over 30 KB:**
  - `extensions/workflow/CHANGELOG.md` 72.7 KB (ships)
  - `extensions/progress/docs/contracts.md` 60.3 KB (ships)
  - `extensions/progress/docs/commands.md` 51.5 KB (ships)
  - `docs/workflow/delegation.md` 46.7 KB
  - root `CHANGELOG.md` 40.3 KB
  - The next largest user page is `extensions/progress/README.md` at 27.8 KB.
- **Stale facts:**
  - `docs/reference/glossary.md:45` says "Sanduq has eight extensions".
  - `docs/start/install-by-host.md:46,78,98` say "all eight", and the block at 101-110 omits Progress.
  - `extensions/README.md:3` says nine.
  - The root `CHANGELOG.md:3,8,12` headings say "(pending release)" for Workflow 1.14.0, 1.13.1 and 1.13.0 and their companions. All of those are published (`gh release list`: `workflow-v1.14.0`, `workflow-v1.13.1`, `workflow-v1.13.0`, `assure-v2.3.4`, `scope-v1.8.0`, `scope-v1.8.1`; `catalog.json` at 1.14.0), and `pending-releases.json` is `released` with no versions.
  - The root changelog's preamble ("All notable changes…") sits at line 25, below three entries.
- **What `check_docs.py` checks today** (`:142-212`): links and anchors, no user link into `docs/internal`, banned terms, `extension.yml` description equal to the command frontmatter, a usage example per command, the `extensions/README.md` version row, overlays in the lifecycle guide, skill sources documented, and the generated hooks page. It does not check:
  - extension counts and install lists against `extensions/*/extension.yml`
  - `dependencies.json` pins against manifest versions
  - per-extension CHANGELOG headings for the manifest version
  - "(pending release)" markers against the catalog
  - prose version mentions (`README.md:137-146`, `docs/start/upgrades.md:77`)
  - a page-size budget

### 6. Release tooling

Steps done by hand for each release (all of them were done in this session; round 2 is commit
e8f24dc, 55 files):

| Step | Files | Checked by | Could a script do it? |
| --- | --- | --- | --- |
| Bump `extension.version` | `extensions/<id>/extension.yml` | pending/manifest equality in the inline CI script (`ci.yml:114-118`) | yes |
| Version row | `extensions/README.md` table | `check_docs.py:190-192` (check only, no `--write`) | yes |
| Workflow pins | `extensions/workflow/dependencies.json` | only at install time, `STAGED_PACKAGE_IDENTITY_MISMATCH` (`install.py:680`), so in the 2-minute `installation` jobs | yes |
| Pending versions and status | `extensions/pending-releases.json` | `release.py:49-57`, CI script | yes (status `ready` stays a human decision) |
| Changelog headings | nine `extensions/<id>/CHANGELOG.md`, root `CHANGELOG.md` | nothing | headings yes, prose no |
| Prose versions | `README.md:137-146`, `docs/start/upgrades.md:77` | nothing | the version list yes, prose no |
| Vendor and marketplace re-pin | `vendor.lock.json`, vendored trees, both marketplaces | `vendor.py check`, inline CI script | already one command (`vendor.py update`, `:129-147`); it does not name or bump the extensions that ship the changed inputs (the vendor PR body says to do that by hand, `vendor-update.yml:64`) |
| After publish: clear "(pending release)" | root `CHANGELOG.md` | nothing | yes, in `release.py promote` |
| Follow-up test pin fixes | e.g. a0fbbd5 "read the pinned Progress version from dependencies.json" | — | avoided when tests read pins from the source |

`release.py` covers prepare, publish and promote (`:48-148`) and says it never changes source versions
(`:2-7`). Everything above it, from "bump" up to "ready", is manual.

## Defects

| Defect | Effect | Where |
| --- | --- | --- |
| Install backups are never pruned | Each `install.py --apply` (every `workflow init`, upgrade and host switch that reinstalls) leaves a 5 MB zip in the consumer; four applies gave 16.8 MB | `extensions/workflow/scripts/install.py:737`, `:202-212` |
| Presets are removed and re-added on every apply | 6 Spec Kit calls and about 9 s on an apply that changes nothing | `install.py:690-694` |
| Release-metadata files and `extensions/project/**` select every suite | A changelog-only commit costs a 46-minute, 16-job run | `.github/scripts/ci_matrix.py:19,57-59` |
| `installation`, `upgrade`, `project-init` and `dryrun` ignore the `changes` job | They run on docs-only changes (about 13 runner-minutes) | `.github/workflows/ci.yml:266-376` |
| Root CHANGELOG keeps "(pending release)" after publication | Readers see released versions as unreleased | `CHANGELOG.md:3,8,12` |
| Extension count is wrong and the install block omits Progress | A manual full install misses Progress | `docs/reference/glossary.md:45`, `docs/start/install-by-host.md:46,78,98-111` |
| Illustrate is missing from `RANGES` | The newer-version retention check uses the generic default range by accident | `extensions/workflow/scripts/workflow.py:42-43`, `install.py:674` |
| `scope.write_json` uses a fixed temp name | Two writers of the same file race on `<file>.tmp` (low likelihood) | `extensions/scope/scripts/scope.py:108-110` |
| Repository CI actions are tag-pinned, shipped templates SHA-pinned | Inconsistent supply-chain policy | `ci.yml:22` and other jobs, against `extensions/workflow/assets/github/workflow-gates.yml:20` |

## Candidate options

Cost basis. These options change no consumer instruction text, so `tok` is the share of model tokens
per consumer run and is 0 unless stated. `time` is a fraction of the named pipeline:

- **CI:** pull-request wall time 46 to 47 min; push to main 20 to 32 min; runner-minutes 75 to 122 per run.
- **Install:** the 44.3 s smoke.
- **Release:** maintainer preparation time per release. This one was not measured; the evidence is the 55-file round-2 commit.

Observability, evidence gates, receipts and GitHub decisions stay intact in every option.

### X1. One command for the version fan-out

- title: `release.py bump` writes every version copy, and `promote` clears the pending markers
- what:
  - Add a `bump` action to `extensions/scripts/release.py` that takes `id=X.Y.Z` pairs and writes, in one transaction:
    - `extension.yml` `extension.version`
    - the `extensions/README.md` row in the exact form `check_docs.py:190` expects
    - every `dependencies.json` pin naming that id (`required`, `selected`, `optional`)
    - `pending-releases.json` `versions`, with status set to `pending`
    - a `## [X.Y.Z] - <date>` heading in `extensions/<id>/CHANGELOG.md` if missing
  - Add `--from-vendor` to derive the ids from the `vendor.lock.json` inputs whose `ref` changed against `main` (each input's `map` already names its extension), with a patch bump. `vendor-update.yml` can then open a PR with those bumps included instead of the note at `:64`.
  - Extend `promote` (`release.py:132-148`) to rewrite " (pending release)" off the root `CHANGELOG.md` headings that name the promoted versions.
  - Prose (changelog bullets, README "adopt" paragraphs) stays human-written.
- effort: M
- tok: [0, 0]
- time: [0.3, 0.5] of release preparation. Of the 55 files in e8f24dc, about 30 carry only a version, a pin, a row or a heading.
- obs: improved. The pending file, catalog and changelogs agree by construction, and stale "(pending release)" headings stop accumulating.
- policy: none. Marking `ready` stays a manual edit, so publication remains a human decision.
- pros: Removes the most error-prone part of a release. Reuses `package.ROOT` and the YAML already loaded in `release.py`. Vendor PRs arrive release-ready.
- cons: Writing `extension.yml` needs a version-only line replacement to keep comments and order; `yaml.safe_dump` would reformat the file. Two release paths exist until maintainers adopt it.
- files: `extensions/scripts/release.py`, `.github/workflows/vendor-update.yml`, `CONTRIBUTING.md` ("Prepare a release"), `extensions/scripts/tests/test_release_bump.py` (new).
- tests: Add bump tests on a fixture tree: every copy is updated, unrelated lines are byte-identical, a second run is a no-op, a lower version is refused. Add a promote test: only the promoted headings lose the marker. Keep green: `extensions/scripts/tests/*`, `check_docs.py`.

### X2. Make check_docs catch the version and count drift

- title: Five consistency rules in `check_docs.py` and fixes for the current stale facts
- what:
  - Add rules to `extensions/scripts/check_docs.py`:
    1. every `dependencies.json` pin equals that extension's source `extension.yml` version (moves the check from the install smoke into lint)
    2. each `extensions/<id>/CHANGELOG.md` has a heading for its manifest version
    3. root `CHANGELOG.md` has no "(pending release)" heading naming a version already in `catalog.json`
    4. sentences matching `(\w+) extensions` and the `install-by-host.md` add-all block agree with the number and ids of `extensions/*/extension.yml`
    5. user pages over 30 KB fail unless listed in an allow-list (today: `docs/workflow/delegation.md`)
  - Fix `glossary.md:45` and `install-by-host.md:46,78,98-111` (nine, with Progress), and the three root CHANGELOG headings.
  - Add `illustrate` to `RANGES`.
- effort: S
- tok: [0, 0]
- time: [0, 0.02] of CI. Pin mismatches fail in the 1-minute lint job instead of the installation jobs.
- obs: improved. Drift that today reaches users or the smoke is reported with file and line.
- policy: none.
- pros: Small and local. Moves checks earlier. Works with or without X1 (X1 writes, X2 verifies).
- cons: The count rule needs a narrow pattern to avoid false hits. The size rule needs an allow-list someone maintains.
- files: `extensions/scripts/check_docs.py`, `extensions/scripts/test_check_docs.py`, `docs/reference/glossary.md`, `docs/start/install-by-host.md`, `CHANGELOG.md`, `extensions/workflow/scripts/workflow.py` (`RANGES`).
- tests: One failing fixture per rule in `test_check_docs.py`. `check_docs.py` passes on the fixed tree. The workflow `test_install` range tests stay green.

### X3. Path filter for release metadata, project, and the always-on jobs

- title: Lint-only for changelogs, READMEs and pending releases; a `project` suite; gate the smoke jobs
- what:
  - In `.github/scripts/ci_matrix.py`, classify these as lint-only: root `CHANGELOG.md`, `README.md`, `CONTRIBUTING.md`, `extensions/README.md`, `extensions/*/CHANGELOG.md`, `extensions/*/README.md` and `extensions/pending-releases.json`. Lint already validates pending/manifest/catalog (`ci.yml:91-163`) and links (`check_docs.py`).
  - Map `extensions/project/**` to no regression suite. It has no tests directory; `dryrun` and the installation smoke cover it.
  - Emit an `install_smoke` output, true when anything other than lint-only or `docs/` changed, and add `needs: changes` with that condition to `installation`, `upgrade`, `project-init` and `dryrun`. Skipped jobs already count as success for the release gate (`ci.yml:14`).
- effort: S
- tok: [0, 0]
- time: [0.9, 0.97] of a metadata-only or docs-only run (46 min to about 2 min; 110 to 13 runner-minutes). [0.05, 0.15] averaged over recent runs: three of the last twelve were docs commits (39262087580, 39157711304, 39157690521), and two of those took 29 and 42 min.
- obs: unchanged. Nightly and `workflow_dispatch` still run everything (`ALWAYS_ALL`).
- policy: none.
- pros: The cheapest large saving. The rules are explicit and testable offline (`--files`).
- cons: A README change that breaks an installed skill path would be caught nightly, not on the PR. A pending-release edit that should have re-run the smoke relies on lint plus the release workflow's own CI check.
- files: `.github/scripts/ci_matrix.py`, `.github/workflows/ci.yml`, `extensions/scripts/tests/test_ci_matrix.py`.
- tests: Extend `test_ci_matrix.py`: each lint-only path gives no regression and `install_smoke=false`; a project script gives no regression and `install_smoke=true`; mixed changes keep today's result; schedule still runs everything.

### X4. Shard the Windows workflow suite and give Windows memory the same event rule

- title: Split the critical-path Windows suites across parallel jobs
- what:
  - Let `ci_matrix.py` emit a `shard` key for the Windows workflow suite: four shards, with `test_delegation.py` (234 KB, the largest module) in its own shard and the other 54 modules round-robin by file size.
  - Run `unittest` on the shard's module list instead of `discover` (`ci.yml:213`).
  - Apply `WINDOWS_WORKFLOW_EVENTS` to Windows memory as well, so a push to main skips it like the workflow suite.
  - Profile the Windows suite once (`python -X importtime`, `--durations` via a small `unittest` result hook) and record the ten slowest tests in the PR. The likely cause, git and process spawn, gets its own follow-up.
- effort: S (sharding), M with a profiling follow-up
- tok: [0, 0]
- time: [0.55, 0.65] of PR wall time. Critical path 42 min to about 11 to 13 min per shard; illustrate (13 to 16 min) and Windows memory (15 min) then set the floor. [0.25, 0.3] of push wall time when memory Windows leaves pushes. Runner-minutes rise by about 3 setups (about 2 min).
- obs: unchanged. The same tests run on the same events.
- policy: none.
- pros: Removes the half-hour wait on every PR. No test changes.
- cons: A test that depends on module order or on shared temp state could surface. Shard lists need a rule-based split, not a hand list. Pushes to main lose Windows memory coverage until the nightly run.
- files: `.github/scripts/ci_matrix.py`, `.github/workflows/ci.yml`, `extensions/scripts/tests/test_ci_matrix.py`.
- tests: `test_ci_matrix.py` checks that the shards cover every `test_*.py` exactly once and that push events omit both Windows suites. One CI run must show the same test count as unsharded.

### X5. Cache the setup

- title: pip cache, Playwright browser cache, one Spec Kit wheel
- what:
  - Add `cache: pip` with `cache-dependency-path` (the requirements files) to every `actions/setup-python` step.
  - Cache `~/.cache/ms-playwright` (and `%LOCALAPPDATA%\ms-playwright` on Windows) keyed on `playwright==1.63.0` and the OS, and run `playwright install-deps` only on a cache miss.
  - In `changes`, build the pinned Spec Kit commit into a wheel once and pass it on as an artifact, or cache pip's wheel of the git URL, so the seven git installs become wheel installs.
  - Optionally pin repository actions by SHA in the same pass, to match the shipped templates.
- effort: S
- tok: [0, 0]
- time: [0.08, 0.15] of runner-minutes (of 22 to 24 setup minutes per run, about half is downloads); [0, 0.05] of wall time, since tests dominate the critical path.
- obs: unchanged.
- policy: none.
- pros: Less network flakiness. Smaller self-hosted runner load.
- cons: The self-hosted `homek8-general` runners must reach the Actions cache service. A stale browser cache needs the version in the key.
- files: `.github/workflows/ci.yml`, `.github/workflows/release-extensions.yml`, `.github/workflows/vendor-update.yml`.
- tests: Two consecutive CI runs: the second shows cache hits and the same results.

### X6. Run the vendored Illustrate verifiers only when the vendored bytes change

- title: Illustrate's own tests on every change; upstream builders, verifiers and render lint on vendor bumps and nightly
- what:
  - Today every illustrate regression job runs the 42 own tests, then 25 builder and verifier commands and `lint-render.py --all` over the vendored skill (`ci.yml:214-239`). That is 10 to 13 min per OS for files that `vendor.py check` proves are byte-identical to an upstream tag, whose own CI ran the same commands on both OSes.
  - Add a `illustrate_vendored` output to `ci_matrix.py`: true when `vendor.lock.json`'s `illustrate` input or anything under `extensions/illustrate/skill/` changed, and on schedule.
  - Run the builders, verifiers and render-lint steps only when it is true. Keep the unittest step and Playwright for the own tests that need it.
- effort: S
- tok: [0, 0]
- time: [0.2, 0.3] of push wall time (the illustrate job stops being the 15-min critical path; Windows memory at 14 min becomes the floor unless X4 also lands). About 20 of 29 illustrate runner-minutes per run.
- obs: unchanged. Vendor bumps and nightly still render-lint everything.
- policy: none.
- pros: Stops paying twice for upstream's verification. Illustrate PRs that touch only commands or hooks become fast.
- cons: A Playwright or Chromium difference between the two repositories' CI would be noticed only nightly. Both pin Playwright; the upstream pin should be compared before landing.
- files: `.github/scripts/ci_matrix.py`, `.github/workflows/ci.yml`, `extensions/scripts/tests/test_ci_matrix.py`.
- tests: `test_ci_matrix.py`: a change to `extensions/illustrate/commands/x.md` gives illustrate without vendored checks; a `vendor.lock.json` change gives both; schedule gives both.

### X7. Installer: prune backups and skip unchanged presets

- title: Keep the last three install snapshots, and add a preset only when it differs
- what:
  - **Pruning.** After a successful apply in `extensions/workflow/scripts/install.py` (after the result is written, `:737` onward), delete `before.zip` from all but the three newest `backups/installs/*` folders. Keep every `result.json` and `before.json` (hash lists, a few KB) as the audit trail. A failed apply prunes nothing.
  - **Presets.** For each preset in `preset_ops` (`:690-694`), compare the bundled `preset.yml` version and a sha256 over the bundled preset files with the installed `.specify/presets/<name>`. Skip remove and add when equal, and record `skipped_presets` in the result.
  - Report both in `doctor`: the backup count and bytes.
- effort: S
- tok: [0, 0]
- time: [0.3, 0.45] of the install smoke (the three re-applies spend about 7 of their 9 to 10 s on preset calls). Consumer `workflow init` and upgrade re-runs save about 9 s when presets are unchanged. Disk: a consumer keeps at most about 15 MB of snapshots instead of 5 MB per apply forever.
- obs: unchanged for rollback (the snapshot of the running apply is always taken). Improved: the result names skipped presets, and doctor reports backup size.
- policy: none. Three is a constant. A `workflow.yml` key would be flexibility nobody asked for.
- pros: Fixes unbounded growth in consumer repositories. Fewer Spec Kit calls means fewer chances of a partial preset state.
- cons: Older snapshots lose their zip, so manual restore beyond three applies is gone (the hashes remain). The preset comparison must include priority, since the `--priority` argument is part of the registration.
- files: `extensions/workflow/scripts/install.py`, `extensions/workflow/scripts/workflow.py` (doctor), `extensions/workflow/tests/test_install.py`, `extensions/workflow/CHANGELOG.md`, `docs/workflow/state-files.md` (backups section).
- tests:
  - New: four applies leave three zips and four result files; a failed apply prunes nothing; an apply with unchanged presets runs no `specify preset` command; a changed preset file runs remove and add.
  - Keep green: the `test_install.py` rollback tests and `smoke_install.py` (whose same-version reinstall assertions at `:91-97` still hold).

### X8. Ship only what a consumer runs

- title: Exclude human-only docs, README images and changelogs from archives
- what:
  - Extend `EXCLUDE_PATHS` in `extensions/scripts/package.py:17`:
    - progress `docs` (130 KB; `verbs.md:4` says it is not needed)
    - workflow `assets/delegate-task/assets` (251 KB of README PNG, SVG and HTML; `delegation.py:813` requires only three files)
  - Add `CHANGELOG.md` at the extension root to the per-file excludes for all nine (134 KB; the catalog links it, `release.py:73`).
  - Change the one Progress reference line to the GitHub URL of the docs.
  - Leave Illustrate's examples to upstream (stream R5). Five variants per type and 7.3 MB of `example-*.html` are the single largest install and backup cost, and choosing which variants the copy step needs is a sanduq-skills change.
- effort: S
- tok: [0, 0]
- time: [0, 0.01] of install. Size: workflow -19% unpacked (1,728 to about 1,400 KB), progress -22% (594 to about 465 KB), others -2% to -8%.
- obs: unchanged. `package-inventory.json` still hashes every shipped file.
- policy: none.
- pros: Smaller downloads and smaller install snapshots. No behaviour change.
- cons: An installed delegate-task README shows broken image links (it is a vendored README, read on GitHub). Offline users lose the local changelog. Spec Kit was not checked for any use of a package's CHANGELOG; confirm in `spec-kit/src/specify_cli/extensions` before landing.
- files: `extensions/scripts/package.py`, `extensions/progress/skills/progress/references/verbs.md`, `extensions/scripts/tests/test_package_check_helpers.py` (or a new packaging test).
- tests: A packaging test asserts the excluded paths are absent and `SKILL_FILES` present. `smoke_install.py` on both hosts. `test_delegation.py` install tests stay green.

### X9. One shared I/O helper module (defer)

- title: `sanduq_io.py` for git, JSON read and atomic write, injected like `check_inputs.py`
- what:
  - Add `extensions/scripts/shared/sanduq_io.py` with three functions:
    - `git(root, *args, text=False)`, raising one `GitError` with the stderr
    - `read_json(path, default)`, utf-8-sig
    - `atomic_write(path, data)`, with a uuid temp name, fsync, and the Windows replace retry from `progress/util.py:93`
  - Inject it with one more `package.py` rule into every extension that has scripts.
  - Migrate the copies listed in lens 1, one extension per commit, each keeping its own error code by catching `GitError` at the call site.
  - This also fixes the `scope.write_json` fixed temp name.
- effort: M
- tok: [0, 0]
- time: [0, 0]
- obs: unchanged, provided each call site keeps its error code.
- policy: none.
- pros: One Windows-safe write path. Removes about 100 to 150 lines and the five divergent git error shapes.
- cons:
  - Touches hot, well-tested code in seven extensions for little measured gain.
  - Error messages are pinned by tests (for example workflow `GIT_ERROR`, memory `git_state`).
  - Progress deliberately avoids `tempfile` imports on its hook path (`util.py:95`), so it may need to keep its own.
  - Recommendation: fix only `scope.write_json` (one line, uuid name) now, and defer the rest.
- files: `extensions/scripts/shared/sanduq_io.py` (new), `extensions/scripts/package.py`, call sites in `workflow`, `scope`, `memory`, `progress`, `project`, `shared/evidence_snapshot.py`, `shared/sanduq_freshness.py`, `extensions/scripts/tests/test_package_deps.py`.
- tests: Unit tests for the module (replace retry, no partial file on error); every extension suite on both OS; `test_package_deps.py` asserts the injection.

## Not verified

- Why the Windows suites are 8 to 9 times slower than Linux. No profile was taken; the git and process-spawn explanation is an inference from call-site counts.
- Whether Spec Kit reads a package's `CHANGELOG.md` (X8).
- Whether the Playwright pins match between this repository and sanduq-skills (X6).
- The Codex host smoke, the upgrade smoke and the memory smoke were not run.
- The release-preparation time behind X1 was not measured.
