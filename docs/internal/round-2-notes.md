# Optimization round 2: stream notes

Append under your heading only, with one shell append. Contract: `round-2-implementation.md`.

## U1 illustration-tools entry and scripts

## U1c illustration-tools type references

## U2 dev-tools and agent-tools

## S1 Assure

## S2 User Manual

## S3 PR

## S4 Project

## S5 Illustrate

## S6 Memory

## S7 Progress

## Orchestrator

### U1c (IL7) split of the oversize type references, 2026-10-19

Sizes before -> after (bytes): type-line.md 43,288 -> 2,803; type-scatter.md 20,266 -> 2,877; type-bar.md 13,736 -> 3,113; type-treemap.md 18,501 -> 9,608.
New files: type-slopegraph.md 15,496; type-ridgeline.md 10,281; type-streamgraph.md 9,467; type-bump.md 6,749; type-bubble.md 8,925; type-beeswarm.md 9,011; type-dumbbell.md 11,037; type-marimekko.md 9,455. Total of the twelve files 98,822 (was 95,791; the delta is the header note per variant and the split Examples/run paragraphs).

Index lines for U1 (type-index.md):
- slopegraph: change between exactly two states across several series -> references/type-slopegraph.md
- ridgeline: one distribution per series, stacked, shapes compared -> references/type-ridgeline.md
- streamgraph: a total and its composition across many periods -> references/type-streamgraph.md
- bump chart: rank movement across 3 to 6 ordered snapshots -> references/type-bump.md
- bubble: three quantities per item, area as the third -> references/type-bubble.md
- beeswarm: one value axis, one dot per item, full distribution -> references/type-beeswarm.md
- dumbbell: two values per category where the gap is the message -> references/type-dumbbell.md
- marimekko: two-way part-of-whole, column width times segment height -> references/type-marimekko.md

Moved sections (each new file = its old `### Variant` block with `####` demoted to `##`, a one-line parent note after the title, and its own `## Examples` rows):
- type-line.md lines 47-143 -> type-slopegraph.md; 144-206 -> type-ridgeline.md; 207-277 -> type-streamgraph.md; 278-319 -> type-bump.md; example rows 325-336 split per variant. Parent keeps lines 1-39, the four Variants bullets as pointers, and its three example rows.
- type-scatter.md lines 35-113 -> type-bubble.md; 114-186 -> type-beeswarm.md; example rows 192-197 split. Parent gains a `## Variants` section with two pointers; its two anti-pattern cross-references now name the files.
- type-bar.md lines 45-100 (Dumbbell layout, element pattern, honesty rules, dark theme, verifier paragraph) -> type-dumbbell.md, whose Best-for line is the old Variants bullet. Parent keeps grouped and stacked bullets and a dumbbell pointer; no dumbbell example existed, so none moved.
- type-treemap.md lines 66-120 -> type-marimekko.md with its four example rows and its half of the run paragraph; parent keeps the verify-treemap half.
- Wording that said "above", "below" or "the parent" across a file boundary now names the file (32 fragments, each asserted unique by the split script; a completeness check asserts every original non-empty line survives in the twelve files).
- Links outside my files: references/type-waterfall.md lines 9 and 59 (`type-bar.md` -> `type-dumbbell.md` for the dumbbell and its honesty rules). assets/ and examples/ link to none of the moved sections.
- Verifier lines that name the references: scripts/verify-dumbbell.py lines 4, 33, 47 (`REFERENCE` default; the checker reads tokens from the reference and would fail closed on the pointer alone), 266; verify-marimekko.py:82; verify-streamgraph.py:81. `python scripts/verify-dumbbell.py` exit 0; `tests/test_verify_dumbbell.py`, `test_verify_marimekko.py`, `test_verify_streamgraph.py` 15 passed; `git diff --check` exit 0.
- Not done: the SKILL.md type table rows (U1) still describe the variants under the parent files; the sanduq vendored copy follows through vendor.py.

### S2 User Manual (AS4, UM1, UM2 command lines, UM3, UM4, IL3 consumer), 2026-10-19

