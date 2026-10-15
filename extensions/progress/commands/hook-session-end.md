---
description: Internal session_end hook handler for the progress report; invoked by the host, never by an agent
scripts:
  py: scripts/hook.py session_end
---

Internal. The host runs this through its native hooks with the hook JSON on stdin. It prints nothing.
