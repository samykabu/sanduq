# Round 4 review: Illustrate and Progress (stream R5, read-only)

Worktree `sanduq-round4` (branch `feat/round-4`, fb17f52). Illustrate 2.6.0 vendors illustration-tools 3.6.0. Progress
1.4.0 vendors agent-tools 1.6.0. `vendor.py check` passes ("vendored inputs match vendor.lock.json"). Upstream is
`sanduq-skills` at dd860c6. Paths are relative to `extensions/<id>/` unless they start with `extensions/`, `.github/`,
`docs/` or `upstream:` (= `sanduq-skills/skills/`). Files under `illustrate/skill/**` and Progress's `scripts/`,
`assets/ui/`, `docs/` and `skills/progress/references/` are vendored. A change there is an **upstream** change.

Measured on this machine (Windows 11). The `python -c pass` floor was 90 to 123 ms, about twice round 3's, so compare
ratios with round 3, not absolute times. Hook times are medians of 9 runs (5 for the slow rows) in scratch projects
under the scratchpad. "Dispatcher" means the real `_EVENTS_DISPATCHER_TEMPLATE` from the installed `specify_cli`
1.1.4.dev0, written to `.specify/events.py`. CI times come from the nightly run 39359728801.

## 1. Summary

1. Round 3 closed most of its own list: the hook is registered only when the key is on, assets pass strict, icon
   lookup, export reads its reference only on failure, the suite copy is gone, and docs are out of the package.
   What is left is smaller and mostly at the edges.
2. Four defects were verified. (a) The opt-in Illustrate hook **fails open** when the hook interpreter has no PyYAML.
   With `self_check: true`, a diagram that fails the check passes silently. (b) The import route never runs the
   mechanical checks (step 7) that every new diagram must pass. (c) CI does not run Workflow's tests of Illustrate's
   hook interface when that hook changes. (d) A consumer cannot make a new hand-drawn diagram: the generator converts
   only the shipped examples and needs Node packages that are not shipped.
3. Progress costs per tool call (bound session, native vs the default dispatcher): 187 to 222 ms vs 535 to 545 ms. It
   rises to 2.4 s when the hook interpreter can import `specify_cli`. Native wiring is still opt-in. Nothing detects
   doubled wiring (native plus a dispatcher entry that Spec Kit re-renders), which would run each event twice.
4. After D5, Workflow no longer reads Progress's v2 document: `progress_bridge.status` is called only from
   `progress_shim.py`. The classic layout, which 1.2.0 kept "for one release", is three releases old. The contract
   that remains is small: the CLI path, the hidden `--root`, `runs --json` (`progress.runs.v1`), `hooks
   install|uninstall|status`, hook markers, and seven verbs that `reporting.md` tells the model to run. After the shim
   tests go, no test covers those verbs.
5. CI spends about 1.8 min (Ubuntu) and 3.3 min (Windows) installing Playwright for a 3 to 4 second Illustrate suite
   that does not use it. Every night it also reruns upstream's identical verifier and render-lint block on both OSs
   (about 17.5 runner minutes), on bytes that `vendor.py check` proves have not changed.

## 2. Correctness defects (verified)

### D1. The Illustrate hook fails open without PyYAML

`hooks/self_check_hook.py` `enabled()` imports `yaml` and returns False on any exception (`:44-50`). The launcher runs
bare `python` (Windows) or `python3` (`command_for`, `:146`), which is not the project venv. All three checks it runs
are standard-library only (`self_check.py:36-43`, `verify-geometry.py:50-55`, `illustration_theme.py:6-13`). PyYAML is
needed only to read one key.

Reproduction: a scratch project with `illustrate: {hooks: {self_check: true}}`, the hook and scripts copied in, and a
Write payload for `docs/d.html`. The PATH Python 3.13 (has PyYAML) exits 2 and prints the first finding. The uv Python
3.11 (no PyYAML) exits 0 and prints nothing. Same payload, same project. A user who turned the gate on gets no gate and
no message. Fix: IP11.

### D2. The import route skips the mechanical checks

`SKILL.md:62-64` (step 7) requires `verify-geometry.py` and `self_check.py --strict` (or `--profile
technical-color`) on every new diagram. `commands/speckit.illustrate.import.md` does not read SKILL.md, and its step 7
runs only `illustration_theme.py apply` and `validate`. The three import references ask for the taste gate and the
`output-spec.md` §6 checklist (`import-drawio.md:116`, `import-excalidraw.md:81`, `import-mermaid.md`). None of them
names `verify-geometry` or `self_check` (grep: 0 hits). An imported diagram is new HTML that never meets the gate.
Fix: IP12.

