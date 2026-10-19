# Round 3 review: assure and user-manual (stream R3)

This is a read-only review of `D:\Projects\Personal\sanduq-round3` at `bd4a361` (assure 2.4.0, user-manual
1.6.0, vendored dev-tools-v1.2.0 at `f260c7b`). I measured byte counts as LF bytes (`tr -d '\r' | wc -c`).
Line references are `path:line`. I ran checks marked "ran" in a scratch directory. The only commands I
ran inside the tree were `assure_scan.py --check`, `vendor.py check` (clean) and both unittest suites
(assure 2.4 s, user-manual 9.8 s, both OK).

## Summary

1. Round 2 did cut the work, but by less than its headline numbers. Per-run instruction bytes for Assure Analyze fell from 16,342 to 10,382 (-36%), and for Document from 16,951 to 12,191 (-28%). The benchmark reports -71.5% and -64.9%, but most of that comes from no longer counting a conditional 34,739-byte Illustrate `SKILL.md`, which has since shrunk to 11,730 bytes anyway.
2. The new Illustrate wording makes the stages that generate diagrams (Assure Document, User Manual Update) skip Illustrate's procedure. That procedure covers the theme gate (§0) plus theme apply, validation, geometry checks and `self_check --strict` (§10 steps 6 to 7). The diagrams come out unthemed and unchecked. This is a correctness regression, not a byte one.
3. `audit_qa.py` (new in round 2) rejects correct manuals. It flags redacted placeholders (`<redacted>`, `${VAR}`, `example-…`), which `audit_manual.py` deliberately allows. It also reports percent-encoded and root-relative links as unresolved. The command then says "Fix every finding" (ran: 3 of 3 placeholders and 2 of 2 valid links flagged).
4. User Manual Update grew from 3,487 to 3,921 bytes (+12%; per run 5,871 to 6,305, +7%), but its script calls fell from up to 8 to 4 or 5. It also sends a `current: true` status down the full-reread branch, and in evidence mode it fingerprints the whole manual twice.
5. The two extensions keep three exclude lists, two freshness CLIs that have drifted (`--summary` counts exist in user-manual only), two narrow YAML readers and a gate heuristic that turns the gate on for `false  # set to true`. The extension's `test_build_manual.py` does not test `--all`, which every build path now depends on.

## What round 2 changed, measured as an agent runs it

| Command | Round-2 baseline (instruction bytes) | Now | Tool calls per first run (now) | Before |
|---|---:|---:|---|---|
| `assure.analyze` | 16,342 | 10,382 (5,909 + SKILL 1,974 + analysis.md 2,499) | 2 reads + deps 1 + artifacts 4 to 10 + scan 1 + 1 to 3 edits + record 1 = 10 to 18 | the same plus 10 to 30 calls for the hand scan |
| `assure.document` | 16,951 | 12,191 (9,458 + 1,974 + 759) | 2 reads + deps + status + 9+ artifacts (k changed on a rerun) + scan + audit + record, plus capture runs | hand scan, 5 hand checks |
| `assure.init` | 3,109 | 3,457 (+11%) | 1 read + 1 script | same |
| `user-manual.analyze` | 5,836 | 5,701 (2,588 + 2,384 + 729) | 2 reads, manual.yml, impact 0 or 1, deps 0 or 1 | same |
| `user-manual.update` | 5,871 | 6,305 (+7%) | status 1 + impact 0 or 1 + audit 1 + build 1 + record 1 = 4 to 5 script calls | audit 1 + up to 6 builds + record 1 = up to 8 |
| `user-manual.release` | 5,531 | 5,821 (+5%) | audit 1 + build 1 | audit 1 + up to 6 builds |

