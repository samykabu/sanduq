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
| `speckit.assure.analyze` | `/speckit-assure-analyze` | Map assertions to existing proof and add tasks only for the gaps, before implementation |
| `speckit.assure.document` | `/speckit-assure-document` | Generate or refresh the implemented feature's QA test manual |

`speckit.assure.init` recommends integrated mode. It makes analysis mandatory before implementation and tells
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

Analyze writes `<feature>/qa/assertions.json`: one row per acceptance assertion with its requirement,
risk, owning test layer, boundary, evidence class, existing proof and disposition (`reuse`, `extend`,
`add`, `not-applicable`). Tasks exist only for `extend` and `add`. It adds no screenshot, mobile, foreground,
VM or native task by default, and no matrix of languages, sizes, zoom or themes; it reads those from your
project's own QA policy. Document adds a screenshot only where an assertion or reference needs one and
reuses captures that tests already produce.

Both analysis and documentation use feature-scoped freshness manifests under
`.specify/extensions/assure/state/`. The existence of an old manual is not enough to pass a lifecycle
gate.

## Limits of the readiness check

The check shows that the record is well formed and that what it cites exists. It cannot show that a test
exercises the assertion, that `boundary: any` was the right call, or that a `not-applicable` reason is
true. The test-economy screen on `not-applicable` reasons is a keyword screen, not a judgment: it catches
phrases such as "minimise tests" or "runtime budget", not every paraphrase, and a word like runtime or
cost on its own is allowed because a requirement can be about either. Those judgments stay with the
analyst and the reviewer. Readiness is not runtime acceptance: passing tests, a package install and a
run in a real project are checked separately.

## Lifecycle phase outside the managed Workflow

The managed Workflow maps `qa_analyze` and `qa_document` to these commands, so this section applies
only to projects that run them through Spec Kit hooks or by hand.

- Run `speckit.assure.analyze` at `after_tasks` (recommended): `spec.md`, `plan.md` and `tasks.md`
  exist and implementation has not started, so missing tests are added before developers begin.
- `before_implement` is the alternative for teams that want a final gate right before coding.
- Do not use `after_implement` for analysis; by then missing test work is usually rework.

The phase comes from the hook configuration in `.specify/extensions.yml`, which `speckit.assure.init`
writes. The commands no longer take a `--phase` flag.

## Scripts

| Script | Used by | What it does |
|---|---|---|
| `scripts/deps.py ensure illustrate` | analyze, document | Checks that `illustrate >=2.0.0,<3.0.0` is installed, follows the project's `update_policy`, prints one line and fails closed. The Illustrate references load only when a diagram is added or generated. |
| `scripts/assure_scan.py` | analyze (`--check`), document | Walks the repository (inside git, only folders git tracks or would add), skipping `scan.exclude` from `assure-config.yml`, classifies projects as web, mobile, backend, infrastructure or tooling, prints one line per project, and rewrites the block between `<!-- assure-scan:start -->` and `<!-- assure-scan:end -->` in `.github/memory/project-memory.md` with a `Last scanned` date. `--check` prints the inventory without writing (`--show-block` adds the block); text outside the markers is kept. |
| `scripts/audit_qa.py <manual.html>...` | document | Fails on an `<img>` without `alt` or `<figcaption>`, a relative `src` or `href` that does not resolve, a missing "Development-only draft" marker, or a secret-shaped value. |
| `scripts/assure_readiness.py check` | analyze | Checks `qa/assertions.json` before Analyze records: required fields, requirement ids that exist in `spec.md`, proof files inside the project and outside the feature folder, whole test names or identifiers in code (comments and partial matches fail), duplicates, task ids that exist outside the User Manual block, `qa-prepare` tasks that cover an `extend` or `add` row, supported `not-applicable` rows, and fixture or emulated evidence against a real boundary. It checks readiness only. |
| `scripts/assure_state.py record\|status` | analyze, document, PR, CI | Records and checks feature-scoped freshness. `status` lists `changed_inputs` and `changed_outputs` when the state is stale. `record --kind analyze` runs the readiness check first and refuses without a valid record. `status` reports an analysis recorded before contract 2 as `needs-reanalysis`. `status --gate` prints `skipped gate=off` and exits 0 unless `lifecycle.require_document_before_pr` is true. |

`scan.exclude` defaults to `.git`, `node_modules`, `bin`, `obj`, `dist`, `build`, `.next`, `.nuxt`,
`.turbo`, `.expo`, `coverage`, `.cache`, `.venv`, `venv`, `__pycache__`, `target`, `vendor`, `Pods` and
`.gradle`; `assure_init.py` writes that list into a new config, and you can edit it. A rerun of init keeps
your edits and changes only the three `lifecycle` values.
