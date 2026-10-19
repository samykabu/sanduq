# Round 3 review: workflow (stream R1)

Read-only review of `extensions/workflow` (1.14.0) on `feat/round-3`. Line references are to the files named.
Measurements come from three sources. The first is `benchmark_front_half.py --repo . --tier full` run on this
worktree, with output in the R1 scratchpad, not committed; its totals match `compare-full.md` "after" to within
0.2% of instruction bytes. The second is `round-3-before-instructions.md`. The third is targeted
`python -m unittest <module> -q` runs from `extensions/workflow/tests`, plus a subprocess counter that wraps
`subprocess.Popen` around one module. Nothing in the tree was changed.

## Summary

- Execute is still the heaviest stage: 40,737 instruction bytes, 20% of the front half's 203,952. 5,211 bytes are the legacy reporter calls (`execution-report.md:201-271`), which apply only without Progress. About 6,400 bytes are delegation-only, and about 2,400 bytes describe an orchestration agent that lean mode (the default for lite and standard) tells the coordinator not to create.
- Runtime cost is git subprocesses, and the count grows with the stage index: claim needs 7 git calls at Scope and 29 at PR, complete needs 8 and 31, 744 per full lifecycle. `source_fingerprints` re-hashes the whole source tree 2 to 4 times in one command once Verify exists. `Run.load` runs `git rev-list --max-parents=0 HEAD`, a full-history walk, on every call.
- The same git pattern dominates the tests. `test_workflow` takes 77.8 s for 44 tests and spawns 2,039 git processes, 46 per test: `check-attr` 633, `config` 484, `rev-parse` 361, `branch` 193, `rev-list` 190. Process creation and pipe reads are the top of the cProfile output. `test_delegation` takes 121 s for 181 tests.
- Two modules are over 2,000 lines: `workflow.py` (3,719 lines, 228 KB, 151 functions) and `delegate_dispatch.py` (2,397 lines, 131 KB). Helpers are mostly centralised already: 14 scripts import from `workflow`, and only 4 git wrappers exist. Dead code is small: two functions with no caller and two used only by tests.
- Host divergence: on Codex the guard hook runs only after approval, and nothing checks for that approval, although `progress_bridge.py:264` already has the check for the Progress hooks. The vendored delegate-task copy writes 310 KB of documentation images and READMEs into each host's skill folder.

## Findings per lens

### Instruction text still worth cutting

Sizes in bytes. The pointer set is the set the skill says to read once per session (`SKILL.ext.md:8-9`).

| File | Bytes | Loaded |
| --- | ---: | --- |
| `SKILL.ext.md` | 3,570 | once per session |
| `receipt-rules.md` | 1,562 | once per session |
| `dispatcher-operations.md` | 5,560 | once per session |
| `delegation-and-decisions.md` | 6,687 | once per session |
| `stage-execute.md` | 2,211 | Execute claim (`reference_text`) |
| `execution-assign.md` | 12,075 | Execute, told to read (`stage-execute.md:5`) |
| `execution-report.md` | 16,596 | Execute, told to read (`stage-execute.md:5`) |
| `reporting.md` | 3,937 | Execute |
| `stage-pr.md` | 4,504 | PR claim |
| `setup-and-updates.md` | 5,358 | init and upgrades only |
| other 25 references | 1,000 to 3,800 each | per stage or entry point |

Execute, by section and by the condition under which each section applies:

| Section | Bytes | Applies when |
| --- | ---: | --- |
| `execution-report.md:201-271` legacy reporter calls | 5,211 | Progress absent (`reporting.md:132`) |
| `execution-report.md:101-172` light-tier, accept, adopt, trust, orchestrator scope | 4,272 | `delegation.enabled` |
| `execution-assign.md:79-111` delegate_dispatch start, collect, reassign, errors | 2,182 | `delegation.enabled` |
| `execution-assign.md:17-40` dedicated orchestration agent | about 1,800 | lean off (`execution-assign.md:3-5` says not to create it in lean mode) |
| `execution-assign.md:41-48`, `162-170` legacy `init` and budget-overrun calls | about 700 | Progress absent |
| `execution-assign.md:57-78` worker prohibitions | 1,448 | always, but the guard hook enforces `git stash`, `git add -A` and the four ledger verbs (`hooks/guard.py:107-118,136-147`); `delegate_dispatch.py` refuses them with `DELEGATION_WORKER_CONTEXT` |
| the rest: scheduling, batching, blocking waits, turn budgets, phase boundary, F3, T7, T8, consumers, delivery | about 13,000 | always |

