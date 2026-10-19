---
description: Internal post-write check for Illustrate diagrams; run by Spec Kit events, never by an agent
scripts:
  py: hooks/self_check_hook.py
---

Internal. Spec Kit's event dispatcher runs this after every Write or Edit, with the host's hook JSON on stdin. The
script exits at once unless `.specify/workflow.yml` sets `illustrate.hooks.self_check: true` and the written file is
an HTML diagram.

This file is deliberately not listed under `provides.commands` in `extension.yml`, so Spec Kit does not register it as
an agent command or skill. The dispatcher still finds it by file name.
