# Sync the feature to the GitHub Project

Keep the configured GitHub Project board in step with the current Spec Kit feature: a
**parent feature issue** whose **Status** advances through the lifecycle, plus one native
**sub-issue per task**, closed as its task is checked off. Requires `project init` to have
been run once in this repo.

## User Input

```text
$ARGUMENTS
```

`$ARGUMENTS` is the **phase**. One of `open` · `analysis` · `engineer-review` · `ready` ·
`in-progress` · `in-review` · `done` · `auto`. If empty, use `auto` (infer from artifacts +
board status).

| phase             | side effect                                              |
| ----------------- | ------------------------------------------------------- |
| `open`            | create parent issue + add to the Project                |
| `analysis`        | advance the card                                        |
| `engineer-review` | advance the card                                        |
| `ready`           | create one sub-issue per task + advance                 |
| `in-progress`     | close sub-issues for checked tasks + advance            |
| `in-review`       | advance (also auto-set when an open PR exists)           |
| `done`            | advance when all sub-issues are closed                  |

The actual Status **column** each phase maps to is whatever `project init` recorded in
`config.json` for this board.

## Outline

1. Resolve the phase from `$ARGUMENTS` (default `auto`). If run from a Spec Kit lifecycle
   hook, the hook prompt names the phase — use it.
2. Run the engine (idempotent, no-regress):

   ```bash
   pwsh .specify/extensions/project/scripts/powershell/project-sync.ps1 -Phase <phase>
   # or
   .specify/extensions/project/scripts/bash/project-sync.sh --phase <phase>
   ```

   Preview with `-DryRun` / `--dry-run`.

3. Preconditions (the script checks them and exits 0 with a logged reason if unmet — surface
   it, don't treat as failure): `config.json` present (else run `project init`); `gh`
   authenticated with the `project` scope; `origin` is a GitHub remote.

   > Only operates on the configured Project and issues in the repo matching `origin`.

4. Report the parent issue #/URL, the Status set, sub-issues created/closed, and `done/total`.

## Notes

- **No-regress:** the card never moves to an earlier column; re-running any phase, or `auto`,
  only advances or reconciles the board.
- **Self-contained In review:** the `in-progress`/`auto` phases advance to the in-review
  column automatically when an open PR exists for the branch — no dependency on any PR extension.
- **State** lives in the configured `stateFile` (committed) so all assistants stay in sync.