Estimated common path (lean on, delegation off, Progress installed): about 13,000 bytes of execution text plus
`stage-execute.md` and `reporting.md`'s projection row, about 16 KB in place of 32.6 KB. Round 1's "review identifiers removed"
(CHANGELOG 1.13.0) missed four headings: `(F1, F2, T0)` at `execution-assign.md:128`, and `(F3)`, `(T7)` and `(T8)` at
`execution-report.md:50,59,78`.

Repeated rules inside the extension. Each copy is worded differently, and exact duplication is 0, as the round-3 duplicates table shows:

| Rule | Copies |
| --- | --- |
| no agent only for reporting | `reporting.md:5`, `execution-report.md:4-6`, `execution-assign.md:14-15,20,36`, `stage-execute.md:9,25` (7) |
| lean mode means no orchestration agent | `delegation-and-decisions.md:43-48`, `execution-assign.md:3-9`, `stage-execute.md:16-20` (3) |
| `DELEGATION_START_UNCERTAIN` recovery | `delegation-and-decisions.md:26-33`, `execution-assign.md:99-104` (2) |
| worker may not stash, add -A or run the ledger verbs | `execution-assign.md:63-77`, `execution-report.md:155-171`, README:130, guard hook (enforced) |

The pointer set costs 17,379 bytes per session. In `delegation-and-decisions.md`, the Delegation section (lines 16-39, about 2,300 bytes)
applies only when the claim carries a `delegation` route. The lean section (lines 41-84, about 2,700 bytes) applies only under lean
policy. The Decisions section (lines 85-102, about 1,700 bytes) applies everywhere. `dispatcher-operations.md:46-56`
restates the stage-to-phase map that `claim` already prints as `project_sync` (`workflow.py:905`).

Across extensions: the workflow command wrappers are 478 to 801 bytes each and only point at the skill. Five of the 13
descriptions have no trigger phrases (`status`, `reconcile`, `ci-report`, `gate-explain`, `worker-brief`, from the benchmark).
The presets' overlays (14,986 bytes) belong to R2.

### Model work the runtime could do

- **Reporting mode.** The coordinator runs `progress_bridge.py mode` once per Execute claim or resume (`reporting.md:13-16`), then reads all three modes' text. The claim could compute the mode and include only that mode's text.
- **Receipt assembly.** `receipt-rules.md:8-14` asks the model to list "every project-relative path relied on" and to include the decision ledger. The runtime already adds both itself: `required_inputs()` (`workflow.py:1485`) and `decisions.json` (`workflow.py:3255`) are fingerprinted in `_stamp` whatever the receipt lists. The stage fields the runtime checks (`_check_stage_rules`, `workflow.py:3208-3247`: `effort_score`, `unresolved`, `answers_applied`, `parent_issue`, `native_links_verified`, `lazy`, `lint`, and `tasks.md` on a merged Plan) are spread over 16 stage references. A missing field costs one failed `complete`, which is recorded as a `rejected-completion` event, plus a retry.
- **Execute protocol selection.** Lean, delegation and reporting mode are all known to the runtime at claim time (`workflow.py:3062-3064`), yet the model reads the text for all eight combinations and decides which apply.

### Code refactoring

- **Oversized modules.** `workflow.py` (3,719 lines) holds identity (`222-610`), policy (`661-1000`), doctor (`1162-1320`), fingerprints and receipt status (`1439-2003`), `Run` (`2213-3438`) and the CLI (`3451-3719`). `delegate_dispatch.py` is 2,397 lines with 82 top-level definitions. A split has to keep the `from workflow import ...` surface: 14 internal scripts, `scope/scripts/scope.py`, `scope/scripts/workflow_policy.py`, `progress/.../model_v3.py`, `scripts/shared/sanduq_freshness.py`, three smoke scripts and the benchmark. The benchmark also monkeypatches `w.fingerprint_files`, `w.git` and `w.doctor` (`benchmark_front_half.py:53-54`), so its counters would miss calls made inside new modules.
- **Duplicated helpers.** These are few. There are four git wrappers: `workflow.git` (`:216`), `sanduq_hash._git` (`:14`), `source_key._git` (`:88`) and `guard.git_output` (`hooks/guard.py:47`, which must stay standalone). Two file-hash helpers do the same job: `delegate_dispatch.file_sha256` (`:1329`) and `execution_tools.sha256_file` (`:80`). Twelve modules call `json.loads(...read_text())` directly instead of `workflow.read`; most are light modules that avoid importing workflow on purpose. The gain from merging is small.
- **Dead code.** `delegation.ledger_state_trusted` (`delegation.py:693`) and `progress_bridge.progress_at_least` (`progress_bridge.py:94`) have no reference anywhere in `extensions/` or `presets/`. `workflow.scope_decision` (`:936`) and `worker_brief.project_result` (`:216`) are referenced only by tests.
- **Options nobody reads.** Some values are validated but never read by any Python module:
  - `updates.policy` (`workflow.py:673`, checked only as a section at `:733`).
  - `execution.checkpoints: every-phase` (`:738`; only prose reads `required-only`).
  - `context.mode: measured-with-estimated-fallback`, which behaves as `measured-only` because only `strict` is compared (`:1414,1430`).
  - `clarification.transport` (`:668`).

  Three keys accept exactly one value: `finalize` (`:750`), `issue_sync.parent_link` (`:748`) and `decisions.transport` (`:768`). Removing any of them would change the policy digest of existing projects, so documenting is the safe step.
