---
description: "Builds versioned User Manual release notes, migration guides, HTML archives and PDFs per audience and language. Use when an application release is tagged or merged, never on a feature branch; triggers: 'release the manual', 'build the v3 manual PDFs'."
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
5. Run `python .specify/extensions/user-manual/scripts/audit_manual.py`, then
   `python .specify/extensions/user-manual/scripts/build_manual.py --all --version <value> --archive --pdf`
   once (every configured audience and language, one PDF each), plus
   `build_manual.py --audience <a> --language <l> --module <id> --pdf` for requested module PDFs.
6. Place generated artifacts under `User-Manual/site/` and `User-Manual/pdf/` for CI collection.
   Do not commit build products unless the consuming project explicitly chooses that policy.
7. Report exact artifact paths and any release-blocking documentation gaps.
