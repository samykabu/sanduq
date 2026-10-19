---
description: "Advances the feature's parent issue on the configured GitHub Project to a lifecycle phase and creates or closes task sub-issues. Use when asked to 'move the card', 'sync the board' or when a lifecycle hook names a phase."
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
| `analysis`, `engineer-review`, `done` | advance the card |
| `ready` | one sub-issue per task, advance |
| `in-progress` | close sub-issues of checked tasks, advance |
| `in-review` | advance (auto-set when an open PR exists) |

Columns come from `config.json` (written by `project init`); the card never moves back.

## Outline

1. Run (add `--dry-run` to preview):

   ```bash
   python .specify/extensions/project/scripts/project_sync.py --phase <phase> --summary
   ```

2. The script checks `config.json`, `gh` auth with the `project` scope and a GitHub `origin`,
   and exits 0 with `skipped reason=<why>` when one is missing: report the reason; a skip is not
   a completed sync. It only touches the configured Project and issues in the `origin` repo.
3. Report the summary line: `ok issue=<n> status=<status> created=<n> closed=<n>`.
