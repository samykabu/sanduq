---
description: "Discover the application, approve its module map, and initialize a bilingual-ready audience-aware User Manual."
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
4. Confirm only project-specific facts not already configured: product name, optional Arabic,
   branding source, authorized development runtime, publishing provider, and edition visibility.
   Preserve these agreed defaults:
   - English required; Arabic optional; RTL always supported.
   - End User public only after approval.
   - Administrator/Operator authenticated and internal.
   - Technical Reference private.
   - Private CI preview on every feature PR.
   - On public repositories, age-encrypt preview artifacts and require the safe public recipient in
     the `USER_MANUAL_PREVIEW_AGE_RECIPIENT` GitHub Actions variable. Keep the private key outside
     the repository and CI.
   - Hosted ephemeral preview only through an explicitly approved provider.
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