- AS4: `sanduq_freshness.record_or_status` returns `changed_inputs` and `changed_outputs` (sorted repo-relative paths: changed, new or deleted) only when `current` is false and saved state exists (`missing` and `legacy-state-regenerate` carry no lists); `manual_state.py --summary` appends `changed_inputs=N changed_outputs=M`. `current`, `reason` and exit codes unchanged. The review's "current: true carries empty lists" was dropped for the contract's "when current is false". assure_state.py (S1) gets the keys for free; its `--summary` suffix is S1's. Tests: `test_manual_state.py` ManualStateChangedPathsTests; workflow `test_freshness`, `test_assure_state`, `test_eol_fingerprints` unchanged and green.
- UM3: new `extensions/user-manual/scripts/manual_impact.py` (+ `tests/test_manual_impact.py`), gated by `lifecycle.impact_scope: all | evidence` (default all, written by `init_manual.py`). Writes `impact` into `User-Manual/.state/coverage.json`. Packaging: it sits in `scripts/` beside manual_state.py; check that package.py ships it (no manifest change made here).
- UM2: `update.md` step 8 and `release.md` step 5 call `build_manual.py --all` once. The vendored build_manual.py (dev-tools-v1.1.2) has no `--all` yet; the lines only work after the dev-tools 1.2.0 vendor sync (U2). Do not release user-manual before that sync.
- UM4: four descriptions identical in frontmatter and extension.yml (catalog form, 235-255 chars); five `skills/*/agents/openai.yaml` deleted; ADAPTER.md row removed. check_docs.py fails only on memory and progress descriptions (S6, S7), none for user-manual.
- UM1 sizes (LF bytes, HEAD -> now): analyze 2,723 -> 2,704, init 2,875 -> 2,551, release 1,292 -> 1,690, update 3,487 -> 4,025. Total 10,377 -> 10,970: the Illustrate and init trims are offset by the catalog descriptions, the AS4/UM3 rerun steps and the explicit build lines.

### S3 PR (PR1 to PR6, IL3 consumer), 2026-10-19

- PR3: `speckit.pr.generate.md` 18,060 -> 11,183 B. Type list, managed preflight paragraph and pr-lint block gone; step 0 is the command plus the exit rule; 4a/4b renumbered 5a/5b; "When Workflow is absent ..." kept in step 6. Step 6 still names `execution_tools.py pr-lint` and "never publishes after a nonzero exit" as a description of the script, which keeps `test_execution_tools.PrLintTests.test_pr_generate_procedure_lints_before_any_github_write` green unchanged.
- PR4: `extensions/pr/references/pr-diagram-recipe.md` (1,694 B) with the IL3 consumer wording, theme resolve, output path, one `export_diagram.py` line, budget sentence. It reads `.specify/extensions/illustrate/skill/references/type-index.md`, which arrives with the U1 vendor drop; `tests/test_pr_diagram_recipe.py` skips only that path until it is vendored (see the shortcut comment there).
- PR1: `scripts/pr_publish.py`; prints `pr_url`, `pr_body_file`, `pr_lint_file`, `pr_body_sha256`, `evidence` (the fields `workflow.py pr_lint_binding` and the `stage == 'pr'` check verify: PR_LINT_EVIDENCE_REQUIRED, PR_LINT_RECEIPT_MISMATCH, PR_SENT_BODY_SHA_MISMATCH, PR_EVIDENCE_INCOMPLETE). Body `specs/<f>/evidence/pr-body.md`, lint `pr-body.lint.json`. `stage-pr.md` points to it.
- PR2: `scripts/pr_changelog.py`; facts between `<!-- speckit-changelog:facts:start/end -->`, rerun regenerates only the block.
- PR5: one description string per command in frontmatter, `extension.yml` and the `after_implement` hook. `image_verification: api|browser` is a receipt field: `_check_receipt` only refuses `RUNTIME_RECEIPT_FIELDS` and `canonical_receipt` keeps extra keys, so no workflow.py change is needed.
- PR6: guard denies `gh pr create|edit --body-file|-F <f>` without a matching `<f stem>.lint.json` in managed projects, and `gh pr create` whose head (`--head`/`-H`, else the current branch) equals `origin/HEAD`; unresolved branch allows. Codex users re-approve the changed guard hash in `/hooks`. Rules listed in a new "Guard hook" section of `extensions/workflow/README.md`.
- Packaging: none needed; `package.py include()` already ships `pr/scripts/*.py` and `pr/references/*.md` (checked by building `pr.zip`). CHANGELOG lines for pr and workflow are the orchestrator's.
- check_docs.py exit 1 only for memory and progress description equality (S6/S7 files); no pr finding.

## S1 Assure

- AS2: analyze 14,031 -> 6,050 bytes, document 14,620 -> 9,609 (above the ~8 KB target; the manual
  content, routing and capture rules were kept whole). Feature resolution and redaction moved to
  SKILL.ext.md, task block rules and report shape to references/analysis.md and documentation.md;
  record lines live once, in the commands. Type lists gone; IL3 type-index wording in both. Lifecycle
  phase text moved to README; `--phase` dropped (the phase is the hook config). D3 fixed.
