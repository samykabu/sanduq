# Content model

Use four distinct page intents:

- Tutorial: teach through a complete, safe learning journey.
- How-to: solve one concrete task with prerequisites, steps, result, and troubleshooting.
- Reference: state exact fields, endpoints, configuration, entities, or commands.
- Explanation: clarify concepts, architecture, rationale, lifecycle, and relationships.

Each page front matter declares `title`, `module`, `audiences`, `language`, `content_type`,
`source_evidence`, `last_verified`, and `status`. Each feature or use case includes a plain-language
purpose, actors, prerequisites, normal flow, alternate/permission/error states, expected outcome,
and applicable screenshots or diagrams.

## Markdown that reads correctly on GitHub

Write GitHub-flavored Markdown, so every page reads correctly in the repository and the build
translates it for any other renderer:

| Need | Write | Avoid (shows as raw text on GitHub) |
| --- | --- | --- |
| Note, tip, warning | `> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!WARNING]`, `> [!CAUTION]` | `!!! note` |
| Collapsible or alternative content | `<details>` with a `<summary>` and a blank line before the body | `??? note`, `=== "Tab"` |
| Tables, task lists, footnotes | GitHub pipe tables, `- [ ]`, `[^1]` | Grid tables, definition lists |
| Links and images | Relative paths; `<path with spaces.png>`; reference links `[text][id]` | Absolute or site-root paths |

The audit warns about MkDocs-only syntax and names the GitHub form to use.

Avoid duplicating the same prose across editions. Share factual source fragments where safe, but
author separate audience explanations when the reader's goal or required detail differs.
