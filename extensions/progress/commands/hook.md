---
description: Internal hook handler for the progress report, invoked by native host hooks and not by agents
scripts:
  py: scripts/progress.py hook
---

Internal. The host runs this through its native hooks with the hook JSON on stdin. Agents never invoke it.