- **Review history in code.** 49 comments cite "round N, finding X" (20 in `workflow.py`, 14 in `delegate_dispatch.py`). They cost nothing at runtime and are noise for agents that edit the code.

### Runtime cost per call

Per-command averages from the benchmark (full tier, 750 source files, Windows):

| Command | Calls | ms per call | git per call | `fingerprint_files` per call |
| --- | ---: | ---: | ---: | ---: |
| claim | 17 | 707 | 16.8 (7 at Scope, 29 at PR) | 10.2 |
| complete | 17 | 1,058 | 20.1 (8 at Scope, 36 at Ready) | 12.5 |
| next | 1 | 239 | 7 | 2 |
| revalidate-upstream | 2 | 1,307 | 43.5 | 37 |

Where the calls come from:

- **Fixed cost of `Run.load`, 5 git calls.** `require_issue_repository_binding` and `normalized_remote` both read `remote.origin.url`; `root_commit_sha` runs `rev-list --max-parents=0 --reverse HEAD` (`workflow.py:377`); `is_shallow_clone` runs `rev-parse --is-shallow-repository` (`:391`); and `branch --show-current` (`:2236`). `save` adds `rev-parse HEAD` (`:2961`). The `rev-list` call walks the whole history on every load, so it is cheap on the fixture but grows with repository age. When a root commit is recorded, `identity_matches` accepts on equality or reachability (`:482-487`), so a single `merge-base --is-ancestor` gives the same answer without computing the root.
- **Linear part, one batched `check-attr` per receipt.** `next_stage` calls `receipt_status` for every existing receipt (`:3011-3020`), and each one calls `fingerprint_files` → `portable_files` → `text_attributes` (`sanduq_hash.py:21-30`). `consulted_drift` and the claim baseline (`:3111`) add more.
- **Source tree hashed once per source receipt.** `receipt_status` calls `source_fingerprints(root)` (`:1896`) for each Verify, Review and Ready receipt. That is `git ls-files` plus a read and hash of every source file, 2 to 4 times per command after Verify (benchmark: complete Ready 4, claim PR 3). Claim time rises from about 500 ms before Verify to 1,300-1,570 ms after it.
- **Delegation health on every claim.** With delegation on, each non-coordinator claim runs `delegation.doctor(install=True)` (`workflow.py:3068`). That costs `node --version`, `node --check`, `node delegate.mjs contract` and `node delegate.mjs doctor` per inspected copy (`delegation.py:902-904,870,1124,1132`): at least 4 node processes per claim, outside the 600 s doctor cache.
- **Other features' checkpoints.** `claim` reads and parses every other feature's checkpoint to find a foreign active claim (`workflow.py:3031-3032`), which is O(features) JSON parsing per claim.
- **Import cost.** About 95 ms per CLI start (`python -X importtime`: `packaging.specifiers` 27 ms, `yaml` 13 ms). Acceptable.

Test runtime, measured on this worktree:

| Module | Tests | Wall | Note |
| --- | ---: | ---: | --- |
| `test_delegation` | 181 | 121.2 s | 1,697 subprocesses: about 905 from `setUp` (`init`, `commit`, `remote` 181 each, plus `config`); `repo_identity` 77 × 3; node 120 (`check_copy` 49, `driver_compatibility` 56) |
| `test_workflow` | 44 | 77.8 s | 2,039 git subprocesses; cProfile top: `TextIOWrapper.read` 26.9 s, `BufferedReader.read` 22.3 s, `CreateProcess` 7.7 s |
| `test_install` | 30 | 16.3 s | |
| `test_lint` | 18 | 10.5 s | |

In `test_workflow` the git calls come from: `text_attributes` 633, `workflow.git` 574, and `normalized_remote`, `root_commit_sha` and `is_shallow_clone` at 190 each (one `repo_identity` per `Run.load`). Each test's `setUp` adds 5 calls (`init`, two `config`, `commit`, `remote add`). The suite total of 25 to 35 minutes (handoff note) is consistent with these rates across 55 modules.

