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

## Documentation diagrams

Documentation uses the tracked Cobalt Porcelain light theme; the logo retains its brand colors.
Editable HTML and SVG exports live in `docs/diagrams/`:

| Source | Export | Explains |
| --- | --- | --- |
| [Dispatcher sequence](../diagrams/dispatcher-sequence.html) | [SVG](../diagrams/dispatcher-sequence.svg) | Stage ownership, host work, and evidence handoff |
| [Feature state](../diagrams/feature-state.html) | [SVG](../diagrams/feature-state.svg) | Completion, blockers, checkpoint continuation, and Finalize |
| [Implementation orchestration](../diagrams/implementation-orchestration.html) | [SVG](../diagrams/implementation-orchestration.svg) | Worker ownership and verified phase integration |
| [Workflow lifecycle](../diagrams/workflow-lifecycle.html) | [SVG](../diagrams/workflow-lifecycle.svg) | The full managed feature lifecycle |

[Progress token usage](progress-token-usage.png) illustrates the implementation report in the
[operations reference](../workflow-operations.md). The `workflow-plan/` directory holds historical
plan-delivery evidence, referenced by implementation records. Keep those records with their assets.

Logo masters and icon sizes are intentional reusable brand assets. Keep them even when only one
size is embedded. Removed overview/theme-preview sets were unused after the README split; the
replacement guides and diagrams now own their explanations. See [cleanup rules](../../CONTRIBUTING.md#update-documentation-and-assets).
