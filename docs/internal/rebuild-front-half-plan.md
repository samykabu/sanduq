# Rebuild the front half: implementation contract

Branch `feat/rebuild-front-half` (sanduq) and `feat/portable-plugins` (sanduq-skills). Baseline for
measurement: the read-only worktree `../sanduq-baseline` (main at 105508f). Do not edit the baseline.

Target versions at release: workflow 1.13.0, scope 1.8.0 (bumped by the orchestrator at the end; streams
do not bump versions or edit CHANGELOGs, they append notes to `docs/internal/rebuild-front-half-notes.md`
under their stream heading).

Rules for every stream: no commits; stay inside the owned files; keep every existing test green or
change the test with a one-line reason in the notes file; new behaviour needs a test; CLI help text and
reference text use the exact names below.

## Shared policy keys (`.specify/workflow.yml`)

```yaml
profiles:                       # B1. Absent means {enabled: false} (current behaviour).
  enabled: true
  lite: {max_score: 3}          # score <= 3
  standard: {max_score: 8}      # score <= 8; above is full
clarification:
  max_questions_per_round: 6    # B6. Absent means no cap (current behaviour).
  in_session_first_round: true  # B3. Absent means false.
artifacts:                      # C3. Absent means no budgets.
  budgets: {spec_kb: 25, plan_kb: 20, research_kb: 15, tasks_detail_lines: 2}
  enforce: lite-standard        # lite-standard | all | warn
issue_sync:
  taskstoissues: required       # existing; new value: phase-lazy (C4)
project_sync:
  points: [specify, execute, pr]  # D6. Absent means the current six points.
scope:
  board_cache_seconds: 300      # B5. 0 disables the cache.
```

`validate_policy` accepts these keys; unknown sub-keys are errors as today.

## Tiers (B1, B7, C1, C2, D5)

- The scope receipt carries `effort_score` (int, one of 1 2 3 5 8 13 21). `complete` for `scope`
  requires it when `profiles.enabled`. The tier is computed by `workflow.tier(policy, score)` and
  frozen into the checkpoint as `profile: {tier, score, fixed_at}` when `plan` is first claimed.
- `stages(policy, tier=None)` returns the stage list for the tier:
  - `full`: current list.
  - `standard`: `tasks` is merged into `plan` (the plan claim returns `merged: ['tasks']`, the plan
    receipt must list `tasks.md` in inputs, `required_inputs` for later stages unchanged);
    `analyze` runs as the runtime stage `workflow:lint` (see C2); `taskstoissues` may be
    `phase-lazy`.
  - `lite`: as standard, plus `qa_analyze`, `manual_analyze`, `qa_document`, `manual_update` skipped,
    and `required_inputs` for plan and later do NOT include research.md, data-model.md,
    quickstart.md or contracts/ (they are optional consulted inputs).
- Skipped stages are recorded in the checkpoint as `skipped: {stage: reason}` and in
  `lifecycle.jsonl` as event `skipped`. `next` and `status` show them.
- `lean_execution.enabled` defaults to true for lite and standard unless the policy sets it false
  explicitly (D5). `lean_policy.enabled(policy, tier)` gains the tier argument.

## Lint (C2, C3): `extensions/workflow/scripts/lint.py`

```text
python lint.py --feature specs/<f> [--tier lite|standard|full] [--json] [--record --token <t>]
```

Checks: every FR-/SC- id in spec.md appears in tasks.md (`Covers` or inline); task ids unique and
sequential; dependency graph acyclic; task headline (first line) <= 200 characters; no
`[NEEDS CLARIFICATION` left in spec.md; every file under contracts/ is referenced by plan or tasks;
artifact byte budgets from `artifacts.budgets` (block on lite/standard when `enforce: lite-standard`,
warn on full). Result: `{ok, findings: [{code, severity, path, message}], needs_model_analyze: bool}`.
`needs_model_analyze` is true when a semantic flag is raised (a requirement with no task, a task
with no requirement, contradictory status markers). `--record` writes the analyze receipt
(`command: workflow:lint`) through `Run.complete` when `ok` and not `needs_model_analyze`.
Module API: `lint.run(root, feature, policy, tier) -> dict`.

## Runtime (A2, D1, D2, D3, D4, D6, B2 hook)

- A2: `claim` prints `reference_text` (the stage reference file content) and omits `baseline`
  unless `--verbose`. `complete` prints `{ok, stage, next: {stage, command, reason}}` only, unless
  `--verbose`.
- D1: `workflow.py revalidate-upstream --feature specs/<f> --through <stage> --receipt <file>`.
  Refuses with an active claim. Computes, per stale or removed receipt from `specify` through
  `<stage>`, the changed input paths (`changed: {stage: [paths]}`) and prints them with `--plan`.
  The receipt file is `{stages: {<stage>: {summary, evidence[], inputs[]}}}`; one locked operation
  re-records each listed stage in order, with one lifecycle episode kind `revalidate-upstream`, and
  the same per-stage validation `complete` applies (binding, decisions ledger, required inputs).
  Whitespace-only differences in a Markdown input count as unchanged (normalise CRLF and trailing
  spaces before hashing comparison for the drift decision, never for the stored hash).
