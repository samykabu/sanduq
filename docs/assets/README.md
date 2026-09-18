# Brand and diagram assets

## Logo and icon

| File | Use it for |
| --- | --- |
| `sanduq-logo.png` | The full lockup — icon, wordmark, tagline. Light backgrounds. |
| `sanduq-logo-dark.png` | The same lockup with the wordmark and tagline in `#F6F8FC`, for dark backgrounds. |
| `sanduq-icon.png` | Icon only, 1080×1080, centred on a transparent square. The master. |
| `sanduq-icon-512.png` | Icon at 512×512 — avatars, social previews, app tiles. |
| `sanduq-icon-128.png` | Icon at 128×128 — inline marks, favicons, README headers. |

Every file has a **transparent background**, so pair the lockup with the matching variant rather
than assuming a page colour:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/sanduq-logo-dark.png">
  <img src="docs/assets/sanduq-logo.png" alt="sanduq — tools for thoughtful delivery" width="460">
</picture>
```

The icon needs no variant. It is a single orange mark that holds its contrast on both themes, which
is why sub-READMEs and any square placement use the icon rather than the lockup.

### Brand colours

| Role | Hex | Where |
| --- | --- | --- |
| Mark orange | `#C65B36` | The toolbox |
| Wordmark green | `#233C32` | "sanduq" and the tagline, on light backgrounds |
| Wordmark on dark | `#F6F8FC` | The same glyphs in `sanduq-logo-dark.png` |

Sampled from the supplied artwork, not eyeballed. The icon and wordmark are separated at the
141-pixel empty column band between them, so the icon crop carries no part of the wordmark.

⚠️ The diagrams in this folder still use the **Cobalt Porcelain** palette from
[`.github/illustration-theme.yml`](../../.github/illustration-theme.yml), which is blue. They do not
yet match the brand. Re-theming them is an `illustrate` theme change plus a re-export of every
diagram, deliberately not bundled with this logo swap.

## Diagrams

`sanduq-packaging`, `sanduq-managed-workflow` and `sanduq-feature-lifetime` each keep their editable
`.html` source beside the `.svg` and `.png` exports. Edit the HTML and re-export with the
`illustrate` skill's exporter; never hand-edit an SVG.
