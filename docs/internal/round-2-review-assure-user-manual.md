# Round 2 review: assure and user-manual (stream R1)

Read-only review on worktree `D:\Projects\Personal\sanduq-round2` at the `feat/round-2` base. Every
number below was measured with `wc`, `grep`, `diff` or `sed -n a,bp | wc -c` on that tree; every
file reference is `path:line`. Options follow the plan's record and are the only output.

## Summary

1. Assure's two big commands (14,031 and 14,620 bytes) carry about 13 KB of prose that is either a copy of the other command, a copy of a reference already loaded in step 0, a restatement of what `deps.py` prints, or lifecycle-phase text the managed dispatcher ignores.
2. The biggest model work is the deep workspace scan and `.github/memory/project-memory.md` rewrite that both Assure commands perform by hand (3,518 and 2,606 bytes of marker rules); it is pure file-glob detection and belongs in a script.
3. Freshness is already scripted (`assure_state.py`, `manual_state.py` on one shared helper) but `status` answers only `stale-input-or-output`, so Document and Update reread every artifact instead of the changed ones.
4. All seven catalog descriptions open with an imperative verb and name no "when" or trigger phrase; `extension.yml` carries a second, different description per command, and six `agents/openai.yaml` files ship for skills no host registers.
5. User-manual is already lean (commands 1.3 to 3.5 KB, references 318 to 1,913 bytes); its wins are two 1 KB Illustrate blocks, one build call instead of six, and an evidence-based module impact list. Its references, scripts and CI templates are vendored, so three of its options are upstream.

## Per-run instruction bytes (baseline for the estimates)

| Command | Command file | Always-loaded skill and reference | Total | Loaded conditionally |
|---|---:|---:|---:|---|
| `speckit.assure.analyze` | 14,031 | SKILL 1,673 + analysis.md 638 | 16,342 | Illustrate SKILL.md 34,739 when a diagram task is weighed |
| `speckit.assure.document` | 14,620 | SKILL 1,673 + documentation.md 658 | 16,951 | Illustrate SKILL.md 34,739 + one `type-*.md` |
| `speckit.assure.init` | 1,436 | SKILL 1,673 | 3,109 | |
| `speckit.user-manual.analyze` | 2,723 | SKILL 2,384 + incremental-update.md 729 | 5,836 | api-docs 1,195, ui-screenshots 1,128, release-docs 946 + their references |
| `speckit.user-manual.update` | 3,487 | SKILL 2,384 | 5,871 | routed references 811 to 1,913 each |
| `speckit.user-manual.init` | 2,875 | SKILL 2,384 + discovery.md 811 | 6,070 | preview-publishing 1,423 + 1,018 |
| `speckit.user-manual.release` | 1,292 | SKILL 2,384 + release-docs 946 + 318 + 591 | 5,531 | |

Managed runs add the 279-byte stage reference inside the claim (`stage-qa_analyze.md` is 279 bytes,
`stage-qa_document.md` 185, `stage-manual_analyze.md` 283, `stage-manual_update.md` 208). The
cost model for `tok` below: instruction bytes above plus about 35 KB of feature artifacts every
command reads (spec, plan, tasks, contracts) plus tool output; about 55 KB per Assure run without a
diagram, 90 KB with the Illustrate skill, 45 to 50 KB per user-manual run. Tokens are bytes / 4.

## Lens 1: model told to do work a script already does or could do

- Workspace scan and project memory. `speckit.assure.analyze.md:98-150` (3,518 bytes) and
  `speckit.assure.document.md:107-154` (2,606 bytes) tell the model to walk the repository, exclude
  eleven vendor folders, test about forty marker files and dependency names, classify projects into
  five roles and write a five-section Markdown file with a `Last scanned` date. Every rule is a glob or
  a `package.json` key lookup. No script does it today: `extensions/assure/scripts/` holds only
  `assure_state.py` and `assure_init.py`; the memory extension states this file "is not the product
  memory" (`extensions/memory/commands/impact.md:38`), so nothing else owns it.
- Generated-manual validation. `speckit.assure.document.md:255-261` asks the model to smoke-test the
  HTML, check every `<img>` for `alt` and caption, check assets exist and index links resolve. The
  user-manual side already has this as code for Markdown (`audit_manual.py:20-21` SECRET and LINK
  regexes, `:96-105` the checks); Assure has no equivalent and the model rereads its own output.
- Freshness delta. `sanduq_freshness.py:118-121` compares the saved input fingerprints to the current
  ones and returns only `{'current': False, 'reason': 'stale-input-or-output'}`. Both
  `speckit.assure.document.md:84-94` ("Read all available feature artifacts", nine items including
  the git diff) and `speckit.user-manual.update.md:21-22` (nine inputs) therefore reread everything on
  a rerun even though the helper already knows which paths changed.
