# Changelog

## Unreleased

- `manual_state.py` gains `--summary` (one line: `ok`/`error`, e.g. `ok
  action=record kind=manual outputs=1 recorded=1`) as an alternative to
  today's full JSON output, which stays exactly as it was and is now also
  selectable explicitly with `--json`. `--summary` and `--json` together is
  rejected. Default (no flag) behaviour and the exit code are unchanged (B7).

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
