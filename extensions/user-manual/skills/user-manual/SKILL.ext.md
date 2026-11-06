---
name: user-manual
description: Create, organize, incrementally update, validate, and publish a complete application User Manual for web, mobile, API, infrastructure, architecture, and data surfaces. Use for speckit.user-manual.init, analyze, update, or release; bilingual English and Arabic manuals; audience editions; tutorials; API references; release notes and migration guides; screenshots; previews; diagrams; documentation coverage; and rendering editions as Markdown, through the project's own templates, or as MkDocs HTML and PDF.
---

# User Manual

Maintain one evidence-backed documentation source under `User-Manual/` and publish filtered editions
for end users, administrators/operators, and technical readers.

## Route only what is needed

- New manual or module discovery: read [discovery.md](references/discovery.md).
- Page structure and content type: read [content-model.md](references/content-model.md).
- Audience or language writing: read [audience-language.md](references/audience-language.md).
- Feature update: read [incremental-update.md](references/incremental-update.md).
- Entities, columns, enumerations, or ER diagrams: read [data-reference.md](references/data-reference.md).
- Renderers, templates, brand, HTML, PDF, RTL, or release build: read [publishing.md](references/publishing.md).
- API work: read [api-docs.md](references/api-docs.md).
- Release notes or migration guides: read [release-docs.md](references/release-docs.md).
- UI screenshots: read [ui-screenshots.md](references/ui-screenshots.md).
- Previews and hosted preview: read [preview-publishing.md](references/preview-publishing.md).

## Non-negotiable rules

1. Require English. Treat Arabic as project-optional while keeping every template RTL-ready.
2. Use plain, natural English or Arabic. Match vocabulary, detail, risks, and examples to the page's
   declared audience.
3. Ground claims in specifications, implementation, contracts, tests, observed development behavior,
   schema metadata, or approved infrastructure sources. Mark unknowns; never invent them.
4. Never include secret values, credentials, tokens, private keys, connection strings, production
   records, or unredacted personal data.
5. Store the approved module map in `User-Manual/manual.yml`. Add later discoveries as `proposed`
   until approved.
6. Keep Markdown canonical and write GitHub's own syntax (alerts, `<details>`), so pages read correctly on
   GitHub. Generate every other format through `build_manual.py` and the renderer `manual.yml` selects.
7. Generate only useful diagrams. Reuse Illustrate and keep system overviews separate from readable
   module-level detail.
8. Preserve hand-authored content outside owned markers and converge on rerun.
