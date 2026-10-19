---
description: Reports policy approval, pending or blocked features, the archive phase and the next command. Use when asked "what is the archive status".
---

# Archive status

Run `python .specify/extensions/memory/scripts/archive.py status`. Summarize policy
approval, pending/blocked features, active phase, checkpoint, candidate location and
`data.next` (the command to run next and why). Do not edit the central document or infer
success from source folder deletion. When a run is interrupted, its checkpoint and journal
remain authoritative recovery evidence; follow
`.specify/extensions/memory/references/recovery.md`. An archive is finished only when its
final commit is verified.