- Build loop. `speckit.user-manual.update.md:49` and `release.md:26-27` say "run the audit and build
  scripts for all configured editions"; that is up to six `build_manual.py` invocations (three
  audiences x two languages) that the model issues one by one. The CI templates spell the same loop in
  bash twice (`user-manual-preview.yml:34-41`, `user-manual-release.yml:37-44`). `build_manual.py`
  takes one `--audience` and one `--language` (`build_manual.py:223-224`).
- Dependency check prose. `deps.py` prints exactly one line (`deps.py:24`), yet the commands explain
  its policy handling at length: `speckit.assure.analyze.md:45-73` 1,835 bytes,
  `speckit.assure.document.md:45-73` 1,804, `speckit.user-manual.analyze.md:30-41` 1,026,
  `speckit.user-manual.update.md:35-45` 1,042, `assure/README.md:41-48` 641,
  `user-manual/README.md:45-51` 565: 6,913 bytes in six places describing one script.
- Task patching. `speckit.assure.analyze.md:199-226` describes an idempotent marker block, continuing
  numbering from the highest `T###`, section placement per story. The workflow already parses task
  lines (`extensions/workflow/scripts/delegation.py:64,119` `TASK_LINE`, `task_lines`) and the runtime
  records `tasks.md` as the stage's only permitted side effect (`workflow.py:84-85`). The authoring is
  model work; the insertion and numbering are not.

## Lens 2: repeated text

Inside Assure (bytes measured with `sed -n | wc -c`, equality with `diff`):

- Step 0a is a near copy: 1,835 vs 1,804 bytes; `diff` shows only lines 19-26 differ (step number
  and "coverage checks" vs "diagram generation").
- Step 1 "Resolve the active feature" `analyze.md:76-81` and `document.md:76-81`: byte-identical.
- Workspace scan 3,518 vs 2,606 bytes; the memory-file section list 1,037 (`analyze.md:132-145`) vs
  376 (`document.md:142-150`).
- Illustrate type enumerations: 744 bytes (`analyze.md:172-179`) and 1,397 bytes
  (`document.md:200-216`) list 27 types by name, and the command then loads the Illustrate skill's own
  selection guide at the same point (`document.md:201-203`). The installed skill ships 44 `type-*.md`
  references (`ls extensions/illustrate/skill/references | grep -c ^type-` = 44); `db-schema`,
  `deployment`, `journey`, `uml-class`, `sankey`, `kanban` and others are absent from the list.
- The freshness `record` line appears twice per command: `references/analysis.md:13` and
  `analyze.md:244` are the same command; `references/documentation.md:12` and `document.md:269`
  likewise, and step 0 loads the reference first (`analyze.md:41`, `document.md:41`).
- Redaction: `document.md:251-253`, `SKILL.ext.md:24`, and on the user-manual side
  `skills/user-manual/SKILL.ext.md:31-32`, `api-docs/references/openapi.md:11-12`.
- Lifecycle phase: `analyze.md:11-16` and `document.md:10-15` plus the `--phase` flag
  (`analyze.md:28-29`, `document.md:29`) and the report bullet (`analyze.md:252-253`).

Inside user-manual:

- The Illustrate blocks `analyze.md:30-41` and `update.md:35-45` (1,026 and 1,042 bytes) differ only
  in "adding the task" vs "generating".
- `init.md:27-36` restates the defaults `init_manual.py:52-83` writes into `manual.yml`
  (audiences, visibility, preview security, provider rule).
- `README.md:39-51` restates the SKILL routing table (`SKILL.ext.md:11-22`) and the deps paragraph.

Against the dispatcher and siblings:

- `stage-qa_analyze.md` and `stage-manual_analyze.md` are identical except the title line (`diff`
  output: line 1 only). Both are 279 and 283 bytes, so the cost is nil; noted for the workflow owner.
- `pr/commands/speckit.pr.generate.md:97-113` restates the status, run, recheck loop that the Assure
  init command summarises (`init.md:25-27`) and that `documentation-gates.yml:24-41` encodes in CI.
- `extensions/scripts/shared/deps.py:4-8` records that the 0a block was already consolidated once
  (B9 of the previous round); the surviving prose is the residue of that change.

## Lens 3: stages rereading large inputs they do not need