### Install and upgrade

The package holds 128 non-test files (`package.py:12` excludes `tests`). With delegation enabled, `install_skill_locked` copies the whole vendored
`delegate-task` folder (531,262 bytes, 13 files) into `.claude/skills/delegate-task` or `.agents/skills/delegate-task`, once per host
(`delegation.py:1055`, which ignores only `test`, `runs` and `node_modules`). 309,874 bytes of that is never read at runtime: two PNG
(200,662), two HTML (30,655), two SVG (25,699) and `README.md` plus `README.ar.md` (52,858). `SKILL.md` links only
`contracts/check-runner.md`, and `SKILL_FILES` needs `delegate.mjs`, `SKILL.md` and `contracts/result-schema-v2.md` (`delegation.py:813`).
The installer and upgrade path in general belong to R6.

### Host divergence after rounds 1 and 2

- **Guard on Codex.** Claude runs the guard from `.claude/settings.json`. Codex runs it only in a trusted project after `/hooks` approval, and the installer only prints `CODEX_HOOK_APPROVAL` (`hosts.py:47`, `install.py:860`). `doctor` and `status` never check the approval, although `progress_bridge.hooks_state` (`:187-200,264`) reads `trusted_hash` for the Progress hooks. On an unapproved Codex worktree, the prose at `execution-assign.md:63-77` is the only enforcement.
- **Hidden skills.** `hide_hook_skills` acts on Claude only (`hosts.py:244-257`). Codex has no hide flag, so all 13 workflow entries and the 5 Scope hook entries stay in its catalog: 3,241 description characters for workflow alone.
- **Reporting mode.** `reporting.md:19-20` tells a Codex coordinator to pass `--host codex` by hand, because the bridge detects the host from the environment. The claim knows the host from `active_host(root)` (`workflow.py:994`).

## Defects

| Defect | Effect | Where |
| --- | --- | --- |
| Review identifiers left in headings | Text the 1.13.0 changelog says was removed; meaningless to a consumer | `execution-assign.md:128`; `execution-report.md:50,59,78` |
| Legacy reporter text loaded in every mode | 5.2 KB per Execute even when Progress is installed | `execution-report.md:201-271`; `stage-execute.md:5` |
| Lean Execute loads the orchestration-agent protocol it forbids | About 1.8 KB of contradictory instruction on the default lite and standard tiers | `execution-assign.md:3-9` against `17-40` |
| Full-history `rev-list` on every `Run.load` | Load cost grows with repository age; 190 calls in `test_workflow` | `workflow.py:377,408,2227` |
| Source tree hashed once per source receipt within one command | 2 to 4 full hashes per claim or complete after Verify; claim time about 3x | `workflow.py:1896,3011-3020` |
| Delegation health re-probed with node on every claim | At least 4 node processes per claim with delegation on; not cached like doctor | `workflow.py:3068`; `delegation.py:902-904,1124,1132` |
| Codex guard approval unchecked | Guard may silently not run on Codex; `doctor` stays green | `hosts.py:47`; `progress_bridge.py:264` covers Progress only |
| Receipt rules ask for inputs the runtime adds itself | Model work and longer receipts with no effect | `receipt-rules.md:8-14`; `workflow.py:3255-3257` |
| Delegate-task docs images installed into skill roots | 310 KB per host copy, never read | `delegation.py:1055`; `assets/delegate-task/assets/*` |
| Functions with no caller | Dead code | `delegation.py:693`; `progress_bridge.py:94` |
| Validated but unread policy values | Settings that do nothing; `measured-with-estimated-fallback` reads as a feature it is not | `workflow.py:673,738,742,668` |
| Five descriptions without trigger phrases | Weaker routing for `status`, `reconcile`, `ci-report`, `gate-explain`, `worker-brief` | `extension.yml` `provides.commands` |

## Options

Cost basis for `tok` and `time`. One full-tier feature, dispatcher side, excluding the workers' implementation tokens: instruction loads of
about 51k tokens (benchmark), claim and complete output of about 12k (49,073 bytes), plus receipts, handoff and decision traffic of
10k to 20k, for about 75k to 85k tokens in all. Runtime time is the benchmark's 33.6 s of command time plus model round-trips, about 60 to 80 per
feature. Test-time effects are stated separately in `time`.

### W1. One git and fingerprint pass per command

