# Round 4 review: Scope and the three presets (stream R2)

Read-only review of `extensions/scope` 1.9.0 and `presets/{scope-gate,scope-brainstorm,workflow}` on
`feat/round-4` (fb17f52). Round 3's options SC1 to SC9 are not repeated; SC1, SC3 to SC7 and SC9 shipped in
1.9.0 (`round-3-notes.md:253-269`). This file continues at SC10.

Method. Code read at the lines cited. Reproductions and call counts use the suite's `FakeGitHub`
(`tests/test_scope.py:18-104`) driven from scratch scripts outside the tree; nothing in the tree changed.
Instruction bytes come from `docs/internal/benchmarks/round-4-before-{full,instructions}.json`. Upstream
command sizes come from `D:\Projects\Personal\spec-kit` at 92b7cf7. Real GitHub object sizes come from
`gh api repos/samykabu/sanduq/issues/94` and its comments.

Tests: `pytest extensions/scope/tests`: 248 passed, 1 skipped (`test_plan.py:351`, needs Playwright), 57.2 s.
Round 3 had 231 tests and 39.5 s.

## Summary

- Three code defects, all reproduced. (1) A split publish aborts **after** it has created the children
  when any unrelated issue in the repository has a free-text "Depends on" or "Dependencies" section.
  (2) Scope derives the repository with its own regex. It rejects remote forms that Workflow accepts,
  and it compares case-sensitively, so a remote whose case differs from GitHub's sees an empty board.
  (3) Two CLI paths end in a traceback instead of an error message.
- One instruction conflict. In a managed Specify claim, the composed `specify-gate.md` tells the agent
  to run `speckit.scope.after-specify` and chain clarification. Workflow disables that hook and requires
  the claim to return control.
- The largest saving is context, not instructions. `scope.py inspect --output` also prints the whole
  snapshot to stdout, and the snapshot holds raw GitHub objects that are about 55% metadata. For a
  typical issue (3 prerequisites, 8 comments), 53 KB goes to about 22 KB.
- Unmanaged Clarify composes the 17,832 B upstream `clarify.md` under the scope-gate prepend. The
  workflow preset already shows that a 2.9 KB `replace` is enough.
- Runtime cost grows with repository history in three places. `reconcile` (an `after_implement` hook)
  makes 1 + 2P calls for P historical parents on every Implement. The prerequisite walk makes 2 + 2N
  calls for a chain of N Done prerequisites. A split publish lists every issue three times under a
  30 s timeout.
- SC8 is still open. The cleanest form is a shared `sanduq_github.py` injected by `package.py`. It also
  removes the cycle where Workflow's `decisions.py` execs `scope.py` for its Project transport.

## 1. Correctness defects

### D1. A split publish fails part-way when any unrelated issue has free-text dependencies

- Where: `rewire` (`scope.py:1173-1176`) calls `dependents`, which calls `declared_dependencies(x)` for
  **every** issue in the repository (`:689-690`). That calls `refs()`, which raises `Unresolved
  prerequisite description` for prose that names no issue (`:655-657`). It also raises for a
  cross-repository URL (`:649`) or an unknown `UC-`/`EPIC-` key (`:653`). The fallback path
  (`:686-687`, then `dependencies()` at `:1177`) fails the same way.
- When: `rewire` runs after every child has been created, linked, labelled and given a receipt
  (`:1125-1161`). `plan-pending.json` and `journal['published']` are never written.
- Reproduced. Issue #2 has the body `## Depends on\n\n- the design review sign-off`. A 2-child split of
  #1 then creates #3 and #4 and fails with `Unresolved prerequisite description: - the design review
  sign-off`. A retry repeats the error. The way out is to edit an issue that has nothing to do with the
  split. `dependency_text` matches the headings "Dependencies" and "Prerequisites" (`:205`), which are
  common in issue templates.
- Fix: find the rewire candidates before the first GitHub write (`publish`, before `:1084`). Parse
  issues outside the chain leniently: an unparseable unrelated issue is a candidate only when its text
  names `#<parent>` or the parent URL, and it gets one stderr line. Strict parsing stays for the scoped
  issue, its prerequisites and the issues actually rewired, so those still fail closed, but before any
  write.
