# Initialise GitHub Project sync

One-time setup for the `project` extension in this repository. Discovers a GitHub Project
(v2), maps the Spec Kit lifecycle phases to that board's **Status** columns, and writes
`.specify/extensions/project/config.json`. Run this once per repo before the lifecycle
hooks can do anything.

## User Input

```text
$ARGUMENTS
```

Optional flags: `--owner <login>` · `--number <n>` · `--owner-type user|org` ·
`--auto-create-columns` · `--non-interactive` · `--dry-run`.

## Outline

1. Ensure `gh` is authenticated with the **`project`** scope:
   `gh auth refresh -h github.com -s project,read:project`.
2. Run the init script (PowerShell primary, bash twin on non-Windows):

   ```bash
   pwsh .specify/extensions/project/scripts/powershell/project-init.ps1 [flags]
   # or
   .specify/extensions/project/scripts/bash/project-init.sh [flags]
   ```

3. It will:
   - resolve the **owner** (default: the authenticated user) and **project number** (lists
     the owner's projects to pick from if not passed),
   - discover the project id, the `Status` field id, and its existing columns,
   - **map each phase to a column** — exact match → fuzzy match → prompt. For any phase with
     no column it offers to **create** one (or does so automatically with
     `--auto-create-columns`),
   - write `config.json` (ids, `phaseToStatus`, `statusOptions`, `statusOrder`, sub-issue
     policy).

4. **Commit `config.json`** so every assistant/checkout shares the same board wiring. Then
   validate with a dry run: `project-sync.ps1 -Phase open -DryRun`.

> Only ever configures the Project you select under the owner you pass; it never touches
> issues. The sync command (not init) creates issues, and only in the repo matching `origin`.
