# PR diagram recipe

Load this from step 4 of `speckit.pr.generate` when at least one diagram is warranted. It replaces
loading the whole Illustrate `SKILL.md` and `export.md` in the PR stage. Paths resolve from the
project root, not from the PR extension directory; `<skill>` is
`.specify/extensions/illustrate/skill`.

1. **Choose the type.** Read `<skill>/references/type-index.md`, choose the type (and variant) the
   evidence supports, and read only its `type-*.md`. Read `<skill>/SKILL.md` only when the
   diagram is created outside this recipe. Choose nothing the evidence does not support.
2. **Theme.** Resolve the project theme once with
   `python <skill>/scripts/illustration_theme.py --project-root . resolve --format yaml`; if the
   file is missing, run the same script with `init --non-interactive` (cobalt/light). The theme
   owns every colour; the type reference owns the layout.
3. **Output path.** Write each source as
   `docs/<feature-slug>/assets/diagrams/<feature-slug>-<type>.html` (for example
   `<feature-slug>-architecture.html`, `<feature-slug>-sequence.html`), one file per diagram.
4. **Export.** `python <skill>/scripts/export_diagram.py docs/<feature-slug>/assets/diagrams/<file>.html`
   writes the SVG and PNG beside the HTML. Read `<skill>/references/export.md` only when this
   command fails.
5. **Budget.** At most 9 nodes, 12 arrows or transitions, 2 accent elements and 2 annotation
   callouts per diagram, plus the type's row in `<skill>/references/layout-budget.md`; when a
   diagram exceeds it, split it into an overview and a detail diagram.

Embedding, the HTML source link and the "PNG export pending" fallback stay in the command's step 4.
