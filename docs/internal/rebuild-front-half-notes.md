# Rebuild the front half: stream notes

Each stream appends under its heading: changed files, tests run with counts, deviations from the
contract with the reason, and anything the orchestrator must wire or decide.

## S0 Measurement

Files: `extensions/scripts/benchmark_front_half.py`, `extensions/scripts/benchmark_compare.py`,
`extensions/scripts/tests/test_benchmark_front_half.py` (3 tests; `discover -s extensions/scripts/tests`
93 tests OK), `docs/internal/benchmarks/{README.md,before-full.json,before-lite.json}`. Method and
reproduction in `docs/internal/benchmarks/README.md`.

BEFORE (sanduq-baseline @ 105508f, 750 source files; full and lite are the same workload because the
baseline has no profiles, `--tier` ignored): 25 stages run, 22 model passes, 9 of them re-run by the
per-stage recovery after the spec edit; 53 CLI commands, 54,313 stdout bytes (claim 44,064, complete
2,865, start 6,312); 25 `doctor` calls (one per claim), 495 `fingerprint_files`, 26 `source_fingerprints`,
187 `git()` and 874 git subprocesses; checkpoint 256,277 bytes (inline source inventories), handoff 587,
lifecycle 24,000; static instruction load 344,449 bytes, about 86k tokens (Execute 52.6 KB, Scope 30.7
KB, Clarify 29.3 KB, Specify 28.7 KB; pointer set 25.9 KB once, linked references 11.2 KB once).
Wall time 62-89 s for identical runs on this host while other streams ran tests: compare counters and
bytes, treat wall time as indicative only.

Deviations and decisions:
- The fixture `scope-source.json` also carries `dependencies: []` so a lean-execution PR receipt (on by
  default for lite and standard, D5) can bind its lint; harmless where lean is off. The lean PR receipt
  adds `pr_body_file`, `pr_lint_file`, `pr_body_sha256` computed with the runtime's own
  `execution_tools.pr_lint`.
- The post-Execute spec edit adds a prose line (no FR id) so `workflow:lint` does not ask for a model
  Analyze; if lint does ask, the harness completes Analyze with `command: speckit.analyze` and counts a
  model pass.
- `revalidate-upstream --through` stops at `taskstoissues` (Execute is not an upstream stage), so the
  new-runtime recovery is: `--plan`, one `--receipt` for `needs_receipt` (plan entries list `tasks.md` on
  merged tiers, the Analyze entry carries a fresh `lint` result when Analyze ran as `workflow:lint`),
  then re-claim Execute. It counts as one model pass plus Execute. Any refusal is recorded in
  `meta.recovery_error` and the harness falls back to per-stage re-claims.
- `lint.py` runs as a subprocess, so its internal calls are not in the counters (its time and stdout are).
- Smoke runs against the in-progress working tree (10 source files) completed on all three tiers with
  `revalidate-upstream` as the recovery path. These are not the AFTER numbers.

