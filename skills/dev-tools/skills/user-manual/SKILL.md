---
name: user-manual
description: Create, organize, incrementally update, validate, and publish a complete standalone application User Manual for web, mobile, APIs, infrastructure, architecture, and data. Use without Spec Kit when starting a manual, documenting a feature or module, auditing coverage, creating bilingual English and Arabic documentation, or building audience-specific MkDocs Material HTML and PDF editions.
---

# User Manual

Maintain one evidence-backed documentation source under `User-Manual/`. Publish three navigable
editions: End User, Administrator/Operator, and Technical Reference.

## Choose the smallest workflow

- New manual: interview the user, inspect the repository, propose a module map, obtain approval,
  then run `scripts/init_manual.py` with an approved JSON module file.
- Existing manual: read `User-Manual/manual.yml`, inspect the requested scope and relevant Git diff,
  then update only affected pages and assets.
- Coverage audit: run `scripts/audit_manual.py` and explain every actionable gap.
- Release build: run `scripts/build_manual.py` only after canonical Markdown passes the audit.

This standalone skill does not require `.specify/`, a feature specification, or any Spec Kit
command. Scope work from the user's request, repository evidence, and version-control changes.

## Route only what is needed

- Discovery and interview: read [discovery.md](references/discovery.md).
- Page structure: read [content-model.md](references/content-model.md).
- Audience and language: read [audience-language.md](references/audience-language.md).
- Incremental changes: read [incremental-update.md](references/incremental-update.md).
- Entities, columns, enumerations, or ER diagrams: read [data-reference.md](references/data-reference.md).
- Theme, HTML, PDF, RTL, previews, or releases: read [publishing.md](references/publishing.md).
- Specialized API, release, screenshot, or hosted-preview work: use the matching optional
  `user-manual-*` skill when installed. Otherwise apply these core rules and report what remains.

## Non-negotiable rules

1. Require English. Arabic is optional per project, but templates, themes, diagrams, and PDFs must
   support RTL from initialization.
2. Use plain, natural English or Arabic. Write for the declared audience; never reuse a technical
   explanation unchanged for an end user.
3. Ground claims in implementation, contracts, tests, observed behavior, schemas, or approved
   infrastructure sources. Mark unknowns and never invent behavior.
4. Never include secrets, credentials, tokens, private keys, connection strings, production
   records, or unredacted personal data. Use deterministic synthetic examples.
5. Store the approved, extensible module map in `User-Manual/manual.yml`. Add later discoveries as
   `proposed` until approved.
6. Keep Markdown canonical. Generate HTML, archives, and PDFs through included scripts.
7. Create a system ER overview plus smaller module ER diagrams. Document every evidenced entity,
   column, data type, relationship, constraint, and enumeration.
8. Preserve hand-authored content outside owned markers and make reruns converge.

## Real-life example

For “Create a manual for our booking platform,” identify booking, customer, payment, and operations
modules from routes, navigation, APIs, tests, and schema files. Ask the user to approve that module
map. Then create audience-aware tutorials, safe screenshots, API and data references, English
content, optional Arabic content, and buildable HTML/PDF editions under `User-Manual/`.