- title: Memoise repository identity, source inventory and git attributes per CLI invocation
- what: The change has four parts.
  - In `workflow.py`, a per-process memo keyed by the resolved root holds `normalized_remote`, `is_shallow_clone` and the `origin` URL that `github_repository` reads. It is cleared at the start of `main()` and by a `clear_caches()` helper the tests call in `setUp`.
  - `verify_checkpoint_identity` stops calling `root_commit_sha` when the checkpoint records a root commit. `root_commit_still_reachable` (one `merge-base --is-ancestor`, `:431`) already gives `identity_matches` the same answer. The full `rev-list` stays for `start` and `relocate`, which record the root.
  - `source_fingerprints(root)` is computed once per command and reused by every `receipt_status` and the claim baseline.
  - `next_stage` prefetches one `fingerprint_files` call over the union of all receipts' dependency paths, so `text_attributes` runs once instead of once per receipt.
  - In the tests, the shared `setUp` (`test_workflow.WorkflowTests.setUp`, which `test_delegation`, `test_install` and others reuse) builds the initial git repository once per class and copies its `.git` per test, replacing 5 git processes per test.

  Receipts, events and refusals are unchanged.
- effort: M
- tok: [0, 0]
- time: Runtime [0.30, 0.45] of command time. git calls per claim or complete drop from 7-36 to about 6-9 flat, and source hashes from up to 4 to 1. That is about 10 to 15 s of the 33.6 s on the fixture and more on a large or old repository. Tests: `test_workflow` [0.25, 0.40] (1,203 of its 2,039 git calls are identity or attribute calls) and `test_delegation` [0.30, 0.50] (about 905 of its 1,697 subprocesses come from `setUp`, and 231 are identity calls).
- obs: unchanged. The same checks run on the same values; lifecycle events and receipt fields are identical.
- policy: none
- pros:
  - The largest runtime and test-time lever in the extension.
  - Fixes the full-history `rev-list` cost before it shows up on large repositories.
  - No instruction or contract change.
- cons:
  - Any long-lived importer must call `clear_caches()`. The scope extension imports `workflow` in-process (`scope/scripts/workflow_policy.py`) and needs one call where it re-reads identity.
  - The benchmark's `git_subprocess` counter changes meaning; record a new baseline.
  - Prefetching changes the order of `check-attr` calls, not their results.
- files: `extensions/workflow/scripts/workflow.py`, `extensions/workflow/scripts/sanduq_hash.py` (accept a precomputed attribute map), `extensions/workflow/tests/test_checkpoint_identity.py`, `extensions/workflow/tests/test_front_half_runtime.py`, `CHANGELOG.md`
- tests:
  - Keep green: all of `test_checkpoint_identity.py` (58 tests, including the relocate, shallow and unrelated-history cases), `test_eol_fingerprints.py`, `test_freshness.py`, `test_receipt_contract.py`, `test_ci_revalidation.py`.
  - Add: claim on a feature with Verify, Review and Ready receipts calls `source_fingerprints` once.
  - Add: `Run.load` with a recorded root makes no `rev-list` call.
  - Add: the identity memo is keyed by root and cleared by `clear_caches()`.

### W2. The Execute claim carries only the protocol that applies

- title: Compose Execute's `reference_text` from mode-selected fragments
- what: Split `execution-assign.md`, `execution-report.md` and `reporting.md` into fragments under `references/execute/`:
  - `core.md`: scheduling, batching, blocking waits, turn budgets, phase boundary, structured results, verification summaries, consumers checklist and delivery, about 13 KB, trimmed of the four restated reporting and lean rules.
  - `orchestrator.md`: the dedicated orchestration agent, loaded when lean is off.
  - `delegation.md`: delegate_dispatch start, collect, reassign, accept, adopt, trust and scope, loaded when `delegation.enabled`.
  - `reporting-projection.md`, used in projection and refresh mode.
  - `reporting-legacy.md`: the legacy calls and init, used in legacy mode.

  `claim` for `execute` computes the reporting mode with `progress_bridge.mode(root, active_host(root))`. It prints `reporting: {mode, reason}` and a `reference_text` that joins `stage-execute.md` with the selected fragments. The old file names stay as one-line pointers for overlays that name them. The review identifiers go. `stage-execute.md` drops "read execution-assign.md, then execution-report.md".
- effort: M
- tok: [0.06, 0.09]. The common path (lean on, delegation off, Progress installed) loads about 16 KB instead of 32.6 KB, about 4.2k tokens per Execute claim and again on each resume. Delegation-on projects save about half of that.
- time: [0.01, 0.03]. One `progress_bridge.py mode` call and two reference reads leave the model's path; there is less conflicting text to reconcile.
- obs: unchanged. Every gate, ledger check and report call stays; the claim now also records which reporting mode it chose.
- policy: none
- pros:
  - The biggest instruction cut left in the extension.
  - Removes the lean/orchestrator contradiction.
  - The mode decision moves from prose to the runtime that already holds the facts.
