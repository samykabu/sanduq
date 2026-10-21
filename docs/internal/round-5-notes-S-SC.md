# Round 5 notes: S-SC (Scope and the scope presets)

## SC8 decision

Move. Scope's `GitHub` client (with `masked_owner_failure`, `verify_project`, the GraphQL-to-REST switch),
`ProjectRest` and `rate_limited` live in `extensions/scope/scripts/sanduq_scope_github.py`, Scope-owned, on top
of `sanduq_gh.run_gh`. The module raises its own `GitHubError` and has no `ScopeError`/`require` dependency;
`scope.py` maps it back by making `ScopeError` that same class (`from sanduq_scope_github import GitHubError as
ScopeError`), so every `except ScopeError`, every error message and every `assertRaises(m.ScopeError)` keeps its
shape. `from scope import GitHub, ProjectRest, rate_limited, PAGE_TIMEOUT` keeps working (re-export).

For S-WF (`decisions.py`): load `sanduq_scope_github` instead of exec-ing `scope.py`. In the source tree it sits
at `extensions/scope/scripts/sanduq_scope_github.py`; in the Workflow archive it must be injected next to
`decisions.py` (request to S-SH below). It imports `sanduq_gh` (same folder in an archive; source checkout falls
back to `extensions/scripts/shared`). `sanduq_scope_github.GitHub()` has the same `project_cfg`, `command(args)`,
`api(...)`, `graphql(...)`, `project_transport` surface as `scope.GitHub` had. It goes through `subprocess.run`
(via `sanduq_gh`), so `patch.object(<any module>.subprocess, 'run', ...)` still intercepts. Until S-WF switches,
`decisions.scope_transport()` (exec of `scope.py`) keeps working unchanged; `test_decisions_corrective.py:96`
passes as is.

## SC16: the prerequisite walk stops at a logical Done

- `scope.py prerequisite_report`: a prerequisite whose `status()` is `Done` (aliases from `scope.statuses`
  applied; `not_planned` and closed-without-Done are not Done) is reported but not descended. In review and every
  other status are descended as before. A prerequisite already fetched in the walk is not fetched again.
- `inspect` reads pull-request timelines for the direct prerequisites only.
- Deliberate rule changes (owner decision 2, Amendment 11): `test_scope.py` `test_transitive_blocker` (was :218)
  now checks In review descends and Done stops; `test_dependency_cycle_fails` uses In review (a cycle through a
  Done prerequisite is no longer walked) and adds a second cycle through two In review issues.
- New semantic tests (`test_scope.py`): `test_walk_stops_only_at_logical_done` (alias `Done: Shipped` stops;
  `not_planned` and closed-without-Done descend and block), `test_timelines_only_for_direct_prerequisites`,
  `test_override_reaches_a_blocker_behind_in_review`, `test_shared_prerequisite_is_reported_once`.
- Call counts (`test_github_calls.py`): chain of 5 Done prerequisites, `inspect(evidence=False)`: 4 calls (issue,
  its links, the Done prerequisite, the board) against 13 before (2 + 2N = 12 API + board). Chain of 5 In review:
  13, unchanged. Full inspect of the In review chain: 1 timeline read instead of 5. The new tests failed before the
  code change (5 failures: 13 != 4, 5 != 1, three semantic ones) and pass after.
- Docs: Scope README "Readiness" section; scope-analyst `SKILL.ext.md` step 3 rule sentence; CHANGELOG line and
  Migration line.
- Request (root docs, orchestrator): `docs/extensions/scope.md`, after the Purpose paragraph (line 5), add:
  "An issue is ready when each prerequisite is In review or Done. The check follows prerequisites of
  prerequisites through In review issues and stops at a Done one, so a Done prerequisite whose own prerequisite
  was reopened does not block."

## SC21: `scope.py cancel <issue>-<hash>`

- `Scope.cancel(operation, apply)` and the `cancel` CLI command. The argument must be the journal id
  `<issue>-<16 hex>` (the folder under `.specify/scope/runs/`): anything else is `SCOPE_CANCEL_OPERATION`
  (paths, `..`, `plan-export-*`, short hashes, empty); a bare issue number is `SCOPE_CANCEL_AMBIGUOUS` and lists
  that issue's operation ids; a folder that does not resolve inside `runs/` (symlink or junction), a missing
  journal or a journal whose `operation` differs is `SCOPE_CANCEL_UNKNOWN`.