- `speckit.assure.document.md:84-94`: unconditional read of spec, plan, tasks, quickstart,
  data-model, research, contracts, `docs/<slug>/` and the branch diff; then `:107-154` repeats the full
  workspace scan that `qa_analyze` ran on the same feature minutes earlier (the runtime even lists
  the memory file as `qa_document`'s permitted side effect, `workflow.py:86-88`, because the second
  pass rewrites it).
- Illustrate: the 34,739-byte `SKILL.md` is loaded whole whenever a diagram is weighed
  (`analyze.md:175-177`, `document.md:201-203`), 2.1 to 2.5 times the command that loads it. R3 owns
  the trim; the Assure and user-manual commands should keep loading it late, as they do now.
- `speckit.user-manual.update.md:21-22` reads "existing manual state" and the whole input set on every
  run; `manual_state.py:31` defaults the output set to every file under `User-Manual/` except
  `.state`, `site`, `pdf`, so the helper already fingerprints the whole manual, but the model never
  receives the delta (Lens 1, freshness).
- `speckit.user-manual.analyze.md:19-20` loads `incremental-update.md` for an analysis that adds
  tasks; the reference is 729 bytes, so this is cheap and correct.

## Lens 4: catalog descriptions and hook-only slots

Measured with `sed -n 2p | wc -c` on the command frontmatter (what Spec Kit renders into both host
catalogs, `presets/__init__.py:1052`) and on `extension.yml`:

| Command | Frontmatter chars | Opens with | has when | has trigger | `extension.yml` chars (differs) |
|---|---:|---|---|---|---:|
| assure.init | 107 | "Configure" (imperative) | no | no | 91 (`extension.yml:29`) |
| assure.analyze | 158 | "Analyze" | no | no | 110 (`:32`) |
| assure.document | 86 | "Generate" | no | no | 84 (`:35`) |
| user-manual.init | 125 | "Discover" | no | no | 86 (`:31`) |
| user-manual.analyze | 122 | "Analyze" | no | no | 109 (`:34`) |
| user-manual.update | 112 | "Create" | no | no | 94 (`:37`) |
| user-manual.release | 103 | "Finalize" | no | no | 88 (`:40`) |

All seven are under 1,024 characters (813 total, about 0.1 percent of a 200K window on either
host). None is third person, none states when to use it or a phrase a user would type, and each has
two different descriptions: the frontmatter one reaches the hosts, the `extension.yml` one reaches
`docs/reference/commands.md` (`check_docs.py:172-175` reads `provides.commands`). No command is
hook-only: the `after_tasks`, `before_implement` and `after_implement` hooks (`assure/extension.yml:37-52`,
`user-manual/extension.yml:42-52`) reuse the user-invocable commands, and in managed projects the
runtime flags any enabled copy as `DUPLICATE_STAGE_OWNER` (`workflow.py:1236-1237`).

## Lens 5: rules prose repeats that a hook or script could enforce

- The documentation gate: `documentation-gates.yml:29` decides whether to run the gate with
  `grep -Eq '^  require_document_before_pr: true$'`, an exact two-space-indentation match on YAML,
  then `:30-32` runs `assure_state.py status`, echoes the JSON and parses it again with an inline
  `python -c` to derive an exit code the script already returns (`assure_state.py:47`:
  `return 0 if result['current'] else 1`). The same inline parse is repeated for user-manual at
  `:39-41`. The rule "an old file does not satisfy the gate" is restated in `assure/README.md:38-39`,
  `init.md:40-41`, `SKILL.ext.md:27-28` and `pr.generate.md:103`.
- Redaction (four prose copies, Lens 2) is a regex in `audit_manual.py:20` for Markdown and nothing
  for the generated QA HTML.
- "Do not record successful evidence in `--report-only` mode" (`analyze.md:247`) and "do not record a
  successful state while the manual remains a draft" (`document.md:272-274`) are the only record-time
  rules and depend on model judgement; the runtime's receipt rules already refuse a passed receipt for
  pending work (`receipt-rules.md:11-12`), so in managed mode they are enforced once.
- The Illustrate dependency rule is already a script (`deps.py`); only its explanation is prose.

## Lens 6: Claude Code and Codex divergence

- Six `agents/openai.yaml` files ship with the path-loaded skills (`assure/skills/assure/agents/openai.yaml`
  201 bytes; user-manual `user-manual` 199, `api-docs` 214, `ui-screenshots` 214, `release-docs` 219,
  `preview-publishing` 250; 1,297 bytes). Spec Kit does not register extension-internal skills with
  either host (first report, standards section), no Sanduq script reads the files
  (`grep -rn openai.yaml extensions/scripts extensions/workflow/scripts docs` returns nothing), and
  their `default_prompt` names `$assure`, `$api-docs` and so on, Codex skills that do not exist.
  `ADAPTER.md:44` lists them as extension-owned, so removing them is not an upstream change.
