# plugins/

This folder is reserved for future Claude Code plugin bundles and MCP-backed plugins.

The currently published sanduq plugin bundles live under [`../skills/`](../skills/) because they are
skill-first packages:

| Plugin | Source | Version |
| --- | --- | ---: |
| `illustration-tools` | [`../skills/illustration-tools`](../skills/illustration-tools/) | 3.0.0 |
| `dev-tools` | [`../skills/dev-tools`](../skills/dev-tools/) | 1.0.0 |

They are registered in [`../.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json).

Install from Claude Code:

```text
/plugin marketplace add samykabu/sanduq
/plugin install illustration-tools@sanduq
/plugin install dev-tools@sanduq
```

For a new plugin, add a folder containing `.claude-plugin/plugin.json`, then register it in the
marketplace manifest and bump the plugin version before publishing.
