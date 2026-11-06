# Changelog

## [2.0.4] - 2026-11-05

- Keep generated workflow, evidence and progress directories under every feature out of implicit manual freshness inputs. Sibling requirements, tasks, contracts and product source still count; explicitly declared outputs still have integrity checks. Existing states need one public freshness rebind to remove the old metadata dependencies.
- The canonical dev-tools 2.0.5 correction makes `build_manual.py --all` build the audience list or map configured in `manual.yml` instead of requiring pages for an undeclared technical edition. Manuals without an audience selection retain the three-audience fallback; invalid selections fail before building. Explicit single-edition behavior is unchanged.

## [2.0.3] - 2026-11-05

- `user-manual-preview.yml` and `user-manual-release.yml` pin `actions/checkout` v7.0.1, `actions/setup-python` v7.1.0, `actions/upload-artifact` v7.0.2 and `actions/github-script` v9.0.0, which run on Node 24. Self-hosted runners need Actions Runner 2.327.1 or newer. The templates are still vendored from dev-tools 2.0.3; `vendor.lock.json` rewrites the pins. Workflow 2.3.1 re-renders an unedited copy on upgrade.

## [2.0.2] - 2026-10-31

- The packaged `sanduq_freshness.py` leaves another feature's untracked files under `specs/<other>/` out of the manual inputs, so an untracked note in a sibling feature no longer stales this feature's manual status (#113). Committed files still count through the branch diff.

## [2.0.1] - 2026-10-31

- Vendors sanduq-skills `dev-tools-v2.0.3`. A `manual.yml` from User Manual 1.x (MkDocs settings such as `theme` or `primary`, and no `renderer.kind`) keeps building with the `mkdocs` renderer instead of switching to Markdown; the build prints a notice to add `kind: mkdocs`, and the release workflow still installs MkDocs and builds PDFs for it. When a renderer command is Pandoc and sets no `--from`, the build adds `--from=gfm+rebase_relative_paths`, so images resolve from each page; the documented recipe is plain `pandoc {pages} ...`. `build_manual.py --help` lists the renderers, placeholders and both behaviours.

## [2.0.0] - 2026-10-30

- Breaking. Vendors sanduq-skills `dev-tools-v2.0.2`. The manual no longer depends on MkDocs: `build_manual.py` assembles each edition as Markdown (only the pages and assets that audience receives, front matter removed, plus `edition.json` and a Pandoc-style `metadata.yml`), then renders it with `renderer.kind` in `manual.yml`: `markdown` (the default; readable on GitHub), `command` (the project's own tool and templates, run from `User-Manual/` with `{pages}`, `{metadata}`, `{output}` and other placeholders), or `mkdocs` (the HTML site and `--pdf`). `--renderer` overrides the kind for one build; `--print-renderer` lets CI install only what the renderer needs. Zensical compatibility builds are removed.
- One skill: the `api-docs`, `release-docs`, `ui-screenshots` and `preview-publishing` skills are removed; their instructions are references of `user-manual` (`skills/user-manual/references/api-docs.md`, `release-docs.md`, `ui-screenshots.md`, `preview-publishing.md`), and the commands read them from there.
- Pages use GitHub's own syntax (`> [!NOTE]` alerts, `<details>`); the MkDocs renderer converts alerts to admonitions titled in the edition's language, and the audit warns about MkDocs-only syntax. Titled links, `<angle-bracketed>` targets and reference definitions are staged like plain links; footnotes are not links.
- `theme/brand.yml` (title, subtitle, author, copyright, logo, primary colour) reaches every renderer; `theme/pdf/cover.html` replaces the PDF cover; `renderer.custom_dir` may be relative to `User-Manual/`. Arabic admonition titles in PDFs no longer overlap their icon.
- Installs are split: `requirements.lock` (PyYAML), `requirements-mkdocs.lock`, `requirements-pdf.lock`. Init writes `renderer.kind: markdown` and `theme/brand.yml`, and no longer copies stylesheets or the unused `mkdocs.yml`. The release workflow template builds PDFs only with the `mkdocs` renderer.
- The MkDocs renderer labels each page in the navigation with its front-matter `title`, and `edition.json` lists every page title under `titles`. The documented Pandoc recipe reads pages with `-f gfm+rebase_relative_paths`, so images resolve from each page's own folder.
- Code examples stay exactly as written: the build and the audit find fenced and indented code blocks with a CommonMark parser (markdown-it-py, now in `requirements.lock` next to PyYAML), so code such as `[region]: endpoint,` is never read as a link, and alerts or `<details>` shown inside code are not converted.
- No migration step: an existing manual adds `renderer: {kind: mkdocs}` to keep its MkDocs site (2.0.1 infers it).