- D2: the permitted-change map becomes `SIDE_EFFECTS = {'clarify': ['<feature>/spec.md',
  '.specify/project-sync-state.json', '<feature>/checklists/*.md'], ...}` with glob support; the
  claim prints `side_effects` for the stage.
- D3: Verify, Review and Ready receipts store `source_inventory: {path:
  'workflow/inventory/<stage>-<claim_id>.json', sha256}` instead of inline `source_fingerprints`;
  `source_fingerprints_of(root, receipt)` reads either form (legacy inline stays readable). The
  resume prompt becomes `Run python .specify/extensions/workflow/scripts/workflow.py status
  --feature <f> and continue with speckit.workflow.continue; do not read checkpoint.json
  directly.` `handoff.md` keeps everything outside `<!-- sanduq-handoff:begin -->` ...
  `<!-- sanduq-handoff:end -->`; the runtime rewrites only that block.
- D4: `claim` reuses the last green `doctor(project=True)` result cached at
  `.specify/workflow/runtime/doctor-cache.json` when `dependency_digest`, the policy digest and the
  mtimes of `.specify/extensions/.registry`, `.specify/presets/.registry`, `.specify/extensions.yml`
  and `.specify/extensions/project/config.json` are unchanged and the cache is under 600 s old.
  `doctor` always runs fresh and refreshes the cache. Skill inventory and `git ls-files --eol`
  run only in the explicit `doctor` command.
- D6: `project_sync.points` is read by the runtime; `claim` prints `project_sync: true|false` for
  the stage; references read that flag.
- B2 hook: when `specs/<f>/spec.md` begins with `<!-- sanduq-scope:rendered <analysis sha256> -->`
  the specify claim returns `mode: bind-only`; the specify receipt then needs no model pass (the
  dispatcher runs Scope bind and `workflow.py bind` and records the receipt with the render marker
  hash in `inputs`).
- C4: `task_issues.py --phase "<Phase heading>"` creates and links only that phase's tasks;
  `--sync-states` unchanged. With `issue_sync.taskstoissues: phase-lazy` the taskstoissues receipt
  needs `lazy: true` and the mapping for the first phase; `ready_checks` requires every task
  mapped by Ready. The Execute reference says to run the adapter at each phase start.

## Scope and clarification (B2, B3, B4, B5, B6)

- B2: `scope.py render-spec <issue> --analysis <file> --feature specs/<f> [--apply]` writes
  spec.md from the approved analysis: first line `<!-- sanduq-scope:rendered <sha256 of the
  analysis file> -->`, then the Spec Kit spec structure (Overview, User Scenarios, Requirements
  with FR ids from `requirements`, Acceptance from `acceptance`, Out of scope, Open questions as
  `[NEEDS CLARIFICATION: ...]` from `uncertainty` items). Dry run prints the text.
- B3: `clarification.py publish <issue> --analysis <file> --answers <answers.json> --apply` for the
  in-session first round. `answers.json` is `[{key, option (1-based) | answer (text), answered_by,
  answered_at}]`; every question must have an answer; `answered_by` must equal the issue creator
  and the authenticated `gh api user` login. The runtime posts ONE managed comment (kind
  `round-in-session`) listing each question, the chosen answer and who answered, applies
  `spec_edits`, writes `clarifications.json` with state `applied` and evidence kind `in-session`,
  and transitions straight to Ready. Refused unless `clarification.in_session_first_round` is
  true and this is round 1.
- B4: remove `ILLUSTRATE_REQUIRED`; `diagram` (Mermaid) is allowed in managed projects and rendered
  as a fenced mermaid block; `diagram_image` stays optional.
- B5: board cache `.specify/scope/board-cache.json` `{fetched_at, repo, items}` with
  `scope.board_cache_seconds` TTL, invalidated by every Scope or clarification mutation; `gate`,
  `approve`, `publish` and `bind` accept `--snapshot <inspect output>` and reuse it when its
  `fingerprint` matches the live issue (one issue fetch) and it is under the TTL.
- B6: `max_questions_per_round` refuses an analysis with more questions than the cap and names the
  overflow; `questions` may carry `priority` (int) and the error says to defer the lowest.

## Text, skills and presets (A1, A3, A4, B7, E1, E2, E3, E5)

- A1: one `references/scope-binding.md` holds the two binding paragraphs; the five copies become a
  one-line pointer. Remove the four copies of the required-only paragraph into
  `references/superspec-checkpoints.md`. Strip review and version identifiers (B11, B12, T0, F1,
  P07, W01d, "round 3", "Scope 1.6.1", "since 1.x") from agent-facing text into the CHANGELOG
  notes file. `dispatcher-operations.md` keeps only run-time rules. Target: Sanduq instruction
  bytes down 40 percent (measured by `benchmark_front_half.py`).
