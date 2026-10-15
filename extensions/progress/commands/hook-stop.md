---
description: Internal stop hook handler for the progress report; invoked by the host, never by an agent
scripts:
  py: scripts/hook.py stop
---

Internal. The host runs this through its native hooks with the hook JSON on stdin. It prints nothing.
