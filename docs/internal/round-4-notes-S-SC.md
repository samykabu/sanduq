# Round 4 notes: S-SC (Scope, scope-gate, scope-brainstorm)

Tests: `uv run --no-project --python 3.11 --with pyyaml --with packaging --with jsonschema --with pytest python -m pytest extensions/scope/tests`.
Before: 248 passed, 1 skipped. After: 262 passed, 1 skipped (Illustrate PNG export, Playwright absent), 50 subtests.
Also run: workflow `test_execution_tools.py`, `test_lean_native_integration.py`, `test_speckit_compat.py`, the
`extensions/scripts/tests/test_package*.py` files (all pass), and `check_docs.py` (OK).

The 14 new tests are in `extensions/scope/tests/test_round4.py`. All 14 fail against HEAD (run from a `git archive`
copy of HEAD, with the remote patch pointed at `check_output`).

## F2 Scope side (W12/SC11/X10)

- `scope.py` imports `sanduq_remote` with the dev-tree fallback (`parents[2]/scripts/shared`). `Scope.__init__` uses
  `origin_url` then `github_slug`. A missing origin and a non-GitHub origin are `ScopeError`s with distinct messages
  (no URL in the message, so no credential leak).
- Case-insensitive `owner/repo` via `same_github_repository`: board cache (`cached_board`), board filter (`board`),
  native dependency rows (`dependencies`, through the new `same_repository`). `refs()` already used casefold.
- Tests: six remote forms, two look-alikes and a missing origin, a real `git init` checkout without origin (CLI exits 2
  with the message), mixed-case remote reads the board and a Done native prerequisite.
- Test setups in four files now patch `sanduq_remote.origin_url` instead of `subprocess.check_output`.

## F3

- SC10: `dependents` became `rewire_candidates`, which `publish` calls before its first GitHub write (split only).
  An issue whose dependency text does not parse is skipped with one stderr line, unless it is tied to the parent (native
  blocking link, `dependencies_before`, or its body names `#<parent>` or the parent URL); then the strict error is raised
  before any write. In the blocking-list fallback, a failing issue gets one native `blocked_by` read to decide.
  `rewire` takes the precomputed `(issue, deps)` list.
- SC12: both mains catch `subprocess.SubprocessError`. `accept_plan.run_tool` has a 300 s timeout and records a timeout
  (124) or a missing binary (127) as a failed step; its `git rev-parse` failure is a message. Text: the scope-brainstorm
  README now says the installer always applies the preset and doctor requires it; the `validate` message says the
  question list is capped only by `clarification.max_questions_per_round`.
- SC18: `specify-gate.md` (2,997 to 2,017 B) keeps the header for both modes. The Backlog rule and the after_specify
  chain moved to `extensions/scope/references/specify-standalone.md` (896 B), read only without `.specify/workflow.yml`.
- SC20: the gap tests above ship with each fix. Fixture reuse (`setUpClass`) was not done; it is not in my item list.

## SC18 contract for S-WF (`presets/workflow/commands/speckit.specify.md`)

What the composed scope-gate text below the Workflow prepend guarantees:

1. It names no after_specify hook, Brainstorm, Clarify chaining, Project sync or Backlog-only rule. Those live only in
   `.specify/extensions/scope/references/specify-standalone.md`, which it tells the agent to read only "Without
   `.specify/workflow.yml`". A test (`SpecifyOverlay`) holds this.
2. It always requires one explicit issue, runs `.specify/extensions/scope/commands/guard.md`, uses the returned
   prompt, keeps every open decision as `[NEEDS CLARIFICATION: ...]` with no three-marker cap, asks nothing in chat,
   does not set Ready, and sends any scope expansion back to Scope.
3. With `.specify/workflow.yml` it says the claim's stage reference owns binding and hand-off and points to
   `scope-binding.md` for flags.

So S-WF can keep "then continue with the upstream instructions below". Nothing else is required; optionally say that
the claim returns after the receipt and that disabled hooks stay disabled.

## Do items

- SC13: `inspect --output` prints `{issue, title, fingerprint, ready, blocked, prerequisites[{number,title,status}],
  comments, images, output, skeleton}`. The snapshot keeps issue `number, id, node_id, title, body, state,
  state_reason, html_url, labels[].name, user.login`; comments `id, author_association, created_at, updated_at, body,
  html_url, user.{login,type}`; prerequisites `number, title, status, body, html_url` (no nested issue). Journal
  before-images use `slim_issue`. Schema stays `schema_version: 1`. The analyst's step 2 says stdout is a summary.
  Measured (fake client returning the real issue #94 object and its comment, 1 issue + 3 Done prerequisites + 8
  comments; script `measure_sc13.py` in my scratchpad): stdout 58,127 B to 924 B; file 58,989 B to 25,693 B.
- SC14: one listing per split publish (`Scope.listing`, kept current by `remember` after POST/PATCH and `issue()`);
  title resolve, standalone `export-plan` and the full reconcile list fresh. Paginated reads use `PAGE_TIMEOUT = 120`.
  Measured, 3-child split with 200 unrelated issues: issue listings 3 to 1, total calls 49 to 47 (the fake answers a
  listing in one call; on GitHub each listing is one call per 100 items, so the real saving grows with the repository).
- SC15: `reconcile [<issue>]`. With an issue it walks `issues/{n}/parent` (404 ends the chain; a parent in another
  repository ends it) and reconciles only those ancestors; children come from the `sub_issues` rows. A parent is
  updated from its PATCH response, never reread. `commands/reconcile.md` (the hook) takes the issue from
  `scope-source.json`. Measured with nothing to change, parents = 2 chain + 1/10/50 unrelated: full sweep 8/26/106 to
  5/14/54 calls; hook form 6/6/6.
- SC19: "Reusing an inspect snapshot" and "Rendering the specification" left `analysis-contract.md` (4,124 to 2,888 B)
  for a new README section. `stage-scope.md` already says how to run render-spec and the error codes explain themselves,
  so I did not request a change there.
- README drift: the version sentence is gone (the catalog and changelog carry versions); the orchestrator's check_docs
  request is met.

## Not done

SC16, SC17, SC21, SC8 (deferred). SC20 fixture speed-up (`setUpClass` copy) not attempted.

## Requests

- S-WF: `presets/workflow/commands/speckit.superspec.brainstorm.md:30` "with no question count limit" is wrong when
  `clarification.max_questions_per_round` is set (`clarification.py:573`). Suggested: "with no question count limit
  unless `clarification.max_questions_per_round` caps the round".
- S-WF: `speckit.specify.md` per the contract above (optional wording only).
- S-SH: `benchmark_front_half.py` may list `extensions/scope/references/specify-standalone.md` for unmanaged Specify if it
  measures that path; the managed set is unchanged.
