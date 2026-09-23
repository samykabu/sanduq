# Changelog

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
