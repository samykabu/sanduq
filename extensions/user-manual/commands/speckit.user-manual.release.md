---
description: "Finalize versioned User Manual release notes, migration guides, HTML archives, and PDFs."
---

# Release User Manual

Generate release artifacts after merge or for an application release tag, never as the normal
feature-branch publication step.

## User input

```text
$ARGUMENTS
```

Flags: `--version <value>`, `--from <ref>`, `--to <ref>`, `--module <id>`, `--dry-run`.

## Instructions

1. Load `skills/user-manual/SKILL.md` and `skills/release-docs/SKILL.md`.
2. Resolve release boundaries from explicit flags, then repository release conventions. Do not
   guess an application version when no reliable source exists.
3. Generate audience-specific release notes. Create migration guides only for user-visible,
   operational, API, configuration, infrastructure, or data compatibility changes.
4. Update version metadata and navigation without rewriting unchanged historical releases.
5. Run a full audit, all configured HTML builds, one PDF per edition/language, and requested
   module-specific PDFs.
6. Place generated artifacts under `User-Manual/site/` and `User-Manual/pdf/` for CI collection.
   Do not commit build products unless the consuming project explicitly chooses that policy.
7. Report exact artifact paths and any release-blocking documentation gaps.
