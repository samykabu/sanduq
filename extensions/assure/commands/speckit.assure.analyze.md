---
description: 'Maps each acceptance assertion to its owning test and adds tasks only for missing proof. Use when asked to "check QA readiness" before implementation.'
---

# Analyze QA Coverage

Review the active Spec Kit feature before implementation. Record which assertion each requirement
needs, which test layer owns it, and what proof already exists. Add a task to `tasks.md` only where
the proof is missing or too thin.

## User Input

```text
$ARGUMENTS
```

Optional flags:

- `--feature <path>` - override feature directory detection, e.g. `specs/006-user-management`.
- `--report-only` - report missing tasks without editing `tasks.md`.

## Instructions

### Start: skip an unchanged rerun

Resolve the feature (`--feature`, else `feature_directory` in `.specify/feature.json`) and check the
last recorded analysis:

```text
python .specify/extensions/assure/scripts/assure_state.py status --kind analyze --feature <feature-path> --summary
```

On `ok`, nothing changed since the last recorded analysis under the current contract (the `after_tasks` and `before_implement`
hooks both run this command): unless `--report-only` was supplied or the user asked for a fresh
analysis, report "analysis current" with that line and stop. On `error`, or when the feature is not
resolved yet, continue.

### 0. Load the QA contract

Read the rules in `.specify/extensions/assure/skills/assure/SKILL.md` and its
`references/analysis.md` (assertion record, task block format, report shape). In
lifecycle-integrated mode this command is a gate: do not report success while a critical assertion
lacks existing proof or a concrete task.

### 0a. Ensure the Illustrate dependency

Run `python .specify/extensions/assure/scripts/deps.py ensure illustrate`. On exit `0`, pass on any
"newer compatible release available" note and load Illustrate only in step 3, before adding a
diagram task. On a non-zero exit, report its line verbatim, follow it, skip the diagram bullet in
step 3 and use no other diagram system.

### 1. Resolve the feature and scan the workspace

Resolve the active feature as the contract says. Read `spec.md`, `plan.md` and `tasks.md` (required),
then `quickstart.md`, `data-model.md`, `contracts/*`, `research.md` and the recent git diff when they
exist.

Run the workspace scan in check mode; this stage reads the inventory and must not write the memory
file (Document writes it):

```text
python .specify/extensions/assure/scripts/assure_scan.py --check
```

Read the printed inventory (one line per detected project) instead of walking the tree. A frontend that the feature artifacts describe but the scan did not detect is
`planned/spec-only`, never detected implementation.

### 2. Identify impacted projects

Map the feature to projects from the inventory plus the plan, task file paths, contracts, routes, menu
names, UI screens, mobile flows, backend endpoints, changed files, and tests. Use the frontend rows to
decide where the tests for `extend` and `add` rows go. When a feature affects a
planned frontend path that is not implemented yet, add tasks against the planned path and report the
project as `planned/spec-only`.

### 3. Build the assertion record

Write `<feature-path>/qa/assertions.json` (shape in `references/analysis.md`). Do not build a matrix
from screens, states or dimensions. For each acceptance assertion in the spec's requirements, success
criteria and acceptance scenarios, record:

- the requirement it comes from, quoted as it appears in `spec.md`;
- the risk (`critical`, `major` or `minor`) and the observable result;
- the owning layer. One layer owns each assertion; add a second row only for a separate claim, such as
  a real IPC path behind a unit-tested rule;
- the boundary: `real` when the requirement names a real boundary (keyring, OS shell, live server,
  restart, connected client), otherwise `any`; and the evidence class of the proof (`real`, `fixture`
  or `emulated`). Fixture or emulated evidence never closes a `real` boundary;
- the existing proof: search the workspace for a test that already checks it and cite its path and
  test name. Cite only what you opened;
- the disposition: `reuse`, `extend`, `add` or `not-applicable`.

Then apply these rules:

