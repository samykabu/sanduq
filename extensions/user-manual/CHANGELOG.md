# Changelog

## [1.8.3] - 2026-10-28

- `requires.tools` declares Python `>=3.11`, the floor every Sanduq extension now states (SAMY-11).

## [1.8.2] - 2026-10-26

- License: this package is MIT; versions before this one were PolyForm Noncommercial 1.0.0. The archive now ships its LICENSE and a THIRD_PARTY_NOTICES.md for the vendored dev-tools material.

## [1.8.1] - 2026-10-21

Vendors dev-tools 1.4.0.

- `init_manual.py` is vendored from dev-tools instead of kept as a separate copy. `speckit.user-manual.init` passes
  `--no-tools`, so nothing is copied into `User-Manual/tools/`. The new `--ci-policy <file>` is not used by the command.
- A new `manual.yml` has its `lifecycle:` block after `renderer:`. Existing files are not rewritten.

## [1.8.0] - 2026-10-21

Optimization round 4. No renames.

Optimization round 4.

- `init_manual.py` never overwrites an existing `docs/<lang>/index.md`, as it already did for module pages.
- Analyze puts its tasks between `<!-- user-manual-tasks:start -->` and `<!-- user-manual-tasks:end -->` and replaces that block on a rerun. Assure's analyze state ignores the block.
- Update builds with `build_manual.py --all` and adds `--archive` only when `manual.yml` names an approved provider. CI builds its own preview archive. On the 3-edition booking sample this cut the build from 16.1 s to 10.4 s.
- `manual_state.py status` no longer walks `User-Manual/`; only `record` collects the default outputs.
- Update's Illustrate step names full script paths (Spec Kit rewrote the bare `scripts/` token). `deps.py` names the next step in its one line; the commands say one sentence about it.

### Migration

- A local Update no longer writes `User-Manual/site/<version>/*.zip` unless an approved provider is configured. They were build output and are not committed.

## [1.7.1] - 2026-10-20

- The shared freshness helper hashes declared outputs as outputs only (see Assure 2.5.1). Update names `User-Manual/.state/features/<feature-name>/reports/` for freshness logs and status reports, written before the final `record`. Part of samykabu/sanduq#99.

## [1.7.0] - 2026-10-20

Optimization round 3.

- Update follows Illustrate's procedure (theme gate and checks) when it draws, makes one impact call and handles an unchanged state.
- One freshness CLI shared with Assure; the extension's build test is vendored from dev-tools.

## [1.6.0] - 2026-10-19

Optimization round 2.

- Freshness `status` reports `changed_inputs` and `changed_outputs` when stale, and `--summary` adds their counts. Update reads only the changed inputs on a rerun.
- `scripts/manual_impact.py` lists the affected modules, pages and audiences from the changed inputs and the manual's evidence paths. It runs when `User-Manual/manual.yml` sets `lifecycle.impact_scope: evidence`; the default `all` keeps today's behaviour.
- Vendors dev-tools 1.2.0: `build_manual.py --all` builds every configured audience and language in one call, and Update, Release and both CI workflows use it.
- Diagrams use Illustrate's type index. The commands are trimmed to the scripts they call. One description per command; the unused `agents/openai.yaml` files are removed.

## [1.5.4] - 2026-10-19

- Vendors dev-tools 1.1.3: the preview workflow skips fork pull requests when the project's linux
  runner is self-hosted, and both workflows pin `actions/checkout` v4.3.0, `actions/setup-python`
  v5.6.0, `actions/upload-artifact` v4.6.2 and `actions/github-script` v7.1.0 by commit. Part of
  samykabu/sanduq#94.

## [1.5.3] - 2026-10-18

- Ship the reviewed shared freshness helper in the User Manual package. Generated Progress
  reports under `specs/*/progress/` and `.specify/progress/` no longer stale manual analysis or
  update state. Changes to true source inputs, including product directories such as
  `src/progress`, still invalidate that state. The helper is injected by Sanduq's package builder;
  the vendored portable User Manual skill files are unchanged.

## [1.5.2] - 2026-10-10

- Scripts, scaffold, CI templates and skill references are vendored from the portable User Manual
  skills in samykabu/sanduq-skills (byte-identical; see `ADAPTER.md`). No behavior change.
- README links point to the new extension page, install-by-host page and command reference.

## [1.5.1] - 2026-10-06

- Link setup and complete usage examples from the package README; links work in installed copies.

## 1.5.0

- **Selectable MkDocs theme.** `renderer.theme` in `manual.yml` picks the
  HTML theme: `material` (default, unchanged), `readthedocs`, `mkdocs`, or
  any installed MkDocs theme. `renderer.theme_options` is merged into the
  theme block. An uninstalled theme fails the build with the list of
  installed ones; `--renderer zensical` stays a Material-only check.
- **RTL for non-Material themes.** The built-in themes ship no Arabic locale,
  so pages always say `lang="en"`. RTL editions (`languages.rtl`) now get
  `rtl-readthedocs.css` (mirrored sidebar, menu, breadcrumbs, footer buttons
  and mobile slide-in, code kept LTR) or `rtl-generic.css` for other themes.
  `theme-readthedocs.css` lets wide tables wrap and scroll in every language.
  Project files in `User-Manual/theme/` override the shipped copies, so
  existing manuals work without re-running init.