- Test: the reproduction above. The publish then succeeds, and an issue that names `#1` in prose plus
  unparseable text still refuses before any write (zero `writes`).

### D2. Repository identity: rejected remotes and case-sensitive comparisons

- Where: `Scope.__init__` matches `github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$` (`scope.py:525-528`).
  Workflow has `normalize_remote_url`/`github_repository` (`workflow.py:312-327,385`) and documents
  "compare with `same_github_repository`, never `==`". Scope uses `==` for the board filter (`:564`) and
  a case-sensitive `endswith` for native dependencies (`:674`). `refs()` uses casefold (`:649`), so the
  two checks disagree.
- Reproduced (`FakeGitHub`, canonical `acme/app`):
  - `ssh://git@github.com/acme/app/`, `https://github.com/acme/app/`, `ssh://git@github.com:22/acme/app.git`
    and `https://GitHub.com/acme/app.git` each fail with `A GitHub origin remote is required.`.
    Workflow accepts all four.
  - Remote `https://github.com/Acme/App.git`: `status(#1)` is `Unknown (not on configured Project)`, and
    `inspect` with one Done prerequisite fails with `Cross-repository prerequisite is unsupported`.
    A renamed repository whose remote still uses the old name (GitHub redirects it) hits the same board
    filter. That case was not reproduced.