- AS1 (`assure_scan.py`) works. It runs once in 0.5 s on this repository. In `--check` mode it prints 3,319 bytes, and 2,347 of those (71%) are the memory block, which repeats the summary rows printed just above it (`assure_scan.py:211-214`). Analyze needs only the rows.
- AS2: the type lists, the duplicated `record` lines and `--phase` are gone (verified by grep). The four dependency blocks remain at 720, 714, 624 and 793 bytes (`assure analyze.md:30-41`, `document.md:33-44`, `user-manual analyze.md:32-38`, `update.md:41-49`). That is 2,851 bytes in total, down from 6,913.
- AS3, AS6, UM2, UM4 and AS5 are wired as designed. The `--all` build is one call in `update.md:53`, `release.md:27`, `user-manual-preview.yml:39` and `user-manual-release.yml:38`. The catalog descriptions grew by 311 characters across the 7 commands (279 to 427, and 369 to 532), which is the intended catalog form.
- AS4 and UM3 work in Assure Document (`document.md:51-60`). In Update, step 2 handles only `stale-input-or-output`; `current` falls into "otherwise … read the full set" (`update.md:23-25`). `manual_impact.py` reruns `manual_state.py status` itself (`manual_impact.py:81-86`), right after Update step 2 has already run it. Each run walks every file under `User-Manual/` (`manual_state.py:130`) plus `git diff`.

## Lens 1: model work a script does or could do

- Repeat analysis. Both `after_tasks` and `before_implement` run `speckit.assure.analyze` (`assure/extension.yml:38-46`), so an unmanaged integrated project analyzes twice back to back. The second run rereads every artifact (`analyze.md:45-47`) even though `assure_state.py status --kind analyze` can already say nothing changed. Analyze never calls `status`.
- Update's no-change rerun does a full reread (D6, above).
- Impact scope. Both User Manual commands ask the model to read `lifecycle.impact_scope` and decide whether to run `manual_impact.py` (`analyze.md:25-27`, `update.md:26-28`). The script already reads the key and handles `all` (`manual_impact.py:50-57`).
- User Manual Init step 2 inventories projects by hand, excluding vendor folders (`init.md:21-22`). That is the walk `assure_scan.py` does, but the script ships only in the assure package. It is noted here without an option, because user-manual must not depend on assure. R6 could move the scanner to `extensions/scripts/shared/`.

## Lens 2: repeated text and duplicated code

- Exclude list, three copies: `assure_scan.py:23-24`, `assure_init.py:54-55` (with a comment saying it mirrors the first) and `assure-config.template.yml:11-24`. `config_text` (`assure_init.py:58-73`) also restates the whole template file.
- The freshness CLIs `assure_state.py` (77 lines) and `manual_state.py` (51 lines) share the import fallback, argparse, `--summary` and `--json` handling and the exit code nearly line for line. They have drifted: only `manual_state.py:142-143` prints `changed_inputs=N changed_outputs=M`. Round 2 AS4 promised the counts for both, and the S2 note left the assure suffix to S1, which did not add it.
- YAML readers: `assure_scan.read_config` (`assure_scan.py:44-66`, strips comments with `split(' #')`), `deps.read_yaml` (`deps.py:241`, quote-aware, raises on unknown layout, already shipped beside `assure_state.py`) and PyYAML in `assure_init.py:11`, `manual_impact.py:20` and the vendored scripts. `gate_on` tries PyYAML, then `read_config`, then a substring scan (`assure_state.py:15-30`).
- `manual_impact.front_matter` (`manual_impact.py:27-33`) re-implements `audit_manual.front_matter` (`audit_manual.py:24`), which is vendored. This is acceptable because importing a vendored module couples to upstream internals. Noted only.
- `audit_qa.SECRET` is "copied byte for byte" (`audit_qa.py:20`), but the placeholder allowlist that gives the regex its meaning (`audit_manual.py:97-98`) was not copied (D2).
- `analysis.md:9-10` repeats the gate sentence of `analyze.md:27-28`, which is about 150 bytes. Too small for its own option.

## Lens 3: large rereads

- Diagram runs read `type-index.md` (6,530 bytes) plus one `type-*.md` (1,079 to 6,780). The index itself says "The drawing procedure is in ../SKILL.md" (`type-index.md:7-8`), and `SKILL.md` is now 11,730 bytes, so the IL3 shortcut saves no more than the procedure costs (see D1).
- `assure_scan.py --check` prints the memory block twice over (Lens 1 above, 2,347 bytes).
- `speckit.assure.init` loads the 1,974-byte skill (`init.md:23`), whose rules cover analysis and documentation only (`SKILL.ext.md:13-32`). That is 57% of the init run's 3,457 bytes.

## Lens 4: descriptions

