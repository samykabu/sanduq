---
description: Queue an implemented feature without deleting it
---

# Prepare pending archive work

Use Python 3.11+ and Git from the repository root.
This command is also the final `after_implement` hook. Do not assume
`implemented` means `completed`. Do not archive an unfinished feature.

1. Run `python .specify/extensions/memory/scripts/archive.py pending`.
   If automatic mode is disabled, report that once and stop this hook successfully.
2. Resolve the feature explicitly from the command argument or current feature
   pointer. Never expand an ambiguous number to the first matching directory.
3. Read the feature's implemented changes and policy to select verification check
   names that cover the changed product behavior and its consumers. Do not pick
   only tooling checks for a product feature.
4. Run `python .specify/extensions/memory/scripts/archive.py queue --spec
   specs/<full-feature-name> --check <approved-name>` (repeat `--check` as needed).
   This records pending scope on the implementation branch. It does not commit,
   synthesize memory, delete, mark completion or claim tests passed.
5. Explain that the full checkpoint, synthesis and archive will run in the next
   local agent session after merge into the configured target branch, completion and verification.

Keep using the feature folder for QA, documentation, review and PR generation.