AFTER (working tree @ bd3c4d3, 750 source files, run on the orchestrator's request): both tiers
recovered with `revalidate-upstream` (no fallback). Tables in `docs/internal/benchmarks/compare-full.md`
and `compare-lite.md`. Full / lite deltas: instruction bytes -40.9% / -49.3% (A1 target 40% met),
model passes 22 -> 15 / 9, claims 25 -> 17 / 12, doctor 25 -> 1, checkpoint 256 KB -> 35.7 / 27.9 KB,
stdout -12.0% / -19.7%, git subprocesses -14.9% / -47.5%. Up: handoff.md (+26% / +49%, the marked
block) and linked-once references (11.2 -> 24.4 KB, text moved behind pointers; net total still down).
`extensions/workflow` unit-test discover timed out at 1700 s on this busy host, so I could not confirm
that suite myself; `discover -s extensions/scripts/tests` is 93 OK on the final tree.

## S1 Runtime

Changed files: `extensions/workflow/scripts/workflow.py`, `lean_policy.py`, `lifecycle.py`, `ci_gate.py`
(minimal: inventory side files and tiered stage list), `schemas/policy-v1.schema.json`,
`schemas/checkpoint-v1.schema.json`, `schemas/receipt-v1.schema.json`, `docs/workflow/schemas.md` (it lists
fields, so the new ones were added there). New test file `extensions/workflow/tests/test_front_half_runtime.py`
(31 tests). Adjusted tests (one-line reasons):
- `test_receipt_contract.py` (2 tests), `test_ci_revalidation.py` (2 asserts): Verify/Review/Ready inventories
  now live in side files; the tests read them through `source_fingerprints_of` (and read the old inventory
  before Complete supersedes it).
- `test_eol_fingerprints.py` (1 test), `test_skill_inventory.py` (3 calls): the line-ending scan and the skill
  inventory now run only in the explicit doctor, so the tests pass `explicit=True`.
- `test_lean_execution.py`, `test_lean_native_integration.py` (1 lambda each): their `fingerprint_files` stub
  now accepts the new `normalize` keyword.

Tests: `test_front_half_runtime.py` 31 OK. Prescribed subset (test_workflow, test_lifecycle, test_receipt_contract,
test_freshness, test_ci_gate, test_lean_execution, test_contracts) plus test_front_half_runtime, test_ci_revalidation,
test_eol_fingerprints, test_skill_inventory all OK (138 + 59 + 141 runs). Full suite in two halves from
`extensions/workflow/tests`: 1176 tests; the only failures are 18 that fail identically on the untouched
`../sanduq-baseline` on this machine (test_verification_plan 13 errors + 1 failure, test_execution_tools 3,
test_memory_handoff 1: `OSError [Errno 22]` hashing the WindowsApps `python.exe` alias), plus one
test_lean_native_integration stub error fixed and rerun green afterwards. `test_verification_plan.py` was not
edited (its receipts are legacy inline and still read).

Interface, exact names:
- Policy keys (all optional, absent = old behaviour): `profiles: {enabled, lite: {max_score}, standard:
  {max_score}}`; `clarification.max_questions_per_round`, `clarification.in_session_first_round`;
  `artifacts: {budgets: {spec_kb, plan_kb, research_kb, tasks_detail_lines}, enforce: lite-standard|all|warn}`;
  `issue_sync.taskstoissues: required|phase-lazy`; `project_sync: {points: [specify, plan, analyze,
  taskstoissues, execute, pr]}`; `scope.board_cache_seconds` (int >= 0). Errors: `PROFILES_POLICY_INVALID`,
  `CLARIFICATION_POLICY_INVALID`, `ARTIFACTS_POLICY_INVALID`, `PROJECT_SYNC_POLICY_INVALID`,
  `SCOPE_BOARD_CACHE_INVALID`, `TASK_ISSUES_REQUIRED`. `policy_cutoff`: `profiles` -> plan, `artifacts` ->
  analyze, `issue_sync` -> taskstoissues; `project_sync`, `scope.board_cache_seconds`,
  `clarification.max_questions_per_round` and `clarification.in_session_first_round` reach no stage.
- Module API: `tier(policy, score)`, `stages(policy, tier=None)`, `required_inputs(root, feature, stage,
  tier=None)` (None reads the tier frozen in the feature checkpoint), `resolve_commands(root, policy,
  tier=None)` (lite/standard map `analyze` to `workflow:lint`), `lean_policy.enabled(policy, tier=None)`,
  `lean_policy.coordinator_owned(policy, stage, commands, tier=None)`, `source_fingerprints_of(root, receipt,
  feature=None)`, `side_effects(policy, feature, stage)`, `project_sync(policy, stage)`,
  `cached_doctor(root, policy, dependency_digest=None)`, `doctor(..., explicit=False)`,
  `upstream_drift(...)`, `Run.revalidate_upstream(through, receipts=None, plan=False, actor=None)`,
  `first_phase_tasks(text)`, `replace_file(source, target)`.
- Checkpoint: `profile: {tier, score, fixed_at}` (frozen at the first Plan claim when `profiles.enabled`),
  `skipped: {stage: reason}` (`tasks: merged into plan (<tier> tier)`, lite also `qa_analyze`,
  `manual_analyze`, `qa_document`, `manual_update: lite tier`), `active.mode: initial|revalidate|bind-only`.
- Receipts: Scope `effort_score` (1 2 3 5 8 13 21; `EFFORT_SCORE_REQUIRED` when profiles are enabled); merged
  Plan must list `<feature>/tasks.md` in inputs (`MERGED_TASKS_REQUIRED`); Analyze on lite/standard needs
  `lint: {ok: true, findings: n}` with no `command` or `command: workflow:lint` (`LINT_RECEIPT_REQUIRED`), or a
  model Analyze receipt with `command: speckit.analyze` (stored with that command); Tasks-to-Issues under
  `phase-lazy` needs `lazy: true` (`TASK_ISSUES_LAZY_REQUIRED`) and every first-phase task linked in
  `workflow/task-issues.json` (`TASK_MAPPING_FIRST_PHASE_INCOMPLETE`); Ready's `TASK_MAPPING_INCOMPLETE` now
  lists the unmapped ids and, under phase-lazy, says to run `task_issues.py --phase "<Phase heading>"`.
  Runtime-only fields: `source_inventory: {path, sha256}`, `text_fingerprints`, `revalidated_upstream`.
- Lifecycle events added: `skipped`, `revalidate-upstream` (episode id `revalidate-upstream:<hex>`, one per
  operation).
- CLI: `claim --verbose`, `complete --verbose`, `status --feature <f>` (`--runs` now optional),
  `revalidate-upstream --feature specs/<f> --through <specify..taskstoissues> [--receipt <file>] [--plan]
  [--actor <name>]`, `doctor [--project]` (always fresh, refreshes `.specify/workflow/runtime/doctor-cache.json`
  when green with `--project`).
- Claim output: `reference_text`, `side_effects` (globs, `*` stays in one folder), `project_sync`
  (bool), `merged: ['tasks']` and `profile` on a lite/standard Plan claim, `mode: bind-only` on a Specify claim
  whose spec.md starts with `<!-- sanduq-scope:rendered <64 hex> -->`. `baseline` printed only with
  `--verbose` (still stored). Complete prints `{ok, stage, next: {stage, command, reason[, status]}}`.
- `status` now also returns `status`, `next_action`, `completed`, `profile`, `skipped`, `pause`, and `active`
  without `baseline`.
- Resume prompt: `Run python .specify/extensions/workflow/scripts/workflow.py status --feature <f> and continue
  with speckit.workflow.continue; do not read checkpoint.json directly.` `handoff.md` keeps everything outside
  `<!-- sanduq-handoff:begin -->` ... `<!-- sanduq-handoff:end -->`.

Deviations and decisions:
- `source_fingerprints_of(root, receipt, feature=None)`: the side-file path is feature-relative, so reading the
  new form needs the feature (legacy inline receipts need only the receipt). Inventory rewrites (revalidate,
  qa_document advancing a Verify/Review inventory) write a new file name with a suffix and delete the old one
  only after the checkpoint is saved, so a crash never leaves a checkpoint naming a file with another hash.
- Whitespace-insensitive drift needs the old normalised hash, so every receipt now stores
  `text_fingerprints` for its Markdown fingerprints (drift decision only; `fingerprints` stay byte hashes). A
  receipt recorded before this release has none, so `revalidate-upstream` counts any change to it as real.
  Normalisation: CRLF to LF, trailing spaces/tabs per line, final newlines.
- `revalidate-upstream`: stages whose only drift is whitespace are re-stamped without an entry; stages with a
  real change (or removed) need an entry; an entry for a current stage is refused
  (`REVALIDATE_UPSTREAM_STAGE_NOT_STALE`). Entries may also restate `input_roles`, `evidence_snapshots`,
  `lint` and the carried stage fields; `unresolved`, `answers_applied`, `parent_issue`,
  `native_links_verified`, `lazy`, `effort_score` are carried from the replaced receipt. `--through` is limited to
  specify..taskstoissues (source stages need a claim). A policy change reaching those stages refuses
  (`POLICY_CHANGED`).
- Compact `complete` keeps `memory_handoff` when it is the reason `ok` is false.
- Changing `profiles` drops the frozen profile; the cutoff forces Plan again, which fixes it anew. Profiles
  enabled after Scope without an `effort_score` freeze `full`.
- `doctor()` callers other than the explicit command (init, ci, migrate, hosts, install) no longer get the eol
  warning or skill inventory.
- `workflow.write` retries `os.replace` on PermissionError up to 10 times (20-50 ms), also used for inventory
  side files (orchestrator request).

For the orchestrator:
- `delegate_dispatch.py` and `delegation.py` call `lean_policy.enabled(policy)` without a tier, so for a
  lite/standard feature they still see lean off unless the policy enables it. Passing
  `workflow.feature_tier(root, feature)` there would align them (not my files).
- S4 must document: the claim fields above, `revalidate-upstream` and its `--plan`/`--receipt` shape, the
  resume prompt, handoff markers, `merged: ['tasks']`, `workflow:lint` recording, `side_effects`,
  `project_sync`, `mode: bind-only`, `lazy: true` and the per-phase `task_issues.py --phase` run in Execute.
- `reference_text` is the single stage file; on a merged Plan claim S4's stage-plan.md must carry the Tasks
  instructions (the runtime does not concatenate stage-tasks.md).
- I did not run `git stash`; I verified workflow.py after S3's merge (no duplicate definitions, all S1
  symbols present) and reran the test subset afterwards.

