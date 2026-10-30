# Publishing: editions, renderers and templates

`scripts/build_manual.py` works in two steps for each edition (one audience and language, optionally
one `--module`):

1. **Assemble.** Select the edition's pages, rewrite links between them, copy only the assets they
   reach, and write `edition.json` (title, language, direction, version, pages in reading order, the
   navigation tree, brand values) and `metadata.yml` (title, subtitle, author, `lang`, `dir`,
   `toc-title`, in the form Pandoc reads). Needs only Python and PyYAML.
2. **Render** with `renderer.kind` in `manual.yml`. `--renderer` overrides it for one build.

| `renderer.kind` | Output in `site/<version>/<lang>/<audience>/` | Install |
| --- | --- | --- |
| `markdown` (default) | The assembled edition itself, readable on GitHub or a wiki | `requirements.lock` |
| `command` | Whatever your own tool writes to `{output}` | `requirements.lock` plus your tool |
| `mkdocs` | An MkDocs HTML site; `--pdf` adds `pdf/<version>/<edition>.pdf` | `requirements-mkdocs.lock`, or `requirements-pdf.lock` for PDF |

`--archive` zips any renderer's output. `--print-renderer` prints the selected kind, which the CI
workflows use to install only what that renderer needs.

## Your own templates: `renderer.kind: command`

The command runs once per edition, from `User-Manual/`, so template paths in it are relative to the
manual. A string is split like a POSIX shell command (quotes work; no globbing, pipes or variables,
and backslashes are escapes, so give Windows paths in list form). Placeholders:

| Placeholder | Value |
| --- | --- |
| `{pages}` | As a whole argument: every page of the edition, in reading order |
| `{edition}` | The assembled edition folder (pages and assets) |
| `{manifest}` | `edition.json` |
| `{metadata}` | `metadata.yml` |
| `{output}` | The folder to write into; the build fails if the command writes nothing |
| `{language}`, `{direction}`, `{audience}`, `{version}`, `{module}`, `{title}` | Edition values |

```yaml
renderer:
  kind: command
  # A Word edition through the team's reference document:
  command: pandoc -f gfm+rebase_relative_paths {pages} --metadata-file {metadata} --reference-doc theme/word.docx -o {output}/manual.docx
```

```yaml
renderer:
  kind: command
  # A Quarto book that reads the edition folder and the brand file:
  command: [quarto, render, theme/quarto, --output-dir, "{output}", -M, "edition:{edition}"]
```

Pages keep links relative to their own folder. Give Pandoc `-f gfm+rebase_relative_paths` so it finds each
page's images from that page, not from `User-Manual/`; check how your Pandoc version shows GitHub alerts.
Each page's front-matter title is in `edition.json` under `titles`.

The tool itself is not installed by the skill: put it on the build machine or the CI runner image,
or add an install step to the generated workflow.

## Brand: `theme/brand.yml`

`title` (defaults to `product_name`), `subtitle` (defaults to the edition's audience), `author`,
`copyright`, `logo` (a path relative to `User-Manual/`) and `colors.primary`. Every renderer gets
them: `edition.json` carries them for a command, `metadata.yml` gives Pandoc its title block, and the
MkDocs renderer uses them for the site name, logo, accent color and PDF cover.

## The MkDocs renderer

`renderer.theme` picks the theme: Material 9.7.6 with MkDocs 1.x by default, or `readthedocs`,
`mkdocs`, or any installed MkDocs theme, with `renderer.theme_options` passed through.
`renderer.custom_dir` (or `theme_options.custom_dir`) is a theme override folder relative to
`User-Manual/`. The build writes its own MkDocs configuration for each edition; a `mkdocs.yml` in the
manual is not read.

Stylesheets come with the skill: `extra.css`, `rtl.css`, `print.css`, `theme-<theme>.css`, and for
a right-to-left edition `rtl-<theme>.css` or `rtl-generic.css`. A file of the same name in
`User-Manual/theme/` replaces the shipped one. The build converts GitHub alerts to admonitions
titled in the edition's language and renders the Markdown inside `<details>`.

PDF (`--pdf`) needs `requirements-pdf.lock`, WeasyPrint's system libraries and, for Arabic, the
Amiri font. On Debian or Ubuntu: `libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0
libharfbuzz-subset0 fonts-hosny-amiri`. The PDF keeps the edition's `lang` and `dir`, sets Arabic
text in `"Amiri", "Noto Naskh Arabic", "Noto Sans Arabic", serif`, titles the contents in the
edition's language, and shows only the cover values that are set. `User-Manual/theme/pdf/cover.html`
and `styles.scss` replace the cover template and add PDF styles. Build a module PDF on request with
`--module <approved-module-id> --pdf`. A manual created before dev-tools 1.6.0 that keeps its own
`rtl*.css` copies does not get the Arabic font unless that rule is copied in.

## Previews and releases

Build each language and audience separately. Always create a private CI preview archive for feature
PRs and add the artifact link to the PR. Deploy an ephemeral preview only when `manual.yml` names an
approved provider. On release, create versioned archives of every edition, plus one PDF per
edition/language with the MkDocs renderer.

For a private repository, restrict the preview artifact through repository read permissions. For a
public repository, upload only an age-encrypted bundle and require the public recipient through the
`USER_MANUAL_PREVIEW_AGE_RECIPIENT` Actions variable; distribute the private key out of band. Never
upload plaintext Administrator or Technical editions to a public artifact store.

Commit Markdown, configuration, `theme/`, approved screenshots, and diagram sources/assets. Treat
`site/` and `pdf/` as generated CI/release outputs unless a project explicitly selects another policy.