- Add a task only for `extend` and `add`. A `reuse` row adds no task. `not-applicable` needs a reason
  and a quotation from the spec or the consumer policy that supports it.
- Count, runtime or budget never removes a critical assertion. Report the conflict instead.
- Screenshot work only where a requirement or reference asks for that visual, or a named manual
  needs the figure. Reuse an existing capture when it fits.
- Mobile work only for a mobile surface the spec, plan or scan names. Otherwise record the limitation
  once in the manual, not as a task.
- No default foreground, VM or native-host task. Add one only when an assertion's boundary is `real`
  and needs it.
- Read the consumer's QA policy when it exists (the constitution, QA policy document or file the spec, plan or
  `assure-config.yml` points to). Apply its dimensions and named exceptions as written;
  never multiply assertions by language, size, zoom, theme or motion on your own.
- Keep real connected journeys, native, security, accessibility and recovery assertions whenever a
  requirement demands them, and keep the useful manual checks.
- An API-only scenario needs a request/response sample task unless existing proof covers it. A
  test task still names path, runner, scenario and expected result.
- Add an Illustrate task only if step 0a confirmed `illustrate` is ready and a visual helps
  verification: read `.specify/extensions/illustrate/skill/references/type-index.md`, choose the type,
  and name it in the task.

### 4. Patch `tasks.md`

Unless `--report-only` was supplied, add the tasks for `extend` and `add` rows following the task block
rules in `references/analysis.md`. Each task names the assertion id it covers. Ground every task in the
spec, plan, contracts, or project structure; do not invent screens, endpoints, or request/response
bodies. Put each task's `T###` in its row's `tasks` list.

Run the mechanical checks, including under `--report-only`:

```text
python .specify/extensions/assure/scripts/assure_readiness.py check --feature <feature-path>
```

Fix every `error` line and rerun. The checks cover the record's shape, requirement references, proof
paths and literal test names, task links, duplicates, `not-applicable` support, and evidence class
against a real boundary. A proof must be a test file: feature records, other features' records,
`.specify`, and document or JSON files are refused. They do not show that a test exercises the assertion.
That judgment stays with you, and the human reviewer.

Every `requirement-unreferenced` warning needs a disposition before you record: give the requirement a
row, or a `not-applicable` row with its cited basis. The scanner only warns because it cannot tell a
testable requirement from a statement of fact. A critical requirement without a row is a critical gap and
blocks recording. Do not invent a test name to silence a noncritical one.

### 5. Record freshness and report

After all edits and validation succeed, record the analysis against the final feature and working
tree state:

```text
python .specify/extensions/assure/scripts/assure_state.py record --kind analyze --feature <feature-path>
```

Record adds `tasks.md`, `qa/assertions.json` and every cited proof file as outputs, and it runs the
same checks first. It refuses without a valid assertion record; there is no way around that. Do not
record in `--report-only` mode or while critical gaps remain unresolved. An analysis recorded before
this contract shows `needs-reanalysis`; it is kept as recorded, never upgraded in place, so rerun the
analysis to move it to the new contract.
Write any freshness log or status report to `.specify/extensions/assure/state/<feature-name>/reports/`
(`<feature-name>` is the feature folder's name), which freshness never reads. A file added to the
feature folder after `record` is a new input and makes the analysis stale.

Report the contract's shape plus: assertions by disposition (reuse, extend, add, not-applicable) with
the proof cited for each reuse; tasks added with their IDs (or, under `--report-only`, the tasks that
should be added); the `requirement-unreferenced` warnings; any unresolved ambiguity, especially parent
feature routing or mobile availability. Do not claim tests exist unless they are present in
`tasks.md` or the workspace, and do not call a file proof of an assertion you did not read.

## Quality Bar

After this command runs, a developer can implement the feature and see which existing tests already
cover each requirement and which tasks are genuinely new. Document should not discover a screen,
state or API sample that no assertion asked for, or one that an assertion needed and nobody planned.