- A3: `presets/workflow/preset.yml` uses `strategy: replace` for `speckit.clarify` and
  `speckit.superspec.brainstorm`; the overlay files carry the few useful upstream taxonomy
  paragraphs.
- A4 and E1: every `commands/*.md` in workflow and scope and every preset overlay gets a
  third-person description: what, when, trigger phrases, key use case first, under 1,024
  characters, no "Sanduq managed lifecycle overlay". Overlay descriptions start with the upstream
  description and end with "(Sanduq managed)".
- B7: scope-analyst steps 4 and 5 are tiered: when the first-pass dimension sum is 3 or less,
  skip prerequisite code archaeology and inspect only referenced images, recording "not
  inspected: lite tier" in evidence.
- E2 and E3: scope-analyst and github-clarification become `SKILL.ext.md` under 60 lines of
  procedure plus `references/managed.md`, `references/standalone.md`, `references/analysis-json.md`,
  `references/controls.md`; every reference one level deep.
- E5: the workflow skill is named `speckit-workflow` (directory stays `workflow`; the installed
  skill dir name must equal the frontmatter name, so document the rename in the notes for the
  installer stream).
- New reference text for: profiles and tiers, `workflow:lint`, merged plan and tasks,
  `revalidate-upstream`, side effects, the new resume contract, Mermaid questions, the in-session
  round, phase-lazy issues, `project_sync.points`, and `claim` printing `reference_text`.

## Cross-host packaging (A5, E4, E6, E7, E8, E9)

- A5: `install.py` installs `speckit-scope` and `speckit-superpowers-bridge` only with
  `--with-aliases`; hook-only Scope commands (guard, bind, after-specify, plan-guard, reconcile)
  get `user-invocable: false` injected on the Claude host after Spec Kit renders them.
- E4: `extensions/workflow/hooks/hooks.json` (shape shared by Claude Code and Codex) with a
  PreToolUse hook on `Bash` running `hooks/guard.py`: deny `git add -A`, `git add .`,
  `git stash`, `delegate_dispatch.py trust-reset|accept|reassign|adopt` unless env
  `SANDUQ_ROLE=coordinator`; exit 2 with the reason. `install.py` registers it in
  `.claude/settings.json` and `.codex/hooks.json` (and documents the Codex `/hooks` approval).
- E6: `extensions/scripts/validate_skills.py` implements the Agent Skills frontmatter rules (name
  1-64 `[a-z0-9-]`, equals directory, description 1-1024, compatibility <= 500, metadata string
  map, body under 500 lines as a warning); CI runs it on every SKILL.md and SKILL.ext.md in both
  repositories and on the smoke-install fixture; add `evals/` with `claude plugin eval` cases
  for the workflow entry points (format from code.claude.com/docs/en/plugin-evals).
- E7: sanduq-skills bundles gain a root `plugin.json` (`$schema`
  `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`); sanduq gains
  `.agents/plugins/marketplace.json` mirroring `.claude-plugin/marketplace.json` with `category`
  and `policy.installation: AVAILABLE`; READMEs document `codex plugin marketplace add
  samykabu/sanduq` and `codex plugin add <bundle>@sanduq`.
- E8: `extensions/workflow/assets/roles/{worker,reviewer}.yml` rendered by `install.py` to
  `.claude/agents/sanduq-<role>.md` and `.codex/agents/sanduq-<role>.toml`; worker_brief.py emits
  a task card (<= 1.5 KB) when roles are installed.
- E9: docs state AGENTS.md as the standing file; `doctor` warns `INSTRUCTION_FILES_DUPLICATED`
  when both CLAUDE.md and AGENTS.md exist without an `@AGENTS.md` import.

## Measurement (S0): `extensions/scripts/benchmark_front_half.py`

```text
python benchmark_front_half.py --repo <sanduq checkout> --out <json> [--tier lite|standard|full]
```

Builds a fixture consumer (as `test_workflow.py` does) with a 750-file synthetic source tree,
runs a scripted effort-2 feature through the runtime (start, every claim and complete with
minimal receipts, one mid-execute spec edit followed by the cheapest recovery the runtime offers,
then verify, review, ready, pr), and records: stages run, model passes (stages whose command is
not `workflow:*`), claim and complete stdout bytes, checkpoint bytes, handoff bytes, doctor
invocations (monkeypatched counter), fingerprint calls, wall time per command, and the static
instruction bytes per stage resolved from the checkout's presets, commands, skills and
references (following the pointer set once). `--tier` selects the profile when the runtime
supports it and is ignored otherwise. Output JSON plus a Markdown table; `compare.py` renders
before and after side by side with percentage deltas. Baseline numbers come from
`../sanduq-baseline`.