All seven command descriptions pass the catalog checks (benchmark `round-3-before-instructions.md:42-54`, "ok"). The frontmatter and `extension.yml` agree, and `test_descriptions.py` enforces it. The two internal `SKILL.ext.md` descriptions are imperative ("Analyze …", "Create …"), but no host registers them, so this has no routing effect. No action.

## Lens 5: rules a hook or script could enforce

- The redaction rule now has a script, but the script contradicts the rule's own guidance on placeholders (D2).
- "Confirm production builds do not ship or link development-only QA docs" (`document.md:163-164`) is still eyeball work. It is noted only, because a check needs the project's build output, which Assure does not know.
- The rule "do not record while the manual is a draft" (`document.md:175-177`) stays model judgement. The runtime receipt rules cover managed mode, as round 2 found.

## Lens 6: host divergence

- Commands still name hosts' nonexistent forms `Assure.Analyze` and `Assure.Document` (`assure init.md:25-26`) and `UserManual.Init` (`user-manual analyze.md:23`). Neither Claude Code (`/speckit-assure-analyze`) nor Codex (`$speckit-assure-analyze`) registers those names. The host-neutral form used elsewhere is `speckit.assure.analyze`.
- `document.md:140-141` says to export with "the installed `scripts/export_diagram.py` and the `references/export.md` contract". In an Assure command, `scripts/` reads as Assure's own folder. The file is at `.specify/extensions/illustrate/skill/scripts/export_diagram.py`.
- Every command calls `python` literally (cross-cutting, R1/R6). The packaged helpers are identical on both hosts (`package.py:38-51`).

## Vendored pieces and shared copies

- `vendor.py check` is clean. dev-tools-v1.2.0, illustration-tools-v3.5.0 and agent-tools-v1.5.0 all pin `f260c7b` (confirmed with `git rev-parse` in sanduq-skills).
- `tests/test_build_manual.py` is hand-maintained in both repositories (`ADAPTER.md:44`). It now differs by 66 lines: the upstream copy has `AllEditionsTests` and the asset-leak test, and the extension copy has neither. Round 2 UM2 said "both must gain the case", and only upstream did.
- Each packaged extension carries Workflow's `sanduq_ci.py` (14,453 bytes) and the shared `deps.py` (26,278 bytes) (`package.py:44-51`). Assure uses `sanduq_ci` only for `render` and `load_ci` in init. The upstream portable subset is 8,818 bytes. These are R6's to size; no option here.

## Defects

| # | Defect | Effect | Where |
|---|---|---|---|
| D1 | The diagram-generating stages are told to read `type-index.md` and the type file, and `SKILL.md` "only when the diagram is created outside that recipe" | The theme gate (§0) and theme apply, validate, `verify-geometry` and `self_check --strict` (§10 steps 6-7) are skipped, so Assure and User Manual diagrams ship unthemed and unchecked | `assure document.md:121-125`; `user-manual update.md:46-48`; vs `illustrate/skill/SKILL.md:16-33,58-62`, `type-index.md:7-8` |
| D2 | `audit_qa.py` flags redacted placeholders | `password: <redacted>`, `api_key=${API_KEY_VALUE}` and `access_token: example-token-value` all fail (ran). The command says "Fix every finding", so the agent deletes correct redacted samples or cannot finish | `audit_qa.py:20,78-80` vs `audit_manual.py:96-99` |
| D3 | `audit_qa.py` resolves links naively | `../../assets/x/a%20b.png` (existing file) and `/qa/assets/x/c.png` (root-relative in a web `public/` dir) are both reported unresolved (ran) | `audit_qa.py:70-75` |
| D4 | `gate_on` substring fallback runs even after a successful parse to `false` | `require_document_before_pr: false  # set to true to require` turns the gate on. Ran: status ran and exited 1 instead of `skipped gate=off` | `assure_state.py:26-30` |
| D5 | `Last scanned: <today>` makes the memory block differ every day, so Document rewrites `.github/memory/project-memory.md` on any later-day rerun | That file is a freshness input of both document and manual kinds (the diff set, `sanduq_freshness.py:68-88`, does not exclude it). A `qa_document` rerun after `manual_update` (stage order `workflow.py:44-46`) stales the manual state and the "Verify User Manual freshness" CI step fails. This is inferred from the code and was not executed | `assure_scan.py:157,207-219` |
| D6 | Update's status branch handles only `stale-input-or-output` | A `current` rerun takes the "otherwise" branch and rereads specs, plan, tasks, contracts, diff, tests and the whole manual | `user-manual update.md:23-25` |
| D7 | `assure_state.py --summary` omits the changed counts | CI and preflight logs for Assure still show only `reason=stale-input-or-output`, while user-manual shows counts | `assure_state.py:64-70` vs `manual_state.py:142-143` |
| D8 | The extension's `test_build_manual.py` has no `--all` test | `--all` is the only build path that Update, Release and both CI templates use, and its extension copy is untested in this repository | `extensions/user-manual/tests/test_build_manual.py` (classes at :14, :93, :162) vs upstream `AllEditionsTests` |
| D9 | Legacy names `Assure.Analyze`, `Assure.Document` and `UserManual.Init` | The agent is told to run commands neither host registers | `assure init.md:25-26`; `user-manual analyze.md:23` |
| D10 | Illustrate export path written relative to the wrong extension | The agent looks in `.specify/extensions/assure/scripts/` for `export_diagram.py` | `assure document.md:140-141` |