Follow-up (orchestrator round 2):
- Lean tier in the dispatcher: `lean_policy.feature_tier(root, feature)` (new; `workflow.feature_tier` now
  delegates to it, so `delegation.py` needs no `workflow` import) and `lean_policy.admit(..., tier=None)`.
  `delegate_dispatch.py`: `lean_enabled(root, feature=None)`, `driver_env`, `launch`, `candidate_start`, `start`,
  `retry_plan(..., tier=None)`, `collect` and `reassign` pass the feature's frozen tier; `delegation.py
  annotate` does too. A lite/standard feature is lean in the dispatcher unless `lean_execution.enabled: false`.
- Tests added to `test_front_half_runtime.py` (now 35): `LeanTierDispatchTests` (lite: lean, claim token passed
  to workers, `stage:execute` refused as coordinator-owned, no automatic retry; full: lean only with
  `lean_execution.enabled: true`; lite with explicit false: off) and `LintRecordEndToEndTests` (real
  `lint.py --record --token` on a lite fixture: stored `command: workflow:lint`, `lint.ok`, next is
  taskstoissues).
- Re-run: test_workflow, test_lifecycle, test_receipt_contract, test_contracts, test_front_half_runtime, test_lint,
  test_lean_execution, test_lean_native_integration 198 OK; test_freshness, test_ci_gate, test_delegation,
  test_ci_revalidation, test_eol_fingerprints, test_skill_inventory 330 OK.

## S2 Lint and task issues

Files: `extensions/workflow/scripts/lint.py` (new), `extensions/workflow/scripts/task_issues.py`,
`extensions/workflow/tests/test_lint.py` (new, 18 tests), `extensions/workflow/tests/test_task_issues.py`
(+5 tests, 25 total). `worker_brief.py` untouched. No existing test changed.

Validation: `python -m unittest extensions.workflow.tests.test_lint extensions.workflow.tests.test_task_issues -q`
runs 43 tests, and all three consecutive runs passed after S1's `replace_file` retry landed in
`workflow.write`. Before that retry, `PermissionError: [WinError 5]` from `os.replace` made these tests flaky
on Windows. The baseline had the same flake.

Incident: during the review round someone ran `git stash` on the shared worktree (`stash@{0}`, "WIP on
feat/rebuild-front-half: bd3c4d3"). It took the S2 edits to `task_issues.py`, `test_task_issues.py` and this
notes section. S2 restored only those three files from the stash with `git checkout stash@{0} -- <files>`.
The stash entry still exists and was not popped or dropped. The orchestrator should check that every other
stream got its files back before dropping it.

Lint API: `lint.run(root, feature, policy, tier) -> {ok, findings: [{code, severity, path, message}],
needs_model_analyze, budgets: {<file>: {bytes, limit_bytes, over}}}`. `ok` is false when any finding is an
error. CLI: `lint.py --feature specs/<f> [--root <dir>] [--tier lite|standard|full] [--json]
[--record --token <t>]`. Without `--tier` the CLI uses the checkpoint's `profile.tier`, or `full` when
there is none. Without `--json` it prints one summary line (`ok|error errors=<n> warnings=<n>
needs_model_analyze=0|1`) and then one line per finding. Exit codes: 0 when ok, 1 otherwise. With
`--record`, it exits 1 and prints `recorded: false, reason` when lint has errors or needs a model Analyze.
Otherwise it writes `<feature>/evidence/lint-<YYYYMMDDTHHMMSSffffffZ>.json`, calls `Run.complete`, and
prints the runtime result. The receipt is `{stage: analyze, outcome: passed, summary, inputs: [spec, plan,
tasks], evidence: [lint file], lint: {ok: true, findings: n}}`. `command: workflow:lint` comes from the
runtime's `state['commands']['analyze']` (S1), not from the receipt.

Finding codes:
- error: `ARTIFACT_MISSING` (spec/plan/tasks), `NO_TASKS`, `TASK_ID_DUPLICATE`, `TASK_HEADLINE_TOO_LONG`
  (more than 200 characters after the checkbox, id included), `TASK_DEPENDENCY_UNKNOWN`,
  `TASK_DEPENDENCY_CYCLE`, `TASK_DEPENDENCIES_INVALID` (malformed `workflow/task-dependencies.json`),
  `SPEC_NEEDS_CLARIFICATION`.
- warning: `TASK_ID_GAP`, `TASK_ID_ORDER`, `CONTRACT_UNREFERENCED`, `REQUIREMENT_UNCOVERED` (for an
  `SC-` id), `TASK_WITHOUT_REQUIREMENT` (a task block with no FR-, SC- or `US<n>` reference). The last one
  is not raised for tasks under a `## Phase ...` heading whose title contains setup, foundational, polish
  or cross-cutting, matched case-insensitively.
- semantic warnings that set `needs_model_analyze` (review round 1): `REQUIREMENT_UNCOVERED` for an `FR-`
  id, and `TASK_STATUS_CONTRADICTORY`. In code, `SEMANTIC = {'REQUIREMENT_UNCOVERED:FR',
  'TASK_STATUS_CONTRADICTORY'}` is matched against an internal flag, so the public code stays
  `REQUIREMENT_UNCOVERED` for both FR and SC.
- budget, error or warning depending on `enforce` and the tier: `BUDGET_EXCEEDED` (spec/plan/research
  bytes), `BUDGET_TASK_DETAIL` (more indented detail lines than `tasks_detail_lines`).
- `run()` raises `LINT_TIER_INVALID` or `LINT_ENFORCE_INVALID`. No finding uses severity `info` yet.

