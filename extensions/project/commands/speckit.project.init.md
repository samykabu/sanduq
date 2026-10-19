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

1. Ask whether sync hooks are **required** (automatic at each lifecycle event) or **optional**
   (offered for approval), unless `$ARGUMENTS` carries `--hooks-mode` or the repo is a managed
   Sanduq workflow (the script then uses required sync without asking). Reruns keep the existing
   `hookMode`; first runs default to `optional`.
2. Run the script non-interactively (PowerShell on Windows, bash elsewhere), passing the user's
   flags in the shell's own syntax plus the non-interactive flag; it never prompts:

   ```powershell
   pwsh .specify/extensions/project/scripts/powershell/project-init.ps1 -NonInteractive [-Owner <login>] [-Number <n>] [-OwnerType user|org] [-HooksMode optional|required] [-AutoCreateColumns] [-DryRun]
   ```

   ```bash
   .specify/extensions/project/scripts/bash/project-init.sh --non-interactive [--owner <login>] [--number <n>] [--owner-type user|org] [--hooks-mode optional|required] [--auto-create-columns] [--dry-run]
   ```

   It resolves the owner and project, maps each phase to a column (exact, then fuzzy), updates
   the `project` hooks in `.specify/extensions.yml` and prints the mapping it wrote.
3. Read the output for missing choices and settle each with the user, then rerun with the flag
   it names: several projects (it lists them) → `--number`; a phase with no column → create it
   with `--auto-create-columns` or add the column on the board; no `project` scope or no login →
   give the user the printed `gh auth` command to run themselves (never start interactive auth).
4. **Commit `config.json` and `.specify/extensions.yml`.** In a managed workflow finish with
   `python .specify/extensions/workflow/scripts/workflow.py doctor --project` (a missing logical
   Scope column must be mapped or created first), then preview a sync:
   `python .specify/extensions/project/scripts/project_sync.py --phase open --dry-run`.
5. The owner and project number live in `config.json`; nothing else needs recording.

> Configures only the Project you select under the owner you pass; it never touches issues.
