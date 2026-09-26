# Changelog

All notable changes to sanduq extensions/plugins are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/). Extensions are versioned
independently via `<extension>-vX.Y.Z` tags.

## Model-aware delegation — workflow 1.5.0, delegate-task driver contract

### Added

- Workflow 1.5.0 adds opt-in model-aware delegation of stages and tasks through the bundled
  `delegate-task` skill. See [`extensions/workflow/CHANGELOG.md`](extensions/workflow/CHANGELOG.md)
  and the [workflow guide](extensions/workflow/README.md#optional-model-aware-delegation).
- `delegate-task` gains `node delegate.mjs contract`, which prints the machine-readable
  `delegate-task.driver.v1` contract: commands, start and collect flags, `DELEGATE_RUNS_DIR`,
  exit codes and published result fields, including `requested_model`, `actual_model` and
  `model_observed`. A contract test checks that every listed field appears in a real result.
  The workflow reuses an installed copy only when this contract matches.
- The exit-5 start failure (supervisor never acknowledged) is produced by an exported
  `finalizeStartFailure`, and a contract test pins the never-launched result the workflow
  relies on to try the next configured route safely.

### Fixed

- `delegate.mjs` did nothing when started through a symlinked skill folder. Its entry-point
  check compared the link path with the module's real path, so every command, including
  `contract`, printed nothing and a symlinked install looked incompatible. It now compares
  real paths, and a contract test runs the driver through a symlink.
- Workflow 1.5.0 review follow-up: dispatcher ledger writes no longer count as worker edits
  (and a worker's ledger edit hidden by a later dispatcher save still does), symlinked and
  Windows-junctioned skill folders survive install and upgrade rollback as the same kind of
  link (dangling links included) and are never replaced by `doctor`, upgrades and
  dispatchers no longer race over live ledger records, a stale upgrade or install lock is
  named with its owner process and how to clear it, documentation-file tasks route to documentation, and
  a failing driver copy is refreshed where it is or reported. See the workflow changelog.
- A skill install no longer deletes a dangling project `delegate-task` junction; the link is
  backed up and restored if the install fails. Rollback recreates junctions without `cmd`, so a
  target containing `%OS%`, `&`, `^` or `!` comes back exactly.
- `extensions/scripts/package.py` no longer ships local test and lint caches. A workflow archive
  built after a local `pytest` run carried `workflow/.pytest_cache/*`; `.pytest_cache`,
  `.mypy_cache`, `.ruff_cache`, `.hypothesis`, `.tox`, `.nox`, coverage output and `.pyo` files
  are now excluded, and a test builds the archive after the suite has run.
- Workflow lock release now tolerates transient Windows file-sharing conflicts
  while rechecking ownership before each retry.

## CI runners are a project decision — workflow 1.2.0, assure 2.2.0, user-manual 1.2.0 — 2026-09-22

### Changed

- **The four shipped CI workflow files are now templates rendered from a project-level selection,
  not copies.** `workflow-gates.yml`, `documentation-gates.yml`, `user-manual-preview.yml`, and
  `user-manual-release.yml` each hard-coded `runs-on: ubuntu-latest`, and the installer wrote them
  into the consumer repository byte for byte. Adopting Sanduq therefore committed a project to
  GitHub-hosted runners without ever asking, and a project that had to run elsewhere could only
  fork the file and lose managed updates to it.
- Added a `ci` section to `.specify/workflow.yml`, validated by the policy schema, recording
  `provider`, `policy`, per-platform `runners`, `capabilities`, and `exceptions`. `init` asks for
  it once, and `workflow.py ci` records or shows it without hand-editing YAML.
- The shipped default is GitHub-hosted and renders the previous files unchanged, so an existing
  project that never records a selection sees no change to its CI.
- Unified the Python version across the shipped assets. The workflow gate asked for 3.13 while
  both User Manual workflows asked for 3.12; the version is now one `ci.capabilities` value.
  Nothing in the User Manual toolchain constrained it to 3.12.

### Added

- `ci.capabilities` carries what the runner can actually do, not just its label. `system_packages:
  preinstalled` removes the `sudo apt-get` steps that install `age` and the Pango/HarfBuzz
  libraries, and `python: preinstalled` removes `actions/setup-python`. Swapping only the runner
  label would have produced jobs that fail on a self-hosted container; these two knobs are what
  make a self-hosted selection actually run.
- `ci.policy: self-hosted-required` for projects that forbid GitHub-hosted runners. Each workflow
  still on a hosted runner then needs a dated `ci.exceptions` entry naming the reason and what
  would remove it, and `doctor` reports `CI_HOSTED_RUNNER_UNDOCUMENTED` until it exists. The
  default `hosted-allowed` requires nothing.
- `doctor` reports `CI_WORKFLOW_STALE` when a workflow file no longer matches what the current
  selection renders, which is what a changed selection that was never re-installed looks like.
  A file explicitly kept with `--preserve-ci` is excluded; that file belongs to the project.
- `provider: none` for projects that want Sanduq to manage no workflow files at all.
- `sanduq_ci.py` lives in `extensions/workflow/scripts/` beside `sanduq_hash.py`, the existing
  convention for a module this repository shares outward, and `package.py` vendors it into the
  `assure` and `user-manual` archives from there. It was first placed in `extensions/scripts/shared/`
  with an import fallback onto the source tree; `project-init.sh` runs `workflow.py` from
  `.specify/extensions/workflow/scripts/`, a plain copy with no package layout, where that fallback
  resolves to nothing and the runtime dies on import. Every test imported from the source tree, so
  none of them noticed. `test_the_runtime_works_from_a_copied_scripts_directory` now runs the
  runtime from exactly that layout.
- A template stays valid YAML before rendering, so the lint job and editor tooling still parse it.
  Substitution tokens are plain scalars (`__sanduq_runs_on_linux__`) rather than anything starting
  with `@`, which is a YAML reserved indicator, and optional steps are delimited by comments.
- `extensions/scripts/shared/sanduq_ci.py`, a dependency-free policy and rendering module vendored
  into the `workflow`, `assure`, and `user-manual` packages and into the standalone `user-manual`
  skill, so all four rendering sites share one implementation.

### Fixed

- The standalone `user-manual` skill copied the same two hard-coded workflow files and now renders
  them from the same selection.

### Compatibility

- `workflow` 1.2.0 requires `assure` >= 2.2 and `user-manual` >= 1.2. An older package still ships
  a non-template asset, which would render to itself and let a stale `ubuntu-latest` gate survive a
  self-hosted selection without any error.
- Changing `ci` never invalidates completed semantic work; like `context` and `updates` it is
  outside the policy-cutoff map.

## Documentation — README, workflow, and diagrams — 2026-09-18

### Added

- Added a **Skills, plugins, and extensions** section explaining the three package kinds sanduq
  ships, how each is installed and invoked, and that `presets/` is bundled at build time rather
  than installed.
- Added **Using a skill once it is installed** and **Using an extension**, covering invocation
  syntax for Claude Code and Codex, why `init` is not optional for a stateful extension, and the
  `illustrate` dependency policy.
- Added **The managed Spec Kit workflow**: the four daily entry points and what each one does
  automatically, the feature lifetime with its claim and its three recoverable detours, where
  state lives on disk, what the CI gate actually checks, and fresh-session continuation.
- Added a `scope` extension section — decomposition, the `keep_together` band, and GitHub
  clarification.
- Added three diagrams generated with the `illustrate` skill under the project's Cobalt Porcelain
  light theme, each with its editable HTML source committed beside the SVG and PNG exports:
  `sanduq-packaging`, `sanduq-managed-workflow`, `sanduq-feature-lifetime`.

### Fixed

- Corrected every version in the Spec Kit extension table. It advertised `project` 2.0.0,
  `assure` 2.0.0, `user-manual` 1.0.0, `pr` 4.0.0 and `illustrate` 2.1.0; the catalog publishes
  2.0.1, 2.0.1, 1.0.1, 4.0.2 and 2.1.2. The table now separates the **published** version from
  the **source** version, so a staged release is no longer mistakable for an installable one.
- Added the `scope` and `workflow` extensions to that table. The badge claimed seven extensions
  while the table listed five, and neither missing extension is installable by id — `scope`
  collides with an unrelated community extension in the public catalog, which the README now warns
  about.
- Recorded hook counts per extension, since lifecycle hooks are what distinguish an extension from
  a skill and were previously undocumented.

## CI — release pipeline no longer fails while work is staged — 2026-09-18

### Fixed

- The Release extensions workflow failed on every push to `main`. `release.py prepare`
  refuses unless `extensions/pending-releases.json` has status `ready` or `released`, but
  `implementation-in-progress` is a normal, long-lived state — reviewed packages sit staged
  there until a maintainer marks them ready. The workflow could not tell "nothing to release"
  from "the release is broken" and reported the former as a failure.
- Added a gate step that reads the pending status and skips the publish, promote, and commit
  steps when nothing is marked ready, recording the status it saw in the run summary. Marking
  the status `ready` remains the only thing that authorizes publication.
- Split the `prepare` guard so its error names the actual cause. It previously reported
  "requires a clean checkout and pending status ready" whichever of the two conditions failed.

### Added

- Recorded the CI runner exception in the README. All 14 jobs run on GitHub-hosted runners because
  the home-office `homek8-general` scale set is registered at organisation scope on `abushanab-net`
  while this repository is owned by a personal account, and GitHub does not share self-hosted
  runners across that boundary. The entry names the workflows, the jobs, the reason, and what would
  remove it.

## Branding — new logo and a standalone icon — 2026-09-18

### Changed

- Replaced the README logo with the new sanduq lockup: the orange toolbox mark, the wordmark, and
  the tagline "Tools for thoughtful delivery".
- Aligned the two identity badges with the brand palette — extensions green `#233C32`, skills
  orange `#C65B36`. Third-party badges keep their own colours.

### Added

- Added `sanduq-icon.png` (1080×1080) plus 512 and 128 variants: the toolbox mark alone, centred
  on a transparent square, with no part of the wordmark. Used as the header mark in the `skills/`,
  `extensions/`, and `plugins/` READMEs.
- Added `sanduq-logo-dark.png`. The supplied artwork is transparent with a dark wordmark, which is
  nearly invisible on a dark page, so the README pairs the two through `<picture>` and
  `prefers-color-scheme`. Only the wordmark and tagline are recoloured; the orange mark is
  untouched, and glyph antialiasing is preserved.
- Added `docs/assets/README.md` recording which asset to use where and the sampled brand colours.

## Documentation — extension usage covers scope and workflow — 2026-09-18

### Fixed

- "Using an extension" documented only the five published extensions. It now covers `scope` and
  `workflow` too: how to build them with `package.py`, install the extracted packages and their
  bundled presets with `--dev`, run the workflow initializer, and which commands each provides.
- Repaired the catalog command in that section. Its line continuation had been lost, leaving
  `--install-allowed   https://...` on one line — the command as printed would not have run.

### Added

- Added "Why `scope` and `workflow` are not published", because the extension table shows no
  published version for either and gave no reason. Both package cleanly; publication is gated only
  by the `implementation-in-progress` status flag, and the four remaining items are named with a
  link to the progress document.
- Added the ambiguous-`scope`-id warning to the easy-to-get-wrong list, where someone about to run
  an install command will actually see it.

## Documentation — context policy corrected to measured-only — 2026-09-19

### Fixed

- The README described the old context behaviour: that without an enforcing host the 60/50/10
  numbers are "an explicitly labelled estimate" and the answer is smaller batches. The workflow now
  defaults to `measured-only`, where only a fresh, reliable measurement can pause a run and missing,
  estimated, stale or malformed telemetry is nonblocking. Rewritten against
  `workflow.py context_gate` rather than the prose: the 120-second staleness bound, the early pause
  when the projected next call plus the reserve would cross the ceiling, the legacy
  `measured-with-estimated-fallback` now behaving the same way, and `strict` as the only mode that
  refuses to proceed.
- Corrected the feature-lifetime table and diagram, which said the checkpoint fires when "context
  reaches the ceiling". It fires on a fresh, reliable measurement crossing the checkpoint fraction;
  the diagram transition now reads MEASURED LIMIT.

## Coordinated workflow release (unreleased)

- Add Workflow 1.0.0 and migrate Scope 1.4.0 with canonical GitHub presets into Sanduq.
- Add independent QA/manual selections, automatic stage dispatch, native task sub-issues,
  context handoffs, upgrade-aware evidence, exact-source installation and rollback.
- Prepare Assure 2.1.0, User Manual 1.1.0, PR 4.1.0 and Project 2.1.0 integration updates.
- Require inline PR visuals and authenticated loading evidence, and publish immutable
  package assets before advertising their URLs in either catalog.
- Preserve legacy behavior outside managed projects; publish only after full acceptance.

## agent-tools — 1.0.0 — 2026-09-18

### Added

- Added the `agent-tools` plugin bundle with the `delegate-task` skill, moved here from the
  DoorCamera repository so it is hosted, versioned, and served from sanduq.
- Added `delegate-task`: hand one task to Claude Code, OpenAI Codex, OpenCode, GitHub Copilot, or
  Pi; run it detached; return a normalised result carrying the status *and the rule that produced
  it*, the file changes git measured against a pre-run baseline, and token counts normalised across
  harnesses that each count differently. Dependency-free Node driver (Node >= 18), 169-case test
  suite driven by a fake harness, and three normative contracts in `contracts/`.
- Registered `agent-tools` in `.claude-plugin/marketplace.json` and bumped the marketplace to 0.6.0.

### Changed

- Documented the driver as install-location relative. The skill's own docs now resolve
  `$DELEGATE` from `CLAUDE_PLUGIN_ROOT` or `.claude/skills/` instead of assuming a single
  repository path, and require `DELEGATE_RUNS_DIR` on a plugin install so run artifacts — which
  hold the task text and the harness's raw output — stay in the consuming project rather than
  accumulating in the shared plugin directory.
- Moved the run-lifecycle and parallel-fan-out diagrams into the skill's own `assets/`, so its
  README renders wherever the skill is installed.

## assure — 2.0.0 — 2026-07-19

### Changed

- Renamed the `qa` extension and command namespace to `assure` as an immediate breaking rename;
  the `qa` id conflicted with an existing Spec Kit community extension and broke installation.
- Updated the `pr` extension's optional dependency to `assure >=2.0.0,<3.0.0`.

## sanduq — licensing and standalone manuals — 2026-07-18

### Added

- Added a standalone `dev-tools` plugin with five independently installable `npx skills` modules
  for complete manuals, API docs, release docs, UI screenshots, and preview publishing.
- Added a comprehensive README with real-life usage examples for every skill and Spec Kit extension.
- Added a repository workflow illustration in editable HTML and exported SVG/PNG formats.
- Consolidated required upstream notices in `THIRD_PARTY_NOTICES.md`.

### Changed

- Changed current and future sanduq original contributions to PolyForm Noncommercial 1.0.0;
  previously released MIT copies retain their original terms.
- Bumped the license-breaking extension releases to `project` 2.0.0, `pr` 4.0.0, and `illustrate`
  2.0.0, and bumped `illustration-tools` to 3.0.0.

## user-manual — 1.0.0 — 2026-07-18

### Added

- Added the modular User Manual extension for three navigable editions: End User,
  Administrator/Operator, and Technical Reference.
- Added bilingual-ready English/Arabic and RTL-aware MkDocs Material scaffolding, audience-specific
  HTML and PDF builds, API/reference, release, migration, tutorial, and screenshot workflows.
- Added approved module-map governance in `User-Manual/manual.yml`, full system and module ER
  documentation rules, synthetic-data screenshot policy, incremental freshness checks, and private
  PR preview artifacts.

## qa — 1.0.0 — 2026-07-18

### Changed

- Replaced the former `how-to-test` extension and command namespace with `qa` as an immediate
  breaking rename.
- Added `speckit.qa.init` to choose integrated or manual QA lifecycle policy.
- Added feature-scoped freshness gates so integrated projects require QA analysis before
  implementation and current QA documentation before PR creation.

## pr — 3.1.0 — 2026-07-18

### Changed

- Added pre-PR freshness checks for installed QA and User Manual extensions, with automatic
  documentation refresh before creating or updating a pull request.

## illustrate — 1.0.4 — 2026-07-18

### Changed

- Updated integration references for the QA and User Manual documentation lifecycles.

## illustration-tools — 2.0.3 — 2026-07-18

### Changed

- Updated bundled Illustrate references for QA and User Manual consumers.

## illustration-tools — 2.0.2 — 2026-07-18

### Added

- Added two modern, responsive Illustrate gallery alternatives: an Atlas sidebar and a Canvas Deck
  filmstrip workspace.
- Kept every editorial and technical-color family selectable in both layouts, with restrained
  preview transitions, keyboard navigation, and reduced-motion support.

## illustration-tools — 2.0.1 — 2026-07-18

### Fixed

- Added first-class Architecture technical-color and Process Flow technical-color selectors to the
  Illustrate gallery, covering all imported light and dark examples.
- Made the former `architecture-diagram` and `process-flow-diagram` capabilities explicit in the
  unified skill description and generation guidance.

## illustration-tools — 2.0.0 — 2026-07-18

### Changed

- Consolidated `diagram-design`, `architecture-diagram`, and `process-flow-diagram` into one
  `illustrate` skill under the `illustration-tools` plugin.
- Renamed the Spec Kit extension and commands to `illustrate` while preserving editorial,
  hand-drawn, technical-color, and export capabilities.

## sanduq — 0.2.0 — 2026-07-09

### Added
- Resal-style automated extension release pipeline on `main`, with catalog/version commits and
  release ZIP publication.
- Marketplace registration for the `devtools` and `illustration-tools` Claude Code plugins.

### Changed
- Root `catalog.json` is now the public Spec Kit catalog, mirrored to `extensions/catalog.json`.
- Extension and plugin documentation now uses the sanduq install paths and release flow.
- Release-critical scripts and manifests are pinned to LF line endings with `.gitattributes`.
- Bumped extension metadata: `project` 1.0.1, `pr` 1.1.2, `pr-review` 1.0.4,
  `how-to-test` 1.4.1.
- Bumped plugin metadata: `devtools` 1.7.1 and `illustration-tools` 1.3.1.

## illustration-tools — 1.3.0 — 2026-07-09

### Added
- Light theme support for `process-flow-diagram`, now used by default.
- Dark process-flow template preserved as `resources/template-dark.html` for prompts that ask for dark output.
- Matching light reference outputs for every process-flow example: `sprint-report-flow-light.html`, `ai-governance-workflow-light.html`, `it-change-management-light.html`, and `inventory-control-light.html`.

### Changed
- `process-flow-diagram` skill instructions now route theme selection from the prompt and document separate light/dark palettes.

## illustration-tools — 1.2.0 — 2026-07-09

### Added
- Light theme support for `architecture-diagram`, now used by default.
- Dark architecture template preserved as `resources/template-dark.html` for prompts that ask for dark output.
- Matching light reference outputs for every architecture example: `web-app-light.html`, `aws-serverless-light.html`, and `microservices-light.html`.

### Changed
- `architecture-diagram` skill instructions now route theme selection from the prompt and document separate light/dark palettes.

## project — 1.0.0 — 2026-07-09

### Added
- Initial release of the `project` Spec Kit extension: GitHub Project (v2) lifecycle sync.
- Parent feature issue per feature; Status column advances through the Spec Kit lifecycle
  (`open → analysis → engineer-review → ready → in-progress → in-review → done`).
- One native sub-issue per task; sub-issues close as tasks are checked off in `tasks.md`.
- `project init` (PowerShell + bash) — board discovery and hybrid phase→column mapping
  (exact → fuzzy → prompt → optional auto-create of missing columns via GraphQL).
- `project sync` engine (PowerShell + bash) — idempotent, no-regress, self-contained
  In-review via open-PR detection, graceful degradation, committed shared state.
- Spec Kit `catalog.json` entry and Claude Code `marketplace.json` scaffold.
