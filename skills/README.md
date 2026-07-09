# skills/

Standalone, shareable agent skills (Claude Code / `.agents` `SKILL.md` format).

Each skill lives in its own folder:

```
skills/
  <skill-name>/
    SKILL.md        # frontmatter (name, description, ...) + instructions
    (optional assets, scripts, references)
```

To expose a skill through the Claude Code plugin marketplace, bundle it inside a plugin
under `../plugins/` and register that plugin in `../.claude-plugin/marketplace.json`.