### D3. CI misses Workflow's tests of Illustrate's hook interface

`extensions/workflow/tests/test_install_hooks.py:21` copies `extensions/illustrate/hooks/self_check_hook.py` into its
fixtures and runs it through `install.wire_illustrate` (14 tests, 25.9 s, all pass). `ci_matrix.py:43` `DEPENDENTS`
has no `illustrate` entry. `ci_matrix.py --event pull_request --files extensions/illustrate/hooks/self_check_hook.py`
selects only `illustrate` (2 jobs, `install_smoke=false`). A change to the management CLI's JSON or exit codes can
therefore merge green and break every managed install. Fix: IP13.

### D4. Hand-drawn output cannot be made in a consumer

`references/variants.md:10` offers "Hand-drawn" as a variant, and `primitive-sketchy.md:9-17` says the files are
generated by `npm install; npm run generate:hand` after `cd skills/illustration-tools/skills/illustrate`, an
upstream-only path. `scripts/generate-hand-variants.cjs:582-586` converts only the fixed `TYPES` examples and the
template. It takes no input file. Its dependencies (`jsdom`, `roughjs`, `svg-pathdata`, `skill/package.json`) are not
installed, and `node_modules` is excluded from the package (`package.py:13`). An agent asked for a new hand-drawn
diagram can copy `template-hand.html`, but it cannot rough-render new content. The 63 example `-hand` files are 1.08 MB
of the 2.79 MB zip (39 percent). Fix: IP18.

### Smaller leftovers (no separate defect)

- `references/technical-color-process-flow.md:268-349` still holds the 3,331-byte "Preview & Fix" procedure for
  Claude.ai (`/mnt/user-data/outputs/`, `present_files`). Round 3's U-IL notes record it as "Not done" (IP17).
- `commands/speckit.illustrate.generate.md` "Output" routes export through "`references/export.md`" (10,463 B). That
  contradicts IP4 and SKILL §12, which read it only on failure (IP16).
- `progress refresh --final` is taught by `skills/progress/SKILL.ext.md` and Workflow's `reporting.md`, but `--help`
  says "accepted for compatibility; every refresh is a full one" (IP23).
- `docs/hosts.md:7` (upstream, not packaged) still says it was verified against `specify_cli` 1.1.1.dev0, as round 3
  noted.

## 3. Runtime cost

### Illustrate hook (only installed when `illustrate.hooks.self_check: true`)

| Case | ms |
| --- | ---: |
| `python -c pass` | 123 |
| key off (entry left behind), Edit `src/app.py` | 257 |
| key on, Edit `src/app.py` | 288 |
| key on, Write a diagram `.html` (3 check processes) | 1,061 to 1,411 |

With the key off the installer removes the entry, so the default cost is 0 (round 3 fixed that). With the key on, a
non-HTML edit pays about 165 ms over the floor. About 30 to 50 ms of that is `import yaml`, and most of the rest is
`runpy`, `json`, `re` and `subprocess` loaded before the payload is looked at (`import json,re,subprocess`: 162 ms vs
90 ms floor). Every one of the 292 diagram assets passes the hook's two file checks. The only failures are the 4
gallery pages (2 m 55 s scan).

### Progress hooks, per event (ms)

| Event | native `hook.py` | dispatcher (PATH Python) | dispatcher, `specify_cli` importable |
| --- | ---: | ---: | ---: |
| Claude post_tool_use, unbound | 96 | 357 | 2,377 |
| Claude post_tool_use, bound (debounced) | 222 | 545 | 2,356 |
| Claude stop, bound (refresh) | 269 | 508 | 2,461 |
| Codex post_tool_use, unbound | 86 | 312 | 2,005 |
| Codex post_tool_use, bound (debounced) | 187 | 535 | 2,460 |
| Codex stop, bound (refresh) | 309 | 543 | 2,812 |

Floors: 92 ms (PATH Python) and 148 ms (specify-cli tool Python). The unbound native path is at the floor
(`quick_unbound` uses string tests only). The debounced bound path imports 12 `sanduq_progress` modules, about 77 ms of
module self time, with no `model` or `theme`. There is nothing left to cut on that path. The dispatcher roughly
doubles every event. `post_tool_use` has no matcher by default, so this is paid on every tool call.

### Collection (CLI, ms)

