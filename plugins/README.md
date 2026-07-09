# plugins/

Claude Code plugins (and MCP servers) hosted by this marketplace.

Each plugin lives in its own folder with a `.claude-plugin/plugin.json` manifest, e.g.:

```
plugins/
  <plugin-name>/
    .claude-plugin/plugin.json
    commands/  agents/  skills/  hooks/   # whatever the plugin ships
```

Register every plugin in [`../.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json)
so consumers can `/plugin install <plugin>@sanduq` after
`/plugin marketplace add samykabu/sanduq`.
