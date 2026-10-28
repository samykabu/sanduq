# Sanduq Scope (retired)

Scope is part of [Sanduq Workflow](https://github.com/samykabu/sanduq/blob/main/extensions/workflow/README.md#scope)
from Workflow 2.0.0. This package, Scope 2.0.0, is the last release: it has no code, presets or hooks.
Installing it over Scope 1.x removes the old commands, and Spec Kit prints the migration step:

```bash
python .specify/extensions/workflow/scripts/upgrade.py --version 2.0.0 --apply
```

The upgrade removes this package and keeps `.specify/scope/`. Every `speckit.scope.<x>` command is now
`speckit.workflow.scope-<x>`; the full table is in
[upgrades](https://github.com/samykabu/sanduq/blob/main/docs/start/upgrades.md).

The [changelog](CHANGELOG.md) lists the earlier releases. Scope is MIT licensed; see
[LICENSE](https://github.com/samykabu/sanduq/blob/main/extensions/scope/LICENSE).
