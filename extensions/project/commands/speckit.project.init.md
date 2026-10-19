---
description: "Sets up GitHub Project sync once per repository, mapping lifecycle phases to Status columns. Use when asked to 'connect the project board'."
---

# Initialise GitHub Project sync

One-time setup per repository: discovers a GitHub Project (v2), maps the Spec Kit lifecycle
phases to its **Status** columns and writes `.specify/extensions/project/config.json`.

## User Input

```text
$ARGUMENTS
```

Optional flags: `--owner <login>` · `--number <n>` · `--owner-type user|org` ·
`--hooks-mode optional|required` · `--auto-create-columns` · `--non-interactive` ·
`--dry-run`.

## Outline

1. Ensure `gh` has the **`project`** scope: `gh auth refresh -h github.com -s project,read:project`.
2. Ask whether sync hooks are **required** (automatic at each lifecycle event) or **optional**
   (offered for approval), unless `$ARGUMENTS` carries `--hooks-mode` or the repo is a managed
   Sanduq workflow (the script then uses required sync without asking). Reruns keep the existing
   `hookMode`; first runs default to `optional`.
3. Run the script (PowerShell on Windows, bash elsewhere), translating the flags to the shell's
   own syntax:

   ```powershell
   pwsh .specify/extensions/project/scripts/powershell/project-init.ps1 -Owner <login> -Number <n> -OwnerType user -HooksMode required
   ```

   ```bash
   .specify/extensions/project/scripts/bash/project-init.sh --owner <login> --number <n> --owner-type user --hooks-mode required
   ```

   It resolves the owner and project (listing the owner's projects when not passed), maps each
   phase to a column (exact, fuzzy, then prompt; `--auto-create-columns` creates missing ones),
   updates the `project` hooks in `.specify/extensions.yml` and prints the mapping it wrote.
4. **Commit `config.json` and `.specify/extensions.yml`.** In a managed workflow finish with
   `python .specify/extensions/workflow/scripts/workflow.py doctor --project` (a missing logical
   Scope column must be mapped or created first), then preview a sync:
   `python .specify/extensions/project/scripts/project_sync.py --phase open --dry-run`.
5. The owner and project number live in `config.json`; nothing else needs recording.

> Configures only the Project you select under the owner you pass; it never touches issues.
