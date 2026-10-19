# Assure Extension

For setup and a worked example, see [Install by host](https://github.com/samykabu/sanduq/blob/main/docs/start/install-by-host.md)
and the [assure page](https://github.com/samykabu/sanduq/blob/main/docs/extensions/assure.md).
Every command and its example is in the [command reference](https://github.com/samykabu/sanduq/blob/main/docs/reference/commands.md#assure).


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
/speckit-assure-analyze --feature specs/412-refund-approval
/speckit-assure-document --feature specs/412-refund-approval
```

## Scope

QA documentation is for testers and reviewers. It includes prerequisites, test data, scenarios,
expected results, screenshots, API examples, accessibility evidence, and useful diagrams. It stays
development-only and is not the end-user application manual.

Both analysis and documentation use feature-scoped freshness manifests under
`.specify/extensions/assure/state/`. The existence of an old manual is not enough to pass a lifecycle
gate.

## Lifecycle phase outside the managed Workflow

The managed Workflow maps `qa_analyze` and `qa_document` to these commands, so this section applies
only to projects that run them through Spec Kit hooks or by hand.

- Run `speckit.assure.analyze` at `after_tasks` (recommended): `spec.md`, `plan.md` and `tasks.md`
  exist and implementation has not started, so missing tests are added before developers begin.
- `before_implement` is the alternative for teams that want a final gate right before coding.
- Do not use `after_implement` for analysis; by then missing E2E work is usually rework.

The phase comes from the hook configuration in `.specify/extensions.yml`, which `speckit.assure.init`
writes. The commands no longer take a `--phase` flag.

## Scripts

| Script | Used by | What it does |
|---|---|---|
| `scripts/deps.py ensure illustrate` | analyze, document | Checks that `illustrate >=2.0.0,<3.0.0` is installed, follows the project's `update_policy`, prints one line and fails closed. The Illustrate references load only when a diagram is added or generated. |
| `scripts/assure_scan.py` | analyze (`--check`), document | Walks the repository, skipping `scan.exclude` from `assure-config.yml`, classifies projects as web, mobile, backend, infrastructure or tooling, prints one line per project, and rewrites the block between `<!-- assure-scan:start -->` and `<!-- assure-scan:end -->` in `.github/memory/project-memory.md` with a `Last scanned` date. `--check` prints without writing; text outside the markers is kept. |
| `scripts/audit_qa.py <manual.html>...` | document | Fails on an `<img>` without `alt` or `<figcaption>`, a relative `src` or `href` that does not resolve, a missing "Development-only draft" marker, or a secret-shaped value. |
| `scripts/assure_state.py record\|status` | analyze, document, PR, CI | Records and checks feature-scoped freshness. `status` lists `changed_inputs` and `changed_outputs` when the state is stale. `status --gate` prints `skipped gate=off` and exits 0 unless `lifecycle.require_document_before_pr` is true. |

`scan.exclude` defaults to `.git`, `node_modules`, `bin`, `obj`, `dist`, `build`, `.next`, `.nuxt`,
`.turbo`, `.expo`, `coverage` and `.cache`; `assure_init.py` writes that list, and you can edit it.