- Without `--apply` it only reports (`dry_run: true`). With `--apply` it takes the same `mutation.lock` as
  `publish --apply` (main's existing lock path) and sets `rolled_back: true` and `rolled_back_at`. Repeatable.
  No GitHub call at all.
- Output: `created` (journal nodes other than the root), `before` (issue before-images), `dependencies_before`,
  `backups` (snapshot, analysis, catalog-before, issue-map-before paths), `published`, and a `repair` sentence.
- Defect found and fixed with it: `publish` journalled a new child only after linking it as a sub-issue, so an
  interrupted link left a created issue out of the journal (and out of `cancel`'s list). It now writes the
  journal right after the issue is created. Regression test: `test_cancel_marks_the_journal_and_prints_the_before_images`
  failed (`[] != [6]`) before that change.
- `controls.md` (scope-analyst) step 4 names the command. Tests: `test_round5.py` `Cancel` (4 tests, including
  the lock and a symlinked folder leaving `runs/`).

## SC17: compact `replace` overlays

- Upstream checked first (read-only `gh api` at the pinned commits, copies in the session scratchpad
  `r5/superspec-brainstorm.md`, `r5/speckit-clarify.md`):
  - Superspec `commands/brainstorm.md` at c20ac6c (tested 1.0.2): 2,015 B. Steps: read spec and constitution;
    use a `brainstorming` skill when present, else the five categories; ask one at a time; map answers to
    Functional Requirements / Open Questions table / Edge Cases; Brainstorm Log; later sessions skip explored
    categories; Superpowers outputs fold into `spec.md`, not `docs/superpowers/`; optional `[focus-topic]` arg.
  - Spec Kit `templates/commands/clarify.md` at 8147943 (tested 1.0.11): 19,507 B.
- What unmanaged users lose (now that both scope presets `replace`): the upstream interactive loop (already
  overridden), Spec Kit's `before_clarify`/`after_clarify` hook-dispatch protocol text (the skill keeps "run
  mandatory hooks" and now names `.specify/extensions.yml`), the `## Clarifications` / `### Session` log format
  (the runtime appends its own review log), the coverage summary table in the completion report (the analysis
  JSON carries `coverage`), and the `check-prerequisites` path discovery (the runtime resolves the spec). From
  Superspec: nothing material; every rule above is in the skill's coverage section, including the focus topic,
  the Brainstorm Log, skipping covered categories and the `docs/superpowers/` rule. Side effect of `replace`:
  Spec Kit scaffolds `speckit.superspec.brainstorm` even without Superspec (it already did in managed projects
  through the workflow preset); `clarification.py dispatch` still chooses Brainstorm only when Superspec is
  installed and enabled. Both preset READMEs and the Scope Migration say so.
- Changes: taxonomy and "applying answers" for both engines moved into
  `skills/github-clarification/references/analysis-json.md` (`## Coverage`, `## Applying answers`; a new
  reference file would break S-WF's `test_skill_split.py:54`, which pins the reference list). The skill's step 7
  points there instead of carrying its own condensed list; step 6 names `.specify/extensions.yml` for hooks.
  The four overlays are pointers; the "Managed workflow precedence" paragraphs are gone; scope-gate Clarify and
  scope-brainstorm Brainstorm use `strategy: replace`. `presets/workflow/preset.yml` already had `replace` for
  both; no change needed there.
- Bytes (overlay / skill / analysis-json), before -> after:
  - scope-gate `clarify-github.md` 2,107 -> 745; scope-brainstorm `brainstorm-github.md` 2,060 -> 726;
    workflow `speckit.clarify.md` 2,857 -> 1,258; workflow `speckit.superspec.brainstorm.md` 2,881 -> 1,564
    (the managed overlays keep the dispatcher contract lines `test_skill_split` requires, so not 600 B).
  - `SKILL.ext.md` 5,030 -> 4,843; `analysis-json.md` 2,023 -> 4,184.
  - Unmanaged Clarify round (overlay + upstream + skill + analysis-json): about 28.6 KB -> about 9.8 KB
    (about 18.8 KB saved). Unmanaged Brainstorm: 2,060 + 2,015 + 7,053 = 11.1 KB -> about 9.8 KB.
  - Managed Clarify: 9,910 -> about 10,300 (+0.4 KB); managed Brainstorm 9,934 -> about 10,600 (+0.7 KB). The
    single source costs each managed engine the other engine's lines. Not the 1.1-1.8 KB saving the round-4
    estimate expected; reported as measured.
- Test: `test_instructions.py` `RenderedProcedureTests` renders Clarify and Brainstorm, unmanaged
  (scope preset alone) and managed (workflow over scope preset), with Spec Kit's layer rule (prepend stacks,
  replace ends the stack) and checks: no upstream layer, the skill path and engine, STOP, no "Managed workflow
  precedence", under 1,700 B, the managed contract and `stage-clarify.md` when managed, and that each coverage
  phrase appears exactly once in the stage file set (rendered command + skill + its references, plus
  `stage-clarify.md` when managed). Failed on the base tree (4 failures: upstream layer present, managed
  overlays 2,534 and 2,567 B), passes now. `test_speckit_compat.py` (S-WF's file) does not render; I did not
  touch it. `test_instructions.py` path checks pass.

## SC8 Scope side and round-3 leftovers

- `sanduq_scope_github.py` (new): `GitHub`, `ProjectRest`, `probe`, `GitHubError`, `require`,
  `rate_limited = sanduq_gh.rate_limited`, `PAGE_TIMEOUT = 120`. `command()` runs `sanduq_gh.run_gh`; a
  `GhError` with `timeout` becomes `GitHub request timed out (<args>) after <t> s.`; gh missing (127) is not
  routed to the REST fallback; every other failure keeps the old message
  `GitHub request failed (<args>): <stderr 700>` and the old GraphQL-exhaustion routing. Timeouts stay Scope's
  (30 s, 120 s paginated), so `test_round4.py:182` is unchanged. `api()` passes `retry=True` only for a GET
  without a body; `graphql()` and every write and `gh project` call never retry. The rate-limit budget probe
  and the masked-owner probe go through `sanduq_gh` too; a timed-out probe now counts as a failed probe instead
  of escaping as `TimeoutExpired`.
- `scope.py`: the moved classes (about 300 lines) removed, one import line added.
- `test_project_rest.py` now targets `sanduq_scope_github` directly (`m.GitHubError`,
  `m.sanduq_gh.subprocess`); `scope.with_transport` stays from `scope`.
- New tests (`test_round5.py` `Transport`): re-export identity; a GET retried once after HTTP 502 (sleep
  patched) and a PATCH never; timeout and missing gh are Scope errors; the module imports in an installed layout
  (only it and `sanduq_gh.py` in a folder, PyYAML blocked) without loading scope, workflow, workflow_policy or yaml.
- `workflow_policy.load`: cached per resolved path, keyed by the file text (not the mtime: a same-size rewrite
  in one mtime tick must not return the old policy; reading is cheap, parsing is what cost 3.5 s), parsed with
  `yaml.CSafeLoader` when present, returned as a deep copy; validation still runs on every call. S-WF's line
  (`schema_version not in (1, 2)`, W27) untouched.
- `_workflow_module` / `_decisions_module`: loaded once per process (`_MODULES`); `_decisions_module` inserts
  the Workflow scripts folder into `sys.path` only when absent. `test_fresh_binding.py` `decisions()` now stubs a
  copy (`types.SimpleNamespace(**vars(...))`) instead of overwriting `reconcile` on the cached module.
  Note for S-WF: `test_front_half_runtime.py:873` still assigns `decisions.reconcile` on the module
  `_decisions_module()` returns; with the cache that assignment now persists in the process. Every call in that
  file patches `_decisions_module` anyway, and the suite passes, but a copy (as in `test_fresh_binding`) is safer.
- `accept_plan.py`: `--spec` and `--archify` removed. `test_plan.py`
  `test_deprecated_flags_still_work_for_one_minor_version` replaced by `test_removed_flags_are_refused`
  (deliberate, plan row); `test_previous_renderer_candidate_requires_regeneration` passes the file with `--html`.
- Tests (`test_round5.py` `PolicyCache`): one parse per text, a copy per call, reparse on a same-size rewrite,
  `CSafeLoader` chosen when present, invalid policy refused every time, missing file None; modules identical
  across calls and `sys.path` does not grow.

## Changelog lines (presets have no CHANGELOG)

- scope-gate: "Clarify now `replace`s the upstream command with a short pointer to Scope's github-clarification
  skill (which holds the coverage categories and answer rules); the never-active managed precedence paragraph is
  gone. Migration: run `specify preset add` again after the update."
- scope-brainstorm: "Brainstorm now `replace`s the Superspec command with a short pointer to the same skill.
  Spec Kit scaffolds the command without Superspec too; automatic dispatch still uses Clarify then. Migration:
  run `specify preset add` again after the update."
- workflow preset: "The Clarify and Brainstorm overlays no longer repeat the coverage categories and answer
  rules; the github-clarification skill holds them."

## Requests

- **S-SH** (`extensions/scripts/package.py`): inject Scope's client into the Workflow archive, next to
  `decisions.py`:
  `if extension == 'workflow': files['workflow/scripts/sanduq_scope_github.py'] = (root / 'extensions/scope/scripts/sanduq_scope_github.py').read_bytes()`
  (guarded by `.exists()` like the other helpers). Scope's own archive already carries it as a normal script.
  Also, after this lands, add `rate_limited` to `OneDefinition.MOVED['sanduq_gh.py']` in
  `test_sanduq_remote.py` (`scope.py` no longer defines it; `sanduq_scope_github` aliases it).
- **S-CI** (`.github/scripts/ci_matrix.py`): if the archive-coverage test (`test_ci_matrix.py:321`) needs an
  `INJECTED` entry for an injected file, add `sanduq_scope_github.py` -> workflow (source `extensions/scope/scripts`).
- **S-WF**: switch `decisions.py` to `sanduq_scope_github` (see "SC8 decision"); keep
  `test_decisions_corrective.py:96` working by patching `module.sanduq_gh.subprocess` or `module.subprocess`.
- **Orchestrator / root docs**: (1) `docs/extensions/scope.md` readiness text (SC16 above). (2)
  `docs/reference/hooks.md` is generated from `presets/*/preset.yml` and is now stale: scope-brainstorm
  `speckit.superspec.brainstorm` and scope-gate `speckit.clarify` are `replace`; regenerate with
  `check_docs.py`. (3) `docs/reference/commands.md:234-236`: "presets prepend policy to provider commands; the
  Workflow preset replaces Clarify and SuperSpec Brainstorm outright" becomes "presets prepend policy to provider
  commands; Clarify and SuperSpec Brainstorm are replaced outright by pointers to Scope's GitHub clarification
  skill". (4) Optional: `docs/extensions/scope.md` near line 52 (where `scope.py render-spec` is named) could add
  "`scope.py cancel <issue>-<hash>` marks an interrupted publish cancelled and prints what to repair by hand."
  `check_docs.py` today fails only on the stale `hooks.md` (item 2).

## Test results (Python 3.11 via uv, end of stream)

- `python -m unittest discover -s extensions/scope/tests -q`: 283 tests OK, 1 skipped (Playwright real-Illustrate
  test).
- Workflow `test_execution_tools` + `test_decisions_corrective`: 39 OK, 1 skipped (local pilot history).
- Workflow `test_skill_split`, `test_front_half_runtime`, `test_checkpoint_identity`,
  `test_lean_native_integration`, `test_speckit_compat`, `test_execution_policy`: 145 OK (`test_skill_split` and
  `test_speckit_compat` rerun after the last text edit: 13 OK).
- `check_docs.py`: fails only on `docs/reference/hooks.md is stale` (generated from the preset strategies I
  changed; orchestrator request 2).

## Codex finding 6 (after commit 4e4a3e3): `cancel` through a linked runs directory

- Defect: `cancel` compared `path.resolve().parent` with `runs.resolve() / value`. When
  `.specify/scope/runs` itself is a symlink or junction pointing outside the project, both sides resolve outside
  and match, so `cancel --apply` wrote an external journal.
- Fix (`scope.py` `Scope.cancel`): before any read or write, `runs.resolve()` must be inside the resolved project
  root; otherwise `SCOPE_CANCEL_UNKNOWN: .specify/scope/runs resolves outside the project; refusing to read or
  write it.` The check also covers the bare-issue listing branch and a linked `.specify` or `.specify/scope`.
- Test: `test_round5.py` `test_cancel_refuses_a_runs_directory_linked_outside_the_project`: runs/ as a directory
  symlink, and on Windows as a junction (`_winapi.CreateJunction`, as in Workflow's tests); both `cancel <id>
  --apply` and `cancel <issue>` exit 2 with the message and the outside journal stays unmarked. With the check
  disabled it failed for both the symlink and the junction (`0 != 2`); with it, both pass on this machine.
- Scope suite: 284 tests OK, 1 skipped (Playwright).