- AS1: scripts/assure_scan.py (stdlib). Also always prunes `.specify` (installed extensions are not
  repository projects). Analyze runs `--check`, Document writes (D7). assure_init.py and the template
  write `scan.exclude` (twelve entries: the eleven in the review plus `.cache`, matching the old prose).
- AS3: scripts/audit_qa.py; document step 7 is one call. SECRET copied byte-for-byte.
- AS6: `assure_state.py status --gate` reads the config with assure_scan.read_config (no PyYAML in
  CI). documentation-gates.yml steps are one run line each with `--summary`. This worktree's base has
  no fork-guard block, pinned checkout or sanduq:if markers in that template (they are on
  fix/issue-94, commit 29a4224); the merge from main must keep both.
- AS5: one description per command, identical in frontmatter and extension.yml; openai.yaml deleted.
  check_docs.py asserts equality for the seven ids. At my last run only memory (7 commands, S6) failed.
- AS4 wording: document step 1 reads changed_inputs/changed_outputs from status.
- Tests: new extensions/assure/tests/ (13 tests). Orchestrator: add `assure` to the suite matrix in
  .github/workflows/ci.yml (line ~213), which I do not own. CHANGELOG must say the rendered
  documentation-gates.yml changes on upgrade.

## U2

- UM2: `build_manual.py --all` (refuses `--audience/--language/--module` with it) reads `languages.required` then
  `optional` from `manual.yml`, keeps those with `docs/<lang>/`, builds end-user, administrator, technical for each,
  passes `--version/--archive/--pdf/--renderer` through and prints one line per edition:
  `<audience> <lang>: <site_dir>[ <zip>][ <pdf>]`. Single-edition output unchanged. Both `assets/github/*.yml` call it
  once (`--all --version ... --archive [--pdf]`); markers, pins, env and paths unchanged. Test: `AllEditionsTests`
  in `tests/test_build_manual.py` (S2 copies it into the extension's test).
- PG6: `scripts/hook.py` sniffs `hook_event_name` (CamelCase or snake_case) from stdin when argv[1] is empty; test in
  `tests/test_review_c1.py` (`test_a_missing_event_argument_is_sniffed_from_the_payload`), the upstream home of the
  dispatcher test S7 deletes.
- PG3/PG4: `hooks_install.py` writes the same five events for Codex (SessionEnd added); flag is
  `progress hooks install --post-tool-matcher REGEX` (empty = every tool), the name S7's install.py already probes.
  `hooks status` counts for Codex are now x/5. Docs: `docs/hosts.md`, `docs/commands.md`, `README.md`, `references/verbs.md`.
- PG5: `references/verbs.md` line 4 names `docs/contracts.md` and `docs/commands.md` as human references.
- Gates: user-manual 29 tests OK; progress-report 581 OK (skipped 11); `git diff --check` clean.

## S5 Illustrate

- IL4: the four command descriptions are catalog form and identical in frontmatter and `extension.yml` (check_docs equality passes for illustrate). `generate.md` drops the type and variant lists for the IL3 pointer to `references/type-index.md`; `theme.md` step 4 says run `init` (the script prompts, or `--non-interactive`); export flag list kept. Command sizes (bytes): export 1,616, generate 1,681, import 2,331, theme 1,039, hook 595.
- IL3 consumer: `scope/references/illustrate-plan.md` step 3 reads `type-index.md`, then `type-dependency.md`, `SKILL.md` only outside the recipe. `type-index.md` is not yet in the vendored `extensions/illustrate/skill/` (U1 sync pending); generate and illustrate-plan point at it.
- IL6: `hooks/hooks.json` (PostToolUse, matcher Write|Edit, workflow's runpy shape) plus `hooks/self_check_hook.py`; `extension.yml` `events: post_tool_use` names `speckit.illustrate.hook`, a hook-only command file kept out of `provides.commands` (same pattern as `speckit.progress.hook`). The script exits 0 unless `.specify/workflow.yml` has `illustrate.hooks.self_check: true`, then for an `.html` write containing `<svg` runs self_check.py, verify-geometry.py, illustration_theme.py validate and returns the first failure with exit 2. Test: `tests/test_self_check_hook.py`.
- Runs: illustrate unittest 142 OK (PNG export did not fail here); validate_skills 0 errors; `git diff --check` 0; check_docs exit 1 only on the seven memory descriptions (S6).

## S7 Progress

- PG1/PG2: catalog-form descriptions (third person, "Use when", quoted phrases, 209 to 266 chars) in the five command frontmatters and `extension.yml`; `tests/test_extension.py` asserts equality, under 1,024, `^[A-Z][a-z]+s\b`, "Use when", a quoted phrase. The skill load line is gone from status, export, theme, refresh; `init.md` keeps it with "record lanes, blockers and notes later with the verbs it lists" (test: only init loads the skill).
- PG3/PG4 (`extensions/workflow/scripts/install.py`): `progress_policy` reads `progress.hook_wiring` / `post_tool_matcher` (defaults speckit / ""); `wire_progress` runs after the last Spec Kit call and reconcile. native: removes the Spec Kit progress entries from `.claude/settings.json` and `.codex/config.toml`, runs `progress.py hooks install --host <h>` (writes `.claude/settings.json` / `.codex/hooks.json`, hook.py direct), passes `--post-tool-matcher` only when `hooks --help` lists it, else records `matcher_applied: false` with a note. speckit + matcher: moves the Claude PostToolUse progress handler into its own group with the matcher, rewrites `matcher =` in the Codex TOML block. Leaving native: `hooks uninstall --host <h>` and progress is re-added through Spec Kit when install-lock.json said native. `install-lock.json` and the receipt get `progress: {hook_wiring, post_tool_matcher, hosts: {<h>: {file, speckit_entries_removed | native_entries_removed, matcher_applied, note, result}}}`. `.codex/config.toml` added to the rollback FILES. `progress_bridge.HOOK_MARKERS` adds `progress/scripts/hook.py` and `--managed-by=progress-report`. Tests: `test_progress_shim.ProgressWiring` (3) and `ReportingModes.test_native_hook_py_entries_mean_projection`. Untested: the one-line re-add condition in `install()`.
- Known limit: Spec Kit re-renders its progress entries on any later `specify extension` command, so a native project gets both sets until the Workflow installer runs again (README says so).
- PG6: `speckit.progress.hook.md` runs `py: scripts/hook.py` (resolved under `.specify/extensions/progress/`); `hooks/dispatch.py` deleted; its test is upstream's now. RELEASE GATE: vendored hook.py (agent-tools 1.4.3) has no `hook_event_name` sniff, so with an empty event the bind handshake on PostToolUse is dropped (`relevant()` needs the event). Vendor agent-tools 1.5.0 (U2) before releasing progress 1.3.0.
- PG5: `assets/skill/SKILL.md` deleted, its map and file entries dropped from vendor.lock.json (`vendor.py check`: match); glob dropped from benchmark_instructions.py; `package.py` `EXCLUDE_PATHS = {'progress': ('docs/assets',)}`; README image links go to raw.githubusercontent.com main. Test: the archive has docs/commands.md but no docs/assets or assets/skill.
- PG7: SKILL.ext.md rules 3, 4 (and 6, which said the same) become one: "The CLI refuses what the contract forbids and prints `progress: error CODE`; fix the cause the error names, do not retry in a loop." reporting.md keeps the bold rule sentence, because `test_reporting_instructions.py` pins it there exactly once (not S7's file); it now names the Progress skill as the rule's home, and its Codex approval paragraph is one sentence linking `../../../README.md#progress-reporting`. 3,937 bytes.
- For the orchestrator, extensions/workflow/README.md (S3 owns it): replace the "Never spawn ... only to maintain the report" paragraph with: "Reporting never spawns, keeps, messages or polls an agent; the rule is stated once in the Progress skill and applied in every mode by [reporting.md](skills/workflow/references/reporting.md)." In the Codex approval paragraph add: "With `progress.hook_wiring: native` the five hooks live in `.codex/hooks.json` and run `python3 .specify/extensions/progress/scripts/hook.py <event> --managed-by=progress-report`, so approve them again after switching."
- Runs: progress tests 14 OK (7 skipped: tiktoken); workflow test_progress_shim + test_install 98 OK; test_progress_integration + test_reporting_instructions 18 OK; extensions/scripts/tests 93 OK; validate_skills 0 errors; `git diff --check` 0; check_docs exit 1 only on the seven memory descriptions (S6).

## S4 Project

- PJ4: `extensions/project/scripts/project_sync.py` (stdlib) replaces `project-sync.sh` and
  `project-sync.ps1` (deleted). Same flags (`--phase --feature --dry-run --no-sub-issues --force
  --json --summary`), same `--summary` lines (`ok issue=<n> status=<s> created=<n> closed=<n>`,
  `skipped reason=<why>`, `error exit=<rc> reason=<msg>`; no `line=` clause, Python has no ERR
  trap), same GraphQL-to-REST fallback. `extension.yml` declares `python` required. Init keeps
  its shell pair (about 460 lines, interactive, smoke-tested per shell); only its "Next" hint
  changed.
- `test_project_sync_summary.py` rewritten for the Python script (reason: the twins it ran are
  gone): flag conflict, skip, scope skip, ok line, --json, mid-run errors, no-regress, --force,
  dry run, sub-issue create and close, open PR to in-review, REST fallback; `gh` mocked in-process.
- PJ1: `claim` prints `project_sync: {"phase": "<phase>", "command": "python
  .specify/extensions/project/scripts/project_sync.py --phase <phase> --summary"}` or `false`
  (`PROJECT_SYNC_PHASES` in workflow.py; map stated once in dispatcher-operations.md).
- Policy keys `progress` and `illustrate` validated in `validate_policy`
  (`PROGRESS_POLICY_INVALID`, `ILLUSTRATE_POLICY_INVALID`); operational, no stage cutoff.
  Not added to `schemas/policy-v1.schema.json` (outside S4; the top level allows extra keys).
- Orchestrator must change: `.github/workflows/ci.yml:377` (dryrun job) from
  `pwsh extensions/project/scripts/powershell/project-sync.ps1 -Phase open -DryRun -Json` to
  `python extensions/project/scripts/project_sync.py --phase open --dry-run --json` (and drop
  `shell: pwsh` at :375 if wanted). The `project-init` job (:347) still runs the init pair and
  needs no change. `.github/scripts/ci_matrix.py`: `project` is not a suite, so a change under
  `extensions/project/` alone runs no test; add a mapping so it runs the workflow suite.
- `execution-report.md:36` (not S4) still says `project-sync`; wording is still correct.

### U1 (IL1, IL3, IL5) entry file, type index, strict checks, 2026-10-19

Took over from a cut-off agent: kept its `self_check.py` strict section (shared skin checks, parser, accent/grid/legend/min-width/font checks), converted the file from CRLF to LF, and fixed its false positives (see below). SKILL.md and the three new references were written from scratch.

Sizes: SKILL.md 34,739 -> 11,703 bytes, 442 -> 155 lines (frontmatter unchanged). New: references/type-index.md 6,530 (52 lines: 44 types + U1c's 8 variant files), taste-gate.md 5,864, variants.md 2,397. Owned references grew slightly: style-guide.md (focal rule, resolver-wins line, type-ramp pointer), primitives-core.md (motion-template marker note, `--orthogonal` pointer, digest wording), export.md (no-path, `--scale`, `--registry`, report-paths lines from the deleted command).

SKILL.md keeps the old section tags in its headings (§0, §3, §5 to §12; §1, §4, §9 point to taste-gate.md) so the roughly 100 "SKILL.md §N" citations in type-*.md, import-*.md, output-spec.md, layout-budget.md and semantic-patterns.md still resolve without editing files outside U1.

Moved-rules checklist (old section -> where the rule lives now):
- §0 theme gate -> SKILL.md §0 (two commands; the interactive dialogue is one sentence that passes --theme/--mode/--font-loading); long form theme-initialization.md, onboarding.md.
- §1 philosophy -> taste-gate.md "Philosophy (§1)".
- §2 when to use: families -> SKILL.md §10 step 2; "don't use for" and the paragraph test -> step 1.
- §3 pattern table -> semantic-patterns.md routing table (already the long form; SKILL.md step 3 points at it); selection guide (44 rows) -> type-index.md; rules of thumb and "always load type-*.md" -> SKILL.md §3; "confirm before drawing" -> SKILL.md §10 step 4.
- §4 universal anti-patterns -> taste-gate.md "Universal anti-patterns (§4)".
- §5 design system: roles, ink-strong, node treatments, typography, font loading, Arabic fallbacks -> style-guide.md (already there); focal rule and resolver-wins line -> style-guide.md (added); SKILL.md digest keeps accent <= 2 and fonts per role.
- §6 primitives and seven connector rules -> SKILL.md digest (one line each) with the long form in primitives-core.md; optional primitives list -> SKILL.md "Other references"; motion-template marker note -> primitives-core.md.
- §7 grid and budget -> SKILL.md digest; per-type rows -> layout-budget.md. §8 summary cards -> one digest line, long form layout-budget.md.
- §9 taste gate -> taste-gate.md checklist (judgement boxes) plus `self_check.py --strict`; the mechanical boxes (accent count, legend strip, viewBox for legend, min-width, writing-mode, 4px grid rects, rule 1) are now script checks; accessible-SVG, rule 6, rule 7, motion stay script-backed as before.
- §10 variants table, hand-drawn, terminal, animation -> variants.md; the create procedure -> SKILL.md §10 (now second).
- §11 import short version and dials table -> import-drawio/mermaid/excalidraw.md and output-spec.md (both already held them); SKILL.md §11 keeps three routing lines.
- §12 output rules -> SKILL.md §12; accessible-SVG contract -> three lines in SKILL.md, long form primitives-core.md; export paragraph -> export.md (registry line added).
- commands/*.md (deleted): export flags and behaviour -> export.md (three lines added); import flags -> import-*.md and output-spec.md; theme command -> theme-initialization.md. package.json version 3.4.1 -> 3.4.3 (matches plugin.json; the orchestrator bumps both to 3.5.0).

IL5: `self_check.py --strict` adds accent on at most two node-sized shapes (rects 60x40+, circles r 20+; connectors, dots, chips, legend, aria-hidden and decorative motion shapes excluded; compound class selectors honoured), legend below the lowest node and inside the viewBox (the paper background is not a node), the svg `min-width` equal to the viewBox width (svg selectors and the inline style only), no `writing-mode` declaration, no `box-shadow` other than `none`, `rx` <= 10 (full pills excepted), node/zone rects on the 4px grid (`.5` offsets and `data-*`-bound rects excepted), font role per role class (terminal variant excepted), pure black, and orthogonal connectors. `lint-skin.py` now imports `HEX_RE`, `normalize_hex`, `canonical_motion_script` and `skin_findings` from `self_check.py` (its `--all` output is byte-identical before and after). `verify-geometry.py --orthogonal` (opt-in; the default check and `--all --baseline` are unchanged): every marker-carrying path, polyline or line is axis-aligned runs joined by quarter turns, hops up to 24px allowed; path parsing reuses verify-arrow-ends.py. Default `self_check.py` output over all 274 assets is byte-identical before and after; self-check-baseline.txt and verify-geometry-baseline.txt unchanged.

Strict results: template-motion.html passes; example-policy-trace-animated.html fails one rule (svg min-width 880px, viewBox 1200). Over the 178 assets that pass the default run, 51 pass --strict; most failures are legacy min-width values below the viewBox width (e.g. 900 or 760 on a 1000 viewBox), then off-grid node rects (w=150, h=50) and the loop type's ring arcs under --orthogonal. No strict baseline was added (strict is opt-in).

Tests: tests/test_self_check.py StrictContract (a passing fixture, 13 failing edits each asserting the default run stays clean, 7 documented exceptions, terminal variant, shared skin checks); tests/test_verify_geometry.py Orthogonality (8 passing, 7 failing, default unchanged); tests/test_skill_frontmatter.py SkillEntry (under 200 lines and 12,500 bytes, procedure before the type section, every relative link in SKILL.md and references/*.md resolves, type-index lists every type-*.md exactly once). tests/verify-{drawio,mermaid,excalidraw}-import.py no longer read commands/ (flag checks moved to the import references; drawio checks --page there, its dials are checked in output-spec.md).

Outside the U1 list (needed by the deletion): references/export-registry.md line 9 linked `../commands/export-diagram.md`, now `export.md`; verify-geometry.py docstring section reference. Left for the orchestrator: import-drawio/mermaid/excalidraw.md line 9 still name `/illustrate:import-*` slash commands that no host loads (the verifiers pin those names in `SLASH_COMMAND`); package-lock.json root version still says 3.1.0; the sanduq consumers (S1, S2, S3, S5) can now read references/type-index.md.
Commands: `python -m unittest discover -s skills/illustration-tools/tests -q` -> Ran 208 tests, OK (system Python 3.13; pytest not needed). The CI builder/verifier step (build --check x2, verify-motion, verify-semantic-motion, verify-geometry --all --baseline, verify-arrow-ends --all, lint-skin --all --baseline, the twelve verify-<type> --all, polar, dumbbell, sequence-oauth, block-registry) exits 0. `git diff --check` exit 0.

## S6 Memory

Options ME1 to ME8 done in `extensions/memory/**` and `docs/extensions/memory.md` (taken over from a cut-off agent; its run.md and frontmatter work kept and finished).

- ME1/ME7/ME8: `commands/run.md` 21,150 -> 4,740 bytes (preamble, 10 numbered steps, one helper call each, pointers). New `references/` (18,303 bytes): candidate-v2.md, verification-override.md, large-runs.md, format-1.md, review-and-publish.md, recovery.md, all named by installed path `.specify/extensions/memory/references/...`. session.md and status.md keep one sentence plus the recovery.md pointer. `prepare` returns `memory_format` and, on format 1, `reference: .specify/extensions/memory/references/format-1.md`. SESSION block in install.py cut to four lines (a test guards its facts).
- ME4: `memory_query.expected_hash` and `memory_query.show`; `memory show` prints `expected_hash: <sha256>`, `memory query --format json` adds `expected_hash` per entry. `Archive.next_step` gives `next: {command, reason}` in `status`, `inspect --view status`, `validate` and `finalize` (derived from phase and review.json; nothing stored). The shell one-liner is gone.
- ME2: the seven frontmatter descriptions are copied verbatim (single-quoted) into extension.yml; install.py reads the frontmatter description (COMMANDS is now a tuple of names).
- ME3: Claude wrappers of prepare and session carry `user-invocable: false`; both skill hosts keep Spec Kit's `argument-hint` and `metadata` block from an earlier render. Skill wrappers also carry one line mapping `speckit.memory.<command>` to `speckit-memory-<command>` (the old run.md host-spelling rule).
- ME6: registry `version` read from extension.yml; comment under `hooks:` about impact on before_specify; `install.HOOKS` is the one list of four registrations the test asserts.
- ME5: `hooks/hooks.json` + `hooks/guard.py` (one PreToolUse group, matcher `Bash|Write|Edit|MultiEdit|apply_patch`); merged into `.claude/settings.json` and `.codex/hooks.json` only when `guard_hooks` is true (template `archive-policy.json` false; a non-bool is rejected by install and Archive). The hook exits 0 when the key is off or no run is active.
- Packaging: `extensions/scripts/package.py` includes the whole extension directory, so `memory/references/*` and `memory/hooks/*` are in `dist/memory.zip` (verified by building to a scratch path). No package.py line needed.
- Tests added: test_guard_hook.py (3), test_install.py (5: descriptions/user-invocable/Spec Kit keys, registry version + four hooks, SESSION facts, guard registration on/off, references exist and stay under 500 lines), test_archive_v2 status-next per phase, test_archive format-1 prepare reference, test_memory_query expected_hash. No existing test changed.
- Environment note: with the Microsoft Store `python` the suite has 57 pre-existing errors (check_inputs cannot open the WindowsApps python.exe alias to hash it); run it with a real interpreter (here uv cpython 3.11).
- Prose kept despite ME5: the hook is opt-in (default false), so run.md keeps one sentence forbidding push, PR creation, stash, reset, clean, broad staging, automatic rollback and implicit bypass, and step 7 keeps "never edit specs/memory/, the registry or feature files"; the hook is named as the enforcement when on.

Checklist of old run.md rules (HEAD) and where they live now ("dropped" = guard restatement from the lens-1 table; the helper's error names the rule):

- Operate only in the configured checkout: run.md preamble.
- No push, PR creation, stash, reset, clean, broad staging, automatic rollback, implicit bypass: run.md preamble; hook (opt-in) for the git verbs.
- JSON `success`, nonzero exit is a blocker: run.md preamble.
- Host command spelling (hyphens vs dots): skill wrapper line written by install.py (SKILL_NAMES).
- `A` alias: run.md preamble; recovery.md.
- Memory format note: prepare result `memory_format`/`reference`; run.md step 5; format-1.md.
- Read policy; explicit selection; `--all-completed`; separate `--retire-reason`; never in automatic/all: run.md step 1.
- Never include this extension's own unfinished feature; never infer completion: step 1.
- Inspect implementation, QA/review/manual, unfinished concerns, external evidence on the target branch: step 2.
- Do not assert completion for convenience; missing infrastructure blocks; external uncommitted code not verified: step 2.
- Preflight `--spec --check`, `data.ok`, keep repair-required and pending guards, fix failures before verification: step 3.
- Verify `--complete --check` binds evidence; `--related` to verify and prepare, never automatic: step 4.
- Prepare, `--automatic` only for ready entries, checkpoint, run id and paths, `--all-completed` skipped list: steps 1 and 5.
- Retired unfinished feature needs reason and named checks unless override: step 1; verification-override.md.
- Prepare refuses while a run is active: dropped (archive.py prepare).
- Override only on explicit owner request, never inferred: step 4; verification-override.md.
- Reason nonempty, printable, single line, at most 500 chars; permanent, concise: verification-override.md (limits as what prepare rejects); README.
- Override omits verify and `--check`; prepare with `--skip-verification`; repeat `--spec`: verification-override.md.
- `--related` stays unverified input; target branch and completion boundary still required; do not mark tasks complete: verification-override.md.
- Automatic and `--all-completed` reject the override: verification-override.md (as what prepare rejects).
- What is skipped and what stays required; inspect journal; review consumer repairs line by line; keep limits; no archive log or claimed pass: verification-override.md.
- Reviewer adds `verification_override`; `passed` means critique; reason in commits, index, ledger: verification-override.md; review-and-publish.md.
- Existing transaction keeps its mode: abandon or roll back, then re-prepare: verification-override.md; recovery.md.
- Do not edit the journal; finalize has no skip flag: dropped (archive.py verification_guard, argparse).
- inspect views, cursor, oversized_record, max-bytes: step 6 (CLI default numbers dropped as restatements).
- Journal references, checkpoint, base_memory_root, scope: step 6.
- Read memory only through query/show/catalog/provenance and INDEX.md, never wholesale, with the query flags: step 6.
- Read evidence at the checkpoint: step 6.
- Edit only candidate.json, never specs/memory, registry or feature files: step 7; hook (opt-in).
- Delta only; keep schema_version/base_memory_root/checkpoint; JSON shape: candidate-v2.md.
- Unknown top-level keys rejected: dropped (memory_delta.py).
- Entry keys, kinds, selector kinds, link meanings, omit empty lists, full entry on update: candidate-v2.md.
- One link list per id, never own id; new ids neither existing nor retired: dropped (memory_store.py, memory_delta.py).
- Anchoring, `reason` on unsupported corrections, never a wholesale rewrite: candidate-v2.md.
- expected_hash for every update and removal; mismatch means memory moved: candidate-v2.md (copied from show / query json).
- Provenance compact form, unit split, evidence outside specs at the checkpoint, every behavior needs evidence, evidence-only re-anchor, specs not proof, uncertainty to limits, no repeated prior provenance: candidate-v2.md.
- Tombstones from `memory provenance` record_hash; only for wrong provenance; ledgers append-only: candidate-v2.md.
- Removals: retire record, never reused, reason, source_unit, live replacement or null, prefer the replacement, constrains must move: candidate-v2.md. No update plus remove or double update: dropped (memory_delta.py).
- Taxonomy add/update, prefer existing domains, a new domain is reviewed: candidate-v2.md. Kebab-case and Windows reserved names: dropped (memory_delta.py).
- Coverage: every unit exactly once, omitted needs reason, others need live ids with provenance: candidate-v2.md (gap/overlap wording dropped).
- Budgets from policy, split oversized entries, never write catalogs or INDEX: candidate-v2.md (numbers dropped; the policy holds them).
- Text rules: heading rule kept in candidate-v2.md; marker and reference-resolution rules dropped (memory_store.py).
- Organize by capability, merge duplicates, no changelog, account for gotchas, no omissions to pass checks: candidate-v2.md.
- Large-run packets steps 1 to 7 and carry-over of partition approvals: large-runs.md. Re-packeting refused: dropped (orchestration.py).
- Format-1 candidate shape: format-1.md.
- Migrations and repairs (both formats): candidate-v2.md; format-1.md points there.
- Preflight `--run` until candidate_guards passed; its data fields; exit semantics: run.md step 8; review-and-publish.md. Stray files refused: dropped (memory_delta.py, archive.py).
- Independent reviewer, content not JSON, read-only delegate, stop if unavailable, workflow authorizes, never changes files, no self-review independence claim: review-and-publish.md.
- review.json fields for both formats and v2 bindings: review-and-publish.md.
- Any candidate edit invalidates the review; checks cannot prove semantics: review-and-publish.md.
- validate semantics (v2 valid is not approval; format 1 requires critique), finalize only on review passed, what finalize writes, no extra prompt under automatic policy: review-and-publish.md; format-1.md; `next` from status/validate.
- Explicit manual run authorizes the selection only, never expand scope: run.md closing; review-and-publish.md.
- Memory moved since prepare: no rebase, abandon and prepare again: review-and-publish.md. Later-phase drift refusal: dropped (archive.py memory_result_guard).
- Interrupted/blocked: status, journal, rerun finalize, preserve edits and checkpoint: recovery.md (status `next`).
- Abandon a stale unpublished proposal: recovery.md. Forbidden after publication: dropped (archive.py abandon).
- Explicit rollback semantics, resumable, refuses after final commit or user edits: recovery.md.
- While a run is active, `pending --gate` before a new spec, branch or broad commit: run.md closing; recovery.md; session.md; SESSION block.
- Do not delete the active journal: recovery.md.
- Report checkpoint/final commit and archived/skipped features; assets via `git show`: run.md step 10; recovery.md.