- `speckit.assure.document.md:104` and `:115` tell the agent to run `/speckit-assure-analyze`; on
  Codex the rendered skill is invoked as `$speckit-assure-analyze` (`docs/reference/commands.md:14-15`).
- Every command invokes `python ...` literally (`analyze.md:52,244`, `document.md:52,269`,
  `user-manual/analyze.md:31`, `update.md:36,56`, `init.md:40`), while the runtime picks `python` on
  Windows and `python3` elsewhere (`hosts.py:259-261`). Cross-cutting with workflow; noted, no option.
- Installed paths (`.specify/extensions/<id>/...`), the shared freshness helper and `deps.py` are
  identical on both hosts (`package.py:34-53`); the `hide_hook_skills` post-processing
  (`hosts.py:244-256`) touches only Scope, which is correct since no Assure or user-manual command is
  hook-only.

## Defects

| # | Defect | Effect | Where |
|---|---|---|---|
| D1 | CI gate detects `require_document_before_pr: true` with an indentation-exact `grep` on YAML | A config reformatted by any YAML writer (`assure_init.py:47` itself uses `safe_dump` for `extensions.yml`), quoted value, or a `lifecycle:` block at another depth silently skips the gate | `extensions/assure/assets/github/documentation-gates.yml:29` |
| D2 | Illustrate type lists name 27 types; the installed skill has 44 `type-*.md` references | The agent picks from a stale list and skips types the skill supports (db-schema, deployment, journey, uml-class, sankey, kanban, story-map, treemap, waterfall, fishbone, heatmap, polar, dependency, exploded, wardley, axonometric-plan, architecture-delta) | `speckit.assure.analyze.md:172-179`, `speckit.assure.document.md:203-207` vs `extensions/illustrate/skill/references/` |
| D3 | Claude slash form `/speckit-assure-analyze` in a host-neutral command | A Codex agent is told to run a command that does not exist in its host | `speckit.assure.document.md:104,115` |
| D4 | Two descriptions per command, both imperative, none with when or triggers | Host routing and the generated command reference disagree; the hosts rank these skills on a description that names no situation | `assure/extension.yml:29,32,35` vs `commands/*.md:2`; `user-manual/extension.yml:31,34,37,40` vs `commands/*.md:2` |
| D5 | Six `agents/openai.yaml` files for skills no host registers, with prompts naming nonexistent `$` skills | 1,297 bytes of dead package content; misleading for anyone reading the skill tree | `extensions/assure/skills/assure/agents/openai.yaml`, `extensions/user-manual/skills/*/agents/openai.yaml` |
| D6 | Lifecycle-phase prose and `--phase` flag survive in managed projects where the runtime maps stages to commands and `assure_init.py` leaves hooks alone | About 1 KB read on every run to decide something the dispatcher already decided; the report bullet asks the agent to recommend `after_tasks` inside a managed stage | `speckit.assure.analyze.md:11-16,28-29,252-253`; `speckit.assure.document.md:10-15,29`; `workflow.py:49-52`, `assure_init.py:79-82` |
| D7 | Both Assure commands claim to own the project-memory pass, but the runtime lists `.github/memory/project-memory.md` as a permitted side effect of `qa_document` only | When an earlier receipt depends on that file, a `qa_analyze` rewrite is refused with `UPSTREAM_INPUT_CHANGED_DURING_STAGE` while the same rewrite in `qa_document` is recorded as lineage | `speckit.assure.analyze.md:100-101`, `speckit.assure.document.md:109`; `workflow.py:84-88,3303-3315` |
| D8 | CI reparses the freshness JSON inline to compute an exit code the script already returns | Two extra lines per gate; `--summary` output (one line) cannot be used because the parse expects JSON | `documentation-gates.yml:30-32,39-41`; `assure_state.py:47`, `manual_state.py:46` |

## Candidate options

Observability, evidence gates, receipts and GitHub decisions stay intact in every option. Policy
keys are opt-in with unchanged defaults. "Upstream" marks a change to vendored files
(`vendor.lock.json` `inputs.user-manual.map`): `scripts/audit_manual.py`, `scripts/build_manual.py`,
`assets/scaffold/**`, `user-manual-config.template.yml`, both `assets/github/*.yml`, and every
`skills/*/references/*.md`. Commands, `SKILL.ext.md` files, `extension.yml`, `README.md`,
`init_manual.py`, `manual_state.py` and `agents/openai.yaml` are extension-owned (`ADAPTER.md:33-62`).

