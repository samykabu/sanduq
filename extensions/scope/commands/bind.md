---
description: "Bind the specification to its validated source GitHub issue."
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
