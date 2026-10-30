# User Manual: themes and a rendered example

The same manual content can have different navigation, typography, and colors. This guide covers the
`mkdocs` renderer (`renderer.kind: mkdocs`) and its themes. The default `markdown` renderer and a
`command` renderer with your own templates are described in the User Manual
[README](../extensions/user-manual/README.md#builds). These screenshots come from
the actual extension builder, using the checked-in synthetic Booking, Payments, and Operations manual.

## Table of contents

- [Supported themes](#supported-themes)
- [Screenshot gallery](#screenshot-gallery)
- [Customize the theme](#customize-the-theme)
- [Install your own theme](#install-your-own-theme)
- [Rebuild the sample](#rebuild-the-sample)

## Supported themes

The portable skill and the Spec Kit extension run the same builder, so both support the same themes:
Material by default, the built-in ReadTheDocs and MkDocs themes, and any other installed MkDocs theme.
Customize through `renderer.theme`, `renderer.theme_options`, `renderer.custom_dir`, project CSS in
`User-Manual/theme/`, and `theme/brand.yml`. The build writes its own MkDocs configuration for each
edition, so a `mkdocs.yml` in the manual is not read. PDF generation has its own native dependency
checks; this gallery verifies HTML only.

## Screenshot gallery

Every screenshot uses the same four authored pages and embedded Illustrate process diagram.
The sample is instructional; its approval metadata refers to the demo's module map, not a real
application owner's signoff. See [sample source and regeneration](examples/booking-manual/README.md).

### Material light

![Actual Material light manual with module navigation and refund diagram](assets/manual-gallery/material-light.png)

### Material dark

![Actual Material dark manual with the same content and embedded diagram](assets/manual-gallery/material-dark.png)

### ReadTheDocs

![Actual ReadTheDocs manual with the same module pages](assets/manual-gallery/readthedocs.png)

### MkDocs

![Actual MkDocs default theme with the same refund diagram](assets/manual-gallery/mkdocs.png)

### Booking Brand customization

![Actual Material manual with custom navy header and gold border](assets/manual-gallery/booking-brand.png)

This last variant customizes Material through project CSS; it is not an additional installed theme.
The manual theme and the diagram theme are independent. Regenerate the diagram to change its palette.

## Customize the theme

For the **extension builder**, edit `User-Manual/manual.yml`:

```yaml
renderer:
  theme: material
  theme_options:
    palette:
      scheme: slate       # default = light; slate = dark
      primary: indigo
      accent: amber
    features:
      - navigation.sections
```

To use built-in alternatives, set `theme: readthedocs` or `theme: mkdocs` and remove Material-only
options. To reproduce the custom screenshot, add this to `User-Manual/theme/extra.css`:

```css
:root {
  --manual-primary: #172033;
  --manual-accent: #875d09;
}
.md-header { border-bottom: 4px solid #caa344; }
```

Both builders copy project CSS. Material selectors apply to Material; another theme needs its own
selectors. For template changes, put an override such as `main.html` in `User-Manual/theme/overrides/`
and set `renderer.custom_dir: theme/overrides`. The path is relative to `User-Manual/`; the builder
resolves it before it stages its config in a temporary directory. Use [Material's documented override blocks](https://squidfunk.github.io/mkdocs-material/customization/).

## Install your own theme

Install a theme package into the **same Python environment** that runs the extension builder,
then set `renderer.theme` to its registered MkDocs theme name. Pin that package in your project's
requirements. An uninstalled name is rejected with the available themes.

For an authored theme, a minimal local package can extend Material:

```text
booking-theme/
  pyproject.toml
  booking_manual_theme/
    __init__.py
    mkdocs_theme.yml
    main.html
```

```toml
# booking-theme/pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
[project]
name = "booking-manual-theme"
version = "0.1.0"
dependencies = ["mkdocs>=1.6,<2", "mkdocs-material==9.7.6"]
[project.entry-points."mkdocs.themes"]
booking_manual = "booking_manual_theme"
[tool.setuptools.package-data]
booking_manual_theme = ["*.html", "*.yml"]
```

Keep `__init__.py` empty. Put `extends: material` in `mkdocs_theme.yml`, and use this template:

```jinja
{% extends "base.html" %}
{% block extrahead %}
  {{ super() }}
  <style>.md-header { border-bottom: 4px solid #caa344; }</style>
{% endblock %}
```

```bash
python -m pip install ./booking-theme
# Then set renderer.theme: booking_manual in User-Manual/manual.yml.
python .specify/extensions/user-manual/scripts/audit_manual.py --root User-Manual
python .specify/extensions/user-manual/scripts/build_manual.py --root User-Manual --audience end-user --language en --version preview
```

This uses MkDocs' [theme package and inheritance contract](https://www.mkdocs.org/dev-guide/themes/).
Keep theme code and assets in version control. Test audience filtering, keyboard navigation, RTL
when offered, and your actual PDF renderer before adopting a new theme.

## Rebuild the sample

```text
$user-manual Generate the booking application's English manual after I approve the Booking,
Payments, and Operations module map. Explain refund requests, decisions, and recovery. Use
$illustrate for the process diagram, then audit and build the end-user preview with Material.
```

The checked-in sample was scaffolded through Init and then authored for this synthetic scenario.
Its [gallery script](examples/booking-manual/build_gallery.py) runs the real audit and extension
builder for all five variants, serves the outputs locally, checks the embedded diagram loaded,
and captures Chromium screenshots. [Exact setup and commands](examples/booking-manual/README.md).