Lint decisions: requirement coverage is a warning, never an error, because the contract sends semantic gaps
to a model Analyze. Only an uncovered FR- id escalates. Dependencies come from `depends on`, `after` and
`Dependencies:` within a task's own headline and indented detail lines, plus
`workflow/task-dependencies.json`. A top-level "Dependencies & Execution Order" section is not parsed.
`enforce` defaults to `lite-standard` when budgets are set.

task_issues `--phase "<heading>"`: matches a `## ` heading case-insensitively after trimming. The phase
ends at the next `#` or `##` heading, so `###` subsections stay inside it. Unknown phase:
`PHASE_NOT_FOUND`. Phase with no tasks: `PHASE_HAS_NO_TASKS`. Both are raised before any GitHub call. The
whole dependency graph is still validated, and only the phase's tasks are created, linked or patched.
Existing marker identity keeps reruns idempotent: no writes on a repeat, and later phases link to
earlier-phase issues in `Depends on`. The result gains `phase` (trimmed) and `lazy: true`, and the summary
line ends `phase="<heading>"`. `--phase` together with `--sync-states` is a usage error.
`task-issues-result.json` holds only the latest phase run, while `workflow/task-issues.json` accumulates
every phase.

`--sync-states --allow-unpublished` (review round 1) skips tasks that have no journal entry. The CLI turns
it on automatically when `.specify/workflow.yml` has `issue_sync.taskstoissues: phase-lazy`. That read is
defensive: a missing, unparsable or non-mapping policy counts as not lazy. With the flag, the result gains
`unpublished: [<task ids>]` and the summary line becomes `ok opened=<n> closed=<n> changed=<n>
unpublished=<n> dry_run=0|1`. Without it, the output and the `UNPUBLISHED_TASK` failure are unchanged, so
the existing summary test is untouched. Like before, a strict apply run patches tasks in order until it
reaches the first unpublished one. That is pre-existing behaviour and was left alone.

## S3 Scope and clarification

Incident: S3 ran `git stash` on the shared worktree at about the middle of this round (to compare against
the baseline) and immediately restored every stashed file. Unchanged files came back from the stash,
`workflow.py` was three-way merged (clean), and `hosts.py` had already been rewritten in full by its owner.
`stash@{0}` is left in place untouched as a safety net. Streams that read a stashed file in that window
should reread it.

Files: `extensions/scope/scripts/{scope,clarification,workflow_policy}.py`,
`extensions/scope/tests/test_front_half.py` (new, 13 tests), `tests/test_clarification.py` (+8 tests, 1
renamed), `tests/test_scope.py`, `tests/fixtures/clarifications-vector.json` (new case),
`examples/{analysis,clarification}.json`, `references/{analysis-contract,illustrate-plan}.md`.

Validation: `python -m unittest discover -s extensions/scope/tests -q` ran 230 tests (209 before) with 1 error:
`test_plan.RealIllustrateTests.test_real_dependency_graph_is_accepted` (Illustrate `export_diagram.py`
PNG export fails in this environment). It fails the same way without these changes.

Changed existing tests (one line each):
- `test_dry_run_has_no_writes`: a dry run now leaves `.specify/scope/board-cache.json` (B5 read cache) and
  nothing else.
- `test_managed_questions_use_illustrate_not_mermaid_or_raw_urls` became
  `test_managed_questions_render_mermaid_but_refuse_raw_urls` (B4 removes `ILLUSTRATE_REQUIRED`).
- The vector test's evidence-kind set now includes `in-session`.

Policy: `workflow_policy.setting(root, section, key, default=None)` (read-only). Keys read:
`clarification.max_questions_per_round` (absent = no cap), `clarification.in_session_first_round`
(must be exactly `true`), `scope.board_cache_seconds` (absent = 300, 0 = no cache, no snapshot reuse).

CLI (exact):
- `scope.py render-spec <issue> --analysis <file> --feature specs/<f> [--apply] [--force]`. Dry run prints JSON
  `{issue, path, analysis_sha256, dry_run: true, text}`; apply returns the same without `text`. Errors:
  `SCOPE_RENDER_FEATURE_REQUIRED`, `SCOPE_RENDER_MISMATCH`, `SCOPE_RENDER_UNAPPROVED` (the issue's published
  receipt `approval.analysis_sha256` must equal the analysis hash), `SCOPE_RENDER_LEAF_REQUIRED`,
  `SCOPE_RENDER_EXISTS`. Marker: `<!-- sanduq-scope:rendered <sha256 of the file bytes> -->` (the
  `analysis_sha256` field is that same file hash, not `analysis_hash`).
- `scope.py gate|approve|publish|bind ... --snapshot <inspect --output file>`; the output gains
  `snapshot_reused: true|false` only when `--snapshot` is given.
- `clarification.py publish <issue> --analysis <file> --answers <answers.json> [--apply]`. Dry run returns
  `{..., status: Ready, in_session: true, comment_preview}`; apply returns `comment_ids: {summary: <id>}` and
  the `/speckit-plan` `next_action`. Errors: `CLARIFICATION_IN_SESSION_DISABLED`,
  `CLARIFICATION_IN_SESSION_ROUND`, `CLARIFICATION_IN_SESSION_STATE` (no open questions, or closed),
  `CLARIFICATION_ANSWERS_INVALID`, `CLARIFICATION_IN_SESSION_UNANSWERED: ...missing <keys>`,
  `CLARIFICATION_IN_SESSION_IDENTITY`, `CLARIFICATION_STALE`.
- B6: `CLARIFICATION_TOO_MANY_QUESTIONS: <n> > <cap>; defer <key>, <key>`.

Decisions and deviations:
- B6 priority: 1 is the most important (Spec Kit P1). Missing = least important; ties defer the later question.
  A priority must be a positive int. The cap is recorded as `max_questions_per_round` in the round comment's
  metadata, not in `clarifications.json`, which has no round-level structure (`{v, items}` is pinned).
- B5: only the first board read in a process may come from the cache, and any reload is live. A gate
  (`Scope.gate`, clarification `gate` and `plan_gate`) that would refuse because of a cached status drops the
  cache and rereads before refusing. So the "move back to Feature Specification and rerun" flow still works
  within the TTL. `set_status`, `add_to_board` and `sync_dependency_fields` (when it writes) drop the cache
  and the in-memory board. `set_labels` and the end of `export_plan` and `reconcile --apply` drop the cache
  file only. Publish, bind and clarification apply go through these helpers. A reused snapshot keeps the
  saved inspect data but replaces `issue` with the fresh fetch, so receipt and labels are live.
