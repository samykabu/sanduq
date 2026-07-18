# QA Extension

Make feature-level QA analysis and test documentation part of the Spec Kit lifecycle.

This extension immediately replaces the former `how-to-test` extension; no deprecated command or
installation aliases are retained.

## Commands

| Command | Invocation | Purpose |
|---|---|---|
| `speckit.qa.init` | `/speckit-qa-init` | Choose integrated or manual lifecycle policy |
| `speckit.qa.analyze` | `/speckit-qa-analyze` | Add missing test and evidence work before implementation |
| `speckit.qa.document` | `/speckit-qa-document` | Generate or refresh the implemented feature's QA test manual |

`QA.Init` recommends integrated mode. It makes analysis mandatory before implementation and tells
the sanduq PR workflow to generate QA documentation when feature evidence is missing or stale.

```text
/speckit-qa-init
/speckit-qa-analyze --feature specs/006-user-management
/speckit-qa-document --feature specs/006-user-management
```

## Scope

QA documentation is for testers and reviewers. It includes prerequisites, test data, scenarios,
expected results, screenshots, API examples, accessibility evidence, and useful diagrams. It stays
development-only and is not the end-user application manual.

Both analysis and documentation use feature-scoped freshness manifests under
`.specify/extensions/qa/state/`. The existence of an old manual is not enough to pass a lifecycle
gate.

The extension depends on `illustrate >=2.0.0,<3.0.0` for applicable diagrams.
