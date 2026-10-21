# Round 5 notes: U-UP (upstream sanduq-skills)

Worktree `D:\Projects\Personal\sanduq-skills-round5`, branch `feat/round-5`. No commits, tags or pushes. Bumps per that repo's
convention (both `plugin.json` files per bundle; Illustrate's `package.json` too): dev-tools 1.3.0 -> 1.4.0,
illustration-tools 3.7.0 -> 3.7.1, agent-tools 1.6.2 -> 1.7.0. Changelog: root `CHANGELOG.md` entry
"2026-10-21 — dev-tools 1.4.0, illustration-tools 3.7.1, agent-tools 1.7.0: round 5" and `skills/agent-tools/CHANGELOG.md`
"1.7.0 — 2026-10-21" with a `### Migration` block (the date is today's; change it at release if needed).

## AU22: vendorable `init_manual.py` (dev-tools 1.4.0)

Diff of sanduq `extensions/user-manual/scripts/init_manual.py` against upstream 1.3.0 had five differences. Where each went:

| Sanduq copy has | Upstream now |
| --- | --- |
| `lifecycle:` / `impact_scope: all` in `manual.yml` | Written always (comment no longer names `manual_impact.py`; sanduq's test reads only the YAML value) |
| No copies in `User-Manual/tools/` | `--no-tools` flag |
| `sanduq_ci.load_ci(root)` (project CI from `.specify/workflow.yml`) | `load_ci(args.ci_policy or root)`; upstream `load_ci` reads a directory as a project root (`<dir>/.specify/workflow.yml`). Without `--ci-policy` a portable user with that file now gets its `ci:` selection instead of the default |
| Import fallback to `../../workflow/scripts` | Not generic (it names sanduq's layout): stays the one import rewrite below |
| `extension_root` variable name | Cosmetic; upstream keeps `skill_root` (same `parents[1]` layout) |

Authored-page protection was already identical (AU10 landed in both in round 4). `--repo-root` kept; no `--project-root`
(Amendment 14). Files: `skills/dev-tools/skills/user-manual/scripts/init_manual.py`, `scripts/sanduq_ci.py`,
`tests/test_init_manual.py` (2 new tests), `SKILL.md`, `docs/skills/user-manual.md`.

Tests: the 2 new tests fail on the 1.3.0 scripts (checked against `git show HEAD:` copies) and pass now. dev-tools suite:
34 tests OK. Sanduq check (scratch copy of `extensions/user-manual` + `extensions/workflow/scripts`, upstream file with the
rewrite below applied): `test_init_manual` and `test_manual_impact` pass (the scratch copy lacked `sanduq_freshness`, so
`test_manual_state` could not import there; unrelated).

**For S-VEND.** Add to `vendor.lock.json` `inputs.user-manual.map`:

```json
["skills/dev-tools/skills/user-manual/scripts/init_manual.py", "extensions/user-manual/scripts/init_manual.py"]
```

and to `inputs.user-manual.replace`:

```json
"init_manual.py": [
  ["import sanduq_ci\n",
   "try:  # vendored beside this script in a built package\n    import sanduq_ci\nexcept ImportError:  # canonical source tree\n    import sys\n    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / \"workflow\" / \"scripts\"))\n    import sanduq_ci\n"]
]
```

(`import sanduq_ci\n` occurs once in the file; `Path` is imported above it.) Then:

- `commands/speckit.user-manual.init.md:31`: add `--no-tools` to the command line
  (`... init_manual.py --repo-root . --modules-file <json> --no-tools`). Without it the vendored script copies the three
  scripts into `User-Manual/tools/`.
- `extensions/user-manual/tests/test_init_manual.py`: pass `--no-tools` in `init()` and assert `User-Manual/tools` is absent.
- `ADAPTER.md` rows 37 and 51: the script is vendored with one import rewrite; the command passes `--no-tools`.

## IP19: `scripts/svg_scan.py` (illustration-tools 3.7.1)

New `skills/illustration-tools/skills/illustrate/scripts/svg_scan.py`: `GROUP_TAGS`, `BODY_TAGS`, `NUMBER_RE`, `DIGIT_RE`,
`Element`, `first_wins`, `Scanner(source, marks, transform_carrier)` (marks collected as `<tag>s` attributes, as before),
`attrs_of` (parser form), `printed_number(body, number)`, `line_of`, `median`, `is_hand_variant`. Verifiers load it like
`theme_tokens.py` (`sys.path.insert` + import). Moved out of 15 verifiers: `is_hand_variant` x15, `line_of` x4, `median` x5,
`attrs_of` (parser form) x4, `first_wins`/`Element`/`_Scanner` x5 (marimekko keeps a 15-line `_Scanner` subclass for its
`segment_carriers` count), `printed_number` x4 (now a one-line wrapper passing the verifier's own `number`). Stay local
(different contracts): every `transform_carrier`, every `number`, regex `attrs_of` in bump, beeswarm, waterfall,
exploded's tree `Element`, `theme_palettes`/`_hex_to_rgb` (heatmap, waterfall; theme code, not scanning).
The 15 verifiers lose 952 lines and gain 77; `svg_scan.py` is 207 lines.

Tests: new `tests/test_svg_scan.py` (scanner, printed number, and a guard that no verifier redefines the shared helpers).
`test_verify_sankey.py` copies the checker into a sandbox; it now copies `svg_scan.py` beside it (one line; the sandbox
mirrors the scripts folder the checker loads from). Suite before: 223 tests OK (skipped 6), 276 s. After: see "Test runs".
CI's verifier block (`verify-<type>.py --all` for the 12 data types, polar, exploded, axonometric) all exit 0.

Sanduq side: the whole skill folder is vendored, so `svg_scan.py` arrives with `vendor.py update`. Nothing in sanduq
copies a single verifier (grep of `extensions/` and `.github/`).

## IP22: Progress v2 output and the classic layout removed (agent-tools 1.7.0)

Code (`skills/agent-tools/skills/progress-report/`):

- `model.py`: `build(ctx, now, rev, state, plan)` returns v3 only; `build_pair`, `SCHEMAS`, `schema_name` gone;
  `build_v2` stays as the internal base document (docstring says no command prints it).
- `refresh.py`: no `layout()`, no `theme` import; `render_data.write(ctx, report)` always writes v3 with
  `ui: {"layout": "timeline"}` (kept so a view still holding a pre-1.7 `blocks.js` draws the timeline; `copy_assets`
  runs only at init).
- `progress.py`: `status --json` and `export` are v3; `--schema v2` raises `PROGRESS_REMOVED` (exit 2, one line).
  Text `status` = unchanged summary line (from `build_v2`'s summary) + codex hint + classic-layout notice + Workflow-below-1.17
  notice, all on the same line.
- `paths.py`: `workflow_version(root)` (regex on `.specify/extensions/workflow/extension.yml`), `workflow_outdated(root)`,
  `removed(what, root)`; `WORKFLOW_UPGRADE = python .specify/extensions/workflow/scripts/upgrade.py --version 1.17.1 --apply`.
- `theme.py`: `LAYOUTS = ("timeline",)`; a stored `classic` validates and resolves to timeline; `--layout classic` and
  `--file` with classic print the `PROGRESS_REMOVED` line and exit 2; a new preset drops a stored classic; `_republish` gone.
- `render_md.render_v2`, `validate.validate_v2`, the classic half of `assets/ui/blocks.js` (header/lanes/boards/events blocks,
  `RENDER`, `ALL`, `TITLES`, `own`, layout switching, v2 acceptance in the poller) removed. `blocks.js` 58,295 -> 41,521 B.

Exact messages (Amendment 7):

```text
progress: error PROGRESS_REMOVED --schema v2 was removed in agent-tools 1.7.0; Sanduq Workflow 1.16.0 is installed and needs 1.17.0 or later: python .specify/extensions/workflow/scripts/upgrade.py --version 1.17.1 --apply
progress: error PROGRESS_REMOVED the classic layout was removed in agent-tools 1.7.0
progress: 2/5 tasks, 0 lanes active, 0 blocked, 0 decisions pending (rev 3) Sanduq Workflow 1.16.0 is installed; Progress needs 1.17.0 or later: python .specify/extensions/workflow/scripts/upgrade.py --version 1.17.1 --apply
progress: ... (rev 3) theme layout classic was removed; the page shows timeline (progress theme --layout timeline)
```

Byte compatibility for Workflow 1.17: the summary line is built from the same `build_v2` summary as before
(`test_the_one_line_summary_and_the_stored_report` unchanged and green; the new status test asserts the line is a prefix
when a hint is added); `runs --json` untouched (`test_legacy` runs-contract tests green). The bench's
`test_generated_report_is_current` stayed green with the new code, so the verb outputs the bench measures are unchanged.

Docs: `docs/commands.md` (status, theme, export, JSON schemas; the v2 field table removed, the measurement paragraph kept
under v3, the export example replaced by real v3 output), `docs/contracts.md` (the v2 section is now "Base document
(internal)" with its rules kept, since v3 is built on them; layout, CLI, `data.js`), `docs/hosts.md`, `README.md`,
`references/verbs.md`. Theme keys `blocks`/`hidden` are still accepted (old files) and documented as unused.

Tests (deliberate rule changes, each marked IP22 in the test): `test_v3_model.py` (v2 refusal with and without a Workflow,
status hint, stored-classic fallback, classic refusal), `test_review_c1b.py` (layout envelope, layout command rebuilds
nothing; the busy-lock republish test removed with `_republish`), `test_projection.py` (v3 export), `test_plan.py`,
`test_legacy.py` and `helpers.run842_report` read the internal base document instead of `--schema v2`,
`test_review_c1.py` (`selectedList` count 0), `test_p1_review.py` (two source checks of the classic page removed).
`tests/test_ui_browser.py` (the classic page) deleted; its poller/banner/token tests ported to v3 in
`test_ui_v3_browser.py` (`PollerTests`, `LightTests`, `ThemeSwapTests`), plus `RemovedClassicTests` and a v2-refusal
test. The browser run caught a regression in my first `blocks.js` cut (`item` and `mvTag` live in the classic region but
v3 uses them); fixed.

## IP24: bench from one source (agent-tools 1.7.0)

`tests/bench/approaches.py` reads `PROGRESS_BENCH_CLI` (default `python .claude/skills/progress-report/scripts/progress.py`)
and `PROGRESS_BENCH_SKILL` (default `SKILL.md`, relative to the folder holding `tests/`); the skill call names
`SKILL_PATH.parent.name` (`progress-report` upstream, `progress` in sanduq). `tests/bench/report.py` reads
`PROGRESS_BENCH_DOC` (default `docs/token-benchmark.md`, same base). Upstream `report.py --check` passes with the defaults.

Proof for sanduq's layout (scratch copy of sanduq `extensions/progress` with upstream `tests/bench` and the env below):
`python -m tests.bench.report` wrote a report byte-identical to the one sanduq's own modified `approaches.py` produces,
and `--check` then exits 0. (Both were with the pre-IP22 Progress scripts; regenerate after the vendor sync.)

**For S-VEND.** In `vendor.lock.json` `inputs.progress-report.map` (line 660 area) add:

```json
["skills/agent-tools/skills/progress-report/tests/bench", "extensions/progress/tests/bench"]
```

`vendor.py planned()` skips paths whose parts include `tests` only relative to the mapped source, so the five bench
files plus `report.py` and `__init__.py` are taken; the input is `exclusive`, so `extensions/progress/tests/bench/` must hold
only them (sanduq's copy is replaced). `package.py`'s `EXCLUDE` has `tests`, so it stays unpackaged.

Sanduq's `extensions/progress/tests/test_token_budget.py` (sanduq-owned) then:

```python
import os
os.environ.setdefault('PROGRESS_BENCH_CLI', 'python .specify/extensions/progress/scripts/progress.py')
os.environ.setdefault('PROGRESS_BENCH_SKILL', 'skills/progress/SKILL.ext.md')
os.environ.setdefault('PROGRESS_BENCH_DOC', 'tests/token-benchmark.md')
```

before `from bench import approaches, report, run, traces`, and restores upstream's
`test_generated_report_is_current`. Generate the sanduq report once (needs tiktoken, as CI's progress suite has):

```bash
cd extensions/progress
PROGRESS_BENCH_CLI="python .specify/extensions/progress/scripts/progress.py" \
PROGRESS_BENCH_SKILL=skills/progress/SKILL.ext.md PROGRESS_BENCH_DOC=tests/token-benchmark.md \
python -m tests.bench.report          # writes tests/token-benchmark.md; add --check to verify
```

`extensions/progress/tests/token-benchmark.md` is sanduq-owned (not vendored, not packaged); the vendored
`docs/token-benchmark.md` stays upstream's numbers. Run: `python -m unittest discover -s extensions/progress/tests -q`.

## Requests

- **S-VEND**: the AU22 and IP24 mappings and edits above; IP22: the sanduq Progress README/CHANGELOG line that `--schema v2`
  and `classic` are gone and Workflow 1.17 is the minimum (Progress already flags an older Workflow in `status`).
- **S-WF** (owner of `extensions/workflow/scripts/sanduq_ci.py`), optional: let `load_ci(root)` read a policy file when it is
  given one (`if Path(root).is_file(): path = Path(root)`), matching upstream. Without it, a sanduq user who passes
  `--ci-policy <file>` to the vendored `init_manual.py` gets the default selection (sanduq's command never passes it).

## Test runs (this worktree, `uv run --no-project --python 3.11 ...`)

Final runs after every edit:

| Suite | Result | Time |
| --- | --- | --- |
| `skills/dev-tools/skills/user-manual/tests` | 34 tests OK | 6 s |
| `skills/agent-tools/skills/progress-report/tests` (with tiktoken) | 507 tests OK, 4 skipped (browser tests opt-in) | 125 s |
| `test_ui_v3_browser.py` with `PROGRESS_UI_TESTS=1` (Playwright, cached Chromium) | 49 tests OK | 67 s |
| `skills/illustration-tools/tests` | 226 tests OK, 6 skipped (223 before; +3 in `test_svg_scan.py`) | 186 s (276 s before, machine load differs) |
| Illustrate CI verifier block (`verify-*.py --all` etc.) | every command exit 0 | |
| `python -m tests.bench.report --check` (upstream defaults) | exit 0 | |
| `git diff --check` | clean | |

Not run: delegate-task node tests (untouched), `validate_skills.py` and `claude plugin validate` (CI-only tools).