### AS1. Script the workspace scan and project memory

- what: Add `extensions/assure/scripts/assure_scan.py` (stdlib only, like `deps.py`) that walks the
  repository with the exclusion list from `analyze.md:103-105`, tests the marker files and
  `package.json` dependency names from `analyze.md:110-126`, classifies each project as web, mobile,
  backend, infrastructure or tooling, and writes or refreshes `.github/memory/project-memory.md` with
  the five sections inside `<!-- assure-scan:start/end -->` markers and a `Last scanned` date. Both
  commands replace steps 2 and 3 with one call plus one sentence: add `planned/spec-only` rows from
  the feature artifacts, which stays model work. The script prints the inventory summary (one line
  per project) so the model reads that instead of the tree.
- effort: M
- tok: [0.10, 0.20]. Derived as bytes removed (3,518 + 2,606 + 1,037 + 376 = 7,537 of prose, about
  0.07 of two 55 KB runs) plus the tool output the model no longer reads (the directory listings and
  `package.json` files of the scan, 10 to 30 tool calls at 200 to 2,000 bytes each).
- time: [0.15, 0.30]. Derived as model passes removed: the scan is 10 to 30 tool calls of a 60 to
  100 call run, replaced by one script call.
- obs: improved. The inventory becomes deterministic and diffable, the markers found and not found
  are listed by the script, and the file keeps its path so `memory/impact.md:38` and the runtime's
  `SIDE_EFFECTS` entry stay valid. Resolves D7 by making `qa_analyze` call the script in `--check`
  mode (report only) and `qa_document` in write mode, matching the runtime table.
- policy: `scan.exclude` list in `assure-config.yml`, default equal to today's eleven folders.
- pros: largest single removal of model work in the two extensions; identical inventory from both
  commands; testable with a fixture tree; no change to receipts or freshness.
- cons: the frontend detection by dependency names needs a maintained table (the prose already has
  it, so this moves rather than adds); `planned/spec-only` rows still need the model.
- files: `extensions/assure/scripts/assure_scan.py` (new), `extensions/assure/commands/speckit.assure.analyze.md`,
  `extensions/assure/commands/speckit.assure.document.md`, `extensions/assure/assure-config.template.yml`,
  `extensions/assure/scripts/assure_init.py` (`config_text`), `extensions/assure/README.md`.
- tests: new `extensions/workflow/tests/test_assure_scan.py` (fixture with `package.json` + Vite,
  `pyproject.toml`, `android/`, `Dockerfile`; exclusions honoured; rerun is byte-stable; `--check`
  writes nothing); `test_assure_init.py` for the new config key.

### AS2. Deduplicate the two Assure commands into the skill references

- what: Cut step 0a in both commands to three lines (run `deps.py ensure illustrate`; on exit 0 load
  the Illustrate skill only at the diagram step; on non-zero report its line and skip diagrams), since
  `deps.py:1-25` already documents the policy. Move the shared "resolve the active feature" block,
  the task-block format and wording examples, the redaction sentence and the report shape into
  `skills/assure/references/analysis.md` and `documentation.md`, which step 0 already loads. Delete
  both Illustrate type enumerations (D2) in favour of "use the Illustrate selection guide". Move the
  lifecycle-phase paragraphs and the `--phase` flag to the README as unmanaged-mode guidance (D6).
  Remove the `record` line duplicated between reference and command. Target: `analyze.md` 14.0 KB
  to about 7 KB, `document.md` 14.6 KB to about 8 KB.
- effort: S
- tok: [0.15, 0.25]. Derived as bytes removed over bytes read: about 13 KB removed from a 55 KB
  run without a diagram (0.24), or from a 90 KB run with the Illustrate skill (0.15).
- time: [0.02, 0.05]. Reading only; no tool calls change.
- obs: unchanged. Every `record` call, flag and report bullet survives, once.
- policy: none.
- pros: cheapest option with the largest byte effect; removes the stale type list; the references
  become the single home of the contract both commands share.
- cons: `assure/README.md:41-48` and `docs/extensions/assure.md` must be trimmed in the same pass
  or the deps prose survives in prose form; the benchmark harness should confirm the target sizes.
- files: `extensions/assure/commands/speckit.assure.analyze.md`, `speckit.assure.document.md`,
  `extensions/assure/skills/assure/references/analysis.md`, `documentation.md`,
  `extensions/assure/skills/assure/SKILL.ext.md`, `extensions/assure/README.md`.
- tests: `python extensions/scripts/validate_skills.py extensions presets`; `check_docs.py`; the
  round-2 `benchmark_instructions.py` before/after; a size assertion for the two commands if the
  harness gains one.

