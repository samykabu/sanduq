# Changelog

## 1.1.0 — 2026-09-26

- Add the machine-readable `delegate-task.driver.v1` contract for workflow
  integration, including requested and observed model fields.
- Make the driver entry point work when the skill is installed through a
  symlinked folder.
- Keep run status and measured file changes explicit in the result contract;
  172 driver tests pass.

## 1.0.0

- Initial `agent-tools` plugin bundle with the `delegate-task` skill.