- B3: the in-session comment's record kind is `round-in-session` (the RECORD regex accepts it) and counts as
  round 1, so a later `inspect` reports `next_round: 2`. Records are written before the move to Ready, so a rerun
  after a failed move finishes without posting again. It uses the stored baseline in
  `.specify/scope/clarifications/<n>-<batch>/snapshot.json`. A text answer is limited to 500 characters.
  Answers are checked in dry runs too, and that includes the `gh api user` call.
- B2: `render-spec` omits Spec Kit's `Created` date so the output is deterministic. `Feature Branch` is the
  feature directory name.
- Follow-up: `examples/answers.json` added (one option answer, one free-text answer), mentioned in
  `references/analysis-contract.md` under "In-session first round", and checked by
  `test_the_answers_example_is_accepted`. Suite: 231 tests, same single Illustrate export error. These test
  modules import `test_scope` as a sibling, so run them with `discover -s extensions/scope/tests` or from that
  folder; `python -m unittest extensions.scope.tests.<module>` fails to import, as it already did for
  `test_clarification`. The `docs/workflow/state-files.md` evidence-kind entry has gone to S4.

## S4 Text, skills and presets


### Measurement

`benchmark_front_half.py --tier full` instruction bytes: baseline (`../sanduq-baseline`) 344,449,
this tree 203,705: **-40.9%** (target -40%). Per stage, before -> after: scope 30,662 -> 19,162;
specify 28,686 -> 14,002; clarify 29,263 -> 15,026; plan 13,699 -> 7,219; tasks 14,981 -> 6,839;
qa_analyze 12,708 -> 5,411; manual_analyze 12,716 -> 5,415; analyze 13,535 -> 7,294;
taskstoissues 14,355 -> 7,359; execute 52,589 -> 40,909; verify 13,541 -> 6,154; review 14,081
-> 6,321; qa_document 12,630 -> 5,317; manual_update 12,652 -> 5,340; ready 13,596 -> 6,116; pr
17,652 -> 9,273. Pointer set: dispatcher-operations 16,122 -> 5,504, delegation-and-decisions
9,826 -> 6,687.

Raw bytes on disk (`wc -c`, LICENSE excluded):

| Directory | Before | After | Change |
| --- | ---: | ---: | ---: |
| `extensions/workflow/skills` | 126,798 | 99,002 | -21.9% |
| `extensions/scope/skills` | 24,805 | 22,654 | -8.7% |
| `extensions/scope/commands` | 10,664 | 7,094 | -33.5% |
| `presets` | 22,023 | 27,678 | +25.7% |
| the four together | 184,290 | 156,428 | -15.1% |
| `extensions/workflow/commands` (descriptions only) | 5,329 | 7,561 | +41.9% |

The raw total falls only 15%: the 40% comes from what each stage loads. Reasons the raw total
cannot reach 40% without dropping rules: `execution-assign.md` and `execution-report.md` (about
29 KB) are pinned nearly verbatim by `test_execution_protocol_b11.py` (B12 section exact text,
legacy reporter calls, F11 bullets, template) and `worker_brief.py` reads them live; new
descriptions (A4/E1) and the two `strategy: replace` overlays that now carry the upstream
taxonomy add about 7 KB to presets and workflow commands; the new feature text (tiers, lint,
phase-lazy, in-session round, render-spec, revalidate-upstream, side effects, doctor cache,
resume contract) is new.

The benchmark's `--tier lite` run stops at `complete analyze` with `LINT_RECEIPT_REQUIRED`
(the scripted run sends a model receipt where the runtime expects `lint.py --record`): an S0/S1
integration item, not text.

### Files

Workflow skill (`extensions/workflow/skills/workflow/`):
- `SKILL.ext.md`: 6,134 -> 3,570 bytes; frontmatter `name: speckit-workflow`, new description;
  step 3 says the claim already contains the stage reference text; the pointer set
  (receipt-rules, dispatcher-operations, delegation-and-decisions) is read once per session;
  profiles summary; the stage reference table is gone (the claim names the file).
- New references: `setup-and-updates.md` (init, updates, migrate, relocate, host, moved out of
  dispatcher-operations), `recovery.md` (drift recipes, `revalidate-upstream`, `amend`),
  `evidence-capture.md` (prior-bytes capture), `scope-binding.md` (the two binding paragraphs
  plus the `execution_tools.py scope-command` helper, previously in five and two files),
  `superspec-checkpoints.md` (the required-only paragraph, previously in four files).
- `dispatcher-operations.md`: run-time rules only: continue (new resume contract), status, doctor
  and its cache, reconcile, context, `project_sync.points` and the claim's `project_sync` flag,
  the `[Collect]` marker sentence, managed-overlay contract (notes the two replace overlays),
  interruption and GitHub behavior (handoff block markers), Memory entry. The duplicated
  "Decision binding and publication" paragraph stays only in delegation-and-decisions.
- `receipt-rules.md`: 6,262 -> 1,562; adds `side_effects`.
- Stage references rewritten self-sufficient: plan (merged plan and tasks), analyze
  (`workflow:lint`, escalation to `speckit.analyze` on `needs_model_analyze`), scope
  (`effort_score`, `render-spec`), specify (`bind-only`), clarify (in-session round, Mermaid,
  question cap), taskstoissues (`--phase`, `lazy: true`), execute (phase-lazy pointer), verify,
  review, ready, pr.
- `execution-report.md`: phase-lazy paragraph (publish each phase at its start; when
  `--sync-states` refuses with `UNPUBLISHED_TASK` because later phases are unpublished, skip the
  boundary sync and run it once all phases are published, before Ready; this answers S2's open
  question without changing `task_issues.py`). Headings "(F11)" and "(B12)" stripped.
- Utility references (apply-pending, worker-brief, verify-affected, gate-explain, ci-report),
  memory-lifecycle, legacy-guard, delegation-and-decisions, execution-assign: pruned, review ids
  removed.

Scope (`extensions/scope/`):
- `skills/scope-analyst/SKILL.ext.md` (48 procedure lines) plus `references/managed.md`,
  `standalone.md`, `analysis-json.md`, `controls.md`. B7: step 4 scores a first pass; a sum of 3
  or less skips prerequisite code archaeology, inspects only referenced images and records
  `not inspected: lite tier`. Managed reference covers `--snapshot` reuse and `effort_score`.
