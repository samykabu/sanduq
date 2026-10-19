---
description: "Runs as the after_specify hook: binds the new spec to its source issue. Use when asked to bind a spec after Specify."
---

# Bind source issue

Use the explicit issue number successfully checked by the guard in this same
Specify invocation. If absent, STOP; never infer it from global pending state.
Run `python .specify/extensions/scope/scripts/scope.py bind <number> --apply`.
This must succeed before the existing `after_specify` Project sync hook runs.
It writes `scope-source.json` beside the spec and initializes that feature's
Project sync state with the original issue ID and Project item, preserving task
sub-issues. It must not create a second feature issue. It must then set the live
Project Status and local sync state to **Feature Specification**. A status write
failure is a hard failure, not a successful Specify completion.

In a managed workflow claim, take the exact command and flags from
`.specify/extensions/workflow/skills/workflow/references/scope-binding.md`.
