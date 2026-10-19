---
description: "Discovers the application, proposes a module map for approval and scaffolds the bilingual-ready, audience-aware User Manual. Use when a project has no User-Manual/ yet or its module map needs a refresh; triggers: 'create a user manual', 'init the manual'."
---

# Initialize User Manual

Create `User-Manual/` when it does not exist, or safely refresh its configuration and module map.

## User input

```text
$ARGUMENTS
```

Flags: `--non-interactive`, `--module <name>`, `--enable-arabic`, `--provider <id>`, `--dry-run`.

## Instructions

1. Read `.specify/extensions/user-manual/skills/user-manual/SKILL.md` and
   `references/discovery.md`.
2. Inventory repository projects, domain boundaries, routes, menus, API groups, database contexts,
   deployment units, specifications, and existing documentation. Exclude generated/vendor folders.
3. Propose a module map with evidence paths. In interactive mode, ask the user to approve, rename,
   merge, or split modules. Never silently replace an already approved module map.
4. `init_manual.py` writes the agreed defaults (languages, audience visibility, private CI preview,
   age-encrypted public previews, approved-provider rule, `lifecycle.impact_scope: all`); confirm
   only product name, Arabic, branding source, development runtime, provider and edition visibility.
5. Run:

   ```text
   python .specify/extensions/user-manual/scripts/init_manual.py --repo-root . --modules-file <json>
   ```

   Add `--enable-arabic`, `--provider`, or `--dry-run` when selected. The JSON file must contain the
   approved module objects with `id`, `name`, `description`, and `evidence`. When Arabic is enabled,
   every module must also provide a reviewed `name_ar` and `description_ar`; never substitute
   English headings or machine-like placeholder Arabic.
6. Generate the full English baseline from grounded repository evidence. Create Arabic pages only
   when enabled; record missing translations without blocking the English build.
7. Generate system-level architecture and ER overviews. Generate smaller module ER diagrams only
   for modules with data ownership. Never include secret values or production records.
8. When a hosted provider was selected, load `skills/preview-publishing/SKILL.md` and create the
   provider descriptor and pinned CI adapter for explicit approval. A provider name in `manual.yml`
   alone never authorizes deployment.
9. Validate with `audit_manual.py` and report the module map, missing evidence, translation coverage,
   and build instructions.