- cons:
  - Five fragment files to keep consistent.
  - The benchmark's `STAGE_EXTRAS['execute']` must follow the claim's composition instead of fixed file names.
  - A coordinator that re-reads `execution-report.md` by habit finds a pointer.
  - `progress_bridge` becomes a claim-time import.
- files: `extensions/workflow/skills/workflow/references/{execution-assign,execution-report,reporting,stage-execute}.md`, `extensions/workflow/skills/workflow/references/execute/*.md` (new), `extensions/workflow/scripts/workflow.py` (`reference_text`, `claim`), `extensions/scripts/benchmark_front_half.py`, `CHANGELOG.md`
- tests:
  - Keep green: `test_reporting_instructions.py`, `test_skill_split.py`, `test_lean_execution.py`, `test_lean_native_integration.py`, `test_execution_protocol_b11.py` (check which pin the old file text), `test_progress_runs.py`.
  - Add: one Execute claim for each of the 8 combinations of lean, delegation and reporting mode; each `reference_text` contains its fragments and no others; every fragment is referenced by at least one combination.

### W3. A conditional pointer set

- title: Read delegation text only when the claim routes through delegation or lean
- what: Split `delegation-and-decisions.md` into `decisions.md` (Invoking and Decisions, about 2.5 KB, still in the once-per-session set) and `delegation.md` (Delegation and Opt-in lean execution, about 4.2 KB). Change `SKILL.ext.md:8-9` and step 4 so that `delegation.md` is read only when a claim carries `delegation` or `environment`. In `dispatcher-operations.md`, replace the restated stage-to-phase map (`:48-51`) with "run `project_sync.command` as printed". Keep the anchor names that commands and overlays link to (`#delegation`, `#opt-in-lean-execution`) by giving the new file those headings.
- effort: S
- tok: [0.03, 0.06]. About 4.6 KB less per session when delegation and lean are off, about 2.3 KB less under lean.
- time: [0, 0.01]
- obs: unchanged
- policy: none
- pros: Small, mechanical cut on a cost paid every session; no runtime change.
- cons:
  - Links from overlays and `execution-assign.md` (`#delegation`) must be retargeted.
  - The benchmark's `POINTER_SET` must change with it.
- files: `extensions/workflow/skills/workflow/SKILL.ext.md`, `references/delegation-and-decisions.md` → `references/decisions.md` and `references/delegation.md`, `references/dispatcher-operations.md`, `references/execution-assign.md` (links), `extensions/scripts/benchmark_front_half.py`, `presets/workflow/commands/*.md` (links only; coordinate with R2)
- tests:
  - Keep green: `test_skill_split.py`, `test_portable_paths.py`, `extensions/scripts/check_docs.py` (link check).
  - Add: every `references/...#anchor` named in the skill, commands and overlays resolves.

### W4. A receipt skeleton in the claim

- title: `claim` prints the receipt fields the runtime will check
- what: `claim` adds `receipt_template` with these fields:
  - `stage` and `outcome: "passed"`.
  - Empty `summary`, `inputs` and `evidence`.
  - `auto_inputs`: what `_stamp` adds anyway, from `required_inputs()` and `decisions.json` when present.
  - The stage fields `_check_stage_rules` requires for this stage and tier, with their types: Scope `effort_score` when profiles are on; Clarify `unresolved: 0` and `answers_applied`; merged Plan `tasks.md` in `inputs`; Analyze-as-lint `lint`; Tasks-to-Issues `parent_issue`, `native_links_verified` and `lazy`; PR `pr_url`, `images_verified` and `image_verification`.

  The table comes from one constant beside `_check_stage_rules`, so the template and the refusal cannot drift. `receipt-rules.md:8-14` shrinks to the judgement rules: no passed receipt for failed or pending work, what counts as evidence, and `input_roles`. The sentence about adding the decision ledger goes.
- effort: S
- tok: [0.01, 0.02]. About 600 bytes off `receipt-rules.md` per session. Field names stop being looked up across stage references, and a rejected-and-retried `complete` (about 1k tokens) is avoided whenever one would have happened.
- time: [0.01, 0.03]. Fewer `rejected-completion` round-trips.
- obs: improved. Fewer `rejected-completion` events, and those that remain are real.
- policy: none
- pros:
  - Moves a deterministic list from 16 references into the runtime that enforces it.
  - Claim output grows by about 300 bytes per stage.
- cons:
  - The claim output budget grows (`claim_stdout_bytes` +5%).
  - Stage references that name receipt fields should drop them in the same change, or they drift.
