# Round 5 notes: S-VEND (vendored sides)

Source: `D:\Projects\Personal\sanduq-skills` after `git fetch origin --tags` only (no branch or working-tree change).
`vendor.py` reads tags with `git show`, so no checkout was needed; the `sanduq-skills-round5` worktree was not touched.
Tags `dev-tools-v1.4.0`, `illustration-tools-v3.7.1`, `agent-tools-v1.7.0` all resolve to `e3faeaa`.

`vendor.py update --source D:/Projects/Personal/sanduq-skills` printed
`illustration-tools-v3.7.1 dev-tools-v1.4.0 agent-tools-v1.7.0`; `vendor.py check`: `vendored inputs match vendor.lock.json`.
It also re-pinned both marketplaces (`.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json`: ref and sha for
the three bundles) and the `delegate-task` input (ref/sha only; no file under `extensions/workflow/assets/delegate-task/`
changed). No change to `extensions/scripts/vendor.py` was needed.

## AU22: vendored `init_manual.py`

- `vendor.lock.json` `inputs.user-manual`: map entry `skills/dev-tools/skills/user-manual/scripts/init_manual.py` ->
  `extensions/user-manual/scripts/init_manual.py`, and `replace["init_manual.py"]`: `import sanduq_ci\n` becomes the
  try/except import with the `parents[2]/workflow/scripts` fallback (exact text from the U-UP notes). The vendored file
  replaced Sanduq's copy at the same path. Net diff against the old copy: `import sys` moved into the fallback,
  `lifecycle:` block after `renderer:`, `--ci-policy` and `--no-tools` flags, `skill_root` name, `load_ci(args.ci_policy or root)`.
- `commands/speckit.user-manual.init.md:31`: the command line ends with `--no-tools`.
- `tests/test_init_manual.py`: `init()` passes `--no-tools`; the fresh-run test asserts `User-Manual/tools` is absent.
  Before the change the old script rejects the flag (`init_manual.py: error: unrecognized arguments: --no-tools`,
  checked on a scratch copy of `HEAD:extensions/user-manual/scripts/init_manual.py`), so both tests fail on it.
- `ADAPTER.md`: the section 3 row for `scripts/init_manual.py` moved to section 2 (one import rewrite; the command passes
  `--no-tools`); section 4's portable `test_init_manual.py` row names the extension test's `--no-tools`; the portable
  `sanduq_ci.py` row now says `load_ci` also reads a project root's `.specify/workflow.yml` when given a directory.
- `CHANGELOG.md` `## Unreleased`.

## IP24: bench from one source

