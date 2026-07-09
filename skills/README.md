# skills/

Standalone skills and skill-first Claude Code plugin bundles.

## Published plugin bundles

| Bundle | Version | Includes |
| --- | ---: | --- |
| [`devtools`](devtools/) | 1.7.1 | `pr-review`, `how-to-test`, `resal-standards-review`, and `pr-generate-description`. |
| [`illustration-tools`](illustration-tools/) | 1.3.1 | `architecture-diagram` and `process-flow-diagram`. |

Install them through the sanduq marketplace:

```text
/plugin marketplace add samykabu/sanduq
/plugin install devtools@sanduq
/plugin install illustration-tools@sanduq
```

## Standalone skills

[`diagrams`](diagrams/) is a standalone diagram-design skill package with its own assets,
references, and generation scripts.

Each standalone skill uses the usual `SKILL.md` structure:

```text
skills/
  <skill-name>/
    SKILL.md
    references/
    scripts/
    assets/
```

When publishing a skill as a Claude Code plugin, include a `.claude-plugin/plugin.json`, register it
in [`../.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json), and bump the plugin
version.