## Options

Every option keeps observability, evidence gates, receipts and GitHub decisions intact, and adds no policy key.
"Upstream" marks a sanduq-skills change; none of the options below needs one.

### AU1. Diagram stages follow the Illustrate procedure; one short dependency block

- what: In `speckit.assure.document.md` step 5.3 and `speckit.user-manual.update.md` step 6, replace the "read `SKILL.md` only when…" clause with "follow `.specify/extensions/illustrate/skill/SKILL.md` §0 and §10 (the theme gate, then type index, type reference, theme, verify)". Keep the type-index-only wording in the two Analyze commands, which only choose a type for a task (D1). Give the export script its full installed path (D10). Cut each of the four dependency blocks to two sentences: run `deps.py ensure illustrate`; on non-zero, report its line verbatim, skip diagrams, and follow the recovery the line prints. `deps.py` already prints the recipe and the `--approve` form (`deps.py:426-471`).
- effort: S
- tok: [-0.15, 0.02]. A diagram run of Document or Update adds the 11,730-byte `SKILL.md` (about 0.15 of a 75 KB diagram run). Every run removes about 1.4 KB of the 2,851 bytes of dependency prose (0.01 to 0.02 of a 50 KB run). The negative bound is the price of correctness.
- time: [-0.03, 0.05]. One more read on diagram runs. Diagrams that fail review for theme or contrast no longer need a redraw.
- obs: improved. `illustration_theme.py validate` and `self_check.py --strict` output appear in the stage transcript.
- policy: none.
- pros: fixes a silent quality regression introduced by IL3; leaves Analyze's cheap path alone; removes the last restatement of `deps.py`.
- cons: diagram runs get larger; the benchmark shows a per-run increase for Document and Update when it counts linked Illustrate files.
- files: `extensions/assure/commands/speckit.assure.analyze.md`, `speckit.assure.document.md`, `extensions/user-manual/commands/speckit.user-manual.analyze.md`, `speckit.user-manual.update.md`.
- tests: `validate_skills.py`, `check_docs.py`, `benchmark_instructions.py` before and after; a grep assertion in `extensions/assure/tests/test_descriptions.py` (or a new small test) that no command says "read `SKILL.md` only when".

### AU2. `audit_qa.py` agrees with the redaction rule and with real links

- what: In `extensions/assure/scripts/audit_qa.py`, skip SECRET matches whose value contains `redacted`, `example`, `placeholder`, `<`, `&lt;` or `${`, the same allowlist as `audit_manual.py:97-98` plus the HTML-escaped `<` (D2). Percent-decode link paths with `urllib.parse.unquote` (D3). Resolve a root-relative `/x` against the nearest ancestor named `public` or `static`, falling back to the repository root, which is where Document writes web manuals (`document.md:110-111`). Keep the exit code, output format and `--feature` mode.
- effort: S
- tok: [0.02, 0.10] of a Document run. Each false finding costs a fix-and-rerun loop over 10 to 40 KB of generated HTML.
- time: [0.02, 0.08].
- obs: improved. Findings become real findings; secret detection is unchanged for actual values.
- policy: none.
- pros: makes the round-2 script trustworthy; four small edits.
- cons: the allowlist could mask a real secret that contains the word `example`. The user-manual audit already accepts that trade-off.
- files: `extensions/assure/scripts/audit_qa.py`, `extensions/assure/CHANGELOG.md`.
- tests: `extensions/assure/tests/test_audit_qa.py`: placeholders pass, a real token still fails, `%20` and `/qa/...` links resolve, and a missing root-relative target still fails.

