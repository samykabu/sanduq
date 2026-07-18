# Publishing and theming

Keep content compatible with MkDocs-style Markdown. Pin Material 9.7.6 with MkDocs 1.x for the
primary build and keep renderer-specific behavior behind scripts. Run a Zensical compatibility check
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

Use `build_manual.py --module <approved-module-id> --pdf` for an on-demand module-specific PDF.
PDF generation is a deterministic renderer responsibility, so it stays in the core publishing
script instead of loading a separate reasoning skill.

Commit Markdown, configuration, themes, approved screenshots, and diagram sources/assets. Treat
`site/` and `pdf/` as generated CI/release outputs unless a project explicitly selects another policy.
