---
description: "Creates the live progress report for the active feature and can install the Claude status line. Use when asked to 'track progress'."
---

Load `.specify/extensions/progress/skills/progress/SKILL.md` (record lanes, blockers and notes later with the
verbs it lists), then run from the repository root:

```bash
python .specify/extensions/progress/scripts/progress.py init $ARGUMENTS
```

Prints one line with the report path and a bind nonce. Report that line; do not narrate it.