- **Localized navigation.** The build generates `nav` in `manual.yml` module
  order, naming each module with its translation for the edition's language
  (Arabic editions no longer show English folder slugs), and localizes the
  Arabic edition names. Material editions keep their tabs.
- `init_manual.py` records `renderer.theme: material` and copies the new
  stylesheets.

## 1.4.0

- **B7 — quiet output.** `manual_state.py` gains `--summary` (one line:
  `ok`/`error`, e.g. `ok action=record kind=manual outputs=1 recorded=1`)
  as an alternative to the previous full JSON output, which is unchanged
  and now also selectable explicitly with `--json`. `--summary` and
  `--json` together is rejected; default (no flag) behaviour and the exit
  code are unchanged. A `reason` with embedded whitespace or newlines is
  collapsed to a single line so `--summary` always prints exactly one
  line.
- **B9 — shared dependency script.** `speckit.user-manual.analyze` and
  `speckit.user-manual.update` now ensure the `illustrate` dependency with
  the shared `scripts/deps.py ensure illustrate` (also shipped to `pr` and
  `assure`) instead of the previous informal "load the installed
  Illustrate skill" wording: it checks the Spec Kit registry, follows the
  project's `update_policy`, and prints one line, failing closed with
  `deps.py ensure illustrate --approve` as the recovery when illustrate
  cannot be brought into range; an exit-0 "newer compatible release" note
  is surfaced to the user. Its `SKILL.md` now loads only when a diagram is
  actually about to be added or generated. `dependencies.yml` gained an
  explicit `defaults:` block (`update_policy: prompt`,
  `check_interval_hours: 24`) matching `pr` and `assure`.

  `deps.py` itself parses `specify extension info`'s real plain-text
  `Name (vX.Y.Z)` header (it has no `--json` output); answers `specify
  extension update`'s unavoidable `typer.confirm` prompt with an explicit
  `y` only on an authorised update, closing stdin otherwise so an
  unexpected prompt fails fast; every subprocess call has a timeout; the
  version comparator follows SemVer precedence for pre-release/build-
  metadata suffixes, a leading `v`, space-separated clauses, `^`/`~=`, and
  npm-semver's pre-release range rule (a plain `>=2.0.0,<3.0.0` never
  admits a pre-release version). `.dependency-checks.json` records a check
  only when the catalog probe actually ran and succeeded. It ships no
  third-party dependency: `dependencies.yml` and
  `.specify/extension-dependencies.yml` are read by a small built-in
  parser (nothing installs a package's `requirements.txt` before its
  commands run) that rejects a tab in leading whitespace, a duplicate or
  quoted key, a flow-style value, and an unbalanced quote, and reports a
  malformed list item's own line number.

## 1.3.3

- The private preview artifact `upload-artifact` step now keeps `retention-days: 2`
  instead of 14. The Cloudflare preview workflow reads the artifact once, right
  after the run; 14 days of ~20 MB copies per push filled the account's artifact
  storage and blocked every Bootstrap run (2026-09-28). A short comment above the
  setting records why, so the rendered workflow file matches byte for byte across
  every project that installs this extension.

## 1.3.2

- `manual_state.py` defaults `--base-ref` to the feature's bound target
  branch recorded in its Workflow checkpoint instead of always assuming the
  origin HEAD default branch, when the checkpoint recorded one. An explicit
  `--base-ref` still wins, and a feature with no checkpoint, or none recorded,
  keeps today's origin-HEAD default (F16).

## 1.3.1

- The bundled freshness helper shares Workflow's checkout-independent
  fingerprints: an unchanged tracked `.sql` or `-text` file that a Windows
  `core.autocrlf` checkout wrote with different line endings hashes as its
  committed blob, so manual state recorded on Windows stays current in Linux CI.

## 1.3.0

- An edition now stages the assets its pages actually reach, with shared
  `docs/assets` paths rebased under the edition and every link rewritten to
  where its target landed. Copying only the language directory left those
  links pointing outside the staged documentation, and the strict site build
  rejected them. A missing asset, a link into a page the audience does not
  receive, and an asset outside the documentation roots now fail the build
  where they can still be fixed, and one audience no longer ships another's
  assets.

## 1.2.0

- Where CI runs is a project decision; the shipped workflow assets are rendered
  from the `ci:` selection in `.specify/workflow.yml`.

## 1.1.0

- Track source and output freshness without hashing workflow state or manual state into itself.

## [1.0.0] - 2026-07-18

### Added

- Added module discovery and approval stored in `User-Manual/manual.yml`.
- Added required English, optional Arabic, and RTL-ready theme/PDF behavior.
- Added End User, Administrator/Operator, and Technical Reference editions.
- Added incremental feature updates, private PR previews, release HTML/PDF builds, and optional
  approved-provider ephemeral previews.
- Added conditional API documentation, release/migration, UI screenshot, and secure preview
  publishing skills.
- Added complete entity/column/enumeration documentation and system plus module ER diagrams without
  secrets or production data.