### AS3. `audit_qa.py` for the generated QA manual

- what: Add `extensions/assure/scripts/audit_qa.py` that takes the manual paths and checks what
  `document.md:255-261` asks the model to check by eye: every `<img>` has non-empty `alt` and a
  caption element, every relative `src`/`href` resolves, the "Development-only draft" marker is
  present, and no secret-shaped value matches the `SECRET` regex copied from `audit_manual.py:20`.
  Step 7 becomes one call; step 8's `record` stays separate so the receipt contract is untouched.
  `documentation-gates.yml` may run it after the freshness check as an optional step.
- effort: S
- tok: [0.05, 0.15]. Derived as bytes no longer reread: a generated manual with screenshots and API
  samples is 10 to 40 KB of HTML the model otherwise opens to validate, over a 55 to 90 KB run.
- time: [0.05, 0.10]. Five manual checks collapse into one tool call.
- obs: improved. The audit result is a JSON line stored beside the state file; CI can print it.
- policy: none (the checks are the ones the prose already requires).
- pros: deterministic validation; the redaction rule gets a mechanical check for the first time on
  the Assure side; same shape as the user-manual audit so reviewers know it.
- cons: HTML parsing in stdlib (`html.parser`) is enough for `img` and links but not for layout
  "smoke" claims; the option replaces the checklist, not a browser.
- files: `extensions/assure/scripts/audit_qa.py` (new), `extensions/assure/commands/speckit.assure.document.md`,
  `extensions/assure/assets/github/documentation-gates.yml` (optional step), `extensions/assure/README.md`.
- tests: new `extensions/workflow/tests/test_audit_qa.py` (missing alt, missing asset, broken index
  link, secret value, clean manual passes); `test_ci_policy.py` if the CI template changes.

### AS4. Freshness `status` reports the changed paths

- what: In `extensions/scripts/shared/sanduq_freshness.py` `record_or_status`, when `current` is
  false compute `changed_inputs` (paths whose fingerprint differs or that are new or deleted) and
  `changed_outputs`, and include them in the JSON; `--summary` prints their counts. `assure_state.py`
  and `manual_state.py` need no CLI change. `speckit.assure.document.md` step 1 and
  `speckit.user-manual.update.md` step 2 then say: on a rerun, run `status`, read the changed inputs
  and the existing manual, and read the full set only when the state is missing. The `current` key
  and exit codes are unchanged, so `pr.generate.md:99-113` and both CI gates keep working.
- effort: S
- tok: [0.10, 0.30] of a rerun (revalidation or a second PR push); 0 on a first run. Derived as
  bytes not reread: 35 KB of artifacts against the handful that changed.
- time: [0.05, 0.15] of a rerun.
- obs: improved. The stale reason names the files in the CI log and in the pr preflight output
  instead of `stale-input-or-output`.
- policy: none.
- pros: one helper change serves assure, user-manual and the pr preflight; prerequisite for UM3;
  the saved state already holds everything needed (`sanduq_freshness.py:109-112`).
- cons: cross-cutting file owned by the shared folder; the two packaged copies ship with the next
  assure and user-manual releases, so both bump.
- files: `extensions/scripts/shared/sanduq_freshness.py`, `extensions/assure/commands/speckit.assure.document.md`,
  `extensions/user-manual/commands/speckit.user-manual.update.md`, both READMEs.
- tests: `extensions/workflow/tests/test_freshness.py`, `test_assure_state.py`,
  `extensions/user-manual/tests/test_manual_state.py` (changed, added and deleted input each
  appear; `current: true` carries empty lists).

### AS5. One description per Assure command, in catalog form

