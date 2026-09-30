# Pre-split fixtures

Frozen, byte-exact copies of the workflow skill sources as they existed at commit
`5c96254` (the last commit before the SKILL.md/execution.md/preset-overlay split), used by
`test_skill_split.py` so the completeness check does not depend on git history being
available (CI checks out shallow, and `git show <sha>:<path>` fails there).

Do not edit these files; regenerate them from commit `5c96254` if the base commit
reference in `test_skill_split.py` ever changes.