### AU3. Skip unchanged reruns

- what: Assure Analyze gains a step 1a: `assure_state.py status --kind analyze --feature <f> --summary`. On `ok`, with no `--report-only` and no user request for a refresh, report "analysis current" with the line and stop. This removes the second full analysis when the `after_tasks` and `before_implement` hooks both fire (`assure/extension.yml:38-46`). Update step 2 names all three outcomes, as Document already does (`document.md:55-60`): `current` refreshes only what the user asked for (D6). `manual_impact.py` gains `--status-json <file|->` so Update can pass the status it already has instead of computing it twice. Its output also carries `current` and `changed_outputs`, so in evidence mode steps 2 and 3 become one call (`manual_impact.py:81-86`). The commands then always run `manual_impact.py`, which reads `impact_scope` itself, and stop telling the model to look up the key.
- effort: S
- tok: [0.6, 0.9] of a repeated Analyze or a no-change Update rerun, and 0 on a first run. Over one feature's Assure work (two Analyze runs plus a Document run), [0.2, 0.3].
- time: [0.2, 0.3] of the same feature's Assure work; one fingerprint pass instead of two per evidence-mode Update.
- obs: unchanged. The status line is printed and reported, and no receipt or `record` call changes. A current state is exactly what `record` wrote.
- policy: none. Managed mode runs `qa_analyze` once, so it is unaffected apart from the extra status call.
- pros: the largest remaining per-feature saving; reuses scripts that already exist.
- cons: one more script call on every first Analyze run (about 0.3 s, `git diff` excluded for the analyze kind, `sanduq_freshness.py:71-78`).
- files: `extensions/assure/commands/speckit.assure.analyze.md`, `extensions/user-manual/commands/speckit.user-manual.analyze.md`, `speckit.user-manual.update.md`, `extensions/user-manual/scripts/manual_impact.py`.
- tests: `extensions/user-manual/tests/test_manual_impact.py` (`--status-json` input; the output carries `current`; no second status subprocess); `extensions/workflow/tests/test_assure_state.py` (analyze status is current right after record).

### AU4. One freshness CLI for both extensions

