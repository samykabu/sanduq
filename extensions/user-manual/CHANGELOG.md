# Changelog

## Unreleased

- `manual_state.py` gains `--summary` (one line: `ok`/`error`, e.g. `ok
  action=record kind=manual outputs=1 recorded=1`) as an alternative to
  today's full JSON output, which stays exactly as it was and is now also
  selectable explicitly with `--json` (byte for byte the same as today's
  default). `--summary` and `--json` together is rejected. Default (no flag)
  behaviour and the exit code are unchanged. A `reason` carrying embedded
  whitespace or newlines is collapsed to a single line so `--summary` always
  prints exactly one line (B7).
- `speckit.user-manual.analyze` and `speckit.user-manual.update` now ensure the `illustrate`
  dependency with the shared `scripts/deps.py ensure illustrate` (also shipped to `pr` and
  `assure`) instead of the previous informal "load the installed Illustrate skill" wording; the
  script checks the Spec Kit registry, follows the project's `update_policy`, and prints one line,
  failing closed when illustrate cannot be brought into range. Its `SKILL.md` loads only when a
  diagram is actually about to be added or generated. `dependencies.yml` gained an explicit
  `defaults:` block (`update_policy: prompt`, `check_interval_hours: 24`) matching `pr` and
  `assure` (B9). A failure now points at `deps.py ensure illustrate --approve` for the user to
  re-run after approving, and an exit-0 "newer compatible release" note is surfaced to the user
  instead of only appearing in the printed line.
- `scripts/deps.py`: fixed after Opus review — parses `specify extension info`'s real plain-text
  `Name (vX.Y.Z)` header (it has no `--json` output); feeds `specify extension update`'s
  unavoidable `typer.confirm` prompt an explicit `y` only on an authorised update and otherwise
  closes stdin so an unexpected prompt fails fast instead of hanging; every subprocess call now has
  a timeout (a timeout is a plain failure, not an exception); the version comparator follows SemVer
  precedence for pre-release/build-metadata suffixes, a leading `v`, space-separated clauses, and
  `^`/`~=`, and ignores a still-unparseable catalog version instead of failing an already-compatible
  install; `.dependency-checks.json` now records a check only when the catalog probe actually ran
  and succeeded. Dropped the PyYAML dependency: `dependencies.yml` and
  `.specify/extension-dependencies.yml` are read by a small built-in parser (nothing installs a
  package's `requirements.txt` before its commands run), tested against the real files of all three
  consuming packages.
- `scripts/deps.py`: further fixes from a second review round — an inline comment no longer
  corrupts `update_policy` into an unrecognised value that silently fell back to `prompt` (an
  actually unknown value now raises instead); the range comparator applies npm-semver's
  pre-release rule, so `>=2.0.0,<3.0.0` never admits a pre-release version and a pre-release
  catalog release is never reported or auto-installed as "newer"; the parser now rejects a tab
  in leading whitespace, a duplicate key, a quoted key, a flow-style `[`/`{` value (previously an
  `AttributeError` later), and an unbalanced quote, type-checks `dependencies` as a list of
  mappings, and reports a malformed list item's own line number.

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
