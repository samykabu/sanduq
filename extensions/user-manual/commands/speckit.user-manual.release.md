---
description: "Builds versioned User Manual release notes, migration guides and release editions. Use when asked to 'release the manual', never on a feature branch."
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

1. Load `skills/user-manual/SKILL.md` and read `skills/user-manual/references/release-docs.md`.
2. Resolve release boundaries from explicit flags, then repository release conventions. Do not
   guess an application version when no reliable source exists.
3. Generate audience-specific release notes. Create migration guides only for user-visible,
   operational, API, configuration, infrastructure, or data compatibility changes.
4. Update version metadata and navigation without rewriting unchanged historical releases.
5. Run `python .specify/extensions/user-manual/scripts/audit_manual.py`, then
   `python .specify/extensions/user-manual/scripts/build_manual.py --all --version <value> --archive`
   once (every configured audience and language, with the renderer `manual.yml` selects). With
   `renderer.kind: mkdocs` add `--pdf` (one PDF per edition), plus
   `build_manual.py --audience <a> --language <l> --module <id> --pdf` for requested module PDFs.
6. Place generated artifacts under `User-Manual/site/` (and `User-Manual/pdf/`) for CI collection.
   Do not commit build products unless the consuming project explicitly chooses that policy.
7. Report exact artifact paths and any release-blocking documentation gaps.