- files: `extensions/workflow/scripts/workflow.py` (`claim`, a `STAGE_RECEIPT_FIELDS` constant used by `_check_stage_rules`), `references/receipt-rules.md`, `references/stage-*.md` (field lists only), `CHANGELOG.md`
- tests:
  - Keep green: `test_receipt_contract.py`, `test_front_half_runtime.py`, `test_lint.py`.
  - Add: for each stage, a receipt built from `receipt_template` plus one evidence file passes `_check_receipt` and `_check_stage_rules`; removing any listed field refuses with the documented code.

### W5. Codex guard approval in doctor and status

- title: Warn when the Sanduq guard hook is registered but not approved on Codex
- what: Move the `trusted_hash` reading out of `progress_bridge.hooks_state` (`:187-200,264`) into a small function both callers use. In `workflow.doctor(project=True)`, on a Codex install (`.codex/hooks.json` holds the guard, `hosts.is_guard`), add the warning `GUARD_HOOK_UNAPPROVED` with the `CODEX_HOOK_APPROVAL` text when the project is not trusted or the guard's hook key has no `trusted_hash`. It is a warning, not an error, so the green doctor cache and claims are unaffected. `status --feature` repeats it. Shorten `execution-assign.md:63-77` to one sentence: the guard enforces it, and on Codex it needs approval, which doctor reports.
- effort: S
- tok: [0.005, 0.01]. About 1 KB of prohibitions leaves the Execute text.
- time: [0, 0]
- obs: improved. The missing enforcement becomes visible where it was silent.
- policy: none
- pros:
  - Closes the one host gap left in enforcement.
  - Reuses the logic Progress already ships.
  - No new hook.
- cons:
  - As in `progress_bridge`, the stored hash is not verified, so a guard changed after approval is not detected; the README notes the same limit.
  - Touches a module the Progress bridge owns.
- files: `extensions/workflow/scripts/progress_bridge.py` (extract), `extensions/workflow/scripts/workflow.py` (`host_warnings`, `doctor`), `extensions/workflow/scripts/hosts.py`, `references/execution-assign.md`, `README.md`
- tests:
  - Keep green: `test_hosts.py`, `test_guard_hook.py`, `test_progress_integration.py`, `test_host_files.py`.
  - Add: a Codex fixture with an unapproved guard warns; an approved one does not; a Claude-only project never warns.

### W6. Cache the delegation health probe

- title: Reuse a green delegation health result across claims
- what: With `delegation.enabled`, `claim` runs `delegation.doctor(install=True)` for every non-coordinator stage (`workflow.py:3068`), which costs four or more node processes. Store a green result in the existing `doctor-cache.json`, under its own key. The key is the driver's sha256, the `node --version` string, the skill path, `install_scope` and the host. Reuse it for the doctor cache's 600 s while the key matches. A cache miss, a non-green result or a changed driver hash re-probes exactly as today. `annotate_tasks` still runs per claim. The explicit `doctor` always probes fresh.
- effort: S
- tok: [0, 0]
- time: [0.02, 0.06] of command time on delegation-enabled projects: about 0.2 to 0.5 s saved on each of about 15 claims. This is an estimate from process counts, not measured: the benchmark runs with delegation off.
- obs: unchanged. Same refusals on a broken driver; the cache records when it was filled.
- policy: none
- pros: Same pattern and lifetime as the doctor cache from 1.13.0; no behaviour change for a broken install.
- cons:
  - A driver deleted within 600 s is detected at `start`, not at claim. `delegate_dispatch.start` already checks the driver.
- files: `extensions/workflow/scripts/workflow.py` (`claim`, cache helpers), `extensions/workflow/scripts/delegation.py` (expose the key), `references/dispatcher-operations.md` (doctor paragraph)
- tests:
  - Keep green: `test_delegation.py` health and install tests, `test_front_half_runtime.py` doctor cache tests.
  - Add: a second claim within 600 s makes no node call; a changed driver hash re-probes.

### W7. Install only the runtime part of delegate-task

- title: Leave delegate-task's documentation assets out of the installed skill copy
- what: Widen the copy's `ignore_patterns` in `install_skill_locked` (`delegation.py:1055`) to `assets`, `README*.md` and `*.png`. The skill folder keeps `SKILL.md`, `delegate.mjs`, `check-runner.mjs` and `contracts/`. The vendored source in `assets/delegate-task` stays byte-identical to upstream, so `vendor.py` pins are unaffected. Upstream (sanduq-skills agent-tools) may later ship a runtime-only layout; record that in the R6 notes. Also check that `check_copy`, `delegate.mjs contract` and `doctor` do not read the excluded files.
- effort: S
- tok: [0, 0]
- time: [0, 0.01]. Install copies 221 KB instead of 531 KB per host.
- obs: unchanged
- policy: none
- pros: About 310 KB and 8 files fewer in each consumer's skill discovery root, which some hosts index; a one-line change.
- cons:
  - A user who opens the installed skill folder finds no README; it stays in the package and upstream.
  - `inspect_skill` must not treat an older full copy as stale only because of extra files (it does not today: `SKILL_FILES` is a minimum).