- `vendor.lock.json` `inputs.progress-report.map`: `skills/agent-tools/skills/progress-report/tests/bench` ->
  `extensions/progress/tests/bench`. The input is exclusive: the folder now holds exactly the seven upstream files
  (`report.py` is new; `approaches.py` replaced Sanduq's edited copy). `package.py` excludes `tests`, so none is packaged.
- `tests/test_token_budget.py`: `os.environ.setdefault` for `PROGRESS_BENCH_CLI`
  (`python .specify/extensions/progress/scripts/progress.py`), `PROGRESS_BENCH_SKILL` (`skills/progress/SKILL.ext.md`) and
  `PROGRESS_BENCH_DOC` (`tests/token-benchmark.md`) before the bench import; `report` imported; upstream's
  `test_generated_report_is_current` restored. The test file now differs from upstream's only in those env lines.
- `tests/token-benchmark.md` generated after the sync (with the agent-tools 1.7.0 scripts):
  `python -m tests.bench.report` with the env above, then `--check` exit 0.

## IP19 and IP22: with the versions

- IP19: `extensions/illustrate/skill/scripts/svg_scan.py` added, 15 verifiers rewritten, `package.json` 3.7.1
  (105 insertions, 969 deletions under `extensions/illustrate/`). No Sanduq test copies a single verifier. CHANGELOG line.
- IP22: Progress scripts, `assets/ui/blocks.js`, `docs/` and `skills/progress/references/verbs.md` from agent-tools 1.7.0.
  Sanduq-owned docs: `README.md` (install section, quick start, command note, theming, upgrade note: v2 and classic are
  removed, Workflow 1.17.0 minimum), `dependencies.yml` (optional `workflow` range `>=1.9.0` -> `>=1.17.0,<2.0.0`, so the
  manifest states the minimum as the plan's IP22 row asks), `CHANGELOG.md` `## Unreleased` with a `### Migration` block
  (upgrade Workflow 1.16 and earlier first; read v3; `progress theme --layout timeline` for a stored classic).
- No Workflow code asks for `--schema v2` or `--layout classic` (grep of `extensions/**/*.py`).
- `WORKFLOW_UPGRADE` in `scripts/sanduq_progress/paths.py:409` pins `upgrade.py --version 1.17.1 --apply` (Workflow's
  current version is 1.17.1). Left as is, as U-UP noted: it is a valid target at or above the 1.17.0 minimum even if this
  round releases a later Workflow. If the orchestrator wants it to name the round's Workflow version, that is an
  upstream change.

## S-DOC request: Progress README

- `hook_wiring` block: the comment says `# unset: native for a new install, else the recorded wiring`; "an absent key keeps
  the behaviour above" is gone; a new first bullet says a new install (no Progress wiring yet) is wired natively and an
  existing one keeps the wiring `.specify/workflow/install-lock.json` records (Spec Kit's when none).
- Install section: Spec Kit 1.1.1 or later (`requires.speckit_version`); the Workflow installer refuses `--with progress`
  on an older Spec Kit with `OPTIONAL_PACKAGE_SPECKIT_INCOMPATIBLE`, and the two fixes.

## Workflow `dependencies.json` check

agent-tools 1.7.0 declares no Spec Kit requirement (no `speckit_version` anywhere in `skills/agent-tools` at `e3faeaa`), and
Progress's `extension.yml` keeps `requires.speckit_version: ">=1.1.1.dev0,<2.0.0"`. So `optional_speckit.progress` in
`extensions/workflow/dependencies.json` needs no change. `optional.progress` is `"1.5.0"`: it must move to the new Progress
version when the orchestrator bumps Progress (request below).

## Test runs (`uv run --no-project --python 3.11 --with pyyaml --with packaging --with jsonschema`)

| Suite | Result |
| --- | --- |
| `extensions/progress/tests` (`--with tiktoken==0.14.0`) | 15 tests OK, none skipped (8 token-budget tests incl. `test_generated_report_is_current`) |
| `extensions/user-manual/tests` | 53 tests OK |
| `extensions/illustrate/tests` | 18 tests OK |
| `extensions/assure/tests` | 41 tests OK (Assure files untouched by vendoring) |
| `extensions/scripts/tests` | 189 tests OK |
| Workflow progress tests (`test_progress`, `test_progress_integration`, `test_progress_reporting`, `test_progress_runs`, `test_lean_native_integration`, `test_install_hooks`), run against the new vendored Progress | 118 tests OK |
| `vendor.py check` | `vendored inputs match vendor.lock.json` |
| `check_docs.py` | `Documentation OK: 70 guides, 47 of 47 commands, 8 of 8 vendored portable skills, ...` exit 0 |
| `extensions/scripts/test_check_docs.py` (run as CI does) | FAILS: `check_docs accepted: missing ['progress']` (not mine, see Requests) |
| `git diff --check` on owned paths | clean |

## Requests

- **Orchestrator / S-WF** (`extensions/workflow/dependencies.json`): set `optional.progress` to the new Progress version
  when Progress is bumped (1.5.0 today). `optional_speckit.progress` stays `>=1.1.1.dev0,<2.0.0`.
- **S-DOC**: `docs/extensions/progress.md:95-96` (Deprecated bullet) and `docs/start/upgrades.md:190` still say v2 and
  classic "still work"; they are removed now (wording in `extensions/progress/CHANGELOG.md` Unreleased).
- **Owner of `extensions/scripts/test_check_docs.py`** (S-DOC or orchestrator): it fails at the committed
  `docs/start/install-by-host.md:109`, which now reads `specify extension add progress     # needs Spec Kit 1.1.1 or later`.
  The test's `install.replace('specify extension add progress\n', '', 1)` no longer matches, so the mutated page still
  passes. The fixture needs the new line text.
- **S-WF** (from U-UP, optional): `sanduq_ci.load_ci(root)` reading a policy file when given one, so `--ci-policy <file>`
  on the vendored `init_manual.py` works in Sanduq. The command does not pass it.
- **Upstream, later** (not blocking): agent-tools `model.py`'s module docstring still says it outputs the v2 compatibility
  document.
