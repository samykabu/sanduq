# Round 3 review: illustrate and progress (stream R5, read-only)

Measured on worktree `feat/round-3` (base fb96e41): `illustrate` 2.5.0 vendoring `illustration-tools-v3.5.0`
(sha `f260c7b`, 504 files in `vendor.lock.json`), `progress` 1.3.0 vendoring `agent-tools-v1.5.0`. Upstream is
sanduq-skills at 8ae7ec5. Paths are relative to `extensions/<id>/` unless they start with `extensions/`, `docs/` or
`upstream:` (= `D:\Projects\Personal\sanduq-skills\skills\`). Everything under `illustrate/skill/**` and Progress's
`scripts/`, `assets/ui/`, `docs/`, `skills/progress/references/` is vendored: options that touch it are marked
**upstream** (change in sanduq-skills, release the bundle, `vendor.py sync`, bump the extension).

Measurements were made on this machine (Windows 11, CPython 3.13 on PATH; the uv tool Python of specify_cli
1.1.4.dev0 where stated). Hook timings are the median of 9 runs in a scratch project
(`<scratchpad>/proj`) that has the installed Spec Kit's `_EVENTS_DISPATCHER_TEMPLATE` as `.specify/events.py`, copies of
both extensions, and a feature initialized and bound with `progress.py init` / `bind`. The interpreter floor
(`python -c pass`) moved between 33 and 66 ms across runs, so differences under about 20 ms are noise. Package sizes come
from `extensions/scripts/package.py` writing to the scratchpad. Test times come from a timed `unittest` runner over
each suite.

## Summary

1. The Illustrate procedure contradicts its own assets. `SKILL.md:55-62` says to copy a template or example and then
   pass `self_check.py --strict`. Only 51 of the 296 shipped HTML files pass `--strict` (178 pass the default run). In
   116 of the 127 strict failures the cause is an svg `min-width` that differs from the viewBox width. All four
   technical-color templates also fail the default check, because they carry CDN scripts and `onclick` that their own
   reference requires.
2. The Illustrate post-write hook is always registered, even though it is opt-in and off by default. Every Write or Edit
   in every consumer project goes through the Spec Kit dispatcher to reach a no-op: 223 ms per call (1,383 ms when the
   hook interpreter can import `specify_cli`; 84 ms direct). On Codex the hook can never fire: its matcher `Write|Edit`
   excludes `apply_patch`, and the script reads only `file_path` or `path`.
3. Four Illustrate reads are larger than the work needs. `primitive-icons.md` (81,851 B) is read whole to copy one
   icon, which is more than the 29 KB minimal diagram read. Export reads 10,180 B of `export.md`, 3.9 KB of which is a
   manual SVG and PNG procedure the command forbids. The B0 figure of 61,141 B for import counts three alternative
   references; the real import read is 28 to 32 KB. Packages also ship dead files: 893 KB of unreferenced PNGs and
   gallery variants, plus maintainer-only scripts.
4. Progress per-event cost (bound session, PostToolUse): 193 ms with the default `speckit` wiring, 86 ms with `native`.
   It rises to 1,451 ms with `speckit` when `specify_cli` is importable (129 ms native). Nothing tells the user which
   case a project is in. Every top-level key of the v3 projection is read by `blocks.js`. `model_v3` is layered on
   `model` (v2), not a copy of it. Neither is waste.
5. Test runtime here: the upstream progress-report suite takes 208.5 s for 581 tests, and 93.3 s of that (45 percent) is
   two browser modules. The sanduq Illustrate suite takes 210.4 s for 142 tests, and 26 of its 30 test files that differ
   from upstream differ only in the `ROOT =` line. That is a path-rewritten copy of upstream's suite.

## Findings per lens

### Lens 1: model work a script does or could do

- **Strict check versus shipped examples.** `SKILL.md:61` requires `self_check.py --strict <file>`, and so do
  `references/taste-gate.md:9,81`. Step 5 (`SKILL.md:55`) starts each diagram from "the closest template or example".
  Running `scripts/self_check.py` with and without `--strict` over `skill/assets/**/*.html` gives 296 files, 178
  passing the default run and 51 passing strict, in 60.8 s. That matches U1's note (`docs/internal/round-2-notes.md`,
  U1: "Over the 178 assets that pass the default run, 51 pass --strict"). The strict failure kinds, counted once per
  file: `svg min-width Npx does not equal the viewBox width` 116, non-orthogonal connector 9, rect off the 4px grid 30
  (several shapes), no `min-width` 3. Among templates, `assets/template-full.html` fails strict (off-grid rects at lines
  249, 250, 259 and 260). An agent that copies a typical example therefore starts from a file that fails the gate it is
  told to pass, and then pays a fix-and-rerun round for a defect it did not create. The min-width failure is
  mechanical: one CSS value per file.
- **Technical-color by construction.** All four technical-color templates
  (`assets/technical-color/{architecture,process-flow}/templates/template{,-dark}.html`) fail the default
  `self_check.py` with `executable attribute onclick on <button>` (x4),
  `remote reference on <script>: https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/...` and `.../jspdf@2.5.2/...`, and
  `svg 1 needs role=img`. Yet `references/technical-color-architecture.md:159-167` (and
  `technical-color-process-flow.md:219-227`) order "keep these intact: the two CDN scripts ... `copyAsImage()`,
  `downloadPNG()`...". `SKILL.md:60` exempts technical-color only from `apply`, not from step 7. With
  `illustrate.hooks.self_check: true`, every technical-color write returns exit 2.
- **Process-flow QA prose.** `technical-color-process-flow.md:280-361` (3,306 B) is a manual "Preview & Fix" procedure
  addressed to Claude.ai (`/mnt/user-data/outputs/`, `present_files`, lines 295 to 299). Neither host runs it, and
  `verify-geometry.py` plus `self_check.py` cover the mechanical part.
- **Data-platform layout formulas.** The seven type references above 16 KB (`type-it-state` 30,194, `type-process`
  28,796, `type-high-level` 26,462, `type-dp-integration` 22,455, `type-medallion` 22,436, `type-data-flow` 21,492,
  `type-dp-security-matrix` 19,086) each carry a "Layout formulas: deterministic geometry" section, 42,455 B in total
  (for example `type-high-level.md` §2 is 9,372 B). Pairwise similarity is low (mean ratio 0.18), so this is per-type
  content the model computes by hand, not duplication. A generator from the YAML input contract (§1 of each file) would
  remove it. The effort is L and it is not proposed this round.
- **Verifier code.** There are 22 `verify-*.py`, 642,928 B. AST comparison finds 14,066 B of byte-identical top-level
  functions repeated across files (`is_hand_variant` x15, `attrs_of`, `median`, `Element`, `targets`, `parse_document`
  x4 to x5, among others) and about 29,806 B of near-duplicates (ratio 0.85 or more; `_Scanner` x5 alone is 14,216 B):
  4.6 percent of verifier bytes. The model never reads them, so this costs maintenance only (see "Not proposed").

### Lens 2: repeated text

- **Technical-color architecture versus process-flow.** Three paragraphs of 25 or more words are identical (1,972
  chars): the Export Toolbar block, `architecture.md:157,159-167,169` = `process-flow.md:217,219-227,229`. One more is
  near-identical: the theme default, `architecture.md:18-21` ~ `process-flow.md:34-37` at ratio 0.95. B0 reports this
  as "four" duplicates; its fourth row is the import dials sentence shared by `import-excalidraw.md:35` and
  `import-mermaid.md:34`. Two more pairs match at 0.85: arrows (`87-92` ~ `106-111`) and Documentation Integration
  (`227-243` ~ `262-278`). Over the whole files, 7,830 of the 12,123 bytes of `architecture.md` match text in
  `process-flow.md`. For a single diagram this is maintenance cost, not token cost, because a diagram loads one family
  file.
- **Stale facts.** `type-it-state.md:71` says "Catalog has 41 icons; `mail` is currently missing". The catalog has 82
  icons (`grep -c '^### ' primitive-icons.md`). `mail` is still missing.
- **Tests.** In `extensions/illustrate/tests/`, 37 entries against 41 upstream. 5 files are identical, 30 differ, and
  26 of those 30 differ in exactly two diff lines: `ROOT = ... / "skill"` versus `/ "skills" / "illustrate"`. Upstream's
  `test_arrow_ends.py`, `test_export_animated.py`, `test_export_page_styles.py` and `test_lint_render_clock.py` are
  missing here. Only `test_self_check_hook.py` and `fixtures/` are sanduq-only.
- **Progress docs.** No paragraph of 25 or more words repeats across `docs/*.md`, `README.md`, `SKILL.ext.md` and
  `references/` (0 found). Round 2 removed the repeats.
- **`model_v3.py` versus `model.py`** (50,029 and 38,793 B). 19 and 27 top-level definitions, 0 identical, and only
  `build` shares a name. `model_v3` imports `model` and builds on the v2 document (`model_v3.py:6-7,112`), and
  `model.build_pair` builds v2 always and v3 on request from one read of the producers (`model.py:251-263`). That is
  layering, not duplication. v2 is persisted only for the `classic` layout (`render_data.py:15-21`) and for the Workflow
  bridge's `status --json --schema v2` (`extensions/workflow/scripts/progress_bridge.py:313-333`).

### Lens 3: rereading large inputs

- **Icons.** `primitive-icons.md` is 81,851 B (782 lines, 82 icons), generated by `scripts/build-icons.py:27`. Its usage
  section (`primitive-icons.md:7`) says to find one icon by `### name` and copy its snippet. It is routed from
  `SKILL.md:155`, `type-high-level.md:61,67`, `type-it-state.md:26,71,149`, `type-dp-integration.md:68,72` and
  `import-drawio.md:102,105`. One icon-bearing diagram therefore reads 82 KB on top of the 29 KB minimal path (SKILL
  11,730 + median type reference 6,097 + median minimal example 11,485).
- **Export.** `commands/speckit.illustrate.export.md:15` reads `references/export.md` (10,180 B) before every export.
  Of that, "SVG export procedure" and "PNG export procedure" (`export.md:91-169`, about 3,895 B) describe by hand what
  `export_diagram.py` does, and step 5 of the command forbids recreating it (`speckit.illustrate.export.md:27`). The
  command already carries every flag (`speckit.illustrate.export.md:19-26`). B0 row: 1,506 + 10,180 = 11,686 B (`round-3-before-instructions.md:80`).
- **Import.** B0 measures 2,204 + 58,937 = 61,141 B (`round-3-before-instructions.md:82`). That sums all three
  `import-*.md` (13,896 + 9,990 + 11,337), which are alternatives at step 2, plus `output-spec.md` (15,724) and
  `theme-initialization.md` (7,990), which is read only when the theme is missing. The real read is 2.2 KB + one
  reference (10.0 to 13.9 KB) + `output-spec.md` 15.7 KB = 28 to 32 KB. In `output-spec.md`, §2 Size is 6,054 B (narrow
  screens, type ramp, legacy examples, safe areas). The import references cite §3 to §6 only (`import-drawio.md:70,72,
  116,118,160`; `import-mermaid.md:56,74`; `import-excalidraw.md:63,81`). Flag for R6: the harness counts routing
  alternatives as one read.
- **References are all routed.** A link crawl from `SKILL.md` reaches all 74 references: 22 at depth 1 and 52 at depth
  2 through `type-index.md` (55 links). None is orphaned. What remains is size: `primitive-icons.md` (above) and the
  seven data-platform references (lens 1).

### Lens 4: descriptions and catalog

- Clean. B0 shows 0/4 Illustrate and 0/5 Progress descriptions failing (`round-3-before-instructions.md:118,120`).
  The hook-only command files (`speckit.illustrate.hook.md`, `speckit.progress.hook.md`) are not in
  `provides.commands`. Nothing to propose.

### Lens 5: hook-enforceable rules, and hook cost

- **Illustrate hook, off-path cost.** `extension.yml:34-38` registers `post_tool_use` with matcher `Write|Edit` and
  timeout 60. The script returns 0 unless `.specify/workflow.yml` sets `illustrate.hooks.self_check: true`
  (`hooks/self_check_hook.py:21-32`), but it first imports PyYAML (`:27`) and is reached only through the dispatcher.
  Measured with the policy absent and an Edit of `src/app.py`: 223 ms via `.specify/events.py` and 84 ms direct
  (`import yaml` alone is 66 ms against a 44 ms floor). With the specify_cli Python: 1,383 ms and 124 ms. Over a
  session with 60 Write or Edit calls, that is 13 s (83 s) spent on a hook that does nothing by default.
- **Codex gap.** The matcher `Write|Edit` (`extension.yml:37`) does not match Codex's `apply_patch`. Even if it did,
  `written_diagram` reads only `tool_input.file_path` or `path` (`self_check_hook.py:40`), while `WRITE_TOOLS` lists
  `apply_patch` (`:18`). `README.md:100` advertises the hook "for Claude Code and Codex". `tests/test_self_check_hook.py`
  has no `apply_patch` case.
- **Progress hooks, per event** (bound session; the unbound rows are the fast path):

  | Event | speckit (PATH Python) | native | speckit (specify_cli importable) | native |
  | --- | ---: | ---: | ---: | ---: |
  | post_tool_use, unbound | 167 | 57 | 1,155 | 54 |
  | post_tool_use, bound, debounced | 193 | 86 | 1,451 | 129 |
  | stop, bound (forced refresh) | 228 | 119 | 1,437 | 194 |

  Round 2 measured 686 to 728 ms for the importable case (`round-2-review-progress.md`, cost table). The dispatcher
  template tries `from specify_cli.events import ...` first (installed `specify_cli/events/__init__.py` template lines
  418 to 437), and `-X importtime` gives `specify_cli.events` a cumulative 474,667 µs. Spec Kit resolves the hook
  interpreter through the project venv (`_resolve_interpreter`, events module line 1154), so the slow case applies to
  any project whose venv has specify-cli installed. Round 2 shipped `progress.hook_wiring: native` and
  `post_tool_matcher` (opt-in, `CHANGELOG.md` 1.3.0), but nothing reports which case a project is in:
  `progress_bridge.mode` (`extensions/workflow/scripts/progress_bridge.py:336-354`) records "hooks registered" and
  nothing about cost.
- **What Progress collects.** Every v3 top-level key (`model_v3.py:820-826`: collection, feature, orchestrator,
  attention, stages, workstreams, tasks, runs, dispatch, decisions, timeline, history, sources, summary,
  stale_after_seconds) appears in `assets/ui/blocks.js` (1 to 26 references each). `report.json` (4,013 B) and
  `data.js` (2,828 B) are both written per refresh. `report.json` is read back by `progress.py:700` and `refresh.py:67`.
  Nothing collected goes unread at the top level, so there is nothing to propose.

### Lens 6: Claude Code versus Codex

- The Codex gap in the Illustrate hook (lens 5).
- `technical-color-process-flow.md:280-361` is written for Claude.ai and Chrome (`present_files`, `/mnt/user-data`).
  Neither target host has those tools.
- `docs/hosts.md:7` (Progress, upstream) still says "Verified ... against `specify_cli` 1.1.1.dev0". The installed
  version is 1.1.4.dev0, which round 2 already noted.

### Packages (what every consumer installs)

| Package | Files | Zip | Raw | Largest parts (raw) |
| --- | ---: | ---: | ---: | --- |
| illustrate | 515 | 3,617,127 | 10,700,411 | `skill/assets` 8,698,702; `skill/scripts` 1,151,705; `skill/references` 726,423 |
| progress | 53 | 215,818 | 607,852 | `scripts/sanduq_progress` 280,046; `docs` 132,846; `assets/ui` 73,330 |

- **Illustrate assets: 303 files, 8.70 MB.** 296 HTML (287 examples 8.37 MB, 12 templates 0.29 MB), 5 PNG, 2 YAML.
  64 `-hand` files (3.26 MB) are Rough.js output that needs `jsdom`, `roughjs` and `svg-pathdata` (`skill/package.json`)
  to regenerate, and `variants.md:10` routes them by pattern, so they stay. Nothing references the 5 PNG previews under
  `assets/technical-color/process-flow/examples/images/` (848 KB: no reference, script, test or HTML names `images/`),
  and nothing references `assets/index-variation-1.html` and `-2.html` (45 KB).
- **Maintainer-only scripts in the package.** `scripts/vendor/icons` (85,371 B), `build-icons.py` (26,241),
  `build-exploded-examples.py` (36,090), `build-axonometric-plan-examples.py` (29,530), `generate-hand-variants.cjs`
  (17,511), `fix-mojibake.py` (2,083), `package.json` and `package-lock.json` (about 20.6 KB). No reference, command or
  hook names them for an agent.
- **Progress.** `docs/` (132,846 B: `contracts.md` 60,289, `commands.md` 51,520, `hosts.md` 14,826,
  `token-benchmark.md` 6,211) is human documentation. `references/verbs.md:4` already marks it so.
  `scripts/live_ab.py` (22,294 B) ships but cannot run in a consumer: it imports `bench` from `tests/`
  (`live_ab.py:50`), and `package.py` excludes `tests`.
- Re-packaging with only the folder exclusions (images, `scripts/vendor`, `docs`; `package.py` filters by folder
  prefix) gives illustrate 428 files, zip 2,785,790 (minus 23 percent), raw 9,755,514. Progress gives 49 files, zip
  165,064 (minus 24 percent), raw 474,605. Excluding the single files listed above saves about 177 KB raw more for
  illustrate and 22 KB for progress.

### Test runtime

- **Upstream progress-report** (`upstream:agent-tools/skills/progress-report/tests`): 581 tests, 11 skipped, 208.5 s.
  `test_ui_browser` takes 50.8 s and `test_ui_v3_browser` 42.5 s, together 93.3 s or 45 percent. The slowest single
  test, `UpdateTests.test_a_stalled_data_load_does_not_stop_the_poller`, takes 13.3 s, and five browser tests take 6
  to 13 s each. `test_review_c1.F6PublishOnce.test_100_debounced_events_write_the_projection_once` takes 5.6 s. The
  brief's 355 s was not reproduced; this machine took 208.5 s.
- **Sanduq illustrate** (`extensions/illustrate/tests`): 142 tests, 210.4 s. `test_theme_matrix.test_matrix` takes
  35.6 s, `test_import_extractors` 45.7 s and `test_verify_sankey.test_upstream_polarities` 20.5 s. Upstream runs the
  same suite (208 tests per round-2 U1) against the same bytes, and `vendor.py check` asserts byte identity.

## Defects

| Defect | Effect | Where |
| --- | --- | --- |
| Procedure demands `--strict` on files copied from assets that fail it | 245 of 296 shipped HTML fail strict, 116 of them on `min-width` versus viewBox alone; each copied example starts a fix round | `SKILL.md:55,61`; `taste-gate.md:9,81`; `assets/**` |
| Technical-color templates fail the default self-check by design | 4 of 4 templates: `onclick` x4, two CDN scripts, no `role=img`; step 7 and the opt-in hook reject every technical-color diagram | `assets/technical-color/*/templates/*.html`; `technical-color-architecture.md:159-167`; `SKILL.md:60-61` |
| Opt-in Illustrate hook registered unconditionally | 223 ms per Write or Edit (1,383 ms with specify_cli importable) for a no-op by default | `extension.yml:34-38`; `hooks/self_check_hook.py:21-32` |
| Illustrate hook cannot fire on Codex | Matcher excludes `apply_patch`, and the payload has no `file_path`; README says Codex is covered | `extension.yml:37`; `self_check_hook.py:18,40`; `README.md:100` |
| Icon catalog read whole for one icon | 81,851 B per icon-bearing diagram (high-level, it-state, dp-integration, draw.io import), 2.8 times the minimal diagram read | `references/primitive-icons.md`; `SKILL.md:155`; `type-high-level.md:61` |
| Stale icon count | "41 icons" against 82 | `type-it-state.md:71` |
| Export reads a manual procedure it forbids | 3.9 of 10.2 KB per export run | `commands/speckit.illustrate.export.md:15,27`; `export.md:91-169` |
| Process-flow QA section targets Claude.ai tools | 3.3 KB of instructions neither host can follow | `technical-color-process-flow.md:280-361` |
| Three identical, one near-identical paragraph across the technical-color references | Two places to edit the toolbar contract and its SRI hashes | `technical-color-architecture.md:18-21,157-169`; `technical-color-process-flow.md:34-37,217-229` |
| Unreferenced and maintainer-only files packaged | Illustrate 893 KB of assets plus about 302 KB of scripts; Progress 133 KB docs plus a non-runnable `live_ab.py` | `extensions/scripts/package.py:12-17`; `live_ab.py:50` |
| Sanduq illustrate tests are a path-rewritten upstream copy | 210 s CI per run; 4 upstream tests missing; 26 files drift only by `ROOT` | `extensions/illustrate/tests/*` |
| Slow-path hook cost invisible | A venv with specify-cli makes each Progress event 1.45 s and nothing says so | `progress_bridge.py:336-354`; `extensions/workflow/scripts/install.py:539-603` |
| Browser tests dominate the Progress suite | 93.3 of 208.5 s | `upstream:.../tests/test_ui_browser.py`, `test_ui_v3_browser.py` |

## Options

Cost bases. **Illustrate**: one diagram costs instruction input of 29 KB (minimal path) to 69 KB (link-following:
plus `taste-gate.md` 5,864, `output-spec.md` 15,724, `primitives-core.md` 13,739 and `layout-budget.md` 4,647). With
output (2k to 4k tokens) and script runs (about 2k), that is 11k to 23k tokens per diagram. Export and import runs
are costed against their own reads. For `time`, reading is taken as about a quarter of wall time, as in round 2,
unless an option removes a round trip or a hook launch. **Progress**: hook wall time per session (N tool calls times
the per-event cost above); the model-visible tokens are about 3.3k per feature (`docs/token-benchmark.md`) and no
option here changes them.

### IP1 (upstream): icon lookup by name instead of the 82 KB catalog

- **title**: `scripts/icons.py NAME...` prints the snippets; `primitive-icons.md` becomes a name index
- **what**: Teach `scripts/build-icons.py` to emit, besides `assets/icons.html`, a compact
  `references/primitive-icons.md` (usage paragraph plus one line per icon: name, group, one-line meaning, about 3 KB)
  and a JSON `scripts/icons.json` (`{name: {svg, source}}`). Add `scripts/icons.py` (stdlib, under 60 lines) that prints
  the snippet for each requested name and exits 2 with the nearest names for an unknown one. Update the routing lines
  (`SKILL.md:155`, `type-high-level.md:61,67`, `type-it-state.md:26,71,149`, `type-dp-integration.md:68,72`,
  `import-drawio.md:102,105`) to "pick names from primitive-icons.md, print them with `icons.py`", and fix the stale
  "41 icons" line.
- **effort**: S to M (generator change, one script, eight routing lines, tests; release and sync)
- **tok**: [0.60, 0.75] of an icon-bearing diagram (82 KB to about 3 KB plus the printed snippets of about 0.4 KB
  each: 111 KB to 32 KB read). Over all types this is [0.05, 0.10], because 4 of 52 type references and the draw.io
  import route to icons.
- **time**: [0.15, 0.20] of an icon-bearing diagram; [0.01, 0.02] averaged
- **obs**: unchanged (same icons, same SVG; an unknown name now fails loudly instead of being guessed)
- **policy**: none
- **pros**: The largest per-diagram read left in the skill. The generator already owns the file, so the index cannot
  drift.
- **cons**: One more script to ship and test. `icons.html` stays the visual gallery.
- **files**: upstream `illustration-tools/skills/illustrate/scripts/build-icons.py`, `scripts/icons.py` (new),
  `scripts/icons.json` (new, generated), `references/primitive-icons.md` (regenerated), `SKILL.md`, `type-high-level.md`,
  `type-it-state.md`, `type-dp-integration.md`, `import-drawio.md`, `tests/test_icons.py` (new); sanduq
  `vendor.lock.json`, `extensions/illustrate/skill/**` (sync), `extension.yml` (version), `CHANGELOG.md`.
- **tests**: upstream: `build-icons.py --check` (no network, from `scripts/vendor/icons`) reproduces both outputs;
  `icons.py laptop server` prints two `<svg` blocks; an unknown name exits 2; every name in the index has an entry
  in the JSON. Sanduq: `test_skill_frontmatter.py` link check, `vendor.py check`.
- **upstream**: yes

### IP2 (upstream): make the shipped editorial examples pass `--strict`, and keep them passing

- **title**: Mechanical fix of the 116 `min-width` failures and the off-grid templates, plus a strict baseline gate
- **what**: Add `scripts/fix-min-width.py` (or a `--fix` mode of `self_check.py --strict` limited to the min-width rule)
  that sets the svg `min-width` to the viewBox width in the svg selector or inline style. Run it over `assets/`, then
  regenerate the `-hand` variants with `generate-hand-variants.cjs` so they inherit the fix. Fix
  `assets/template-full.html` (rects at lines 249, 250, 259, 260 onto the 4px grid). Add `strict-baseline.txt` with the
  remaining failures (off-grid example rects, the loop type's ring arcs) and a test that fails on a new strict failure
  and on a stale entry, the pattern of `self-check-baseline.txt` (`tests/test_self_check.py:122-126`). Optionally,
  `variants.md` names the strict-clean example per type first.
- **effort**: M (scripted fix and regeneration are mechanical; reviewing the visual diff of about 120 files is the cost)
- **tok**: [0.05, 0.25] of a diagram started from an example. The fix round avoided is a re-read of the file (about
  11.5 KB, 2.9k tokens) plus edit and rerun (about 0.5k) against 11k to 23k; 127 of 178 default-clean examples fail
  strict today, so most example-based diagrams pay it.
- **time**: [0.05, 0.20] (one avoided fix-and-verify loop; the scripts take under a second each)
- **obs**: improved (strict results on shipped assets become a CI-guarded number instead of an unknown)
- **policy**: none (`--strict` stays what step 7 already asks for)
- **pros**: Removes the contradiction between step 5 and step 7 without weakening any check. The baseline makes the
  51 of 296 visible and shrinking.
- **cons**: Large asset diff (about 120 HTML plus their `-hand` twins) and a release. Hand variants need Node with
  `roughjs` to regenerate (maintainer machine only).
- **files**: upstream `scripts/self_check.py` or `scripts/fix-min-width.py` (new), `assets/*.html`,
  `scripts/strict-baseline.txt` (new), `tests/test_self_check.py`, `references/variants.md`; sanduq sync, version,
  changelog.
- **tests**: upstream strict-baseline test (new failures and stale entries); the CI builder step (`build --check`,
  `verify-geometry --all --baseline`, `lint-skin --all --baseline`) unchanged; default `self_check` over all assets
  byte-identical except the fixed files.
- **upstream**: yes

### IP3 (upstream): technical-color gets a check profile, one shared toolbar section and no Claude.ai QA prose

- **title**: `self_check.py --family technical-color` allows the pinned toolbar; shared text lives once
- **what**: In `self_check.py` add a `technical-color` profile, selected by a marker the templates already carry
  (`id="report-container"` plus `.toolbar`) or by `--family`. It allows exactly the two SRI-pinned CDN scripts and the
  toolbar's `onclick` handlers named in `technical-color-architecture.md:159-167`, and still requires `role=img`, title
  and desc. Fix the four templates' accessible-SVG markup. Move the Export Toolbar block (`architecture.md:155-169`,
  `process-flow.md:215-229`) and the theme-default paragraph into `references/technical-color-common.md` and link it
  from both. Replace `process-flow.md:280-361` (3,306 B) with three lines: run `verify-geometry.py` and `self_check.py`,
  and ask the user to open the file when no browser tool exists. State in `SKILL.md:60-61` that step 7 uses the profile
  for technical-color files.
- **effort**: M
- **tok**: [0.02, 0.06] of a technical-color process-flow diagram (minus 3.3 KB QA prose and about 2 KB shared text
  against 21.7 KB plus template and SKILL); architecture about [0, 0.01]; the bigger effect is the avoided failure
  loop, which the next field covers.
- **time**: [0.05, 0.15] of a technical-color diagram (today `self_check` fails it by construction; an agent that
  follows step 7 either loops or reports a false failure)
- **obs**: improved (technical-color output gets a real pass or fail instead of a guaranteed failure; the opt-in hook
  becomes usable for this family)
- **policy**: none
- **pros**: Closes a contradiction between two parts of the same skill. Removes host-foreign instructions.
- **cons**: An allowlist in a safety check needs care: pin the exact URLs and SRI hashes, not a domain. One more
  reference file.
- **files**: upstream `scripts/self_check.py`, `references/technical-color-architecture.md`,
  `technical-color-process-flow.md`, `technical-color-common.md` (new), `SKILL.md`, the four templates,
  `tests/test_self_check.py`; sanduq sync, version, changelog.
- **tests**: upstream: a template passes the profile; the same template with a third script, an unpinned URL or a
  changed hash fails; an editorial file with the toolbar markup but no family marker fails as today; the link check
  covers the new file.
- **upstream**: yes

### IP4 (sanduq, plus one upstream split): export and import read only what the run needs

- **title**: Export reads `export.md` only on failure; import reads only the dials part of `output-spec.md`
- **what**: In `commands/speckit.illustrate.export.md` replace step 1 ("Read `export.md` before exporting") with "Read
  `export.md` only when the exporter exits non-zero or the user asks for animation details." The command keeps its
  flag list and refusal rules (lines 19 to 33), which are what a normal run needs. Upstream, split
  `references/output-spec.md` (15,724 B) into `output-spec.md` (head, §1 Format, §3 Detail, §4 Audience, §5 Fidelity
  ledger, §6 Checklist; about 9.7 KB) and `size-classes.md` (§2 Size, 6,054 B, linked from §1 and from `layout-budget.md`).
  Keep section numbers so the about 100 "§N" citations resolve. Step 6 of `commands/speckit.illustrate.import.md` then
  reads `output-spec.md` and opens `size-classes.md` only for a non-default size.
- **effort**: S (sanduq one line; upstream text move plus link check)
- **tok**: export run [0.60, 0.75] (11.7 KB to 1.5 KB instructions); import run [0.15, 0.20] (28 to 32 KB to 22 to
  26 KB); a create run that follows the `output-spec` link [0.03, 0.08]
- **time**: [0.10, 0.20] of an export run; [0.03, 0.05] of an import run
- **obs**: unchanged (same script, same report of paths and sizes)
- **policy**: none
- **pros**: The export half is a one-line sanduq change with no release dependency. The split also shortens the create
  path's optional read.
- **cons**: An agent hitting an edge case (gallery file, several SVGs) reads `export.md` after the failure, one extra
  round trip in that case. The upstream split needs a release.
- **files**: sanduq `extensions/illustrate/commands/speckit.illustrate.export.md`, `speckit.illustrate.import.md`,
  `CHANGELOG.md`; upstream `references/output-spec.md`, `references/size-classes.md` (new), `references/layout-budget.md`
  (link).
- **tests**: `benchmark_instructions.py` AFTER (export row 11,686 to about 1,500); upstream link-resolution test;
  `tests/verify-*-import.py` that check dials in `output-spec.md`.
- **upstream**: partly (the `output-spec.md` split; the export command change is sanduq-owned)

### IP5 (sanduq): register the Illustrate post-write hook only when it is turned on; make it reach Codex

- **title**: No dispatcher launch per Write or Edit while `illustrate.hooks.self_check` is false
- **what**: Remove the `events: post_tool_use` entry from `extension.yml`. In `extensions/workflow/scripts/install.py`
  add `wire_illustrate` on the pattern of `wire_progress` (`install.py:539-603`): when the policy key is true it writes
  one PostToolUse entry per host that runs `hooks/self_check_hook.py` directly. That is 84 ms instead of 223 ms on
  the rare hit and nothing on a miss. When the key is false it removes the entry, and the receipt and `install-lock.json`
  record the result. In `self_check_hook.py`, skip the PyYAML import when the policy file text does not contain
  `self_check` (a cheap substring test). For Codex, add `apply_patch` to the Codex matcher and parse the target paths
  from the patch text (`*** Add File: ` and `*** Update File: ` lines) so `.html` writes are seen.
- **effort**: M (installer wiring with rollback and receipt; Codex patch parsing; tests)
- **tok**: [0, 0]
- **time**: hook wall time per Write or Edit [0.95, 1.0] removed while the key is false (223 ms, or 1,383 ms, to 0);
  [0.55, 0.62] when it is true (223 to 84 ms; 1,383 to 124 ms)
- **obs**: unchanged at the default (the hook does nothing today with the key off); improved on Codex when on (the
  check finally runs)
- **policy**: `illustrate.hooks.self_check`, default false, unchanged; turning it on now needs the installer re-run,
  which the README must say
- **pros**: Removes a per-edit cost every Sanduq project pays for a feature it did not enable. The wiring pattern
  already exists and is tested for Progress.
- **cons**: Spec Kit no longer owns the entry (`specify extension remove illustrate` leaves it, so the installer must
  remove it). Codex users approve one more hook when they turn it on. Touches Workflow's installer, which is shared
  with R1 and R6.
- **files**: `extensions/illustrate/extension.yml`, `commands/speckit.illustrate.hook.md` (delete or keep as docs),
  `hooks/self_check_hook.py`, `README.md`, `tests/test_self_check_hook.py`; `extensions/workflow/scripts/install.py`,
  `extensions/workflow/tests/test_install.py`.
- **tests**: installer writes and removes the entry per host on toggling the key, and the receipt shows it; the hook
  returns 0 without importing yaml when the file lacks `self_check`; an `apply_patch` payload that adds an `.html` with
  `<svg` and a failing fixture exits 2 with the first finding.
- **upstream**: no

### IP6 (sanduq): leave dead weight out of the Illustrate package

- **title**: Exclude 893 KB of unreferenced assets and about 302 KB of maintainer-only scripts from `dist/illustrate.zip`
- **what**: Extend `EXCLUDE_PATHS` in `extensions/scripts/package.py` with `skill/assets/technical-color/process-flow/
  examples/images` (5 PNG, 848 KB) and `skill/scripts/vendor` (85 KB). Teach the filter to accept file paths as well as
  folders (today it matches `folder + '/'` only, `package.py:35-36`), then add `skill/assets/index-variation-1.html`,
  `-2.html`, `skill/scripts/build-icons.py`, `build-exploded-examples.py`, `build-axonometric-plan-examples.py`,
  `generate-hand-variants.cjs`, `fix-mojibake.py`, `skill/package.json` and `skill/package-lock.json`. The vendored tree
  in the repository is unchanged, so `vendor.py check` stays a byte match.
- **effort**: S
- **tok**: [0, 0]
- **time**: [0, 0] per diagram. Install and upgrade download minus 23 percent measured on folders alone (zip 3,617,127
  to 2,785,790 B), about minus 25 percent with the files.
- **obs**: unchanged
- **policy**: none
- **pros**: The same mechanism round 2 used for Progress screenshots. Nothing an agent route names is removed (checked
  against `SKILL.md`, every reference, the commands and the hook).
- **cons**: A consumer who wants to rebuild icons or hand variants needs the upstream repository, which they already
  need for `npm install`. A future reference that starts naming one of these files must also leave the exclude list
  (add a test).
- **files**: `extensions/scripts/package.py`, `extensions/scripts/tests/` (package test).
- **tests**: archive test asserts the excluded paths are absent and that every path named in `SKILL.md`,
  `references/*.md`, `commands/*.md` and `hooks/*.py` is present.
- **upstream**: no

### IP7 (upstream plus sanduq): stop running a path-rewritten copy of the upstream Illustrate suite

- **title**: One test suite, run against the vendored tree through an environment root
- **what**: Upstream, read the skill root in `tests/_helpers.py` and the 26 test files from `ILLUSTRATE_SKILL_ROOT`
  when set (default unchanged), so one line per file becomes an import of `_helpers.ROOT`. Sanduq: delete the 26
  ROOT-only copies, keep `test_self_check_hook.py` and the sanduq part of `test_skill_frontmatter.py`, and add one CI
  job (or a `--vendored` switch in the existing runner) that runs the upstream suite at the locked sha against
  `extensions/illustrate/skill` only when `vendor.lock.json` changes. The four upstream tests missing here then run
  as well.
- **effort**: S to M (mechanical in both repositories; the CI job belongs to R6)
- **tok**: [0, 0]
- **time**: CI per sanduq run: 210.4 s to under 10 s on changes that do not touch the vendored tree (the hook and
  frontmatter tests). The full suite still runs on a vendor bump.
- **obs**: unchanged (same assertions; coverage grows by 4 test files)
- **policy**: none
- **pros**: Removes 30 drifting files. A test fixed upstream is fixed here.
- **cons**: Sanduq CI depends on fetching the upstream tests at the locked sha (or vendoring `tests/` as a separate
  input that is not packaged). Overlaps R6's CI stream.
- **files**: upstream `illustration-tools/tests/_helpers.py` and 26 test files; sanduq `extensions/illustrate/tests/*`
  (26 deleted), `vendor.lock.json` (optional tests input), CI workflow (R6).
- **tests**: the upstream suite passes with `ILLUSTRATE_SKILL_ROOT` pointing at `extensions/illustrate/skill`;
  `test_self_check_hook.py` unchanged.
- **upstream**: yes (test helper), plus sanduq deletions

### IP8 (sanduq): leave human docs and the non-runnable A/B tool out of the Progress package

- **title**: Exclude `docs/` (132,846 B) and `scripts/live_ab.py` (22,294 B) from `dist/progress.zip`
- **what**: Add `docs` and the file `scripts/live_ab.py` to `EXCLUDE_PATHS['progress']` (file support from IP6). At
  package time, rewrite the README's relative `docs/...` links (`README.md:40,190,211,226,244,262-263`) to
  `https://github.com/samykabu/sanduq/blob/main/extensions/progress/docs/...`, as round 2 did for the screenshots.
  `references/verbs.md:4` already calls the docs "human references", so no agent route loses anything. `live_ab.py`
  imports `bench` from `tests/` (`live_ab.py:50`), which is never packaged, so it cannot run in a consumer anyway.
- **effort**: S
- **tok**: [0, 0.02] (an agent that still follows `verbs.md:4` to a 60 KB contract file can no longer do so offline)
- **time**: [0, 0]; download minus 24 percent (zip 215,818 to 165,064 B measured with `docs` excluded)
- **obs**: unchanged (`progress status` and the report are untouched; the docs stay in the repository)
- **policy**: none
- **pros**: Same pattern as round 2's screenshot exclusion. Removes a shipped script that fails on import.
- **cons**: Offline readers of an installed copy lose the reference docs (they keep the README). `verbs.md:4` should
  then name the URL (an upstream one-liner, optional).
- **files**: `extensions/scripts/package.py`, `extensions/scripts/tests/` (package test); optional upstream
  `agent-tools/skills/progress-report/references/verbs.md`.
- **tests**: archive has `scripts/progress.py`, `scripts/hook.py` and `README.md` but no `docs/` and no `live_ab.py`;
  every link in the packaged README is absolute or resolves inside the archive.
- **upstream**: no (optional one line)

### IP9 (sanduq): make the slow Progress hook path visible, keep the default

- **title**: Installer and bridge report the hook interpreter's cost class and point at `progress.hook_wiring: native`
- **what**: In `extensions/workflow/scripts/install.py` (`wire_progress`) resolve the interpreter Spec Kit wrote into
  the host hook entry. Run it once with `-c "import specify_cli.events"` (timeout 5 s) and record
  `progress.hosts.<h>.dispatcher: {interpreter, imports_specify_cli: bool}` in `install-lock.json` and the receipt.
  When the wiring is `speckit` and the import succeeds, print one line: "Progress hooks cost about 1.4 s per tool call
  through Spec Kit's dispatcher in this project; set `progress.hook_wiring: native` (about 0.13 s)." `progress_bridge.mode`
  copies the flag into its decision so `workflow status` shows it. Nothing changes wiring by itself.
- **effort**: S
- **tok**: [0, 0]
- **time**: [0, 0] at the default by itself. For a user who acts on the hint in an affected project: [0.85, 0.91] of
  hook wall time (1,451 to 129 ms bound post_tool_use, 1,437 to 194 ms stop). In an unaffected project: [0.48, 0.55]
  if they switch anyway (193 to 86, 228 to 119 ms).
- **obs**: improved (the receipt records a cost that today is invisible)
- **policy**: none new; `progress.hook_wiring` stays default `speckit`
- **pros**: Uses round 2's shipped native path. The probe runs once per install, not per event.
- **cons**: The probe is an approximation (an interpreter on PATH can change after install). One more receipt field
  for the schema tests.
- **files**: `extensions/workflow/scripts/install.py`, `extensions/workflow/scripts/progress_bridge.py`,
  `extensions/workflow/tests/test_progress_shim.py`, `extensions/workflow/tests/test_install.py`,
  `extensions/progress/README.md`.
- **tests**: a fake interpreter that imports a stub `specify_cli.events` yields `imports_specify_cli: true` and the
  hint; a plain one yields false and no hint; `native` wiring prints no hint.
- **upstream**: no

### IP10 (upstream): Progress browser tests out of the default run

- **title**: Gate the two browser modules behind `PROGRESS_UI_TESTS=1` and cut the real-time waits
- **what**: In `test_ui_browser.py` and `test_ui_v3_browser.py`, skip unless `PROGRESS_UI_TESTS=1`, and run them in
  one CI job on changes under `assets/ui/` or `render_data.py`. Lower the poll interval the page reads in tests (the
  stalled-poller test takes 13.3 s, four others 6.3 to 7.6 s) through the test fixture's query string or `data.js`
  `ui` block instead of wall-clock waits. Keep `test_review_c1.F6PublishOnce` (5.6 s) as is.
- **effort**: S
- **tok**: [0, 0]
- **time**: default suite 208.5 s to about 115 s (minus 45 percent); the UI job about 60 s after the timer change
- **obs**: unchanged (the same browser assertions run where the UI changes)
- **policy**: none
- **pros**: Most Progress changes are collector and CLI changes that never touch the page.
- **cons**: A UI regression from a non-UI file (for example a projection field rename) would be caught only by the
  UI job's path filter, so include `model_v3.py` in the filter.
- **files**: upstream `agent-tools/skills/progress-report/tests/test_ui_browser.py`, `test_ui_v3_browser.py`, CI
  workflow; overlaps R6.
- **tests**: the suite count and skips (581, 11 to 581, 11 plus the UI tests when the flag is unset); the UI job green
  with the flag.
- **upstream**: yes

## Not proposed

- **Generator for the data-platform layout formulas** (42,455 B over seven references): the right fix for lens 1,
  but L effort (seven families, YAML contract, tests) and the bytes are read only for those seven types.
- **Shared verifier module** (14 KB identical, about 30 KB near-duplicate of 643 KB): no agent cost, and every
  verifier is pinned by its own test. Revisit when a verifier is next rewritten.
- **Dropping `model.py` (v2) or the classic layout**: v3 is built from v2 (`model.py:251-263`), and Workflow reads
  v2 (`progress_bridge.py:313-333`). Retiring classic saves the classic branch of `blocks.js` and `theme.py` only.
- **Trimming `-hand`, `-dark` or `-full` assets**: routed by pattern (`variants.md:6-10`). The hand variants need
  Node and `roughjs` to regenerate, which a consumer does not have.
- **Progress per-event work beyond wiring**: native bound post_tool_use at 86 ms is 30 to 50 ms over the interpreter
  floor. The remainder is package import and the debounce write, already optimized in 1.0.1.