- `skills/github-clarification/SKILL.ext.md` (47 procedure lines) plus the same four references.
  The "Mandatory automatic Plan handoff" section moved to `references/standalone.md`; managed.md
  carries the in-session first round (`--answers`, `round-in-session`), Mermaid allowed, the
  `CLARIFICATION_TOO_MANY_QUESTIONS` cap with `priority` (1 most important).
- `commands/*.md`: new descriptions; guard and bind keep their standalone rules and point to
  `scope-binding.md`. `extension.yml`: command descriptions synced to the frontmatter (version
  untouched).

Workflow commands and manifest: 13 new third-person descriptions, synced into
`extensions/workflow/extension.yml` (version untouched). `continue.md` now links
`evidence-capture.md#capturing-prior-document-bytes`.

Presets:
- `presets/workflow/preset.yml`: `strategy: replace` for `speckit.clarify` and
  `speckit.superspec.brainstorm`. Both overlays are now the whole command: managed contract, the
  github-clarification skill, and short upstream taxonomy (Clarify's ten coverage categories and
  answer-integration rules; SuperSpec's five categories, spec placement and Brainstorm Log). Both
  keep `<!-- sanduq-workflow-managed:v1 -->` once (hosts.py), and Brainstorm stays over the
  2,500-byte floor `smoke_install.py` checks. The preset version (1.1.1) should be bumped by the
  orchestrator, since composition changed.
- Every overlay description starts with the upstream description (SKILL_DESCRIPTIONS; SuperSpec
  and Bridge from their extension.yml) and ends with "(Sanduq managed)".
- scope-gate and scope-brainstorm: the triple "Managed workflow precedence" block shortened;
  specify-gate's two binding paragraphs replaced by the scope-binding pointer.

Docs: `docs/workflow/stages.md` (profiles and tiers section, dispatcher section rewritten),
`lifecycle.md` (tiers, in-session round, bind-only, revalidate-upstream, replace overlays),
`operating-guide.md` (new "Optional policy keys" section, resume contract and handoff block),
`state-files.md` (new section for profile, skipped, merged, lint receipt, lazy, episode,
source_inventory, doctor and board caches, handoff block, render marker; `skipped` event;
`in-session` evidence kind), `docs/reference/commands.md` (runtime commands section,
`speckit-workflow` skill row, replace overlays), `docs/extensions/workflow.md`,
`docs/extensions/scope.md`. `docs/reference/hooks.md` regenerated with `check_docs.py --write`
(generated from preset.yml strategies; not otherwise edited).

### Identifiers moved out of agent text (A1)

66 occurrences before: B13 x6, W01d x5, "Scope 1.6.1" x5, T7 x4, "round 1" x3 (review rounds),
T0 x3, G6 x3, F11 x3, B12 x3, "finding 3" x2, T8 x2, T1 x2, S6 x2, F9 x2, F3 x2, F2 x2, F15 x2,
F10 x2, F1 x2, "since 1.8.0", "round 7", "round 8" (now "the last allowed round"), "finding 2",
"finding 4", "finding 5", "finding 10", "finding 11", P07, F7, B4 (the B4 in reporting.md is a
blocker id in an example, kept). For the CHANGELOG: these named the retrospective findings
(F1 spawn and relay, F2 blocking waits, F3 report on state change, F7/F9 local lanes and
cancelled runs, F10 verbatim requirements, F11 consumers checklist, F15 pending artifact
updates), token findings (T0 turn budgets, T1 brief size, T7 result template, T8 summary first),
S6 forbidden commands, G6 drift recovery, B12 light-tier collection, B13 utility entry points,
P07 deferred receipt amendment, W01d and Scope 1.6.1 the managed binding restrictions, and the
1.8.0 portable checkpoint identity. Kept on purpose: the headings `worker_brief.py` parses
("(F1, F2, T0)", "(F3)", "(T7)", "(T8)"); whoever owns `worker_brief.py` can rename them
together with its `section_body` headings.

### Tests

- `test_skill_split.py` rewritten as a rule-inventory test. The old test compared every
  sentence of frozen pre-split originals (`fixtures/pre-split/`, now deleted) with the current
  text, so it failed on any pruning or deduplication, which is the point of A1. It now checks
  `fixtures/rules-inventory.json` (57 gate rules, each with file, rule text and reason), that
  every non-stage reference is named somewhere (stage references arrive through
  `stage_reference()`), that each Scope skill links its four references, that the binding and
  required-only paragraphs exist once, the preflight and handoff anchors, the overlay STOP rule,
  description rules (1-1,024 chars, no "Sanduq managed lifecycle overlay", presets end with
  "(Sanduq managed)", dispatcher name `speckit-workflow`) and no review ids in agent text.
- `test_execution_protocol_b11.py`: four expectations changed: "forwards each T7 result once"
  -> "forwards each structured result once"; "never Haiku (standing rule 5)" -> "never Haiku";
  "override (B12), never by default" -> "override, never by default"; the headings "Consumers
  checklist after a fix" and "Light-tier collection results" without "(F11)"/"(B12)". Reason:
  review ids stripped from agent text (A1). The B12 body is unchanged and still exact-matched.
- `test_reporting_instructions.py`, `test_speckit_compat.py`: unchanged, passing.
- Run: `python -m unittest extensions.workflow.tests.test_skill_split
  extensions.workflow.tests.test_execution_protocol_b11
  extensions.workflow.tests.test_reporting_instructions extensions.workflow.tests.test_speckit_compat -q`
  -> 33 tests OK. `test_every_stage_has_an_installed_reference_file` and
  `test_core_skill_stays_under_the_six_kilobyte_budget` OK. `check_docs.py` OK (70 guides, 47 of
  47 commands).

Full suites after S4 (shared tree, other streams mid-change): workflow 1,176 tests, 1 failure and
19 errors, none in instruction text: 16 `test_verification_plan`/`test_execution_tools` and 1
`test_memory_handoff` fail on the Windows Store Python stub (`OSError [Errno 22]` launching
`WindowsApps\...\python.exe`, also in the earlier run); 2 (`test_lean_execution`,
`test_lean_native_integration`) fail because a test lambda does not accept the new `normalize`
keyword the S1 runtime passes (S1). Scope 231 tests, 1 error (`test_real_dependency_graph_is_accepted`,
real Illustrate run, same before). `extensions/scripts/tests` 93 OK.

### For the installer stream (E5)

The dispatcher skill's frontmatter is now `name: speckit-workflow`; its source directory stays
`extensions/workflow/skills/workflow/` and the package path
`.specify/extensions/workflow/skills/workflow/SKILL.md` is unchanged (every overlay and command
reads it by that path). Today `install.py` and `hosts.py` install only the `speckit-scope` and
`speckit-superpowers-bridge` aliases into host folders, and no other repository file or the
`sanduq-skills` repo names `sanduq-workflow`. If S5 installs the dispatcher skill into a host skill
folder (`.claude/skills/<name>/`, `.agents/skills/<name>/`), the folder must be
`speckit-workflow`, because the Agent Skills spec requires the directory name to equal `name`.
An existing `sanduq-workflow` host folder from an earlier install should be removed (with the
usual backup) when the new one is written. For E6: the source directory `workflow` differs from the
name, so `validate_skills.py` must either check the installed host folder or allow this one
source whose package path is fixed. Repository mentions
of `sanduq-workflow` as a skill name were updated (docs/reference/commands.md); the remaining
`sanduq-workflow-*` strings are the CI file `sanduq-workflow-gates.yml` and overlay markers,
which are unrelated.

### Process note

During this stream I ran `git checkout -- presets/scope-gate/LICENSE presets/scope-brainstorm/LICENSE`
once, before the coordinator's rule against it, to undo a line-ending change my own script had
made to those two files; it touched nothing else. I did not run `git stash`.

## S5 Cross-host packaging

Files (sanduq): `extensions/workflow/scripts/install.py`, `hosts.py`, `reconcile.py` (one call, see
below), `worker_brief.py`, `workflow.py` (E9 warning only, 6 lines in `doctor` after `host_warnings`),
`extensions/workflow/hooks/hooks.json` and `guard.py` (new), `extensions/workflow/assets/roles/worker.yml`
and `reviewer.yml` (new), `extensions/scripts/validate_skills.py` (new), `extensions/scripts/vendor.py`
(repins both marketplaces, see E7), `.agents/plugins/marketplace.json` (new), `evals/` (new),
`.github/workflows/ci.yml`, `README.md`, `docs/start/install-by-host.md`, `docs/start/prerequisites.md`.
Tests: `extensions/workflow/tests/test_guard_hook.py` (new, 6), `test_host_files.py` (new, 12),
`test_worker_brief.py` (+4, class `TaskCardTests`), `extensions/scripts/tests/test_validate_skills.py`
(new, 6), `test_marketplaces.py` (new, 1). Files (sanduq-skills): `skills/{agent-tools,dev-tools,
illustration-tools}/plugin.json` (new), `.github/workflows/ci.yml`. No existing test changed.

Validation: from `extensions/workflow/tests`, `python -m unittest test_install test_hosts test_worker_brief
test_guard_hook test_host_files -q` runs 109 tests, OK. (The contract's dotted command fails to import
on this checkout before any change: the tests import each other as top-level modules, so run them from
that folder.) `python -m unittest discover -s extensions/scripts/tests -q` runs 93, OK. The full workflow
discover ran 1,119 tests with 9 failures and 28 errors while other streams were mid-edit; none has a
traceback through install.py, hosts.py, reconcile.py, worker_brief.py or guard.py (they are in
source_fingerprints, skill_inventory, the stage references, task_issues phase-lazy, and
test_verification_plan's WindowsApps `python.exe` OSError). `npx -y @anthropic-ai/claude-code plugin
validate .` passes in sanduq, for each sanduq-skills bundle with its new root `plugin.json`, and for
`evals` with `--strict`. `python extensions/scripts/smoke_install.py --host claude --second-host codex`
passed with the local Spec Kit 1.1.4.dev0 (CI pins 8147943): both hosts got the guard hook and both role
files; Claude's five hook-only Scope skills carry `user-invocable: false` (Codex's and
`speckit-scope-run` do not); no `speckit-scope` alias without `--with-aliases`; the installed hook
command returned 2 for `git stash` and 0 for `git status`; `validate_skills.py` found 92 rendered skills
with 0 errors.

A5: `install.py --with-aliases` / `--without-aliases` (mutually exclusive; neither keeps the earlier
choice). The choice is stored as `with_aliases` in install-lock.json; a 1.12 lock without the key keeps
aliases when it lists any (`hosts.aliases_enabled`). `--without-aliases` deletes only files whose whole
content Sanduq recognises (packaged, legacy hash or lock hash); an edited alias stays. Deviation: a
registered upstream Superpowers Bridge is always replaced by the Sanduq alias, flag or not, because the
upstream render is an executor that bypasses the workflow and doctor already refuses it
(`LEGACY_ALIAS_RECONCILIATION_REQUIRED`). `hosts.switch` and `hosts.alias_errors` follow the stored
choice. `user-invocable: false` goes into `.claude/skills/speckit-scope-{guard,bind,after-specify,
plan-guard,reconcile}/SKILL.md` (CRLF kept; an existing `user-invocable: true` is flipped). skill_report
checks presence only, so it tolerates the flag.

Re-application: `reconcile.reconcile(apply=True)` (not `--restore`) now ends with
`hosts.apply_host_files(root, policy)`: hidden hook-only skills, guard hook and role agents for every
installed host. Install and `host --use` already call reconcile after Spec Kit renders, so all three
paths re-apply them; install's receipt carries the result as `host_files`. reconcile.py was not in the
owned list; the change is 5 lines. There is no uninstall command. A removed workflow package leaves the
hook entry, which then allows everything: the command runs the guard only when the script exists
(Python's own exit 2 for a missing script would otherwise block every Bash call).

E4: the packaged `hooks/hooks.json` is a template whose command starts `{python} -c
"...runpy.run_path(guard.py)..."`; `hosts.guard_hooks` renders `python` when `os.name == 'nt'` and
`python3` otherwise into `.claude/settings.json` and `.codex/hooks.json` (install reaches it through
reconcile), with the path from `$CLAUDE_PROJECT_DIR` or the cwd. Policy after review: `git add
-A|--all|.|./` and `git stash` (except `list`/`show`) are denied in every session unless
`SANDUQ_ROLE=coordinator`. `delegate_dispatch.py trust-reset|accept|reassign|adopt` is denied only in a
worker context: env `SANDUQ_DELEGATED_RUN` set (delegate_dispatch's `driver_env` already sets it for
plain workers), env `SANDUQ_ROLE=worker`, or a payload carrying `agent_id` or `agent_type`. A subagent
stays a worker even under an inherited `SANDUQ_ROLE=coordinator`. The top-level session needs no
variable. The guard splits on `&& || ; | &` and newlines and skips git global options; a Codex argv list
is checked item by item. Unexpected input allows. The installer merges only
its own entry (found by `workflow/hooks/guard.py` in the command) and refuses with `HOOK_SETTINGS_INVALID`
a file that is not a JSON object, without writing it. `.claude/settings.json`, `.codex/hooks.json` and the
four role files are in install's rollback snapshot. Install prints the Codex `/hooks` approval line on
stderr and in the result (`codex_hook_approval`). Tests after the review: `test_guard_hook.py` 6 (git
denial with and without `agent_id` and both role overrides; ledger verbs allowed at top level and denied
for `agent_id`, `agent_type`, `SANDUQ_DELEGATED_RUN`, `SANDUQ_ROLE=worker`, and `agent_id` under
`SANDUQ_ROLE=coordinator`), `test_host_files.py` +1 (both interpreter branches and the installed
command). The owned workflow modules now run 110 tests, OK. Smoke install rerun
(`--host claude --second-host codex`, local Spec Kit 1.1.4.dev0) passed. In it, both installed hook
commands start with `python -c` and returned 2 for `git add -A`, 0 for a top-level `delegate_dispatch.py
accept`, and 2 for the same call with `agent_id`; 92 rendered skills, 0 errors.

E6: a name/directory mismatch is an error except for the allowlist `DIRECTORY_EXCEPTIONS` in
validate_skills.py: (`workflow`, `speckit-workflow`) for the dispatcher, read by path and never a host
skill, and (`skill`, `illustrate`) and (`skill`, `progress-report`) for the vendored copies, which install
under their own name. Any other mismatch fails, `SKILL.ext.md` or not. A `metadata` value that is a YAML
boolean or number is a warning (vendor.py writes `internal: true`); a nested value is an error. CI runs
it in the lint job on `extensions presets skills`, and in the installation job on the smoke project's
`.claude/skills` and `.agents/skills`. sanduq-skills CI sparse-checks out `samykabu/sanduq@main` for the
script, so merge the sanduq PR first or that step fails. Evals: `evals/` is a plugin root
(`experimental.evals: cases`) with four `tool_used: Skill` cases (scope-issue, continue-feature,
finalize-pr, open-pull-request); `evals/skills/` is copied from a smoke install before a run (README;
ignored by `evals/.gitignore`). Not run here: it needs model calls.

E7: each bundle's root `plugin.json` copies name, version, description, author, license, keywords and
repository; sanduq-skills CI now fails when they differ from `.claude-plugin/plugin.json`, so a release
bump edits both. `.agents/plugins/marketplace.json` mirrors the Claude marketplace (same pins, `category`,
`policy.installation: AVAILABLE`); `test_marketplaces.py` checks it, and `vendor.py update` (not in the
owned list, 6 lines) now repins both files so the daily vendor PR keeps them equal.

E8: roles are rendered for every installed host; a same-named file without the `sanduq-role:v1` marker
is left alone and listed in `roles_skipped`. The model is set only when `delegation.enabled`, from
`delegation.models.<host>.<model_tier>`. `worker_brief.build` returns a card (`format: card`, `role`) of
at most 1,536 bytes when the role file for the work type exists (`review` uses `sanduq-reviewer`);
verbatim requirement lines become ids first, then it falls back to the full brief.

E5: nothing in install.py or hosts.py registers or checks the dispatcher skill by name; it is read by
path from `.specify/extensions/workflow/skills/workflow/SKILL.md` and never installed as a host skill, so
the `speckit-workflow` rename needed no installer change.

E9: `doctor` warns `INSTRUCTION_FILES_DUPLICATED` when CLAUDE.md and AGENTS.md both exist at the root and
CLAUDE.md lacks `@AGENTS.md`; install-by-host.md documents AGENTS.md as the standing file.

Not verified here: a Codex plugin install from the marketplace; Codex running the project hook (the
approval flow, and whether the tested Codex needs a hooks feature flag); `claude plugin eval` runs; the CI
steps themselves; Spec Kit 8147943 renders (only 1.1.4.dev0 locally). Unrelated: `check_docs.py` reports
`docs/reference/hooks.md` stale after other streams' `extension.yml` edits; run `check_docs.py --write`
once S4 settles.

Incident: during this round someone ran `git stash` in the shared worktree (`stash@{0}`, left
untouched). Before the orchestrator's rule arrived I ran `git checkout -- extensions/workflow/scripts/hosts.py`
and a `git stash pop` that aborted without changing anything (the stash had already been re-applied). The
checkout reset only my own hosts.py, which I restored from the stash entry with `git show`. I did not
create the stash.

## Orchestrator

- Versions: workflow 1.13.0, scope 1.8.0 (requires workflow >=1.13.0), workflow preset 1.2.0,
  `dependencies.json` scope pin 1.8.0, `pending-releases.json` status `implementation-in-progress`.
  CHANGELOG entries written for both packages and the root log; package READMEs updated;
  `docs/reference/hooks.md` and `commands.md` regenerated with `check_docs.py --write`.
- Release order: publish sanduq (workflow 1.13.0, scope 1.8.0) first; sanduq-skills CI fetches the
  skills validator from `samykabu/sanduq@main`. The three bundles' root `plugin.json` files are on
  the `feat/portable-plugins` branch only; both marketplaces still pin the released tags
  (`illustration-tools-v3.4.2`, `dev-tools-v1.1.1`, `agent-tools-v1.4.2`), which do not contain a
  root manifest. A Codex install from the marketplace therefore needs a patch release of each bundle
  and a vendor re-pin before it can be exercised.
- `validate_skills.py` warns that `metadata.internal` is a boolean in the three vendored skills.
  `npx skills` documents `metadata.internal: true` (boolean) as the hide flag, so it stays boolean;
  the warning is accepted.
- Pre-existing failures on this machine (also on the untouched baseline, excluded from acceptance):
  `test_execution_tools` (3), `test_verification_plan` (14), `test_memory_handoff` (1), all from
  hashing the Microsoft Store `python.exe` link; `extensions/scope/tests/test_plan.RealIllustrateTests`
  (1), Illustrate PNG export without Chromium.
- Stash incident: S3 ran `git stash` during the round; every stashed file was restored and later
  exceeded the stash content. `stash@{0}` is kept until the branch is merged, then dropped.
