# Round 3 review: scope and the three presets (stream R2)

Read-only review of `extensions/scope` 1.8.1 and `presets/{scope-gate,scope-brainstorm,workflow}` on
`feat/round-3`. Byte counts are from the files named; instruction totals per stage are from
`docs/internal/benchmarks/round-3-before-full.json` and `round-3-before-instructions.md`. GitHub call
counts were measured by driving `Scope` and `Clarification` with the test suites' `FakeGitHub` and
`ReviewGitHub` wrapped in a call counter (scratch script outside the repository; nothing in the tree was
changed). `python -m unittest discover -s extensions/scope/tests`: 231 tests, 0 failures, 39.5 s of test
time on this machine.

## Summary

- In every managed install the workflow preset `replace`s `speckit.clarify` and `speckit.superspec.brainstorm` at priority 1, so Spec Kit discards the lower layers (`spec-kit/src/specify_cli/presets/__init__.py:3160-3163`): `scope-gate/commands/clarify-github.md` (2,113 B) and all of `scope-brainstorm` are never rendered there, yet the installer adds both and `doctor` requires both (`install.py:691`, `workflow.py:1258`).
- `scope.py publish` makes 63 GitHub calls for a three-child split in an empty repository and 263 with 200 unrelated issues, because `rewire` reads `blocked_by` for every issue in the repository (`scope.py:1068-1079`); four full `project item-list --limit 10000` reads and eight repository label listings per publish come from per-node refetches (`scope.py:905-929`).
- The managed Specify path never reuses the inspect snapshot that round 1 (B5) built: the printed gate and bind commands carry no `--snapshot` (`execution_tools.py:283-294`, "run the printed command unchanged" at `scope-binding.md:16-17`), so gate costs 12 calls and bind 16 (with two prerequisites), including comments and timelines neither reads; with the snapshot gate costs 2.
- `commands/plan.md:7-8` still tells the agent to read "the installed Illustrate skill" (11,730 B) on every plan run although 1.8.1 rewrote `illustrate-plan.md:20-22` to read only the type index and the type reference; together with 1 KB of 1.5.x/1.6.0 migration history and 1.9 KB of clarification-image text, the plan path loads about 14.6 KB it does not need.
- Model work a script can do remains in the plan step (topological waves, critical path, `graph_sha256` and `issue_to_node`, `illustrate-plan.md:16-19,32-35`) and in clarification (checkbox answers the runtime already parses, `clarification.py:103-116`, and the hand-written `## Clarifications` bullets, `speckit.clarify.md:42-43`, next to the runtime's own review log, `clarification.py:726-739`).

## Measured cost per run

| Path | Instruction bytes loaded | Source |
| --- | ---: | --- |
| Managed Scope stage | 19,162 counted + 4,619 analyst references not counted (managed.md 1,438, analysis-json.md 940, controls.md 2,241) = 23,781 | benchmark `per_stage.scope`; files |
| Managed Specify stage (not bind-only) | 14,002 (specify-gate.md 3,348, guard.md 1,737, bind.md 1,131 of it) plus upstream Specify | benchmark `per_stage.specify` |
| Managed Clarify stage | 15,026 counted + 5,469 skill references (managed.md 2,599, analysis-json.md 1,858, controls.md 1,012) = 20,495 per round | benchmark `per_stage.clarify`; files |
| `/speckit-scope-plan` after a split | plan.md 517 + illustrate-plan.md 7,973 + Illustrate SKILL.md 11,730 + type-index.md 6,530 + type-dependency.md 4,462 = 31,212 | files |

| GitHub operation (fake client, counted) | Calls | Breakdown |
| --- | ---: | --- |
| `inspect` with 2 Done prerequisites | 11 | issue 3, `blocked_by` 4 (root twice), item-list 1, comments 1, timeline 2 |
| `gate` without `--snapshot` (same issue) | 12 | the above plus one more issue read |
| `gate` with a fresh `--snapshot` | 2 | issue 1, item-list 1 |
| `bind --apply` without `--snapshot` | 16 | issue 5, item-list 2, `blocked_by` 4, comments 1, timeline 2, item-add 1, item-edit 1 |
| `publish --apply`, single leaf | 13 | label listings 2, field-list 1, item-list 1 |
| `publish --apply`, 3 children, empty repo | 63 | label listings 8, field-list 5, item-list 4, `blocked_by` 4, issue 9, issue lists 3 |
| same, 50 unrelated issues | 113 | `blocked_by` 54 |
| same, 200 unrelated issues | 263 | `blocked_by` 204 |
| `clarification.py publish --apply`, 1 question | 16 | issue 6, comments list 5, posts 2, item-list 2, item-edit 1 |
| same, 6 questions | 26 | comments list 10 (one reread before each post), posts 7 |
| same, 0 questions (Ready) | 16 | issue 7, item-list 3 |

## Findings per lens

### Lens 1: model work a script does or could do

Prose that restates a guard the runtime already raises (each still costs attention on every run):

| Prose | Enforced at |
| --- | --- |
| `scope-analyst/SKILL.ext.md:22-25` prerequisites exactly In review or Done; unknown, cancelled, cycles block | `scope.py:629-630,659-660,587-590` (`blocked`, `rejection`) |
| `analysis-json.md:7` every image `viewed: true` | `scope.py:764-765` |
| `analysis-contract.md:20-21` sum-to-points table; `SKILL.ext.md:44` "never lower a score" | `scope.py:154-158` `effort`, `:776-777` declared score must match |
| `controls.md:23-24` `--apply` cannot bypass a missing approval | `scope.py:876-879` `APPROVAL_REQUIRED` |
| `controls.md:29` never resume a `rolled_back` operation | `scope.py:949` `SCOPE_ROLLED_BACK` |
| `plan.md:9` do not mark Scope complete while `plan-pending.json` exists | `scope.py:713-715` `SCOPE_PLAN_PENDING` |
| `github-clarification/SKILL.ext.md:32-36` unchecked recommendations, bots, AI text are never answers | `clarification.py:504-518` evidence check |
| `analysis-json.md` (clarification) `:9` every historical question exactly once | `clarification.py:497-498` |
| `managed.md` (clarification) `:22-24` cap and defer | `clarification.py:549-554` names the keys to defer |

Work the model does that a script could hand it:

- Plan arithmetic. `illustrate-plan.md:16-19` asks the model to "recalculate topological waves and the critical path" and `:32-35` to write `implementation-plan.mapping.json` with `graph_sha256` (SHA-256 of `scope-dependencies.json`) and `issue_to_node`. `export_plan` already holds the full graph (`scope.py:1112-1134`) and writes `scope-dependencies.json` (`:1162`); waves are the topological levels of that graph. `accept_plan.py:59-110` re-derives reachability independently, so a generated mapping is still checked.
- Clarification answers. `history()` and `selection()` already classify each prior question's checkbox state as `selected`, `ambiguous`, `edited` or `unanswered` and list `reply_candidates` (`clarification.py:103-116,151-191`); the model then rewrites the same facts as `answers[]` with `comment_ids` (`analysis-json.md:7-10`). For the common case (one checked option, no reply) the disposition and evidence are deterministic.
- Clarification log. The workflow Clarify overlay tells the model to keep `## Clarifications` / `### Session` / `- Q: … → A: …` bullets as `spec_edits` (`speckit.clarify.md:42-43`) while the runtime already appends `### GitHub clarification review N` with every disposition and evidence link (`clarification.py:726-739`): two records of the same answers, one hand-written.
- Analysis skeleton. The analyst copies `issue`, `fingerprint` and every image URL from the inspect output into the analysis (`analysis-json.md:6-7`, `analysis-contract.md:4-5`), and `validate_analysis` refuses any mismatch (`scope.py:760,764-765`). A skeleton writer removes the copy step.

### Lens 2: repeated text, inside scope and against the dispatcher

| Rule | Copies |
| --- | --- |
| Managed-precedence paragraph (355 B, identical) | `specify-gate.md:5-10`, `clarify-github.md:6-11`, `brainstorm-github.md:6-11`; the workflow overlay composed directly above specify-gate says the same in one line (`speckit.specify.md:6`) |
| Publication approval flow | `analysis-contract.md:44-57` (942 B) and `controls.md:1-32`; both are read in the Scope stage |
| Snapshot reuse and board cache | `analysis-contract.md:59-70` (731 B) and `scope-analyst/references/managed.md:7-9` |
| In-session first round | `analysis-contract.md:72-77` (358 B, read in the Scope stage where it never applies), `github-clarification/references/managed.md:26-40`, `stage-clarify.md:22-25` |
| `render-spec` | `analysis-contract.md:79-91` (898 B), `stage-scope.md:20-23`, `analysis-json.md:12-13`, `scope-analyst/references/managed.md:18-19` |
| Question cap | `github-clarification/SKILL.ext.md:47`, `references/managed.md:22-24`, `analysis-json.md:15`, `stage-clarify.md:26-27` |
| Mermaid / diagram image | `illustrate-plan.md:93-122` (1,938 B), clarification `managed.md:17-21`, `standalone.md:10-11`, `analysis-json.md:15-17`, `stage-clarify.md:28` |
| Coverage taxonomy | `github-clarification/SKILL.ext.md:43-48` and `speckit.clarify.md:23-38` (1,096 B), both loaded in the Clarify stage |

The benchmark's duplicate detector reports none of these because presets are outside its measured set
and the copies are reworded, not identical (`round-3-before-instructions.md:123`).

### Lens 3: large rereads

- Plan: 11,730 B of Illustrate `SKILL.md` per plan run from `plan.md:7-8`, contradicting the 1.8.1 entry and `illustrate-plan.md:20-22`; 1,001 B of version history (`illustrate-plan.md:76-91`, "until Scope 1.7.0" in a 1.8.1 file) and 1,938 B on clarification images that the plan step never uses.
- Scope stage: `analysis-contract.md` is 5,456 B; 2,929 B of it (approval, snapshot, in-session, render) duplicate or do not apply to the analyst (sections measured above). The 2,250 B rubric is the part the analyst needs.
- Clarify stage: `clarification.py inspect` returns `comments` in full and again inside `history` reply candidates, and the snapshot embeds `spec` text (`clarification.py:482-484`); the model reads the spec from the snapshot, so the file read in the overlays is a second copy only when the agent also opens it.

### Lens 4: descriptions and catalog slots

- The seven command descriptions are 200-265 characters (1,638 total), identical in `extension.yml` and the files. Five are hook-only (`hosts.py:43`); Claude hides them from the menu (`hosts.py:245-258`), Codex has no flag and lists all seven. The hook-only five each carry "use when" text and a trigger phrase they do not need; the benchmark marks six of seven as missing quoted triggers.
- Skill descriptions: `scope-analyst` 418 and `github-clarification` 497 characters; both skills are read by path, never listed, so their length costs only the read.
- Overlay descriptions: workflow preset 186-300 characters each (15 entries). The scope-gate `clarify-github.md:2` and `brainstorm-github.md:25` say "no question-count limit", which contradicts `clarification.max_questions_per_round` (1.8.0).
- Error text points to `/speckit-scope` (`scope.py:575,687,705,711,712,717,719,1340`; `guard.md:13`; `specify-gate.md:16`; `standalone.md:5`), an alias installed only with `--with-aliases` (`hosts.py:54-58`); a fresh install has only `/speckit-scope-run`.

### Lens 5: rules a hook could enforce

Scope is already hook-driven (guard, bind, after-specify, plan-guard, reconcile). The remaining prose
rules are either already script guards (lens 1 table) or judgement (approval wording, question
quality). No new hook is proposed; the gain is deleting the restatements.

### Lens 6: host divergence

- Invocation sigils are hard-coded: `$speckit-…` 5 times (`after-specify.md:14-15`, `standalone.md:16`, `clarify-github.md:30`, `brainstorm-github.md:29`) and `/speckit-…` 8 times, while `clarification.py dispatch` returns `/speckit-…` (`:469`). Spec Kit renders `__SPECKIT_COMMAND_<NAME>__` per host in command files (`spec-kit/src/specify_cli/agents.py:635-637`); scope does not use it.
- `clarify-github.md:32` says "the Codex conversation" in a file rendered for Claude too.
- Catalog: as lens 4, five extra entries on Codex.

### Do the three presets earn their separate existence?

| Preset | License | Managed install (workflow installer) | Scope-only install (`package.py scope`, public preset CLI) |
| --- | --- | --- | --- |
| `workflow` | PolyForm-Noncommercial (`preset.yml:10`) | 15 overlays, priority 1; `replace` for clarify and brainstorm | not shipped with scope |
| `scope-gate` | MIT | only `specify-gate.md` survives (composed under the workflow prepend); `clarify-github.md` is discarded | both templates live |
| `scope-brainstorm` | MIT | entirely discarded | live only when Superspec is installed |

`scope-brainstorm` holds one template whose command name has three parts, and Spec Kit already skips a
`speckit.<ext>.<cmd>` template when `.specify/extensions/<ext>` is absent
(`presets/__init__.py:619-627`); the stated reason for a separate preset (install only with Superspec,
`scope-brainstorm/README.md:3-4`) is both unnecessary and not what the installer does
(`install.py:691` adds it unconditionally). It can be folded into `scope-gate`. `scope-gate` should
stay separate from `workflow`: it is the MIT gate the scope package ships, and folding it into the
PolyForm preset would change what scope-only users receive.

### Code refactoring

- `scope.py` is 1,400 lines (86,305 B); `GitHub` and `ProjectRest` (`:189-486`, about 300 lines) are transport, separate from scope logic. `project/scripts/project_sync.py:75-120` has its own GraphQL-to-REST fallback; the two are independent implementations of the same idea (cross-cutting, R4/R6).
- `workflow_policy.load` reparses `.specify/workflow.yml` on every `setting`, `statuses`, `paths`, `board_ttl` call: 27 parses in one managed six-question `clarification.py publish`. `_workflow_module` execs the 228 KB `workflow.py` on each `bound_claim` and `fresh_claim` (27 ms each measured), and `_decisions_module` inserts into `sys.path` on every call (`workflow_policy.py:167`).
- Duplicate policy logic: status-mapping validation (`workflow_policy.py:57` and `workflow.py:807-809`) and the keep-together band (`workflow_policy.py:24-40` and `workflow.py:820-825,937-944`).
- Dead code by its own text: `accept_plan.py:218-219,237-238` (`--spec`, `--archify`, "removed in 1.7.0") at 1.8.1.
- Tests: 39.5 s, of which one real-Illustrate browser test is 10.45 s (`test_plan.RealIllustrateTests`) and `test_fresh_binding` 11.9 s; acceptable, no change proposed.

## Defects

| Defect | Effect | Where |
| --- | --- | --- |
| Plan command reads the whole Illustrate skill | 11,730 B per plan run that 1.8.1 meant to remove | `commands/plan.md:7-8` vs `illustrate-plan.md:20-22`, CHANGELOG 1.8.1 |
| Managed gate and bind never pass `--snapshot`; analyst reference says they should | Round-1 B5 reuse is lost on the managed Specify path; gate 12 and bind 16 calls instead of 2 and about 8 | `execution_tools.py:283-294`, `scope-binding.md:16-17` vs `scope-analyst/references/managed.md:7-9` |
| Gate/bind fallback runs the full inspect | Comments and one timeline per prerequisite fetched and discarded | `scope.py:566` → `:669-681` |
| Root `blocked_by` read twice per inspect | One redundant paginated call per inspect, gate and bind | `scope.py:634` (via `prerequisite_report`) and `:664` |
| `rewire` reads `blocked_by` for every repository issue | Publish cost grows with repository size: 204 calls at 200 issues | `scope.py:1068-1079` |
| Labels listed per label per node; field-list per node | 8 label listings and 5 field-lists for a 3-child publish | `scope.py:905-909,935,1136` |
| Unconditional `item-add` and full board reload after every board write | 4 `item-list --limit 10000` GraphQL reads per 3-child publish, 2 per bind | `scope.py:918-929,1010-1012,1244-1251` |
| Errors name `/speckit-scope`, off by default | The suggested command does not exist on a fresh install | `scope.py` 8 sites, `guard.md:13`, `specify-gate.md:16`, `standalone.md:5`; `hosts.py:54-58` |
| scope-brainstorm installed unconditionally, README says conditional | Doc and doctor disagree; a preset that is always discarded in managed installs | `install.py:691`, `workflow.py:1258`, `scope-brainstorm/README.md:3-4` |
| Scope-gate overlays promise "no question-count limit" | Contradicts `max_questions_per_round` for scope-only installs | `clarify-github.md:2,15-16`, `brainstorm-github.md:25` |
| `--spec`/`--archify` kept past their stated removal | Help text and reference describe a promise not kept | `accept_plan.py:218-219`, `illustrate-plan.md:76-81` |
| Hard-coded `$`/`/` sigils | Each host sees the other's syntax in places | lens 6 |
| README version line | Says 1.8.0 at 1.8.1 | `extensions/scope/README.md:8` |

## Options

Cost basis for every `tok` and `time`: Scope's share of one managed feature's front half, the Scope,
Specify and Clarify stages (and the plan step when a split happens). Scope stage about 40k-120k tokens
(24 KB instructions, inspect output, prerequisite code archaeology, the analysis it writes); Specify
10k-20k (zero model work in bind-only mode); Clarify 30k-70k per round; plan after a split 40k-80k.
Total 90k-220k tokens without a split, about 30 to 45 tool round-trips and 30 to 120 GitHub calls.
GitHub calls cost wall time (0.3-1 s each through `gh`), not tokens. Tokens are bytes / 4.

### SC1. Trim the scope instruction path and remove the duplicate copies

- title: One copy of each scope rule; plan step reads only what 1.8.1 intended
- what: Remove "and the installed Illustrate skill" from `commands/plan.md:7-8` (the reference already routes to `type-index.md` and the type reference). Cut `illustrate-plan.md` to the dependency-plan handoff: the 1.6.0 and 1.5.x sections (1,001 B) go to the CHANGELOG (keep one line naming `--migrate-only` and `PLAN_REGENERATION_REQUIRED`), and "Clarification images on GitHub" (1,938 B) moves to `skills/github-clarification/references/diagrams.md`, read from clarification `managed.md`/`standalone.md` only when a question carries `diagram_image`. Cut `analysis-contract.md` to the rubric, the tree schema and the top-level fields: approval becomes a pointer to `controls.md`, the in-session section goes (clarify references carry it), snapshot reuse stays here and leaves analyst `managed.md`, and render-spec keeps only its three error codes. Delete the 355 B managed-precedence paragraph from `specify-gate.md` (the workflow overlay composed above it says it) and keep it in the two scope-gate clarify/brainstorm overlays, which are live only without the workflow preset. Delete the lens-1 restatements in the analyst and clarification skills, leaving the error code names.
- effort: S
- tok: [0.005, 0.04]. Scope stage about 2.3 KB less, Specify 0.35 KB, Clarify 0.3 KB per round: about 0.75k tokens per feature (0.5% to 1%); a split adds 14.6 KB less on the plan step (about 3.7k tokens), up to 4%.
- time: [0, 0.01]. One fewer large read on the plan step.
- obs: unchanged. Receipts, journals, gates and error codes untouched.
- policy: none.
- pros: Fixes the plan.md defect; each rule has one home; the benchmark's next duplicate pass has less to find.
- cons: Reviewer must confirm no rule only lived in a removed copy (approval text rules in `analysis-contract.md:51-57` vs `controls.md:13-24` overlap fully except "legacy small/medium receipts remain valid", which moves to `controls.md`); `test_front_half.py` and workflow's `rules-inventory.json` may pin some text.
- files: `extensions/scope/commands/plan.md`, `extensions/scope/references/{analysis-contract,illustrate-plan}.md`, `extensions/scope/skills/scope-analyst/{SKILL.ext.md,references/managed.md,references/controls.md}`, `extensions/scope/skills/github-clarification/{SKILL.ext.md,references/managed.md,references/standalone.md,references/diagrams.md (new)}`, `presets/scope-gate/commands/specify-gate.md`, `extensions/scope/CHANGELOG.md`.
- tests: Keep green: `test_front_half.py`, `test_plan.py`, workflow `test_speckit_compat.py` and the rules-inventory check. Add: every reference path named in a scope command or skill exists, and `plan.md` does not name `skill/SKILL.md`.

### SC2. Fold scope-brainstorm into scope-gate (three presets become two)

- title: One MIT scope preset with Specify, Clarify and Brainstorm templates
- what: Move `presets/scope-brainstorm/commands/brainstorm-github.md` into `presets/scope-gate/commands/` and add its template entry to `scope-gate/preset.yml`; Spec Kit already skips the `speckit.superspec.brainstorm` template when Superspec is not installed (`presets/__init__.py:619-627`), which is what the separate preset was for. Update `MANAGED_PRESETS` (`hosts.py:29`), the installer list (`install.py:691`), doctor's required list (`workflow.py:1258`), `package.py:10-11`, `benchmark_front_half.py:94-99` and the docs that name it. Migration: on upgrade the installer runs `specify preset remove scope-brainstorm` when it is registered, before re-adding `scope-gate`; doctor accepts its absence. Fix the "no question-count limit" wording in both clarify and brainstorm overlays while moving them. Keep `scope-gate` separate from `workflow` (MIT versus PolyForm; scope-only installs need it).
- effort: M
- tok: [0, 0.002]. Nothing it removes is loaded in managed installs today.
- time: [0, 0.005]. One fewer `specify preset add` per install and upgrade.
- obs: unchanged.
- policy: none.
- pros: One fewer package unit, registry entry, doctor check and README; removes the README/installer contradiction and the cap contradiction.
- cons: An upgrade path must remove the old preset cleanly on both hosts (its rendered skill is replaced by the scope-gate layer of the same name, so nothing user-visible disappears); a Superspec install after the preset still needs the preset re-added, as today.
- files: `presets/scope-gate/{preset.yml,README.md,commands/brainstorm-github.md,commands/clarify-github.md}`, `presets/scope-brainstorm/` (removed), `extensions/workflow/scripts/{install.py,hosts.py,workflow.py}`, `extensions/scripts/{package.py,benchmark_front_half.py}`, `extensions/workflow/tests/{test_install.py,test_workflow.py,test_speckit_compat.py}`, `README.md`, `docs/reference/{commands,hooks,licenses,compatibility,glossary}.md`, `docs/extensions/scope.md`, `docs/workflow/{lifecycle,development}.md`, `docs/start/prerequisites.md`.
- tests: Keep green: `test_speckit_compat.py` (bundled presets), `test_install.py` preset ordering, `test_workflow.py` doctor fixtures (update the preset tuple). Add: upgrade from a registry holding scope-brainstorm removes it and doctor passes; with Superspec absent the brainstorm template is not rendered.

### SC3. Cut the GitHub call count of publish, bind, reconcile and clarification publish

- title: Per-process caches and targeted reads instead of repository-wide scans
- what: In `scope.py`: list repository labels once per process (`set_labels`, `:905-909`) and project fields once (`sync_dependency_fields`, `export_plan`, `:935,1136`); call `item-add` only when the board has no item for the issue (`:1010,1244`) and update the in-memory board row after `item-add`/`item-edit` instead of dropping it, while still removing the shared `board-cache.json` after every write (B5 rule unchanged); read `blocked_by` once per issue in the publish dependency loop (`:1028-1031`); reuse the root's dependencies in `inspect` (`:664`); in `rewire` (`:1068-1079`) take candidates from the parent's `GET …/issues/{n}/dependencies/blocking` plus the bodies, board "Blocked by" text and catalogue entries already in memory, and call `dependencies()` only for those. In `clarification.py publish`: fetch the issue once for gate and transition (`:800,804`) and reuse the comments read by the `fresh` inspect for the first post; keep the reread before every later post (lost-response and new-input protection).
- effort: M
- tok: [0, 0.005]. Stdout is unchanged; only fewer stderr fallback lines.
- time: [0.01, 0.08]. Measured 63 calls for a 3-child split drop to about 30; 263 at 200 unrelated issues drop to about 35; bind 16 to about 12; 6-question clarification 26 to about 22. At 0.3-1 s per call that is 10 s to 4 min per publish, and the full-board GraphQL reads (`item-list --limit 10000`) fall from 4 to 1 per publish, which is what exhausted the GraphQL budget that 1.6.1's REST fallback works around.
- obs: unchanged. Journals record the same before-images; every write still happens in the same order and invalidates the shared cache.
- policy: none.
- pros: Biggest wall-time and rate-limit saving in this review; scales with repository size instead of with it.
- cons: The `dependencies/blocking` endpoint must be confirmed on the live API and in the REST fallback; an in-memory board row must mirror exactly what `item-list` would return for `status`, so tests must compare both paths.
- files: `extensions/scope/scripts/scope.py`, `extensions/scope/scripts/clarification.py`, `extensions/scope/tests/test_scope.py`, `extensions/scope/tests/test_clarification.py`, `extensions/scope/tests/test_project_rest.py`.
- tests: Keep green: all of `test_scope.py` (publish, retry, rewire, reconcile), `test_project_rest.py`, `test_clarification.py` (lost response, stale input). Add: a call-count test with `FakeGitHub` (3-child split with 200 unrelated issues stays under 40 calls; one `item-list` per publish); rewire still finds a dependent that names the parent only in its body text.

### SC4. Light gate and snapshot reuse on the managed Specify path

- title: Gate and bind stop fetching comments and timelines; the managed command carries `--snapshot`
- what: Give `Scope.inspect` an `evidence=False` mode that stops after prerequisites (no comments, images or timelines, `scope.py:669-681`) and use it in the `load_snapshot` fallback that `gate` and `bind` take (`:566`); the analyst's `inspect --output` keeps the full mode. Have `execution_tools.py scope-command` append `--snapshot .specify/scope/issue-<n>-snapshot.json` when that file exists (the analyst writes it at `SKILL.ext.md:20`), so the printed command and `scope-analyst/references/managed.md:7-9` agree; the runtime already rejects a stale or mismatched snapshot and falls back. Bind also reuses the issue it resolved for `resuming` instead of resolving again inside `gate` (`:1230-1237`).
- effort: S
- tok: [0, 0]
- time: [0.005, 0.02]. Measured gate 12 calls to 2 with the snapshot (about 7 without, light mode); bind 16 to about 8; both run once per Specify, and again on a revalidation.
- obs: unchanged. `snapshot_reused` is already reported; the receipt and labels still come from the fresh issue read (`scope.py:564-565`).
- policy: none. `scope.board_cache_seconds` keeps bounding reuse (0 disables).
- pros: Restores the round-1 B5 saving where it was meant to apply; removes a documented contradiction.
- cons: `execution_tools.py` is workflow's file (coordinate with R1); a snapshot older than the TTL silently falls back, which is the existing behaviour.
- files: `extensions/scope/scripts/scope.py`, `extensions/workflow/scripts/execution_tools.py`, `extensions/workflow/skills/workflow/references/scope-binding.md`, `extensions/scope/tests/test_front_half.py`, `extensions/workflow/tests` (scope-command test).
- tests: Keep green: `test_fresh_binding.py`, `test_revalidation.py`, `test_front_half.py` snapshot tests. Add: light gate makes no comments or timeline call; `scope-command` adds `--snapshot` only when the file exists.

### SC5. Script computes the plan's waves, critical path and mapping

- title: `export-plan` writes waves and a draft mapping; the model only draws
- what: `Scope.export_plan` adds `waves` (topological levels of executable leaves, aggregates and `kind: epic` excluded, the rule in `illustrate-plan.md:16-18`) and `critical_path` to `scope-dependencies.json`, and writes `implementation-plan.mapping.json` with `graph_sha256` and `issue_to_node` (`W1`…`Wn`). `illustrate-plan.md` steps 2 and 4 shrink to "draw one node per wave from `waves`, mark `data-plan-node` with the wave id and every edge between waves". `accept_plan.py` keeps its independent checks (`:59-110`), so a wrong generator fails acceptance rather than passing silently. The model may still split a large wave into linked diagrams.
- effort: M
- tok: [0, 0.03]. Only on splits: the graph reasoning and hashing (2k-5k tokens) go, and a failed acceptance (browser check, re-edit) is less likely.
- time: [0, 0.05]. One `accept_plan.py` rerun avoided is a three-viewport Chromium pass plus the fix.
- obs: improved. The waves and path are recorded in the dependency file, not only drawn.
- policy: none.
- pros: Deterministic part moves to code the acceptance step already mirrors; less to read in `illustrate-plan.md`.
- cons: Two implementations of reachability (generator and checker) must agree; the model loses freedom to regroup waves (it can still add focused diagrams).
- files: `extensions/scope/scripts/scope.py` (`export_plan`), `extensions/scope/references/illustrate-plan.md`, `extensions/scope/tests/test_plan.py`.
- tests: Keep green: `test_plan.py` (including `RealIllustrateTests`). Add: waves for a diamond and a chain; the generated mapping passes `check_graph_mapping` unchanged.

### SC6. Clarification runtime hands over the deterministic answers and writes the Q/A log

- title: `inspect` suggests answers for clean checkbox selections; publish writes the Clarifications bullets
- what: `clarification.py inspect` adds `suggested_answers`: for each prior question whose `selection().state` is `selected` and that has no reply candidate, `{question_id, disposition: "answered", comment_ids: [the question comment], option}`; the model copies or overrides and still writes `explanation` and `spec_edits`. `validate` is unchanged, so evidence rules hold. Publish adds the question text and chosen answer to each line of the review log it already appends (`clarification.py:728-733`), and the workflow Clarify overlay drops its instruction to hand-write `## Clarifications` bullets (`speckit.clarify.md:42-43`), keeping only "apply each answer where it belongs".
- effort: S
- tok: [0.005, 0.02]. A round with several checkbox answers saves the model re-deriving them and one duplicated log; about 0.5k-2k tokens per round.
- time: [0, 0.02]. Fewer `validate` refusals for mismatched `comment_ids`.
- obs: improved. The spec log carries the question and answer text next to the evidence link.
- policy: none.
- pros: Removes a duplicate record; the parsing already exists.
- cons: Spec log format changes (anything that parses the review log must accept the longer line); the overlay is workflow-owned text (coordinate with R1).
- files: `extensions/scope/scripts/clarification.py`, `extensions/scope/skills/github-clarification/references/analysis-json.md`, `presets/workflow/commands/speckit.clarify.md`, `extensions/scope/tests/test_clarification.py`, `extensions/scope/tests/fixtures/clarifications-vector.json` (if the log is asserted).
- tests: Keep green: `test_clarification.py` evidence and conflict tests, the vector test. Add: a single checked option yields one suggestion; an ambiguous or edited one yields none.

### SC7. Descriptions, error text and host sigils

- title: Short hook-only descriptions, real command names in errors, per-host invocation tokens
- what: Rewrite the five hook-only descriptions (guard, bind, after-specify, plan-guard, reconcile) to one third-person sentence of about 90 characters naming the hook ("Runs as the before_specify hook: …") without trigger phrases, in both `extension.yml` and the files; keep `run` and `plan` as they are. Replace `/speckit-scope <issue>` with `/speckit-scope-run <issue>` in the eight `scope.py` messages, `guard.md:13`, `specify-gate.md:16` and `standalone.md:5`. Replace hard-coded `$speckit-…` in rendered command files with `__SPECKIT_COMMAND_<NAME>__` tokens Spec Kit renders per host, and drop "in the Codex conversation" (`clarify-github.md:32`). Update the README version line.
- effort: S
- tok: [0.001, 0.004]. Catalog characters about 1,638 to about 900 (about 185 tokens per session on Codex, where all seven are listed).
- time: [0, 0.005]. An agent following an error message reaches a command that exists.
- obs: improved. Error messages name an installed command.
- policy: none.
- pros: Fixes a user-visible defect; the catalog stops spending text on commands users never call.
- cons: Tests that assert the `SCOPE_REQUIRED` text change; `__SPECKIT_COMMAND_*__` resolves only in Spec Kit-rendered files, not in skills read by path, so `standalone.md` keeps a literal name.
- files: `extensions/scope/extension.yml`, `extensions/scope/commands/*.md`, `extensions/scope/scripts/scope.py`, `extensions/scope/skills/scope-analyst/references/standalone.md`, `presets/scope-gate/commands/*.md`, `extensions/scope/README.md`, tests that match the messages.
- tests: Keep green: `test_scope.py` messages (update the expected text), `validate_skills.py`. Add: no scope file or message names `/speckit-scope ` without a suffix.

### SC8. Refactor the scripts: transport module, cached policy, one validation

- title: `github_client.py`, a cached `workflow_policy`, shared validation, dead flags removed
- what: Move `rate_limited`, `GitHub` and `ProjectRest` (`scope.py:189-486`) to `scripts/github_client.py`, re-exported from `scope.py` so `clarification.py` and the tests keep their imports. Cache `workflow_policy.load` by path and mtime (27 parses per managed six-question publish today), cache `_workflow_module` and `_decisions_module` per process and stop the per-call `sys.path.insert` (`workflow_policy.py:62-78,163-171`). Have `statuses` and `keep_together` call the workflow module's validation (`workflow.py:807-809,820-825`, `scope_decision` at `:937-944`) when it loads, keeping the local fallback for unmanaged projects. Remove `--spec` and `--archify` from `accept_plan.py` as its help text promised for 1.7.0, with a CHANGELOG line. Flag the second GraphQL-to-REST fallback in `project_sync.py:75-120` to R4/R6.
- effort: M
- tok: [0, 0]
- time: [0, 0.005]. Milliseconds per call; the value is maintenance.
- obs: unchanged.
- policy: none.
- pros: `scope.py` drops to about 1,100 lines with transport testable on its own; one definition of each policy rule.
- cons: Removing `--spec` breaks any script still passing it (none in this repository; consumers were told in 1.6.0); importing workflow validation couples error messages (scope's `ValueError` text changes to workflow's codes unless wrapped).
- files: `extensions/scope/scripts/{scope.py,github_client.py (new),workflow_policy.py,accept_plan.py,clarification.py}`, `extensions/scope/tests/{test_project_rest.py,test_scope.py,test_plan.py}`, `extensions/scope/CHANGELOG.md`.
- tests: Keep green: the whole scope suite (231 tests), `test_project_rest.py` in particular. Add: `load` parses once per mtime; `accept_plan.py --spec` exits with a usage error.

### SC9. Analysis skeleton from inspect

- title: `scope.py inspect --skeleton <file>` writes the fields the model now copies
- what: Add `--skeleton <analysis.json>` to `inspect`: writes `issue`, `fingerprint`, `images` (each `{url, viewed: false, observations: ""}`), empty `requirements`, `evidence`, `alignment` and a root `tree` with `key: "root"` and the five dimensions at null. Let `validate_analysis` fill a missing `score` from the dimensions (`effort()`), still refusing a declared score that disagrees (`scope.py:776-777`). `analysis-json.md` and `analysis-contract.md` point at the skeleton instead of `examples/analysis.json`.
- effort: S
- tok: [0, 0.01]. The copy of fingerprint and image URLs and the rubric arithmetic leave the model; a few hundred tokens and the occasional mismatch refusal.
- time: [0, 0.02]. One avoided publish-dry-run refusal per mistyped fingerprint or image URL.
- obs: unchanged. The `viewed: true` rule still requires the model to inspect each image.
- policy: none.
- pros: Small, and every analysis starts consistent with the snapshot it must match.
- cons: A skeleton with `viewed: false` must not be publishable (it is not: `scope.py:765` refuses).
- files: `extensions/scope/scripts/scope.py`, `extensions/scope/skills/scope-analyst/references/analysis-json.md`, `extensions/scope/references/analysis-contract.md`, `extensions/scope/tests/test_scope.py`.
- tests: Keep green: `test_scope.py` validation tests. Add: the skeleton round-trips through `validate_analysis` only after images are marked viewed; an omitted score is filled, a wrong one refused.

## Notes for the orchestrator

- SC1 and SC7 both touch `specify-gate.md` and `standalone.md`; SC2 moves the files SC7 edits. Do SC2 first or in the same stream.
- SC4 and SC6 change workflow-owned files (`execution_tools.py`, `scope-binding.md`, `speckit.clarify.md`); coordinate with R1.
- SC3 and SC4 overlap on gate and bind call counts; count SC4's bind saving only once.
- Not verified: the live `dependencies/blocking` endpoint (SC3), and real GitHub latency per call (counts were measured on the fake client only).
