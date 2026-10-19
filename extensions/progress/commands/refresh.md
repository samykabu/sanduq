---
description: "Forces one progress snapshot now (hooks already refresh it); never marks the feature complete. Use when asked to 'refresh the progress report'."
---

Run from the repository root:

```bash
python .specify/extensions/progress/scripts/progress.py refresh --verbose $ARGUMENTS
```

Automatic collection already refreshes the report. Use this only for a forced snapshot; it does not mean the feature is complete.