`refresh` 470, `status` 260, `status --json` 269, `--schema v2` 279, `export --format md` 271, `runs --json` 238. A
cProfile of `refresh` (281 ms in-process) shows imports and file opens dominate. `model.build_pair` takes 21 ms.
`refresh.layout()` imports `theme` only to read the layout name: 41 ms, 15 percent of the refresh (IP22).

### CI (nightly 39359728801)

| Job | Playwright cache plus install | Suite | Builders and verifiers | Render lint |
| --- | ---: | ---: | ---: | ---: |
| illustrate, Ubuntu | 1 m 46 s | 4 s | 21 s | 10 m 39 s |
| illustrate, Windows | 3 m 18 s | 3 s | 15 s | 6 m 46 s |
| progress, Ubuntu / Windows | - | 20 s / 14 s | - | - |

Local runs: Illustrate suite 11 tests in 12.1 s. Progress suite 14 tests in 0.1 s, 7 skipped without `tiktoken`
(CI installs it). Upstream `sanduq-skills/.github/workflows/ci.yml:70-108` runs the same verifier and `lint-render`
block on Ubuntu and Windows on every push and PR. It has no schedule.

## 4. Architecture and refactoring

### Illustrate verifiers (upstream)

The scripts folder has 38 `.py` files (1,054,907 B). The 25 checkers (`verify-*`, `lint-*`, `self_check`) total
767,276 B. By AST over top-level definitions:

- Byte-identical copies: 12,632 B. `is_hand_variant` x15 (a one-line test), `parse_document` x5, `line_of` x4,
  `median` x4 of 5, `attrs_of` x4 of 7, `Element` x3 of 6, `theme_palettes` and `_hex_to_rgb` (heatmap, waterfall),
  and three extractor helpers (`_configure_stdout_utf8`, `_escape_markdown`, `_escape_table`).
- Near copies: 23,688 B. `_Scanner` x5 (17,690 B, ratio 0.86 to 0.94). The copies differ only in which tags they
  collect (bubble circles, slopegraph lines, ridgeline paths and lines, marimekko rects).
- Not duplication: `transform_carrier` x8 (ratio 0.10 to 0.67), `transformed_spans` x3 (0.39 to 0.46) and `number`
  x8 (0.09 to 0.39). Each verifier applies its own transform contract. Merging those would change behaviour.

The repository already has the pattern for this: `theme_tokens.py` and `axonometry.py` are shared helpers that the
hyphen-named scripts load with `importlib`. A `svg_scan.py` with `Scanner(tags=...)`, `Element`, `attrs_of`,
`parse_document`, `line_of`, `median`, `printed_number` and `is_hand_variant` belongs upstream. The transform checks
stay local. Cost: maintenance only. No agent reads these files, and the package saving is about 30 KB raw (IP19).

### Progress module structure

`sanduq_progress` has 28 files (280 KB): the hook, snapshot, refresh, model (v2) and model_v3, theme, render, plus the
`collect/` and `hosts/` packages. The layering is sound: the hot path stays light, and `model` is imported only on
refresh (`refresh.py:23`). Two structural leftovers: v2 and the classic layout (IP22), and `refresh.layout()`, which
loads all of `theme` for one key.

### The Progress contract that Workflow relies on once the forwarder is gone (D5)

| Surface | Where Workflow uses it | Covered after D5 by |
| --- | --- | --- |
| `.specify/extensions/progress/scripts/progress.py` plus hidden `--root` (`progress.py:50`, `docs/commands.md:31`) | `progress_bridge.run` | test_progress_runs (runs) |
| `runs --json [--runs-dir] [--now] [--stall-seconds]`, schema `progress.runs.v1` | `execution_tools.py:504-511` | test_progress_runs |
| `hooks install\|uninstall --host`, `hooks --help` probe, `--post-tool-matcher` | `install.py:630-663` | test_install_hooks, test_progress_integration |
| Hook markers `speckit.progress.hook`, `progress/scripts/hook.py`, `--managed-by=progress-report` | `progress_bridge.HOOK_MARKERS` | the bridge tests in test_progress_shim.py (keep them) |
| `.registry` `enabled` | `progress_bridge.extension_enabled` | same |
| Verbs the model runs: `init`, `lane L1 --tasks --owner --harness --model --effort --workstream`, `block --by`, `unblock`, `note --target`, `refresh`, `bind --host --model --effort` | `skills/workflow/references/reporting.md` | **nothing** once ShimMappings goes (IP23) |
| `status --json --schema v2`, `progress_version` | only `progress_shim.py:68,101,109` | not needed after D5 |