- files: `extensions/workflow/scripts/delegation.py`, `CHANGELOG.md`
- tests:
  - Keep green: `test_delegation.py` install, reuse and rollback tests (`:263` copies the bundled skill).
  - Add: the installed copy contains no `assets/` and passes `check_copy`.

### W8. Cleanup: dead functions, unread policy values, review history

- title: Remove dead code and document the policy values that do nothing
- what:
  - Delete `delegation.ledger_state_trusted` and `progress_bridge.progress_at_least`, which have no callers. Move `workflow.scope_decision` and `worker_brief.project_result` into the tests that use them, or delete them with their tests if nothing in Scope or Progress needs them (grep showed none).
  - Keep the unread policy keys for digest stability, and say so where they are validated: `updates.policy`, `execution.checkpoints: every-phase`, `context.mode: measured-with-estimated-fallback` (same as `measured-only`) and `clarification.transport`. Add a comment and a README "accepted, no effect" line instead of new behaviour.
  - Remove the 49 "round N, finding X" citations from docstrings, keeping the reasons they explain.
  - Add trigger phrases to the five descriptions the benchmark flags.
- effort: S
- tok: [0, 0.005]. Catalog descriptions grow slightly; routing improves.
- time: [0, 0]
- obs: unchanged
- policy: none
- pros: Less to read for every agent that edits these modules; settings no longer suggest behaviour that does not exist.
- cons:
  - Rewording descriptions changes the catalog text both hosts list.
  - Removing a public function could break an out-of-tree caller; none is known.
- files: `extensions/workflow/scripts/{delegation,progress_bridge,workflow,worker_brief,delegate_dispatch,ci_gate,verify_affected,apply_pending}.py`, `extensions/workflow/extension.yml`, `extensions/workflow/commands/{status,reconcile,ci-report,gate-explain,worker-brief}.md`, `README.md`, the affected tests
- tests:
  - Keep green: the full module set touched (`test_delegation.py`, `test_progress.py`, `test_worker_brief.py`, `test_workflow.py`).
  - Add: none beyond the description check `benchmark_instructions.py` already reports.

### W9. Split workflow.py behind its import surface

- title: Move identity, policy, doctor and receipt status out of `workflow.py`
- what: Move four blocks into new modules, and have `workflow.py` re-export every moved name so that `from workflow import ...` keeps working for its 14 internal and 7 external importers:
  - `identity.py` (`workflow.py:222-610`)
  - `policy.py` (`661-1000`)
  - `health.py` (`1162-1320`)
  - `receipts.py` (`1439-2003`)

  `workflow.py` keeps `Run` and the CLI, about 1,600 lines. Tests and the benchmark that monkeypatch `w.fingerprint_files`, `w.git` or `w.doctor` must patch the defining module. Do this after W1 so the memo lives in `identity.py` and `receipts.py` from the start. Leave `delegate_dispatch.py` (2,397 lines) as it is; its subcommands share ledger state, and a split there buys less.
- effort: L
- tok: [0, 0] for consumers. Agents editing the runtime read 30 to 90 KB modules instead of 228 KB.
- time: [0, 0] for the runtime. Import time unchanged.
- obs: unchanged
- policy: none
- pros:
  - Each concern becomes reviewable on its own.
  - Edit sessions on the runtime cost less.
  - The memo of W1 gets a natural home.
- cons:
  - The widest blast radius of any option: every `patch.object(w, ...)` in 55 test modules has to be checked, along with the benchmark's counters and the scope extension's imports.
  - No consumer-visible gain, so it is optional.
- files: `extensions/workflow/scripts/workflow.py`, `extensions/workflow/scripts/{identity,policy,health,receipts}.py` (new), `extensions/scripts/benchmark_front_half.py`, tests that patch moved names
- tests:
  - Keep green: the full workflow suite (this option requires one full run), `extensions/scope/tests`, `extensions/scripts/tests`.
  - Add: an import-surface test that every name in the old `__all__`-equivalent list is importable from `workflow`.

## Double-counting notes for the orchestrator

- W2 and W5 both shorten `execution-assign.md:63-77`. Count the 1 KB once, in W2, when both are chosen.
- W3 and W2 both touch the lean-mode text. W3 moves the policy description and W2 drops the restatements, so their savings add.
- W1's test-time gain overlaps any CI or test-sharding option in R6's `X` set.
- W9 depends on W1 for ordering only.
- W6 and W7 are independent of the rest.
