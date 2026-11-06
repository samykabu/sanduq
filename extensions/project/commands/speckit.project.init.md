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

## Outline

1. Unless `$ARGUMENTS` sets the hook mode or the repo is a managed Sanduq workflow (always
   `required`), ask whether sync hooks are **required** (automatic) or **optional** (offered for
   approval). Reruns keep the existing mode; first runs default to `optional`.
2. Run, passing the user's flags; it never prompts:

   ```sh
   python .specify/extensions/project/scripts/project_init.py [--owner <login>] [--number <n>] [--owner-type user|org] [--hooks-mode optional|required] [--auto-create-columns] [--dry-run]
   ```

   Exit 4: the last line is `{"ok": false, "needs": [...]}`; ask the user to pick from each
   entry's `options` and rerun with its `flag`. A warning that a phase has no column: create it
   with `--auto-create-columns` or add the column on the board, then rerun. No `project` scope or
   no login: give the user the printed `gh auth` command (never start interactive auth).
3. **Commit `config.json` and `.specify/extensions.yml`.** In a managed workflow finish with
   `python .specify/extensions/workflow/scripts/workflow.py doctor --project` (a missing logical
   Scope column must be mapped or created first), then preview a sync:
   `python .specify/extensions/project/scripts/project_sync.py --phase open --dry-run`.

> Configures only the Project you select under the owner you pass; it never touches issues.
