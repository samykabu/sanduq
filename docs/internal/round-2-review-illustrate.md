# Round 2 review: illustrate (stream R3, read-only)

Measured on worktree `feat/round-2`, extension `illustrate` 2.4.2, vendored from sanduq-skills
`illustration-tools-v3.4.3` (sha `1f0a7d8`, `vendor.lock.json`). Everything under
`extensions/illustrate/skill/**` is an upstream file (498 files in the lock); options that touch it
are labelled **upstream** (change in sanduq-skills, release the bundle, `vendor.py sync`, bump the
extension). `commands/*.md`, `extension.yml`, `README.md` and `tests/` are sanduq-owned.

## Summary

- `skill/SKILL.md` is 34,739 bytes, 442 lines (436 body lines; `validate_skills.py` warns at 500) and every route into the skill reads it whole: the sanduq command (`commands/speckit.illustrate.generate.md:15` "Read ... SKILL.md completely"), the plugin skill on both hosts, and five consumer commands in `pr`, `assure` (x2), `user-manual` and `scope`.
- For one editorial diagram the minimal read is SKILL.md 34,739 + median type reference 5,920 + median minimal example 11,485 = 52,144 bytes; SKILL.md is 67 percent of it. Following the links SKILL.md itself asks for (output-spec 15,724, primitives-core 13,428, layout-budget 4,647) makes 85,943 bytes, SKILL.md 40 percent.
- About 24 KB of the entry file is condensed duplicates of references it links (connector rules, accessible-SVG contract, dials, budget, design roles, variants, import and export procedures) plus a 37-box checklist of which 8 boxes are script-backed. The procedure ("To create a new diagram", lines 370 to 376) sits at byte 28,900 of 34,739, past the 20 KB (5,000 token) point Claude Code keeps after compaction.
- The four sanduq commands pass the size rule but all four fail "when" and "triggers"; two are imperative; each has two different description strings (`extension.yml` versus command frontmatter). Together with the plugin skill they put 1,376 catalog characters (about 17 percent of Claude Code's 1 percent listing budget on a 200k window) behind one capability on both hosts.
- The biggest option, IL1 (upstream), cuts the entry to 11 to 12 KB and the minimal per-diagram read from 52 KB to about 29 KB (minus 45 percent; minus 27 percent on the link-following path); the same saving repeats in every consumer command that loads the skill.

## Findings per lens

### Lens 1: model told to do what a script does or could do

- `SKILL.md` §9 (lines 291 to 346) is 37 checkbox lines (`grep -c '^- \[ \]'`), 3,622 bytes. Script-backed: 3 accessible-SVG boxes, §6 rule 6 (`verify-geometry.py`, line 327), rule 7 (`verify-arrow-ends.py`, 328), theme literals (`illustration_theme.py apply`, 335), `self_check.py` (336), motion (`verify-motion.py`, 337). The other 29 are hand judgement, and at least 9 are mechanical: accent on at most 2 elements (312), legend below all nodes (330), `viewBox` expanded for the legend (332), `min-width` equals viewBox width (333), no `writing-mode` (331), 4px grid for rect geometry (334), shadow and `rx` limits (§4 table, lines 170 to 180), sans/mono/serif per role (341 to 345).
- `scripts/lint-skin.py` already checks fonts, pure black, `<script>` and external assets (`lint-skin.py:185-243`) but `self_check.py` describes itself as "a distilled subset" of it (`self_check.py:12-14`) and does not run those checks; the agent is asked to eyeball them instead.
- `SKILL.md` §6 rules 1, 3, 4, 5 (orthogonal only, no overlaps, fan attach points 12px apart, no transit behind a box; lines 255 to 259) are geometry statements with no verifier; `verify-geometry.py` covers masks versus nodes only (`verify-geometry.py:2-12`).
- `commands/speckit.illustrate.theme.md:18-20` and `SKILL.md:24-30` spell out the interactive theme dialogue that `illustration_theme.py init` already implements (`illustration_theme.py:732`, `--non-interactive`).

### Lens 2: text repeated

Inside the skill (upstream), condensed copies of linked references:

| SKILL.md section | bytes | long form it links |
|---|---:|---|
| §6 "Mandatory connector rules" (lines 251 to 261) | about 1,900 | `references/primitives-core.md:54-80` (same 7 rules, same numbering) |
| §12 "Accessible SVG contract" (lines 423 to 434) | about 900 | `references/primitives-core.md:138` |
| §11 dials table (lines 398 to 403) | about 800 | `references/output-spec.md:10-48`; also in the three `import-*.md` and the three `skill/commands/import-*.md` (`doc-inline` and "fidelity ledger" appear in 8 files) |
| §7 and §8 budget and cards (lines 265 to 289) | 1,249 | `references/layout-budget.md:21-74` (`1.1fr 1fr 0.9fr` appears in both) |
| §5 roles and typography (lines 186 to 230) | 2,770 | `references/style-guide.md` |
| §10 variants table (lines 353 to 367) | about 1,600 | `primitive-sketchy.md`, `primitive-terminal.md`, `animation.md` |
| §11 import procedure (lines 382 to 390) | 2,694 | the three `import-*.md`, each of which already repeats the dials paragraph (B0 duplicate list, `instructions-before.md:95`) |

B0's cross-file duplicate list finds 4 of its 7 repository-wide duplicate paragraphs inside `skill/references/technical-color-*.md` (`instructions-before.md:91-95`), all upstream.

Sanduq-owned repeats:

- `commands/speckit.illustrate.generate.md:26-40` (about 1,500 bytes) lists the 44 types and the variants that `SKILL.md` §3 and §10 already carry; the command then tells the agent to read SKILL.md completely, so the list is read twice per run.
- `commands/speckit.illustrate.export.md:19-26` restates the flag table of the vendored `skill/commands/export-diagram.md:22-31`, which no host loads (it sits under `skills/illustrate/commands/`, not at the plugin root) and which uses Claude-only keys (`argument-hint`, `allowed-tools`). Five such files, 14,520 bytes, linked from `SKILL.md:382` and `:440`.
- Consumers carry their own stale type lists: `extensions/assure/commands/speckit.assure.document.md:203` says "all twenty-seven types" and `speckit.assure.analyze.md:173-175` lists 27; the skill has 44. (R1 owns assure; recorded here as evidence that the type index should be one importable reference, see IL3.)

Against the workflow dispatcher: only `extensions/workflow/skills/workflow/references/stage-clarify.md:28` mentions Illustrate (one line, "diagram_image is optional"); no repetition. Scope's `references/illustrate-plan.md` (115 lines) is the one managed route that draws, and it loads "the installed Illustrate skill" plus `type-dependency.md` (`illustrate-plan.md:20-21`).

### Lens 3: rereading large inputs

- Every route reads the whole 34,739-byte file for any diagram: `speckit.illustrate.generate.md:15`; `pr/commands/speckit.pr.generate.md:136` ("load ... SKILL.md now ... use its selection guide"); `assure/commands/speckit.assure.document.md:202`; `speckit.assure.analyze.md:177`; `user-manual/commands/speckit.user-manual.analyze.md:32`; `scope/references/illustrate-plan.md:20`. The part they name, the selection guide, is 6,029 bytes (44 table rows, lines 104 to 148).
- Per diagram (B0, `instructions-before.md:44-48`): `speckit.illustrate.generate` 37,592 instruction bytes before the type reference and example are opened. The skill row counts 724,496 linked bytes across 63 references; the agent never needs more than three or four of them per diagram, so the honest per-diagram figure is the 52 to 86 KB computed in the summary, not 759 KB.
- Harness caveat for the orchestrator: B0 counts script files named in a command as "linked". `export` 26,973 = `export.md` 9,737 + `export_diagram.py` 17,236; `theme` 40,550 = `theme-initialization.md` 7,990 + `illustration_theme.py` 32,453; `import` 91,390 = three import references 35,223 + `output-spec.md` 15,724 + `theme-initialization.md` 7,990 + `illustration_theme.py` 32,453. The agent runs those scripts; it does not read them. Reads are about 11 KB, 9 KB and 59 KB.
- Compaction (Claude Code only): the first 5,000 tokens of an invoked skill survive, about 20,000 bytes. Section byte offsets: §6 starts at 17,653, §7 at 21,509, §9 taste gate at 22,758, §10 procedure at 26,380, §11 at 29,852, §12 at 32,546. After compaction the model keeps the theme gate, philosophy and the type table and loses the budget, the checklist, the create procedure, the import routing and the output contract. The procedure should be first.
- Type references are skewed: 44 files, min 991, median 5,920, mean 9,988, max 43,288 (`type-line.md`); 10 are above 16 KB (`type-line`, `type-it-state` 30,194, `type-process` 28,796, `type-high-level` 26,462, `type-medallion` 22,436, `type-dp-integration` 22,455, `type-data-flow` 21,492, `type-scatter` 20,266, `type-dp-security-matrix` 19,086, `type-treemap` 18,501). Those ten carry variants (slopegraph, ridgeline, streamgraph, bump under `type-line`; bubble and beeswarm under `type-scatter`) that could be split so a plain line chart reads 8 KB, not 43 KB. 29 of 63 references link further references (`import-drawio.md` links 17), so the "one level deep" rule is already broken below SKILL.md.

### Lens 4: descriptions and catalog slots

- Plugin skill (`SKILL.md:3`): 992 characters, third person, what, when, trigger words, "not for" boundary. Passes every rule; `tests/test_skill_frontmatter.py` guards the 1,024 limit and five trigger words.
- The four commands (B0 `instructions-before.json`, `illustrate.commands[].description`): all four fail `has_when` and `has_triggers`; `export` ("Export an Illustrate HTML source ...") and `theme` ("Initialize, select, validate ...") fail `third_person`. 4/4 failing, 384 catalog characters.
- Two description strings per command: `extension.yml:25-36` ("Select and generate the right illustration ...") versus `commands/speckit.illustrate.generate.md:2` ("Generate the most appropriate technical ... using the versioned Illustrate skill package."), and likewise for export, theme and import. Spec Kit renders the command file's frontmatter to both hosts (first report, "What Spec Kit does"), so B0 measured the string the hosts do not see; both strings fail the same rules.
- Double listing: in a sanduq consumer both the marketplace plugin skill `illustrate` (992 characters, `.claude-plugin/marketplace.json:13-21` and `.agents/plugins/marketplace.json:9-15`, same ref and sha) and the four `speckit-illustrate-*` skills (384 characters) are catalogued on both hosts: 1,376 characters, about 17 percent of an 8,000-character (1 percent of 200k) Claude listing budget, for one capability. No command is hook-only; all four are user commands.
- `extension.yml` carries 30 tags (lines 38 to 68); no host reads them.

### Lens 5: rules a hook could enforce

Prose that repeats a check a `PostToolUse` (Write or Edit of `*.html` containing `<svg`) hook could run: "Ran `illustration_theme.py apply`?" (`SKILL.md:335`, `:376`, `:389`, `commands/speckit.illustrate.import.md:37-38`, `commands/speckit.illustrate.generate.md:40`), "Did `self_check.py` pass?" (`SKILL.md:336`, `:434`), `verify-geometry.py` (`:327`), `pr.generate.md:175` and `scope/references/illustrate-plan.md:43` (where `accept_plan.py` already runs the same three scripts, the one place the rule is enforced). "Do not auto-install Playwright" (`commands/speckit.illustrate.export.md:28`, `skill/commands/export-diagram.md:36`) and "never produce export files unprompted" (`SKILL.md:442`) are PreToolUse-deny candidates but low value. Both hosts accept the same `hooks/hooks.json` shape; a plugin with hooks cannot enter Codex's public directory, so the hook belongs on the sanduq side, not in the bundle.

### Lens 6: Claude Code versus Codex

- Paths are identical: every command and consumer resolves `.specify/extensions/illustrate/skill/...` from the project root; Spec Kit renders the four commands to `.claude/skills` and `.agents/skills` from one source (`README.md:14-19`).
- The bundle is listed for both hosts at the same ref (`.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json`); upstream ships a root `plugin.json` (Agent Plugins 1.0.0) plus `.claude-plugin/plugin.json`, one skill, no hooks, no agents.
- Codex-only `skill/agents/openai.yaml` (235 bytes: display name, short description, default prompt). No Claude-specific frontmatter; the vendored copy adds only `metadata.internal: true` (34,739 versus upstream 34,712 bytes, 27 bytes = the `vendor.py` `mark_internal` string).
- Divergences: (a) the compaction rule above is Claude-only, so the file order costs Claude and not Codex; (b) `skill/commands/*.md` use Claude-only keys and `$1` positional arguments although neither host loads them; (c) directory name `skill` differs from `name: illustrate`, allowed only through `validate_skills.py:29` `DIRECTORY_EXCEPTIONS`, harmless because that copy is path-loaded; (d) `skill/package.json` says version 3.4.1 while the bundle is 3.4.3 (cosmetic, upstream).
- Tests: `extensions/illustrate/tests` (36 files, 645 KB) is a near-copy of upstream `skills/illustration-tools/tests` (upstream has 4 more files; `test_self_check.py` identical, `_helpers.py` and `test_verify_sankey.py` drifted). CI time only, no agent cost; not an option below.

## Defects

| Defect | Effect | Where |
|---|---|---|
| Entry file read whole for any diagram | 34.7 KB (about 8.7k tokens) per diagram, 67 percent of the minimal read; repeated by 5 consumer commands | `skill/SKILL.md`; `commands/speckit.illustrate.generate.md:15`; `pr.generate.md:136`; `assure.document.md:202`; `assure.analyze.md:177`; `user-manual.analyze.md:32`; `scope/references/illustrate-plan.md:20` |
| Procedure and checklist last in the file | After Claude Code compaction the model keeps the type table and loses §7 to §12 (offsets 21,509 to 34,739) | `SKILL.md:370-376` (procedure), `:291-346` (taste gate) |
| Condensed duplicates of linked references | About 12 KB of §5, §6, §7, §8, §10, §11, §12 restate `primitives-core`, `style-guide`, `layout-budget`, `output-spec`, `import-*`, `export` | table in lens 2 |
| 29 of 37 taste-gate boxes are hand checks; 9 are mechanical; `lint-skin` checks not in `self_check` | Model re-reads and re-judges what a script could fail in one run; fix loops are prose-driven | `SKILL.md:291-346`; `scripts/self_check.py:12-14`; `scripts/lint-skin.py:185-243` |
| Ten type references above 16 KB hold several variants each | A plain line chart reads 43 KB (`type-line.md`), a scatter 20 KB | `references/type-line.md`, `type-scatter.md`, `type-it-state.md`, `type-process.md`, and six more |
| Four command descriptions fail when and triggers; two imperative; two strings per command | Weaker routing on both hosts; the measured string is not the rendered one | `extension.yml:25-36`; `commands/*.md:2` |
| Type list and variant list repeated in the generate command | About 1.5 KB read before the same list in SKILL.md §3 | `commands/speckit.illustrate.generate.md:26-40` |
| Five unloaded command files inside the skill, Claude-only keys | 14.5 KB vendored and linked from SKILL.md for nothing a host runs | `skill/commands/*.md`; `SKILL.md:382`, `:440` |
| Plugin skill plus four command skills in every consumer catalog | 1,376 catalog characters on both hosts for one capability | marketplace files; `extension.yml` |
| Consumers keep their own stale type lists | "twenty-seven types" in assure versus 44 in the skill | `assure.document.md:203`, `assure.analyze.md:173-175` (R1 scope) |

## Options

Cost basis for `tok` and `time`: one diagram task through `speckit.illustrate.generate` is taken as
instruction input 52 to 86 KB (13k to 21.5k tokens, the minimal and link-following paths above) plus
the diagram output (8 to 15 KB, 2k to 4k tokens) plus script runs and reporting (about 2k), so 17k to
27k tokens per diagram, of which SKILL.md is 8.7k. `tok` is the saved bytes divided by that span,
lower bound against the link-following path, upper bound against the minimal path. `time` assumes
reading is roughly a quarter of wall time per diagram (drawing and script runs dominate), so time
fractions are about a quarter of the token fractions unless an option removes a round trip.

### IL1 (upstream): restructure SKILL.md into a procedure and a type index

- **title**: Procedure-first entry file of 11 to 12 KB
- **what**: Rewrite `skills/illustration-tools/skills/illustrate/SKILL.md` in sanduq-skills so it holds, in this order: frontmatter (1.1 KB); theme gate as two commands and one sentence (0.9 KB); "To create a new diagram" as the second section (1.5 KB: family, pattern, type, state the plan, copy template, apply, validate, geometry, self_check); the type index with one line per type (44 lines, cue of 6 to 8 words plus type name plus reference link, about 5.0 KB, down from 6.0 KB) with the 9-row semantic-pattern table folded to one line that points at `semantic-patterns.md`; rules digest (7 connector rules as one line each, the budget row, accent at most 2, legend strip, fonts per role, 4px grid: about 1.7 KB); theme and export rules (apply last, never produce export files unprompted, load `export.md` on request, `--registry`: 0.8 KB); accessible-SVG contract as three lines (0.4 KB). Expected entry: 11.4 KB, 170 to 190 lines. Moves: §4 anti-patterns and §9 taste gate into a new `references/taste-gate.md` (about 5 KB, loaded once per diagram at the end); §5 into `style-guide.md` (already covers roles); §6 long form is already `primitives-core.md`; §7 and §8 are already `layout-budget.md`; §10 variants table into a new `references/variants.md` (or `style-guide.md`); §11 shrinks to the three routing lines (the import references own the procedure and the dials); §12 export paragraph to `export.md`. Delete `skill/commands/*.md` (no host loads them; the sanduq commands and the import and export references cover them) and fix `package.json` version. Release `illustration-tools` 3.5.0, `vendor.py sync --input illustrate --ref illustration-tools-v3.5.0`, bump the sanduq extension to 2.5.0.
- **effort**: M (upstream edit and tests two days, release plus vendor sync plus sanduq docs one day)
- **tok**: [0.20, 0.35]. Per diagram the minimal read drops from 52,144 to about 28,900 bytes (11.4 + 5.9 + 11.5 KB) and the link-following read from 85,943 to about 62,700 (the taste-gate reference, 5 KB, is added back once); saving 23 KB, about 5.8k tokens, over 27k to 17k.
- **time**: [0.05, 0.10]
- **obs**: unchanged; the same scripts run, the same files are written.
- **policy**: none
- **pros**: The saving repeats in every consumer command that loads the skill (pr, assure x2, user-manual, scope) and in every clarification or plan diagram in the managed workflow. Claude Code keeps the whole procedure after compaction. The 500-line edge disappears (about 180 lines).
- **cons**: Upstream release cycle; every reference link in SKILL.md (63 files) must be re-checked; `tests/test_skill_frontmatter.py` is unaffected but upstream tests that quote SKILL.md section numbers in docstrings (`verify-geometry.py:4`, `verify-arrow-ends.py:9`) need their references updated; the plugin skill and the sanduq command change together, so the version floor for consumers (`>=2.0.0,<3.0.0`) stays valid but docs that quote section numbers (`docs/extensions/illustrate.md`) need a pass.
- **files**: sanduq-skills `skills/illustration-tools/skills/illustrate/SKILL.md`, `references/taste-gate.md` (new), `references/variants.md` (new), `references/style-guide.md`, `references/export.md`, `commands/*` (deleted), `package.json`, `CHANGELOG.md`; sanduq `vendor.lock.json`, `extensions/illustrate/skill/**` (synced), `extensions/illustrate/extension.yml` (version), `extensions/illustrate/CHANGELOG.md`, `docs/extensions/illustrate.md`.
- **tests**: upstream: a test that SKILL.md is under 200 lines and 12,500 bytes and that every `references/*.md` link resolves; sanduq: `tests/test_skill_frontmatter.py` (unchanged), `extensions/scripts/vendor.py check`, `validate_skills.py`, the benchmark AFTER run.

### IL2 (upstream): reorder only, procedure and checklist first

- **title**: Move §10 "To create a new diagram" and a 12-line checklist to the top without moving any text out
- **what**: Fallback if IL1 is not chosen. Reorder `SKILL.md` so the create procedure, the connector digest and the mechanical checklist sit within the first 18 KB; the type table and the design-system prose follow. No reference moves, no deletions. Same release and vendor steps as IL1.
- **effort**: S
- **tok**: [0, 0] (same bytes)
- **time**: [0, 0.02] (fewer "which step am I on" re-reads after compaction; no measured basis, treat as zero)
- **obs**: unchanged
- **policy**: none
- **pros**: Zero risk of dropping a rule; fixes the Claude compaction cut.
- **cons**: Keeps every byte; superseded entirely by IL1.
- **files**: sanduq-skills `SKILL.md`; sanduq `vendor.lock.json`, `extensions/illustrate/skill/SKILL.md`.
- **tests**: `tests/test_skill_frontmatter.py`; `vendor.py check`.

### IL3 (upstream plus sanduq): a standalone type index for consumers

- **title**: `references/type-index.md` so consumer commands load 5 KB, not 35 KB
- **what**: Upstream: publish the one-line-per-type index from IL1 as its own file `references/type-index.md` (about 5 KB) that SKILL.md includes by link rather than inline, or keep it inline and ship the file as a copy generated by a script in CI. Sanduq: the five consumer sites (`pr.generate.md:136`, `assure.document.md:202`, `assure.analyze.md:177`, `user-manual.analyze.md:32`, `scope/references/illustrate-plan.md:20`) load `type-index.md` plus the chosen `type-*.md` instead of SKILL.md, and drop their own type lists (assure's stale "twenty-seven"). Those consumer files belong to R1, R2 and the scope owner; this record is the cross-cutting half.
- **effort**: S upstream, S sanduq (five one-line edits plus deleting two stale lists)
- **tok**: [0.15, 0.30] of a consumer's diagram step (SKILL.md 34.7 KB replaced by 5 KB, saving about 7.4k tokens, against the same 17k to 27k per diagram; the consumer also still needs the procedure, so count only 60 to 80 percent of that saving unless IL1 ships, which makes the consumer read the 11 KB entry anyway)
- **time**: [0.03, 0.08]
- **obs**: unchanged
- **policy**: none
- **pros**: Pays off in managed runs (scope plan, clarification images, PR diagrams) where the skill is loaded by a command that already knows the family. Removes the consumers' stale lists.
- **cons**: Two copies of the index to keep aligned unless generated; the consumer still needs the procedure, so it only works paired with IL1 or with a short "procedure" reference. Overlaps R1 and R2 files; the orchestrator must dedupe.
- **files**: sanduq-skills `references/type-index.md`, `SKILL.md`; sanduq `extensions/pr/commands/speckit.pr.generate.md`, `extensions/assure/commands/speckit.assure.document.md`, `speckit.assure.analyze.md`, `extensions/user-manual/commands/speckit.user-manual.analyze.md`, `extensions/scope/references/illustrate-plan.md`.
- **tests**: upstream link-resolution test; sanduq `benchmark_instructions.py` AFTER shows the consumer `linked` bytes drop; existing pr, assure, user-manual and scope suites unchanged.

### IL4 (sanduq): fix the four command descriptions and dedupe the command bodies

- **title**: One third-person what-when-triggers description per command, no repeated type list
- **what**: Write one description per command in `commands/*.md` frontmatter and copy the same string into `extension.yml` (or drop the `extension.yml` duplicate if Spec Kit ignores it, to be confirmed against the renderer). Example for generate: "Draws one of 44 diagram types (architecture, sequence, flowchart, ER, Gantt, Sankey, charts) as themed HTML with inline SVG using the installed Illustrate skill. Use when asked to draw, diagram, chart or visualize something in a spec, doc or PR." Delete `speckit.illustrate.generate.md:26-40` (the type and variant lists, about 1.5 KB) and `speckit.illustrate.theme.md:18-20` (the dialogue the script runs). Keep the export command's flag list (it is the only place a host-loaded file carries it).
- **effort**: S
- **tok**: [0.005, 0.01] per generate run (1.5 KB of 52 to 86 KB), plus about 100 fewer catalog characters per session
- **time**: [0, 0]
- **obs**: improved (hosts route "draw me a ..." to the right command; today the plugin skill wins on both hosts because the command descriptions carry no trigger words)
- **policy**: none
- **pros**: Zero risk; measurable in B0's description columns (4/4 failing to 0/4).
- **cons**: Two places to keep in sync until the `extension.yml` duplicate is confirmed unused.
- **files**: `extensions/illustrate/commands/speckit.illustrate.generate.md`, `speckit.illustrate.export.md`, `speckit.illustrate.theme.md`, `speckit.illustrate.import.md`, `extensions/illustrate/extension.yml`, `extensions/illustrate/CHANGELOG.md`.
- **tests**: `benchmark_instructions.py` description checks; `extensions/scripts/tests/test_validate_skills.py` if it covers command frontmatter; a one-assert test that each command's frontmatter description equals its `extension.yml` entry.

### IL5 (upstream): mechanical taste-gate boxes become `self_check.py` checks

- **title**: `self_check.py` grows the nine mechanical checks and the `lint-skin` rules; §9 shrinks to the judgement boxes
- **what**: Add to `scripts/self_check.py`: accent token used on at most 2 elements; legend group below the lowest node; `viewBox` height covers the legend and `min-width` equals the viewBox width; no `writing-mode`; no `box-shadow`; `rx` at most 10; rect x, y, width, height on the 4px grid (with the documented exceptions from `layout-budget.md`); font role per element class; plus the pure-black, external-asset and `<script>` checks already in `lint-skin.py`. Add an orthogonality check (every path segment H, V or a quarter arc) to `verify-geometry.py`. Then the taste gate keeps about 12 judgement boxes (type fit, remove test, signal) and one line "run self_check".
- **effort**: M
- **tok**: [0.03, 0.06] (the 3.6 KB checklist shrinks by about 2.5 KB; fewer fix-and-reread loops on failed geometry, which today surface only when the user looks)
- **time**: [0.05, 0.10] (one script run replaces a visual pass over the file)
- **obs**: improved (failures become one machine-readable line per rule; `accept_plan.py` and `pr.generate` get the stricter check for free)
- **policy**: none
- **pros**: Deterministic; the checks already exist in `lint-skin.py` and only need to be shared; the 44 test files in `tests/` give fixtures.
- **cons**: Grid and font-role checks need an allowlist for the technical-color family and the legacy examples (`lint-skin.py` keeps a baseline for them, `lint-skin-baseline.txt`); false positives would cost more than the prose they replace, so ship behind `--strict` first.
- **files**: sanduq-skills `scripts/self_check.py`, `scripts/verify-geometry.py`, `scripts/lint-skin.py` (shared module), `SKILL.md` §9, `tests/test_self_check.py`; sanduq synced copies and `extensions/illustrate/tests/test_self_check.py`.
- **tests**: new fixtures per rule (pass and fail) in upstream `tests/`; sanduq `tests/test_self_check.py` after sync; scope `tests/test_plan.py` still passes (`accept_plan.py` calls `self_check.py`).

### IL6 (sanduq, opt-in): a post-write hook runs the three checks

- **title**: `PostToolUse` hook on written diagram HTML runs `self_check`, `verify-geometry` and `illustration_theme validate`
- **what**: Add `extensions/illustrate/hooks/hooks.json` (same shape on both hosts) matching Write or Edit of `*.html` whose content has `<svg`, running the three scripts from `.specify/extensions/illustrate/skill/scripts/` and returning the first failure as the hook message. The installer registers it only when `illustrate.hooks.self_check: true` is set (default false). The prose lines that ask the agent to run the scripts (`SKILL.md:335-336`, `commands/speckit.illustrate.generate.md:40`, `commands/speckit.illustrate.import.md:37-38`) stay until IL1 trims them upstream.
- **effort**: S
- **tok**: [0.01, 0.03] (removes the forgotten-check re-draw: when the agent skips `self_check`, the user reports a broken figure and the whole diagram is regenerated; no measured frequency, so the range is a guess from one such loop in ten runs)
- **time**: [0, 0.05]
- **obs**: improved (every written diagram leaves a check result in the transcript)
- **policy**: `illustrate.hooks.self_check`, default false
- **pros**: Enforces what six prose sites repeat; the scope route already does this in `accept_plan.py`, so the behaviour is proven.
- **cons**: Hook runs on every HTML write in the project (filter by `<svg` and a path prefix); Codex project hooks need per-hash approval in `/hooks`; a plugin with hooks cannot enter the Codex public directory, so this stays a sanduq-side hook, not an upstream one.
- **files**: `extensions/illustrate/hooks/hooks.json` (new), `extensions/illustrate/extension.yml` (hooks entry), the installer that writes host hook files (shared with workflow's E4 hook, `extensions/scripts/`), `extensions/illustrate/README.md`.
- **tests**: a hook test that feeds a failing fixture from `tests/fixtures` and asserts exit 2 with the script's first line; `extensions/scripts/tests/test_validate_skills.py` unchanged.

### IL7 (upstream): split the ten oversize type references by variant

- **title**: Variant files so a plain line chart reads 8 KB, not 43 KB
- **what**: Split `type-line.md` (43,288) into `type-line.md` plus `type-line-slopegraph.md`, `-ridgeline.md`, `-streamgraph.md`, `-bump.md`; `type-scatter.md` (20,266) into scatter, bubble, beeswarm; `type-bar.md` (13,736) out of dumbbell; `type-treemap.md` (18,501) out of marimekko. Leave the data-platform family (`type-process`, `type-it-state`, `type-high-level`, `type-medallion`, `type-dp-*`) as it is unless their examples section can move to the assets gallery. The type index gets one line per variant.
- **effort**: S to M (text moves, link updates, example cross-references)
- **tok**: [0.02, 0.25] per diagram of an affected type only (a line chart: 43 KB to about 8 KB, saving 35 KB of 52 to 86 KB; a slopegraph saves nothing); averaged over the 44 types about [0.02, 0.04]
- **time**: [0.01, 0.06]
- **obs**: unchanged
- **policy**: none
- **pros**: The largest single-file saving in the skill after IL1; keeps each file under the 500-line rule.
- **cons**: More files to keep linked; verifiers (`verify-slopegraph.py`, `verify-ridgeline.py`, `verify-streamgraph.py`, `verify-bump.py`, `verify-bubble.py`, `verify-beeswarm.py`) reference the reference names in docstrings only.
- **files**: sanduq-skills `references/type-line.md`, `type-scatter.md`, `type-bar.md`, `type-treemap.md` plus the new variant files, `SKILL.md` type index; sanduq synced copies.
- **tests**: upstream link-resolution test; `benchmark_instructions.py` AFTER (skill `references_bytes` unchanged in total, per-type reads smaller).

## Not proposed

- Trimming `assets/` (8.7 MB, 281 files, 303 in the lock): examples are opened one at a time by name, so they cost nothing until used; the only waste is `index.html` (40,811) if an agent opens the gallery, which `export` already refuses.
- Deduplicating `extensions/illustrate/tests` against upstream `tests/`: CI minutes, not agent tokens.
