# Round 5 notes: S-DOC (root docs)

Docs requests from the stream notes and the live run, applied. No migration table yet (after S-VEND and S-W9).

## IP21: new installs get native Progress wiring (S-INST request)

- `docs/workflow/delivery-policy.md`: the `hook_wiring` comment no longer calls `speckit` the default; a second
  comment line says unset means native for new Progress installs, existing installs keep their wiring.
- `docs/start/upgrades.md`: same, in the opt-in keys block.
- `docs/extensions/progress.md` (With Workflow): "Defaults keep today's wiring" became "A new Progress install is
  wired natively; an existing one keeps its wiring until you set the key."
- `README.md` (round-2 upgrade section): "(new Progress installs get it by default)".

## D1: Progress needs Spec Kit 1.1.1+ (live run, S-INST)

- `docs/extensions/progress.md`: Requires row says Spec Kit 1.1.1 or later; Setup gains a paragraph naming
  `OPTIONAL_PACKAGE_SPECKIT_INCOMPATIBLE` and the two fixes (upgrade Spec Kit, or install without `--with progress`).
- `docs/start/install-by-host.md`: comment on `specify extension add progress`.
- `README.md`: Progress row Requires is "Python 3.11+, Spec Kit 1.1.1+".

## X23 (S-SH request)

- `CONTRIBUTING.md` release block: `release.py check-bumps` line, plus two sentences: what it fails on, and that
  edits to only `README.md`, top-level `CHANGELOG.md`, `LICENSE` or `docs/**` need no bump. Command checked: exit 0
  (bootstrap notices only).

## SC16, SC21, SC17 (S-SC requests)

- `docs/extensions/scope.md`: the readiness paragraph after Purpose (S-SC's exact wording); the
  `scope.py cancel <issue>-<hash>` sentence after the `render-spec` sentence.
- `docs/reference/commands.md:234-236`: sentence replaced with S-SC's wording.
- `docs/reference/hooks.md`: regenerated with `check_docs.py --write` (the generator is `hooks_text` in
  `extensions/scripts/check_docs.py`). Diff: scope-brainstorm `speckit.superspec.brainstorm` and scope-gate
  `speckit.clarify` are `replace`.

## W27, PR-RES (S-WF requests)

- `docs/workflow/state-files.md`: `repo_path` "still written by ..." replaced: version 2 checkpoints no longer carry
  it, version 1 checkpoints that do still load.
- `docs/workflow/lean-execution-delivery.md` P04: "Result projections preserve unknown usage honestly." removed.

## PM5, PM2b (S-PM)

- No root doc named `project-init.sh`/`.ps1` or `jq`. Updated what still implied shells:
  `docs/extensions/project.md` Requires ("Python 3; uses `gh` when available", was "Init also needs PowerShell or
  bash"); `CONTRIBUTING.md` smoke line is now `smoke_project_init.py` (default `--shell python`) and CI text says
  "Project initialization on Linux and Windows" (matches the `project-init` job S-CI landed).
- `docs/extensions/pr.md`: Review Feedback posts replies and resolves threads only from the approved plan file and
  resolves none until the PR head contains the pushed fixes.

## Not done / pending

- Migration table: not written (after S-W9).
- `extensions/README.md`: nothing needed (version column changes come with the bumps).

## IP22 (after S-VEND landed it; docs commit 5bb8366 was before this)

- `docs/extensions/progress.md`: the Deprecated bullet became Removed: `--schema v2` and `--layout classic` exit 2
  with `PROGRESS_REMOVED`; a stored `layout: classic` shows the Timeline with one notice, cleared by
  `progress theme --layout timeline`. Requires row: Workflow (1.17.0 or later) optional. With Workflow: with
  Workflow installed Progress needs 1.17.0 or later; an older one gets `PROGRESS_REMOVED` with the upgrade command,
  and `progress status` names the upgrade.
- `docs/start/upgrades.md:190` is in the Round 4 (1.17.0) table, so the row stays history: "Both still work in
  Progress 1.5.0; later releases refuse them with `PROGRESS_REMOVED` (exit 2)".
- No other root-doc mention of Progress v2 or the classic layout ("Sanduq Classic" is an Illustrate theme).
- `test_check_docs.py:49` (orchestrator's regex for the Progress line in install-by-host) kept.

## Requests

- **S-VEND** (`extensions/progress/README.md:118-129`): the `hook_wiring` block says `# default speckit` and "an absent
  key keeps the behaviour above". Change to: unset, a new Progress install (no Progress wiring yet) is wired
  natively; an existing install keeps the wiring `install-lock.json` records (Spec Kit's when none). Also, in the
  install section, Progress needs Spec Kit 1.1.1 or later (`requires.speckit_version`), and the Workflow installer
  refuses it on an older Spec Kit with `OPTIONAL_PACKAGE_SPECKIT_INCOMPATIBLE`.

## Checks

- `check_docs.py` (uv, Python 3.11): `Documentation OK: 70 guides, 47 of 47 commands, ...`, exit 0.
- `git diff --check` on README.md, CONTRIBUTING.md, docs: clean.
- After IP22: `check_docs.py` exit 0 (same OK line); `python extensions/scripts/test_check_docs.py` (as CI runs it):
  "check_docs regression checks passed.", exit 0.