- what: Rewrite the three frontmatter descriptions in third person with what, when and trigger
  phrases, key use case first (for example: "Audits the active feature's tasks.md for missing E2E,
  screenshot, API sample, diagram and accessibility work and adds the tasks. Use after tasks exist and
  before implementation, when asked to 'check QA readiness' or 'add the test tasks', or as the managed
  qa_analyze stage."). Make `extension.yml` `provides.commands[].description` identical and have
  `check_docs.py` assert the equality so they cannot drift again (D4). Replace `/speckit-assure-analyze`
  with the host-neutral "run `speckit.assure.analyze`" (D3). Delete `skills/assure/agents/openai.yaml`
  (D5).
- effort: S
- tok: [0, 0.01]. The descriptions grow by about 100 characters each inside a budget that is 0.1
  percent of the window; the deleted file was never loaded.
- time: [0, 0].
- obs: improved. Routing on both hosts uses a description that names the situation.
- policy: none.
- pros: zero risk; fixes three defects; the equality check is a few lines in an existing gate.
- cons: `docs/reference/commands.md` regenerates (`check_docs.py --write`), so R2's and the
  orchestrator's doc pass must include it.
- files: `extensions/assure/commands/*.md` (frontmatter), `extensions/assure/extension.yml`,
  `extensions/assure/skills/assure/agents/openai.yaml` (delete), `extensions/scripts/check_docs.py`.
- tests: `extensions/scripts/test_check_docs.py` (mismatch fails), `validate_skills.py`, the
  benchmark's description checks.

### AS6. The CI gate reads the config through `assure_state.py`

- what: Add `--gate` to `assure_state.py status`: read `lifecycle.require_document_before_pr` from
  `assure-config.yml` with the narrow YAML reader already in `deps.py` (`read_yaml`), print
  `skipped gate=off` and exit 0 when it is false, otherwise behave as today. `documentation-gates.yml`
  steps become one `run:` line each (`assure_state.py status --gate --summary ...` and
  `manual_state.py status --summary ...`), using the exit code the scripts already return (D1, D8).
  `pr.generate.md:97-103` can later call the same flag (R2's file; noted only).
- effort: S
- tok: [0, 0]. Agent reads are unchanged; CI only.
- time: [0, 0] for the agent.
- obs: improved. The gate prints one readable line with the reason; the decision no longer depends
  on YAML indentation.
- policy: none (the config key and its default are unchanged).
- pros: closes a silent-bypass defect in a gate consumers already run; removes a bash and an inline
  Python layer from the rendered workflow; `install-lock.json` re-renders the file on upgrade (issue
  94 notes).
- cons: the rendered CI file changes for every consumer on upgrade, so the assure CHANGELOG must say
  so; `read_yaml` must be imported from the packaged `deps.py` (same directory in a package,
  `extensions/scripts/shared` in source).
- files: `extensions/assure/scripts/assure_state.py`, `extensions/assure/assets/github/documentation-gates.yml`,
  `extensions/assure/CHANGELOG.md`.
- tests: `extensions/workflow/tests/test_assure_state.py` (gate off prints skipped and exits 0; gate
  on and stale exits 1; indentation variants of the config), `test_ci_policy.py` (rendered template).

### UM1. Trim the user-manual commands and README to the scripts they call

- what: Replace the two Illustrate blocks (`analyze.md:30-41`, `update.md:35-45`) with two lines
  each pointing at `deps.py ensure illustrate` and the late-load rule; cut `README.md:45-51` to one
  sentence; replace `init.md:27-36` with "`init_manual.py` writes these defaults; confirm only product
  name, Arabic, branding, runtime, provider and edition visibility" (the values live in
  `init_manual.py:52-83`); keep every flag, approval rule and `record` line.
- effort: S
- tok: [0.04, 0.06]. Derived as bytes removed over bytes read: about 2.5 KB of a 45 to 50 KB run.
- time: [0.01, 0.02].
- obs: unchanged.
- policy: none.
- pros: no vendored file touched; no script change; the commands become the pointer bodies the
  first report recommends.
- cons: small absolute saving; worth doing only in the same pass as AS2.
- files: `extensions/user-manual/commands/speckit.user-manual.analyze.md`, `update.md`, `init.md`,
  `extensions/user-manual/README.md`.
- tests: `validate_skills.py`, `check_docs.py`, benchmark before/after.

### UM2. `build_manual.py --all` (upstream)

- what: In sanduq-skills `skills/dev-tools/skills/user-manual/scripts/build_manual.py`, add `--all`
  that reads `languages.required` and `languages.optional` from `manual.yml`, keeps only languages
  with a `docs/<lang>/` directory, and builds the three audiences for each, passing `--version`,
  `--archive` and `--pdf` through, printing one summary line per edition. Update both CI templates
  in the same bundle to one invocation (`user-manual-preview.yml:34-41`, `user-manual-release.yml:37-44`)
  and the extension's `update.md:49` and `release.md:26-27` to call it once. Vendor with
  `vendor-update`, bump the extension.
- effort: M (upstream PR, bundle tag, vendor PR, extension release)
- tok: [0.02, 0.05]. Six tool calls with six outputs become one call with six lines.
- time: [0.03, 0.08]. The model issues one build and waits once instead of six times.
- obs: improved. One line per edition in the model's transcript and in CI.
- policy: none; `--audience/--language` keep working.
- pros: removes the only loop the model must drive in the update and release commands; the CI
  templates shrink by eight lines each; the portable skill benefits too.
- cons: two repositories and a vendor cycle; `test_build_manual.py` exists in both copies
  (`ADAPTER.md:45`) and both must gain the case.
- files (upstream): `skills/dev-tools/skills/user-manual/scripts/build_manual.py`,
  `assets/github/user-manual-preview.yml`, `user-manual-release.yml`, `tests/test_build_manual.py`;
  (extension) `vendor.lock.json`, `extensions/user-manual/scripts/build_manual.py`,
  `extensions/user-manual/assets/github/*.yml`, `commands/speckit.user-manual.update.md`,
  `release.md`, `tests/test_build_manual.py`, `CHANGELOG.md`.
- tests: `extensions/user-manual/tests/test_build_manual.py` (`--all` with and without `docs/ar`;
  pass-through of `--pdf`/`--archive`); `test_ci_policy.py` for the rendered templates.

### UM3. Evidence-based module impact list for Analyze and Update

- what: Add extension-owned `extensions/user-manual/scripts/manual_impact.py` that takes the
  changed inputs from AS4 (`manual_state.py status --json`), joins them with `manual.yml` module
  `evidence` paths and each page's `source_evidence` front matter (parsed as `audit_manual.py:24-31`
  does), and prints the affected modules, pages and audiences, plus unmatched changed paths. `analyze.md`
  step 4 and `update.md` steps 2 and 3 start from this list; the model still decides the content and
  proposes new modules for unmatched paths. The list is written into `User-Manual/.state/coverage.json`
  alongside what step 7 already records.
