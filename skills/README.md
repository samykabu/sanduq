# skills/

Portable skills and skill-first Claude Code plugin bundles that remain independent from Spec Kit.

## Portable skills

| Skill | Version | Includes |
| --- | ---: | --- |
| [`illustrate`](illustration-tools/skills/illustrate/) | 3.1.0 | Twenty-seven diagram types, tracked project light/dark color and font themes, icons, exports, hand-drawn variants, and technical-color architecture/process packs. |
| [`user-manual`](dev-tools/skills/user-manual/) | 1.0.0 | Self-contained manual discovery, audience editions, Markdown, Material HTML, PDF, English/Arabic, RTL, audit, and build automation. |
| [`user-manual-api-docs`](dev-tools/skills/user-manual-api-docs/) | 1.0.0 | Safe, filtered API reference documentation. |
| [`user-manual-release-docs`](dev-tools/skills/user-manual-release-docs/) | 1.0.0 | Release notes and migration guides. |
| [`user-manual-ui-screenshots`](dev-tools/skills/user-manual-ui-screenshots/) | 1.0.0 | Deterministic, synthetic-data UI screenshot workflows. |
| [`user-manual-preview-publishing`](dev-tools/skills/user-manual-preview-publishing/) | 1.0.0 | Private PR artifacts, approved hosted previews, and versioned releases. |

The same capability is packaged as the versioned [`illustrate`](../extensions/illustrate/) Spec Kit
extension so consuming extensions can install and update it through the `specify` CLI.

## Published plugin bundles

| Bundle | Version | Includes |
| --- | ---: | --- |
| [`illustration-tools`](illustration-tools/) | 3.1.0 | One unified `illustrate` skill with project-level theme initialization. |
| [`dev-tools`](dev-tools/) | 1.0.0 | Five modular standalone User Manual skills. |

Install them through the sanduq marketplace:

```text
/plugin marketplace add samykabu/sanduq
/plugin install illustration-tools@sanduq
/plugin install dev-tools@sanduq
```

Install a portable skill directly with `npx skills`, for example:

```bash
npx skills add samykabu/sanduq --skill user-manual
```

When publishing a skill as a Claude Code plugin, include a `.claude-plugin/plugin.json`, register it
in [`../.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json), and bump the plugin
version.
