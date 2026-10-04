# Changelog

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

## 1.1.0 (unreleased)

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