All seven verbs exit 0 against the real CLI in a scratch project (checked by hand). `test_progress_shim.py` mixes the
shim tests (ShimMappings, ProcessCounts, CompatibilityErrors, WorkstreamMarker) with bridge tests (ReportingModes,
ProgressWiring, AbsentProgress). D5 must keep the bridge half. That is R1's file, but the coverage is Progress's
contract.

## 5. Options

Numbering continues from round 3 (IP1 to IP10). "tok" bases: one Illustrate diagram reads 29 to 69 KB of instructions
(round 3). Progress model-visible tokens are about 3.3k per feature and no option changes them.

### IP11 (sanduq): the hook reads its key without PyYAML and looks at the payload first

- **What**: in `enabled()`, when `import yaml` fails, read the key with a small stdlib fallback:
  `illustrate:` then `hooks:` then `self_check: true` by indentation. Mark it `shortcut:` (flow mappings and anchors
  are not handled, so the fallback errs to off). In `main()`, run `written_paths` and the `.html` filter before the
  policy read, and import `subprocess` inside `first_failure`.
- **Evidence**: D1. The import timings in §3.
- **Saving**: correctness. Estimated 100 to 130 ms of the 288 ms per non-HTML Write or Edit when the key is on (base:
  key-on projects only).
- **Effort / risk**: S / low (the fallback errs to off, as today).
- **Consumer impact**: none. The next Illustrate release replaces the file, and the installed command is unchanged.
- **Tests**: `test_self_check_hook.py` with `sys.modules['yaml'] = None` still exits 2 on a failing diagram. A `.py`
  Edit returns 0 without loading `yaml` or `subprocess`.
- **Repo**: sanduq (`extensions/illustrate/hooks/`).
- **Verdict**: **fix-first**. A gate the user turned on is silently off.

### IP12 (sanduq plus upstream): imports run the step 7 checks

