---
description: "Moves the feature issue to a lifecycle phase on the GitHub Project; standalone, it also creates and closes task sub-issues. Use when asked to 'sync the board'."
---

# Sync the feature to the GitHub Project

## User Input

```text
$ARGUMENTS
```

`$ARGUMENTS` is the phase (default `auto`, inferred from the artifacts and the board); a
lifecycle hook or a managed claim names it.

| phase | side effect |
| --- | --- |
| `open` | create the parent issue, add it to the Project |
| `analysis`, `engineer-review` | advance the card |
| `ready` | one sub-issue per task (standalone only), advance |
| `in-progress` | close sub-issues of checked tasks (standalone only), advance |
| `in-review` | advance (auto-set when an open PR exists) |
| `done` | close sub-issues of checked tasks (standalone only), advance; only when passed explicitly, never inferred |

Columns come from `config.json` (written by `project init`); the card never moves back. Under
Sanduq Workflow, Workflow owns task issues, so no phase creates or closes sub-issues.

## Outline

1. Run (add `--dry-run` to preview):

   ```bash
   python .specify/extensions/project/scripts/project_sync.py --phase <phase> --summary
   ```

2. The script checks `config.json`, `gh` auth with the `project` scope and a GitHub `origin`,
   and exits 0 with `skipped reason=<why>` when one is missing: report the reason; a skip is not
   a completed sync. It only touches the configured Project and issues in the `origin` repo.
   `error ... project-sync-state.json ...` means the state file is malformed: it is kept as it is;
   restore it from git or fix it, then rerun.
3. Report the summary line: `ok issue=<n> status=<status> created=<n> closed=<n>`.
