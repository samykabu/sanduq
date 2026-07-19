# Assure Extension

Assure makes feature-level QA analysis and test documentation part of the Spec Kit lifecycle.

This extension immediately replaces the former `qa` extension (itself a rename of `how-to-test`);
no deprecated command or installation aliases are retained. The `qa` id was retired because it
conflicts with an existing Spec Kit community extension.

## Commands

| Command | Invocation | Purpose |
|---|---|---|
| `speckit.assure.init` | `/speckit-assure-init` | Choose integrated or manual lifecycle policy |
| `speckit.assure.analyze` | `/speckit-assure-analyze` | Add missing test and evidence work before implementation |
| `speckit.assure.document` | `/speckit-assure-document` | Generate or refresh the implemented feature's QA test manual |

`Assure.Init` recommends integrated mode. It makes analysis mandatory before implementation and tells
the sanduq PR workflow to generate QA documentation when feature evidence is missing or stale.

```text
/speckit-assure-init
/speckit-assure-analyze --feature specs/006-user-management
/speckit-assure-document --feature specs/006-user-management
```

## Scope

QA documentation is for testers and reviewers. It includes prerequisites, test data, scenarios,
expected results, screenshots, API examples, accessibility evidence, and useful diagrams. It stays
development-only and is not the end-user application manual.

Both analysis and documentation use feature-scoped freshness manifests under
`.specify/extensions/assure/state/`. The existence of an old manual is not enough to pass a lifecycle
gate.

The extension depends on `illustrate >=2.0.0,<3.0.0` for applicable diagrams.