- Fix: one normaliser (D4's shared helper, see SC8). Compare `owner/repo` with casefold at `:553`,
  `:564`, `:674` and `:1174`. `bound_claim` already compares strings that came from the same remote.
- Tests: the five remotes above. A mixed-case remote reads board status and native dependencies.

### D3. Tracebacks instead of messages

- `clarification.py main` catches `(ScopeError, OSError, ValueError, KeyError, TypeError)`
  (`clarification.py:1013`), but not `subprocess.TimeoutExpired`, which the 30 s `gh` timeout raises
  (`scope.py:249-250`). `scope.py main` does catch it (`:1534`). The two hook commands `dispatch` and
  `plan-gate` run through this main.
- `Scope.__init__` uses `check_output` for `git remote get-url origin` (`:525`). With no origin this
  raises `CalledProcessError`, which neither main catches. Reproduced: a traceback, and the intended
  "A GitHub origin remote is required" is never shown.
- `accept_plan.py run_tool` runs Illustrate's export (Chromium) with no timeout (`accept_plan.py:202`).
- Fix: catch `subprocess.SubprocessError` in both mains, turn a missing origin into the existing
  message, and give `run_tool` a timeout. Effort S.

### D4. Instruction conflict in the managed Specify prompt

- In a managed claim, the workflow prepend (`presets/workflow/commands/speckit.specify.md`) says to
  follow `stage-specify.md` "then continue with the upstream instructions below". "Below" includes
  `specify-gate.md`, which says without condition: "Complete ALL mandatory after_specify hooks,
  including `speckit.scope.after-specify`, which automatically invokes Superspec Brainstorm ... Then
  run bind, Project sync, and the mandatory clarification dispatcher" (`specify-gate.md:27-40`).
- Workflow disables `speckit.scope.after-specify` in managed projects (`reconcile.py:36`). The overlay
  contract says "do the domain work once and return control ... disabled hooks stay disabled"
  (`dispatcher-operations.md:104-106`), but that sits in a file the agent reaches only through a link.
- Effect: a managed agent may chain Clarify inside the Specify claim. This is shown in text only. No
  managed run was made. Fixed by SC19.

### D5. Text defects (round 3 found these, still open)

- `presets/scope-brainstorm/README.md:3-4`: "The installer applies this prepend preset only when
  Superspec is installed". `install.py:771` applies it unconditionally, and doctor requires it
  (`workflow.py:1473`).
- The question cap is described as absent where it applies: the workflow Brainstorm overlay says "with
  no question count limit" (`speckit.superspec.brainstorm.md:30`), and the `validate` error says "(no
  numeric cap)" (`clarification.py:517`). Yet `clarification.max_questions_per_round` caps managed
  rounds (`clarification.py:573`). Correction to round 3: the scope-gate wording is right. Without
  `.specify/workflow.yml`, `setting()` returns no cap (`workflow_policy.py:18-21`).

## 2. Measurements

| What | Number | Source |
| --- | ---: | --- |
| Managed instruction bytes per stage: Scope / Specify / Clarify | 18,143 / 13,760 / 14,839 | before-full.json `per_stage` |
| Scope extension instruction bytes (catalog chars) | 38,679 (969) | before-instructions.md:113 |
| Upstream `clarify.md` / `specify.md` | 17,832 / 18,193 B | spec-kit 92b7cf7 |
| Real issue object, indented JSON / body only / kept fields only | 7,041 / 2,571 / 3,078 B | issue #94 |
| Real comment, indented JSON / body | 3,126 / 1,288 B | issue #94 comments |
| Call counts (fake client) | in SC14, SC15, SC16 | scratch scripts |
| Scope tests | 57.2 s; `test_fresh_binding` 26.1 s, `test_revalidation` 14.9 s, `test_clarification` 13.7 s | pytest durations |
| `test_fresh_binding` alone | 273 `subprocess.run` = 19.6 s; 86 `yaml.safe_load` = 3.5 s; 47 `_workflow_module` = 0.8 s | cProfile |
| `workflow.py` exec per process | about 200 ms on first load (cold imports), then 2-5 ms | timed |

## 3. Options

Cost basis (round 3's, unchanged): Scope's share of one managed front half is about 90k-220k tokens,
30-45 tool round-trips and 30-120 GitHub calls. One `gh` call takes 0.3-1 s. Tokens are bytes / 4. All
savings are estimates until remeasured.

### SC10. Fix D1: find rewire candidates before any write, parse unrelated issues leniently

- What: as in D1. Evidence: D1.
- Saving: correctness. It removes a stuck half-published split.
- Effort S. Risk low: strict parsing stays for every issue that is really rewired.
- Consumer impact: none. Tests: D1's two cases.
- Verdict: **fix-first**. Every split in a repository with one prose dependency section fails after it
  has written to GitHub.

### SC11. Fix D2: one repository normaliser, casefold comparisons

- What: as in D2. Use the shared normaliser (R4's J3/D4 helper) rather than a third copy.
- Saving: correctness for consumers whose remote form or case differs from GitHub's.
- Effort S. Risk low. Consumer impact: none. `scope-source.json` keeps the remote's own spelling.
- Tests: D2's cases.
- Verdict: **fix-first**. Workflow accepts these projects and Scope then fails in them.

### SC12. Fix D3 (tracebacks, run_tool timeout) and D5 (text)

- What: as in D3 and D5. Correct the scope-brainstorm README, the workflow Brainstorm cap sentence (R1
  owns that file) and the `validate` message.
- Effort S. Risk low. Tests: a CLI test with a `gh` stub that sleeps (exit 2 and a message), and one
  with no origin.
- Verdict: **fix-first** (small).

### SC13. Compact `inspect` stdout and a slim snapshot

- What: with `--output`, print only `{issue, title, fingerprint, ready, blocked, prerequisites:
  [{number, title, status}], comments: <n>, images: <n>, output, skeleton}`. `clarification.py`
  already does this (`clarification.py:1007-1008`). Store issues and comments with the fields that are
  read: issue `number, id, node_id, title, body, state, state_reason, labels[].name, html_url,
  user.login`; comment `id, user.login, user.type, author_association, created_at, updated_at, body,
  html_url`. Store prerequisite entries without the nested full issue object (`scope.py:711`), but keep
  `body` and `html_url` for the analyst's step 6. Journal before-images use the same fields. Nothing in
  code reads them (see SC21).
- Evidence: `main` prints the full result even with `--output` (`scope.py:1530-1532`). The analyst's
  step 2 always passes `--output` (`scope-analyst/SKILL.ext.md`). Real objects: issue 7,041 B, slimmed
  3,078 B; comment 3,126 B, of which the body is 1,288 B. Code reads only `comments[].body`
  (`scope.py:743`, `test_revalidation.py:131`).
- Saving: a typical inspect (1 issue, 3 prerequisites, 8 comments) goes from about 53 KB to about 22 KB
  in the file. Stdout goes from the same 53 KB to under 1 KB. That is 8k-20k tokens per Scope stage
  (fewer if the agent reads stdout only, more if it reads both), or 6% to 20% of the Scope stage's
  40k-120k. A gate that reuses the snapshot reads a smaller file.
- Effort M. Risk medium: the snapshot schema stays `schema_version: 1`. Each field gate, approve and
  publish read must be on the kept list. `load_snapshot` replaces `issue` with a fresh fetch anyway
  (`:601`).
- Consumer impact: snapshot files written by 1.9.0 still load, because the fields read are a subset. No
  migration.
- Tests: the stdout of `inspect --output` is under 2 KB. Gate, approve and publish succeed from a slim
  snapshot. The images list still comes from comment bodies.
- Verdict: **do**. This is the largest token saving in Scope.

### SC14. One issue listing per process; a timeout that fits paginated reads

- What: `publish`, `rewire` and `export_plan` each list every issue and pull request with
  `state=all&per_page=100 --paginate` (`scope.py:1084,1174,1215`). Keep one listing per `Scope`
  instance, updated in memory by each issue POST and PATCH that Scope makes (the code already appends
  created issues, `:1105`). Raise the timeout of paginated calls to 120 s, the value Project already
  uses (`project_sync.py` `TIMEOUT`).
- Evidence: a 3-child split with 200 unrelated issues makes 44 calls, including 3 full issue listings
  and 1 label listing (fake client). A repository with 5,000 issues and pull
  requests means 50 pages per listing. At 0.3-1 s per page that is 15-50 s, against a 30 s timeout
  (`:250`). Not measured live.
- Saving: two of the three listings per split (about 30-100 s at 5,000 items), and the timeout failure
  that is likely at that size.
- Effort S-M. Risk low: a body read after Scope's own write comes from the PATCH response.
- Tests: the fake counts 1 listing per split publish. A paginated call gets the longer timeout.
- Verdict: **do**.

### SC15. Reconcile only the implemented issue's ancestors in the hook

- What: `speckit.scope.reconcile` runs as a mandatory `after_implement` hook (`extension.yml`) and stays
  enabled in managed projects (`reconcile.py:11,36`). It lists every issue, then for **every** Scope
  parent ever made it reads `sub_issues` and rereads the parent (`scope.py:1370-1408`). Add `reconcile
  --issue <n>`, which walks `GET issues/{n}/parent` up to the root and reconciles only that chain. The
  hook passes the bound issue (from `scope-source.json`). Plain `reconcile` keeps the full sweep for the
  manual command. Separately, reread a parent (`:1408`) only after a write to it.
- Evidence: 3 / 21 / 101 calls for 1 / 10 / 50 parents with nothing to change.
- Saving: per Implement, about 2P calls down to 2-3 per ancestor level. With 50 parents that is 101
  calls (30-100 s) down to about 4. The reread fix alone saves P calls (S).
- Effort M. Risk low-medium: a parent whose child changed outside Sanduq waits for the next full sweep
  or the next Implement under it.
- Consumer impact: none. The hook command text gains `--issue`. Tests: a chain reconcile touches only
  ancestors. A full sweep is unchanged.
- Verdict: **do**.

### SC16. Stop the prerequisite walk at Done; timelines only for direct prerequisites

- What: `prerequisite_report` walks every transitive prerequisite, two calls each (`scope.py:692-712`).
  The full inspect then reads a timeline for each of them (`:745-753`). Do not descend below a Done
  prerequisite, keep descending through In review, and read timelines only for direct prerequisites.
- Evidence: 2 + 2N calls (2, 12, 42 for N = 0, 5, 20). A full inspect is about 3 + 3N. Approve and
  publish run a full inspect again whenever the snapshot is older than `board_cache_seconds` (300 s,
  `:593`), which is normal after an approval conversation.
- Saving: in a repository with long chains, roughly 40 calls down to 4 per inspect, gate or bind, and a
  shorter snapshot.
- Effort S. Risk medium: it changes the readiness rule. A Done issue whose own prerequisite was reopened
  no longer blocks.
- Verdict: **defer** until the owner decides on the rule. The code change is small.

### SC8 (round 3, carried). One GitHub transport, shared across extensions

- What: move `rate_limited`, `GitHub` and `ProjectRest` (`scope.py:220-515`, 296 lines) into
  `extensions/scripts/shared/sanduq_github.py`. Inject it with `package.py`, as `deps.py` and
  `check_inputs.py` are (`package.py:65-84`), into scope, workflow and project (pr optional). Keep
  `from scope import GitHub` working through a re-export.
- Why shared: there are six clients today. Scope `GitHub` (30 s timeout, GraphQL to REST fallback);
  Workflow `decisions.GitHub` (a copy of `api()`, and it execs the whole `scope.py` to reach the Project
  transport, `decisions.py:26-31,57-60`); `task_issues.GitHub` (**no timeout**, `task_issues.py:93-94`);
  `ci_evidence.GhClient` (bytes); `project_sync` `gh_raw`/`rest`/`call` (its own fallback, 120 s);
  `pr_publish.gh`. Today's load chain is `scope.py` → `workflow_policy` → `workflow.py` and
  `decisions.py` → `scope.py` again.
- Proposed interface (stdlib only):

  ```python
  class GitHubError(Exception): ...            # .args[0] message; .stderr, .returncode, .timeout
  def rate_limited(text) -> bool
  def run_gh(args, *, payload=None, timeout=60, binary=False) -> str | bytes   # GH_MISSING, GH_TIMEOUT
  class Client:
      def __init__(self, *, project=None, timeout=60, page_timeout=120)  # project: owner, ownerType, projectNumber, projectId
      def api(self, endpoint, method='GET', payload=None, pages=False)    # REST JSON; pages flattens --slurp
      def graphql(self, query, **variables)
      def project(self, args)          # `gh project ...`; REST fallback with today's validation (ProjectRest)
      project_transport: str | None    # 'graphql', 'rest' or 'graphql+rest', as now
      calls: collections.Counter       # per endpoint kind, for call-count tests and receipts
  def normalize_remote_url(url) / github_repository(root) / same_repository(a, b)   # R4 J3 / D4
  ```

  Each caller wraps `GitHubError` in its own error type and code (`ScopeError`, `GITHUB_DECISION_API_FAILED`,
  `GITHUB_API_FAILED`, `RuntimeError`), so messages and tests stay the same.
- Also in SC8, from round 3 and still open: cache `workflow_policy.load` by path and mtime, and use
  `yaml.CSafeLoader` when it is available (86 parses took 3.5 s in one test file; round 3 counted 27
  per six-question clarification publish). Cache `_workflow_module` and `_decisions_module` per
  process, and stop the `sys.path.insert` on every call (`workflow_policy.py:62-78,163-171`). Remove
  `accept_plan.py --spec/--archify` (`:218-219,237-240`), which their help text says were "removed in
  1.7.0".
- Saving: maintenance. `scope.py` drops by about 300 lines. One timeout policy (it fixes the hang in
  `task_issues`). The `decisions.py` to `scope.py` exec goes (one 95 KB module load for each decision
  Project call). Runtime is 0.1-0.5 s per command.
- Effort M (Scope's part). Its owner is R6 for the module and the packaging. Risk medium: three
  extensions change together. `test_project_rest.py` (30 KB) moves with `ProjectRest`.
- Consumer impact: none. The injected files are internal.
- Tests: the whole scope suite, `test_project_rest.py` against the module, and a package test that each
  archive carries the same `sanduq_github.py` digest.
- Verdict: **do**, with one owner (R6). Do the Scope fixes SC10 and SC11 first. They do not need it.

### SC17. Clarify and Brainstorm overlays in scope-gate and scope-brainstorm become compact `replace`

- What: the scope-gate Clarify overlay is a `prepend` (`scope-gate/preset.yml`), so unmanaged Clarify
  composes the whole upstream `clarify.md` (17,832 B) under it, only to say "do not execute its old
  interactive loop" and to keep its taxonomy "as reference" (`clarify-github.md:15-19`). Change both
  scope presets to `replace`. Move the coverage taxonomy (per engine) and the "applying answers" rules
  into the `github-clarification` skill, which every mode reads. The two scope overlays and the two
  workflow overlays then shrink to pointers of about 600 B each. Drop the "Managed workflow precedence"
  paragraphs in both scope overlays (`clarify-github.md:5-10`, `brainstorm-github.md:5-10`). They are
  never active: managed projects never render these files (a top-layer `replace`, structure O4), and
  unmanaged projects have no `.specify/workflow.yml`, so the condition is false.
- Evidence: the workflow preset's `replace` versions (2,857 B and 2,735 B) already work at priority 1.
  The taxonomy is held twice in the managed Clarify stage (round 3 lens 2: `SKILL.ext.md` step 7 and
  `speckit.clarify.md:23-38`, 1,096 B). Overlap between the scope and workflow versions is only 269-291
  characters of literal text, so there is nothing to share as-is.
- Saving: unmanaged Clarify about 18 KB per round (about 4.5k tokens). The unmanaged Brainstorm saving
  is not measured (the Superspec source was not available). Managed Clarify about 1.1-1.8 KB per round
  (14,839 B, down 8-12%). The shadowed preset text goes from 4.2 KB to about 1.2 KB. Answer to O4: in
  managed projects the shadowed text costs no tokens today, only package bytes. This option shrinks it
  and keeps both presets.
- Effort S-M. Risk medium: unmanaged users lose upstream Clarify wording they may lean on, and the
  Superspec upstream text needs a check. The workflow overlays are R1's files.
- Consumer impact: preset versions bump. `install.py` re-adds presets whose digest changed (round 3
  X7). Unmanaged users run `specify preset add` again, which is already the documented step after an
  update (`scope-gate/README.md`).
- Tests: `test_speckit_compat.py` renders each bundled preset. A test checks that the taxonomy appears
  once in the Clarify stage file set. `test_instructions.py` path checks.
- Verdict: **do**.

### SC18. Split `specify-gate.md` into an always-on header and a standalone reference (fixes D4)

- What: keep about 1 KB that applies in both modes: one explicit issue; run the guard; use the returned
  prompt; keep every open decision as `[NEEDS CLARIFICATION]` with no three-marker cap; any expansion
  returns to Scope. Move the Backlog-only rule, the after_specify chaining and the "no questions in chat"
  text to `extensions/scope/references/specify-standalone.md`, read only "without
  `.specify/workflow.yml`". Managed Specify then reads only `stage-specify.md`, which already holds the
  clarification-marker rule (`stage-specify.md` "Managed overlay").
- Evidence: D4. `specify-gate.md` is 2,997 B and is composed in every managed Specify run
  (before-full `per_stage.specify`).
- Saving: about 1.5-2 KB per managed Specify (13,760 B, down 11-15%), and the conflicting instruction
  goes.
- Effort S. Risk low. Consumer impact: scope-gate version bump, re-added by the installer.
- Tests: `test_instructions.py` (the path exists). A test checks that `specify-gate.md` does not name
  `after-specify` outside the standalone condition.
- Verdict: **fix-first**, for the conflict.

### SC19. Take gate, bind and render text out of the analyst's contract

- What: `analysis-contract.md` sections "Reusing an inspect snapshot" (873 B) and "Rendering the
  specification" (445 B) are read on every Scope stage. Gate and bind find the snapshot on their own
  (`scope.py:604-609`). `stage-scope.md` already carries render-spec. Move the snapshot rules to the
  README (operators) and the render error codes to `stage-scope.md`.
- Saving: 1,318 B per Scope stage (18,143 B, down 7%).
- Effort S. Risk low. Tests: `test_instructions.py`.
- Verdict: **do**.

### SC20. Faster scope tests; close the gaps

- What: `test_fresh_binding` and `test_revalidation` take 41 of 57 s. The cost is 273 git subprocesses
  in their fixtures (19.6 s). Build one fixture repository per class (`setUpClass`) and copy it per test
  with `shutil.copytree`. The workflow-policy cache from SC8 also removes most of the 3.5 s of YAML.
  Add the missing tests: D1 (an unrelated prose dependency), D2 (remote forms and case), D3 (`gh`
  timeout, no origin), and a reconcile call-count test for SC15.
- Saving: an estimated 15-25 s of 57 s (30-45%) per scope suite run on Windows CI.
- Effort S-M. Risk low: isolation holds, because each test still gets its own copy.
- Verdict: **do** (the gap tests ship with SC10 to SC12).

### SC21. The rollback protocol has no writer

- What: `publish` refuses a journal marked `rolled_back` (`scope.py:1049`), and `controls.md:29` tells
  the agent about it, but no code sets the flag. The journal stores full before-images of every issue it
  touches (`:1082,1129,1180,1260`), and no code reads them. Either add `scope.py cancel <operation>`,
  which marks the journal and lists the before-images for manual repair, or say in `controls.md` that
  cancelling means editing the journal by hand. Slim the before-images with SC13.
- Effort S. Risk low. Verdict: **defer**. Decide with W/X7 backup and recovery requirements. Ship only
  the doc line now.

### Not recommended

- **SC2 / P3** (fold or stop installing `scope-brainstorm`): **drop**. The user decided on 2026-10-20 to
  keep three presets (`round-4-plan.md` "Decision"). SC17 gets most of the text reduction without it.
- **SC7 host tokens** (`__SPECKIT_COMMAND_*__` for the 5 remaining `$speckit-` sigils): **defer**, as
  round 3 did. It is still not verified on the pinned Spec Kit (8147943).

## 4. Recommended do-list and order

1. Fix first: SC10 (D1), SC11 (D2), SC12 (D3, D5), SC18 (D4). All S. Ship them with their SC20 gap
   tests.
2. Then: SC13 (inspect output, M), SC14 (one listing, S-M), SC15 (reconcile scope, M), SC17 (compact
   overlays, S-M; coordinate the workflow overlay files with R1), SC19 (S).
3. With R6: SC8 shared `sanduq_github.py` plus the policy cache and the dead flags.
4. Defer: SC16 (needs a rule decision), SC21 (cancel command), SC7.

Overlaps: SC11 uses the normaliser that D4/J3 (R4) and SC8 (R6) also need. Land the helper once.
SC13 and SC21 both slim the journal before-images. SC17 and SC18 change preset files, so bump
scope-gate and scope-brainstorm together.

## 5. Not verified

- Real `gh` latency for paginated listings (SC14) and for the reconcile sweep (SC15). The counts come
  from the fake client.
- D4's effect on agent behaviour. No managed run was made.
- The size of the upstream Superspec Brainstorm (SC17's unmanaged Brainstorm saving).
- The token saving of SC13 depends on whether agents read stdout, the file, or both.
- The Illustrate PNG export test was skipped here (Playwright absent), not failed.
