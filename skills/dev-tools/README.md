# dev-tools

Five modular, standalone skills for creating and maintaining application User Manuals without
requiring Spec Kit.

| Skill | Use it for |
| --- | --- |
| `user-manual` | Complete discovery, initialization, incremental updates, audits, HTML, and PDF. |
| `user-manual-api-docs` | Public, administrator, and private API reference bundles. |
| `user-manual-release-docs` | Audience-aware release notes and migration guides. |
| `user-manual-ui-screenshots` | Deterministic, redacted web and mobile screenshots. |
| `user-manual-preview-publishing` | Private PR artifacts, approved previews, and releases. |

Install the complete core:

```bash
npx skills add samykabu/sanduq --skill user-manual
```

Or install the Claude Code plugin bundle:

```text
/plugin marketplace add samykabu/sanduq
/plugin install dev-tools@sanduq
```

See the root [README](../../README.md) for prompts and real-life scenarios for every skill.
