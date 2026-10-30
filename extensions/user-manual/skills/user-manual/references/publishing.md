# Publishing and theming

Keep content compatible with MkDocs-style Markdown. The theme is `renderer.theme` in `manual.yml`:
Material 9.7.6 with MkDocs 1.x by default, or `readthedocs`, `mkdocs` or any installed MkDocs theme.
Theme-specific RTL and layout fixes live in `theme/rtl-<theme>.css` and `theme/theme-<theme>.css`;
verify RTL editions visually after changing theme. Pin the primary build and keep renderer-specific behavior behind scripts. Run a Zensical compatibility check
when available. Do not use Material's deprecated projects or typeset plugins.

Theme priority: explicit `User-Manual/theme/` tokens, detected project design-system tokens, then the
extension defaults. Support light, dark, print, and RTL without changing content files.

Build each language and audience separately. Always create a private CI preview archive for feature
PRs. Add the artifact link to the PR. Deploy an ephemeral preview only when `manual.yml` contains
an approved provider. On release, create versioned HTML archives and one PDF per edition/language;
build module PDFs only on request.

For a private repository, restrict the preview artifact through repository read permissions. For a
public repository, upload only an age-encrypted bundle and require the public recipient through the
`USER_MANUAL_PREVIEW_AGE_RECIPIENT` Actions variable; distribute the private key out of band. Never
upload plaintext Administrator or Technical editions to a public artifact store.

PDF needs WeasyPrint's system libraries and, for Arabic, the Amiri font. On Debian or Ubuntu:
`libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 libharfbuzz-subset0 fonts-hosny-amiri`. The RTL
stylesheets set Arabic text to `"Amiri", "Noto Naskh Arabic", "Noto Sans Arabic", serif`, and the PDF
keeps the edition's `lang` and `dir`. A manual created before dev-tools 1.6.0 has its own copies of
`rtl.css`, `rtl-generic.css` and `rtl-readthedocs.css` in `User-Manual/theme/`, which the build uses
instead; copy the font rule from the shipped stylesheets into them.

Use `build_manual.py --module <approved-module-id> --pdf` for an on-demand module-specific PDF.
PDF generation is a deterministic renderer responsibility, so it stays in the core publishing
script instead of loading a separate reasoning skill.

Commit Markdown, configuration, themes, approved screenshots, and diagram sources/assets. Treat
`site/` and `pdf/` as generated CI/release outputs unless a project explicitly selects another policy.
