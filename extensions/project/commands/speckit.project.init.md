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
`--hooks-mode optional|required` · `--auto-create-columns` · `--non-interactive` ·
`--dry-run`.

## Outline

1. Ensure `gh` is authenticated with the **`project`** scope:
   `gh auth refresh -h github.com -s project,read:project`.
2. Ask whether Project sync lifecycle hooks should be:
   - **required** — Spec Kit renders them as automatic hooks and the assistant must execute
     sync at each configured lifecycle event;
   - **optional** — Spec Kit offers the hook for manual/user-approved execution.

   When `$ARGUMENTS` contains `--hooks-mode`, use it without prompting. Otherwise let the
   script ask. Non-interactive reruns preserve the existing `hookMode`; first-time runs
   default to `optional` unless the flag is supplied.

3. Run the init script (PowerShell primary, bash twin on non-Windows). Translate the
   command arguments to the shell's native parameter syntax; do not append double-dash
   arguments verbatim to the PowerShell script:

   ```powershell
   pwsh .specify/extensions/project/scripts/powershell/project-init.ps1 `
     -Owner <login> -Number <n> -OwnerType user -HooksMode required
   ```

   ```bash
   .specify/extensions/project/scripts/bash/project-init.sh \
     --owner <login> --number <n> --owner-type user --hooks-mode required
   ```

4. It will:
   - resolve the **owner** (default: the authenticated user) and **project number** (lists
     the owner's projects to pick from if not passed),
   - discover the project id, the `Status` field id, and its existing columns,
   - **map each phase to a column** — exact match → fuzzy match → prompt. For any phase with
     no column it offers to **create** one (or does so automatically with
     `--auto-create-columns`),
   - update every `project` hook in `.specify/extensions.yml` to `optional: true` or
     `optional: false`, according to the selected mode,
   - write `config.json` (ids, `phaseToStatus`, `statusOptions`, `statusOrder`, sub-issue
     policy, and `hookMode`).

5. **Commit `config.json` and `.specify/extensions.yml`** so every assistant/checkout shares
   the same board wiring and hook policy. Then validate with a dry run:
   `project-sync.ps1 -Phase open -DryRun`.

6. Once the **owner** and the **project number** are retrieved, remember to store them in the Spec Kit memory file so it can be used when creating and tracking specs.

> Only ever configures the Project you select under the owner you pass; it never touches
> issues. The sync command (not init) creates issues, and only in the repo matching `origin`.
