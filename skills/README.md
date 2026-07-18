# skills/

Portable skills and skill-first Claude Code plugin bundles that remain independent from Spec Kit.

## Portable skills

| Skill | Version | Includes |
| --- | ---: | --- |
| [`illustrate`](illustration-tools/skills/illustrate/) | 3.0.0 | Twenty-seven diagram types, themes, icons, terminal/export support, hand-drawn variants, and technical-color architecture/process packs. |

The same capability is packaged as the versioned [`illustrate`](../extensions/illustrate/) Spec Kit
extension so consuming extensions can install and update it through the `specify` CLI.

## Published plugin bundles

| Bundle | Version | Includes |
| --- | ---: | --- |
| [`illustration-tools`](illustration-tools/) | 2.0.0 | One unified `illustrate` skill. |

Install them through the sanduq marketplace:

```text
/plugin marketplace add samykabu/sanduq
/plugin install illustration-tools@sanduq
```

The former `devtools` bundle was retired after its workflows moved into the `pr` and `how-to-test`
extensions; the Resal standards skill was removed.

When publishing a skill as a Claude Code plugin, include a `.claude-plugin/plugin.json`, register it
in [`../.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json), and bump the plugin
version.
