---
description: Inspect pending archival and recovery state
---

# Archive status

Run `python .specify/extensions/memory/scripts/archive.py status`. Summarize policy
approval, pending/blocked features, active phase, checkpoint and candidate location.
Do not edit the central document or infer success from source folder deletion.
When a run is interrupted, its checkpoint and journal remain authoritative recovery
evidence. An archive is finished only when its final commit is verified.