- what: Move the shared CLI body of `assure_state.py` and `manual_state.py` into `sanduq_freshness.cli(argv, kind_choices, state_path, default_outputs)`. That body is the import fallback, argparse, `--summary` and `--json`, the one-line reason, the changed counts and the exit code. Each script keeps only its own parts: the state path, `--kind` or the fixed `manual`, the default output set, and Assure's `--gate`. This fixes D7 by construction. The CLI, output and exit codes stay byte-compatible apart from the added counts in Assure's `--summary`.
- effort: S
- tok: [0, 0]. time: [0, 0].
- obs: improved. Assure's stale line names how many inputs and outputs changed, as user-manual's does.
- policy: none.
- pros: removes about 40 duplicated lines; one place to change the summary format; the portable `manual_state.py` keeps its own copy (`ADAPTER.md:38`), so nothing goes upstream.
- cons: touches a shared helper that ships in two packages, so both bump; R6 must not move the helper in the same round.
- files: `extensions/scripts/shared/sanduq_freshness.py`, `extensions/assure/scripts/assure_state.py`, `extensions/user-manual/scripts/manual_state.py`, both CHANGELOGs.
- tests: `extensions/workflow/tests/test_freshness.py`, `test_assure_state.py`, `extensions/assure/tests/test_assure_state_gate.py`, `extensions/user-manual/tests/test_manual_state.py` (unchanged expectations, plus Assure's `--summary` counts).

### AU5. Assure scripts: one exclude list, a correct gate, a stable memory block

- what: `assure_init.py` imports `DEFAULT_EXCLUDE` from `assure_scan.py` (same directory) and writes the config by substituting the mode into `assure-config.template.yml`, so the template stays the only literal copy. `gate_on` falls back to the substring scan only when both readers raised, not after a clean `false` (D4). `assure_scan.py` compares the new block with the old one, ignoring the `Last scanned` line, and keeps the old date when nothing else changed (D5). `--check` prints the summary rows and the `would write` line, and adds the block only with `--show-block` (saves 2,347 bytes of a 3,319-byte output here).
- effort: S
- tok: [0.02, 0.05] of an Analyze run (the duplicated block).
- time: [0, 0.02].
- obs: unchanged. The block is still written and still available on demand; the gate prints the same lines.
- policy: none. The `scan.exclude` default is unchanged.
- pros: closes a false gate and a cross-extension stale-state trigger; removes two literal copies of the exclude list.
- cons: init reads a packaged template at runtime, so the template must stay in the package (`package.py` ships it today).
- files: `extensions/assure/scripts/assure_init.py`, `assure_state.py`, `assure_scan.py`, `extensions/assure/commands/speckit.assure.analyze.md` (one word), `extensions/assure/CHANGELOG.md`.
- tests: `extensions/assure/tests/test_assure_state_gate.py` (a `false` value with a trailing "true" comment is off; an unparseable file naming true is on); `test_assure_scan.py` (a rerun on a different `today` with no project change writes nothing; `--check` omits the block); `extensions/workflow/tests/test_assure_init.py` (written config equals the template with the mode substituted).

### AU6. Vendor `test_build_manual.py` instead of hand-copying it

- what: Add `user-manual/tests/test_build_manual.py` to the `user-manual` map in `vendor.lock.json` as an explicit file mapping. `vendor.py:65` skips `tests` folders only inside directory maps; confirm this during implementation, and if it blocks a file map, allow explicit test files. Replace the hand-maintained copy, which brings in upstream's `AllEditionsTests` and the asset-leak test (D8). Remove the `ADAPTER.md:44` row and move the file to section 1.
- effort: S
- tok: [0, 0]. time: [0, 0] for the agent; adds about 1 s to the user-manual suite.
- obs: improved. The build path every command and CI template uses is tested in the repository that ships it.
- policy: none.
- pros: ends a drift that round 2 already tripped over; no upstream change.
- cons: the extension can no longer edit that test locally; changes go upstream first.
- files: `vendor.lock.json`, `extensions/user-manual/tests/test_build_manual.py`, `extensions/user-manual/ADAPTER.md`, possibly `extensions/scripts/vendor.py`.
- tests: `python extensions/scripts/vendor.py check`; `python -m unittest discover -s extensions/user-manual/tests`; `extensions/scripts/tests` vendoring tests if the map shape changes.

### AU7. Command hygiene: host-neutral names, a lighter init

- what: Replace `Assure.Analyze` and `Assure.Document` (`assure init.md:25-26`) and `UserManual.Init` (`user-manual analyze.md:23`) with `speckit.assure.analyze`, `speckit.assure.document` and `speckit.user-manual.init` (D9). Drop step 1 "Load SKILL.md" from `speckit.assure.init.md`; the command is self-contained, and the skill's rules concern analysis and documentation. Delete the gate sentence in `references/analysis.md:9-10` that the command already states.
- effort: S
- tok: [0.45, 0.57] of an init run (1,974 of 3,457 bytes); 0 to 0.01 elsewhere.
- time: [0, 0.01].
- obs: unchanged.
- policy: none.
- pros: a trivial edit; fixes wrong names on both hosts.
- cons: init is a one-time command, so the absolute saving is small.
- files: `extensions/assure/commands/speckit.assure.init.md`, `extensions/assure/skills/assure/references/analysis.md`, `extensions/user-manual/commands/speckit.user-manual.analyze.md`.
- tests: `validate_skills.py`, `check_docs.py`, `benchmark_instructions.py`.

## Notes for the orchestrator

- AU1 deliberately raises the diagram-run cost. Count it as a fix, not a saving, and pair it with R5's view of Illustrate's own `SKILL.md` size.
- AU3 and AU4 both touch `manual_state.py` behaviour; implement them in one stream. AU4 and R6 both touch `sanduq_freshness.py`.
- R6 owns the cross-cutting items left without an option: the scanner shared with user-manual init, the packaged sizes of `deps.py` and `sanduq_ci.py`, and the literal `python`.
