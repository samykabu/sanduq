# Spec Kit entry-point fixtures

These pinned upstream scripts exercise the archive transaction integration with pinned Spec Kit entry points. They are test data, excluded from release ZIPs. Shell fixtures retain upstream declaration style with a scoped ShellCheck annotation. See `../../THIRD_PARTY_NOTICES.md` for their MIT terms.

The separate `extensions/scripts/smoke_memory_install.py` suite installs the actual release package using Sanduq CI's pinned Spec Kit build on Codex, Claude Code and Copilot, with both Bash and PowerShell templates and optional Git-extension guards.