- effort: M
- tok: [0.10, 0.25]. Derived as bytes not read: the model opens only affected pages instead of
  "existing manual state" for a manual that is typically far larger than the 45 KB run baseline.
- time: [0.05, 0.15]. One script call replaces the mapping pass over every story, route and entity.
- obs: improved. The impact list is recorded with the evidence that produced it.
- policy: `lifecycle.impact_scope` in `User-Manual/manual.yml` (written by the extension-owned
  `init_manual.py`, so not upstream): `all` (default, today's behaviour: read everything) or
  `evidence` (start from the list).
- pros: builds on the evidence paths the manual already requires (`discovery.md:11-13`,
  `content-model.md:10-11`); nothing changes for projects that keep the default.
- cons: depends on AS4; quality of the list depends on how well pages declare `source_evidence`,
  which `audit_manual.py:19,81-83` already enforces as required front matter.
- files: `extensions/user-manual/scripts/manual_impact.py` (new), `scripts/init_manual.py`
  (`manual_yaml` writes the key), `commands/speckit.user-manual.analyze.md`, `update.md`, `README.md`.
- tests: new `extensions/user-manual/tests/test_manual_impact.py` (changed evidence path maps to its
  module and pages; unmatched path reported; `all` scope prints everything); `test_manual_state.py`
  for the JSON consumed.

### UM4. One description per user-manual command, host hygiene

- what: Same as AS5 for the four user-manual commands: third-person what, when and trigger phrases
  in the frontmatter, `extension.yml` made identical and checked by `check_docs.py`; delete the five
  `skills/*/agents/openai.yaml` files (D5; extension-owned per `ADAPTER.md:44`). The `SKILL.ext.md`
  descriptions already follow the "Use when" pattern and stay.
- effort: S
- tok: [0, 0.01]. time: [0, 0].
- obs: improved (routing).
- policy: none.
- pros: zero risk; removes 1,096 bytes of dead package content; pairs with AS5 in one PR.
- cons: regenerates `docs/reference/commands.md`; `ADAPTER.md:44` row must be removed.
- files: `extensions/user-manual/commands/*.md` (frontmatter), `extensions/user-manual/extension.yml`,
  `extensions/user-manual/skills/*/agents/openai.yaml` (delete five), `extensions/user-manual/ADAPTER.md`,
  `extensions/scripts/check_docs.py` (shared with AS5).
- tests: `extensions/scripts/test_check_docs.py`, `validate_skills.py`, `extensions/scripts/tests/test_package_deps.py`
  if it enumerates packaged files.

## Double-counting notes for the orchestrator

- AS2 and UM1 remove the deps prose; `deps.py` itself is unchanged and shared with `pr` (R2 may
  propose the same trim for `speckit.pr.generate.md`; count the script once).
- AS4 is a shared-helper change that assure and user-manual both ship; count its cost once and its
  saving per extension only on reruns. UM3 depends on it.
- The Illustrate skill size (34,739 bytes) is R3's; AS2 only stops enumerating its types.
- `stage-qa_analyze.md` and `stage-manual_analyze.md` being identical is a workflow observation with
  no option here.
