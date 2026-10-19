---
description: "Forces one progress report snapshot now; the host hooks already refresh it, and a snapshot never marks the feature complete. Use when implementation ends, or when asked to 'refresh the progress report' or 'take a final progress snapshot'."
---

Run from the repository root:

```bash
python .specify/extensions/progress/scripts/progress.py refresh --verbose $ARGUMENTS
```

Automatic collection already refreshes the report. Use this only for a forced snapshot; it does not mean the feature is complete.
