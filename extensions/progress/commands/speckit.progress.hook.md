---
description: Internal hook handler for the progress report; run by Spec Kit events, never by an agent
scripts:
  py: hooks/dispatch.py
---

Internal. Spec Kit's event dispatcher runs this for every Progress event, with the host's hook JSON on stdin. The
script reads the event from that JSON. It prints nothing.

This file is deliberately not listed under `provides.commands` in `extension.yml`, so Spec Kit does not register it as
an agent command or skill. The dispatcher still finds it by file name.
