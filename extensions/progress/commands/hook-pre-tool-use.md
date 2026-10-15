---
description: Internal pre_tool_use hook handler for the progress report; invoked by the host, never by an agent
scripts:
  py: scripts/progress.py hook pre_tool_use
---

Internal. The host runs this through its native hooks with the hook JSON on stdin. It prints nothing.
