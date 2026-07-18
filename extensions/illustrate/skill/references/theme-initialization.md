# Project Theme Initialization

Use this reference when initializing, selecting, importing, or creating an Illustrate theme. Theme
policy belongs to the target project at `.github/illustration-theme.yml`; never rewrite the installed
skill to customize one project.

## Resolution order

Before every generation:

1. Read `.github/illustration-theme.yml` when it exists.
2. Resolve the selected preset or project custom theme with `scripts/illustration_theme.py`.
3. Apply the resolved mode, color roles, font stacks, and font-loading policy to the output.
4. If the file is absent and the run is interactive, ask which preset or custom theme to use.
5. If the file is absent and the run cannot ask questions, initialize `cobalt/light`.

```bash
python scripts/illustration_theme.py --project-root . resolve --format yaml
```

The resolver creates the missing file automatically. It never overwrites an existing configuration.

## Built-in themes

| ID | Name | Character | Typography |
| --- | --- | --- | --- |
| `cobalt` | Cobalt Porcelain | Precise, high-clarity developer tooling. Default. | IBM Plex Sans/Serif/Mono with Arabic fallbacks. |
| `emerald` | Emerald Mist | Calm, trustworthy manuals and workflows. | Source Sans/Serif/Code with Arabic fallbacks. |
| `classic` | Sanduq Classic | Backward-compatible orange and blue-slate skin. | Geist, Instrument Serif, and Geist Mono with Arabic fallbacks. |

Every preset contains complete `light` and `dark` palettes. The registry lives at
`assets/illustration-themes.yml` and is versioned with the skill.

List available themes:

```bash
python scripts/illustration_theme.py --project-root . list
```

## Initialize a project

Interactive initialization presents themes, color mode, and font-loading choices:

```bash
python scripts/illustration_theme.py --project-root . init
```

Deterministic initialization for automation:

```bash
python scripts/illustration_theme.py --project-root . init \
  --theme cobalt --mode light --font-loading remote --non-interactive
```

Generated project file:

```yaml
schema_version: "1.0"
active:
  theme: "cobalt"
  mode: "light"
  font_loading: "remote"
custom_themes: {}
```

Commit this file. It is project policy, not local editor state.

## Select a preset or mode

```bash
python scripts/illustration_theme.py --project-root . set --theme emerald --mode light
python scripts/illustration_theme.py --project-root . set --theme cobalt --mode dark
```

`font_loading` accepts:

- `remote`: emit the preset/custom `remote_css_url` import.
- `local`: use named font families without a remote import; the project supplies the fonts.
- `system`: omit remote imports and rely on the configured fallback stacks.

Change it without replacing the theme:

```bash
python scripts/illustration_theme.py --project-root . set \
  --theme cobalt --font-loading system
```

## Create a custom light and dark theme

Run the interactive creator. It starts from a built-in preset, then asks for all semantic colors and
the sans, serif, and mono stacks. It always creates both modes so future mode changes are safe.

```bash
python scripts/illustration_theme.py --project-root . create --name product-brand
```

For non-interactive use, prepare a mapping and import it:

Start from [`../assets/custom-theme.example.yml`](../assets/custom-theme.example.yml) when useful.

```yaml
name: "product-brand"
label: "Product Brand"
description: "Application documentation theme."
typography:
  sans: "'Brand Sans', 'Noto Sans Arabic', system-ui, sans-serif"
  serif: "'Brand Display', 'Noto Naskh Arabic', serif"
  mono: "'Brand Mono', 'Noto Sans Arabic', ui-monospace, monospace"
  remote_css_url: ""
light:
  paper: "#f7f9fc"
  paper-2: "#ffffff"
  ink: "#172033"
  muted: "#526078"
  soft: "#748198"
  rule: "rgba(23,32,51,0.12)"
  rule-solid: "#cbd4e2"
  accent: "#175cd3"
  accent-tint: "rgba(23,92,211,0.09)"
  link: "#0b63ce"
dark:
  paper: "#111827"
  paper-2: "#182235"
  ink: "#f5f7fb"
  muted: "#bac5d6"
  soft: "#8b98ad"
  rule: "rgba(245,247,251,0.12)"
  rule-solid: "#42516b"
  accent: "#79a7ff"
  accent-tint: "rgba(121,167,255,0.14)"
  link: "#8fc1ff"
```

```bash
python scripts/illustration_theme.py --project-root . create \
  --from-file docs/product-illustration-theme.yml
```

The custom definition is copied into `.github/illustration-theme.yml`, selected immediately, and
validated. The source file may then remain as design documentation or be removed.

## Initialize from a project design source

If the user wants colors and fonts extracted from an existing design system, inspect sources in this
order unless a path is supplied:

1. `design.md`
2. `system-design.md`
3. `system design.md`
4. `docs/design.md`
5. `docs/system-design.md`
6. `docs/system design.md`
7. `docs/design-system.md`
8. `.agents/design.md`

Also accept websites, installed skills, CSS/SCSS tokens, Figma token JSON, and local design-system
folders as described in [`onboarding.md`](onboarding.md).

Map the source into Illustrate semantic roles, derive missing values, create both light and dark
modes, and preserve the source font families. Show the proposed mapping and contrast results before
writing. Save the approved definition through `create --from-file`; do not edit bundled presets.

## Applying the resolved theme

Resolve as YAML for an agent-readable mapping, JSON for automation, or CSS for direct injection:

```bash
python scripts/illustration_theme.py --project-root . resolve --format yaml
python scripts/illustration_theme.py --project-root . resolve --format json
python scripts/illustration_theme.py --project-root . resolve --format css
```

Apply every resolved role, including literal fills/strokes inside SVG, marker colors, mask fills,
HTML background, and all font-family declarations. Examples and templates may contain historical
literal values; they do not override the project selection.

## Validation

```bash
python scripts/illustration_theme.py --project-root . validate
```

Validation requires:

- complete light and dark semantic palettes;
- sans, serif, and mono stacks;
- valid hex/rgba values;
- WCAG AA contrast for `ink` and `muted` on `paper`;
- a known preset or valid project custom theme;
- `remote`, `local`, or `system` font loading.

Never store credentials, signed font URLs, or private registry tokens in the tracked YAML. Use local
font stacks or a public stylesheet URL instead.
