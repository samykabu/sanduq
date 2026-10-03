---
description: Configure Sanduq Memory for this Spec Kit project
---

# Initialize project memory

Inspect the project's default/merge branch, implementation directories and actual
verification commands. Run `python .specify/extensions/memory/scripts/install.py
--target-branch <branch>` from the target project root. This installs host wrappers,
session instructions, ordered lifecycle hooks and guarded feature/auto-commit
scripts. It creates `.specify/memory-policy.json` only when absent and preserves
existing project settings while refreshing the installed `guard_paths`. It does not enable archiving or remove feature files.

Review and configure the generated policy's named `checks` using executable argument
arrays, timeouts and `covers` globs. Set `default_checks`, `product_prefixes` and
`product_files` to match the project. No checks are shipped as assumed verification.
Commit the policy and integrations before enabling automatic mode. Use the enable
command for the owner's one-time review of the concrete policy and its hash.

Core feature scripts must match the shipped patch contexts. Local edits or unsupported
upstream versions stop initialization before guard writes. Preserve them and adapt
the guard explicitly; do not overwrite scripts. Git-extension guards are installed
when that extension exists. Re-run initialization after installing/upgrading it.

If the Engage archive extension is present, initialization stops. Preserve it until
the owner approves cutover after the Sanduq release is verified; never uninstall it
as a side effect of initializing Memory.