- **What**: `commands/speckit.illustrate.import.md` step 7 adds "`verify-geometry.py <out>` and `self_check.py --strict
  <out>` (technical-color: `--profile technical-color`); fix and rerun". Upstream adds the same line to the three
  `import-*.md` "3. Run ..." steps.
- **Evidence**: D2.
- **Saving**: about 1 s of script time per import. It avoids an imported diagram that fails the gate.
- **Effort / risk**: S / low.
- **Consumer impact**: none.
- **Tests**: `benchmark_instructions.py` import row (+0.2 KB). `test_skill_frontmatter` link check upstream.
- **Repo**: sanduq (command), upstream (references).
- **Verdict**: **fix-first**.

### IP13 (sanduq CI): an Illustrate hook change runs Workflow's hook tests

- **What**: map `extensions/illustrate/hooks/` to the Workflow module `test_install_hooks`. Use a module list (the shard
  mechanism already passes `modules`), not the whole Workflow suite.
- **Evidence**: D3.
- **Saving**: about 26 s more per hook change, on both OSs.
- **Effort / risk**: S / low.
- **Consumer impact**: none.
- **Tests**: a new `test_ci_matrix.py` case for that path.
- **Repo**: sanduq (`.github/scripts/ci_matrix.py`, R6's file).
- **Verdict**: **fix-first** (small).

### IP14 (sanduq CI): install Playwright only for the vendored steps

- **What**: add `&& needs.changes.outputs.illustrate_vendored == 'true'` to "Cache the Playwright browser" and "Install
  Playwright" (`ci.yml:218-229`). The two remaining Illustrate tests import no browser (grep).
- **Evidence**: §3 CI. Round 3 kept Playwright on every Illustrate change when the suite still had render tests. Those
  tests were deleted (IP7).
- **Saving**: about 1.8 min (Ubuntu) plus 3.3 min (Windows) per Illustrate change that is not a vendor bump.
- **Effort / risk**: S / low. A future sanduq test that needs a browser fails loudly at import.
- **Repo**: sanduq (R6).
- **Verdict**: **do**.

### IP15 (sanduq CI): no nightly rerun of upstream's identical verifier block

- **What**: run "Illustrate builders and verifiers" and "rendered-layout lint" only when `vendor.lock.json` or
  `extensions/illustrate/skill/**` changes, on Ubuntu only, plus once a week. `vendor.py check` already proves byte
  identity in lint, and upstream runs the same commands on both OSs at the locked sha.
- **Evidence**: §3 CI. `ILLUSTRATE_VENDORED` includes schedule and dispatch (`ci_matrix.py:134`).
- **Saving**: about 17.5 runner minutes per night. About 7 min of Windows time per vendor-bump PR.
- **Effort / risk**: S / low. Runner-image drift is caught weekly, not nightly.
- **Repo**: sanduq (R6).
- **Verdict**: **do**.

### IP16 (sanduq): command text reads references only when needed

- **What**: `generate.md` "Output" says export per SKILL §12 (drop the `export.md` pointer). `theme.md` step 1 reads
  `theme-initialization.md` only for `create` or a design source; `init`, `set`, `list` and `validate` use the script
  and its `--help`. `import.md` step 3 uses the full `.specify/...` path like its other steps.
- **Evidence**: §2 leftovers. `theme-initialization.md` is 7,990 B; its create and design-source sections are lines
  88-162.
- **Saving**: a generate-and-export run, about 10.5 KB (2.6k tokens) when the agent follows the link. A theme run,
  about 5 KB of 9 KB.
- **Effort / risk**: S / low.
- **Tests**: benchmark AFTER rows.
- **Repo**: sanduq.
- **Verdict**: **do**.

### IP17 (upstream): drop the Claude.ai QA prose from technical-color process flow

- **What**: replace `technical-color-process-flow.md:268-349` with three lines: run step 7 (`verify-geometry`,
  `self_check --profile technical-color`), `lint-render.py <file>` when Playwright is present, else ask the user to
  open the file.
- **Evidence**: §2 leftovers (round 3 IP3, part not done).
- **Saving**: 3,331 of 19,898 B (17 percent) of that reference, per technical-color process-flow diagram.
- **Effort / risk**: S / low.
- **Repo**: upstream illustration-tools, then sync and an Illustrate bump.
- **Verdict**: **do**.

### IP18 (upstream): make hand-drawn reachable, or say plainly that it is not

- **What (a)**: `generate-hand-variants.cjs [--in X.html --out Y.html]` converts one file (the default stays all
  examples). `primitive-sketchy.md` gives the installed path, `npm ci` in `.specify/extensions/illustrate/skill/`, and
  the Node requirement. `variants.md` says: without Node, deliver the minimal variant and say so.
- **What (b)**, only if (a) is rejected: document hand-drawn as gallery-only and leave the 63 example `-hand` files
  out of the package (keep `template-hand.html`).
- **Evidence**: D4.
- **Saving**: (a) correctness, a promised variant that works. (b) zip about minus 1.0 MB (minus 37 percent).
- **Effort / risk**: (a) S to M, low (the default behaviour is unchanged). (b) S, but a variant disappears.
- **Consumer impact**: (a) none. (b) agents lose copyable hand examples.
- **Tests**: upstream, `--in/--out` reproduces a committed `-hand` file byte for byte from its source.
- **Repo**: upstream (plus `package.py` for b).
- **Verdict**: **do (a)**. (b) defer.

### IP19 (upstream): one SVG scan module for the verifiers

- **What**: `scripts/svg_scan.py` as in §4. Each verifier loads it the way the others load `theme_tokens.py`.
- **Evidence**: §4. 12.6 KB identical plus 23.7 KB near-identical in 767 KB of checkers.
- **Saving**: maintenance. Package about 30 KB raw (about 1 percent of the zip). No tokens.
- **Effort / risk**: M / low to medium. Every verifier's upstream test must stay green, and the transform checks are
  untouched.
- **Repo**: upstream.
- **Verdict**: **defer**. Do it the next time those verifiers change. No consumer cost today.

### IP20 (sanduq, Workflow side): doctor reports doubled Progress wiring

- **What**: when `install-lock.json` says `progress.hook_wiring: native`, doctor and `status` warn
  `PROGRESS_HOOKS_DOUBLE_WIRED` if a host file also holds a `speckit.progress.hook` dispatcher entry. The fix it names
  is `install.py --apply`.
- **Evidence**: README `:128-133` says any later `specify extension` command re-renders the dispatcher entries.
  Spec Kit's refresh runs on add, remove, enable, disable and update (round-3-notes S-INST). Doctor has no Progress
  hook check (grep in `workflow.py`). Each event then runs twice: about 222 + 545 ms instead of 222 ms (by code, not run).
- **Effort / risk**: S / low.
- **Repo**: sanduq (`extensions/workflow/scripts/workflow.py`, R1's file).
- **Verdict**: **do**. It is also the precondition for IP21.

### IP21 (sanduq, Workflow side): native wiring by default for new Progress installs

- **What**: `install.py --with progress` on a project with no Progress wiring yet writes `hook_wiring: native`.
  Existing projects keep their choice and the IP9 hint.
- **Evidence**: §3. 323 to 348 ms saved per bound event (60 percent), and about 2.1 s when `specify_cli` is
  importable.
- **Saving**: about 65 s of hook time per 200-tool-call session here (round 3's machine: about 21 s).
- **Effort / risk**: S / medium (Spec Kit no longer owns the entries; doubled wiring after a `specify extension`
  command until IP20 warns).
- **Consumer impact**: new installs only. Codex approves the hooks once, as it does today.
- **Repo**: sanduq (R1).
- **Verdict**: **defer** until IP20 ships and one Claude Code run with native wiring is recorded.

### IP22 (upstream agent-tools plus sanduq): retire the v2 schema and the classic layout after D5

- **What**: Progress 1.5 warns on `--schema v2` and `--layout classic`. 1.6 removes them, the v2 `display` document,
  and the classic half of `blocks.js` (lines 1-366, 19,592 B). `refresh` stops importing `theme` for the layout.
  `model.py` stays, because v3 is built on it (`model_v3.py:6-7`). Update `docs/contracts.md:393` and
  `commands.md:244`, which name "the Workflow shim".
- **Evidence**: §4 contract table. CHANGELOG 1.2.0 ("classic ... for one release").
- **Saving**: about 40 ms per refresh (15 percent). About 20 KB of UI copied into every feature's `.view/`. Less code
  to keep.
- **Effort / risk**: M / low. Only an outside reader of v2 breaks, after one warning release.
- **Consumer impact**: a project with `layout: classic` falls back to timeline with one notice.
- **Tests**: upstream test_theme and test_projection v2 cases become deprecation and removal cases. The browser module
  for classic goes.
- **Repo**: upstream (code and docs), sanduq (sync and CHANGELOG).
- **Verdict**: **do**: deprecate in this round, remove in the next.

### IP23 (sanduq): a contract test for the verbs Workflow tells the model to run

- **What**: a Workflow test that reads the `progress ...` commands out of `reporting.md`, swaps `<placeholders>` for
  fixture values, and runs each against the real `extensions/progress/scripts/progress.py --root <tmp>` in an
  initialised fixture (exit 0, one line). Also teach `progress refresh` instead of `refresh --final` in `reporting.md`
  and `SKILL.ext.md`.
- **Evidence**: §4. The coverage leaves with ShimMappings in D5.
- **Saving**: a renamed flag in Progress fails CI instead of a live run. `DEPENDENTS progress -> workflow` already
  runs it on Progress changes.
- **Effort / risk**: S / low.
- **Repo**: sanduq (Workflow tests, R1, with D5). The `SKILL.ext.md` line is sanduq; `verbs.md` is upstream.
- **Verdict**: **do**, in the same change as D5.

### IP24 (upstream plus sanduq): Progress bench tests from one source

- **What**: `tests/bench/approaches.py` (13.7 KB) is upstream's file with three lines changed (CLI path, skill path,
  skill name). `bench/report.py` and `test_generated_report_is_current` are missing here. Upstream would read them
  from an env root (the IP7 pattern), and sanduq would vendor `tests/bench` as an unpackaged input.
- **Evidence**: `diff` of both trees (32 KB copy).
- **Saving**: maintenance only.
- **Effort / risk**: S / low.
- **Repo**: both.
- **Verdict**: **defer** (low value).

## 6. Not proposed

- **Running the three hook checks in-process** (saves 2 interpreter starts, about 200 ms per HTML write when on). The
  checks are separate scripts by design, and the hook is opt-in.
- **`--strict` in the hook.** It would block existing user diagrams on edit. Step 7 already asks for strict.
- **Trimming the debounced Progress path.** It is already 77 ms of module self time.
- **The browser-test poll-interval cut (IP10 leftover, upstream).** It saves about 13 s of one opt-in job.
- **Dropping `model.py`.** v3 layers on it.
- **The seven data-platform layout-formula references (42 KB).** Round 3's reasoning holds: L effort, per-type
  content.

## 7. Not verified

- That Codex reads project `.codex/hooks.json` and runs hooks from the repository root. Upstream `docs/hosts.md:25,28`
  marks both unverified. Illustrate's launcher depends on the same thing (`os.getcwd()`): a Codex session started in a
  subdirectory makes the hook silently inert.
- Doubled native and dispatcher wiring (IP20) is shown by code and docs, not by a run.
- Hook and CLI times are from one noisy machine. Ratios are more reliable than absolute values.
