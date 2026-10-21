# Round 5: plan (round 4's deferred items)

Approved by the owner 2026-10-21 (in chat). Brief: `handoff-2026-10-21.md`. Design sources: the round-4 review file named
per item, as amended by `round-4-codex-review.md`. Operating model as in round 4: the orchestrator plans, routes and
commits; Opus 5.5 streams (effort high) code with disjoint file ownership; Codex cross-checks the plan and the diff;
nothing is implemented before the owner approves this plan.

## Owner decisions (2026-10-21)

| # | Question | Decision |
| --- | --- | --- |
| 1 | X23: do docs-only or README-only package edits need a bump? | No. The guard hashes shipped behaviour only; `README.md`, `CHANGELOG.md`, `LICENSE` and `docs/**` are exempt. |
| 2 | SC16: may the prerequisite walk stop at a Done prerequisite? | Yes. Stop below Done, keep descending through In review, read timelines only for direct prerequisites. |
| 3 | W25, W26: still dropped? | In. |
| 4 | `worker_brief.project_result`: remove or keep? | Remove (with `project_usage`, `PROJECTION_SCHEMA` and their tests). |
| 5 | X14: cluster change or image `python3`? | Deferred. CI stays as is. |

## Items and design

| Id | Item | Design (binding points) | Stream |
| --- | --- | --- | --- |
| SC8 / X22 | `extensions/scripts/shared/sanduq_gh.py`, injected by `package.py` into scope, workflow, project, pr (as `sanduq_remote.py`) | Interface below. One timeout policy, one retry rule, one rate-limit rule. Callers wrap `GhError` in their own error type and code, so messages and tests keep their shape. Shared `git()` stays dropped. | S-SH (module), consumers in their streams |
| X23 | Bump guard | `release.py prepare` stores `inventory_sha256` (behaviour inventory: every packaged file except `README.md`, `CHANGELOG.md`, `LICENSE`, `docs/**`) in each catalog entry. A lint check fails when a package's current behaviour inventory differs from the catalog entry for its manifest version and the package is not listed in `pending-releases.json`. Spec Kit ignores the extra field. | S-SH |
| CRLF | `release.py bump` tolerates a CRLF working copy | Read and write the manifest preserving its line endings. | S-SH |
| W18 | Stat-keyed hash cache for `package_digest` | `{label: [size, mtime_ns, sha256]}` in `.specify/workflow/runtime/hash-cache.json` (git-excluded); reuse only when size and mtime match and mtime is over 2 s old. Full-hash fallback: every evidence write (`complete`, `sync-amend`, `finalize`) hashes fully and refreshes the cache; the cache serves claims and read-only checks only. | S-WF |
| W24 | Same cache for the source inventory | Same rules as W18. Measure first on a large tree (the fixture's 2.5 s is mostly first-open scanning); ship only if the measured saving holds. | S-WF |
| W19 | Resolve each directory once in `canonical_path` | Memoise resolved parents per operation, `lstat` the leaf, resolve fully when the leaf is a link. Adversarial tests: symlinked leaf, symlinked directory, Windows junction, case-differing path on Windows, `..` segments, a link created between two calls in one operation. | S-WF |
| W25 | Index the foreign active claim | A derived cache, never a source of truth: entries keyed by checkpoint path with size and mtime; a stale or missing entry re-reads that checkpoint. The claim result is identical with and without the index (test). | S-WF |
| W26 | Merge the git and sha256 helpers inside the Workflow package | One `sha256` helper and one `git` runner per package, keeping each caller's error contract and the W1 memo invalidation. No cross-extension `git()`. | S-WF |
| W27 | Drop `repo_path` from the checkpoint | Writers stop writing it; readers accept old checkpoints that carry it; checkpoint schema version and the JSON schema updated; a migration test loads a 1.17 checkpoint. | S-WF |
| PR-RES | Remove `worker_brief.project_result`, `project_usage`, `PROJECTION_SCHEMA` | Delete with their tests; grep proves no other reference. | S-WF |
| IP21 | Native Progress hook wiring by default for new installs | `install.py --with progress` on a project with no Progress wiring writes `hook_wiring: native`. Existing projects keep their choice and the IP9 hint. Gate: the live run L-RUN with native wiring (below). | S-INST |
| SC8 Workflow side | `decisions.py`, `task_issues.py`, `ci_evidence.py` on `sanduq_gh`; `decisions.py` stops exec-ing `scope.py` | `ProjectRest` moves into `sanduq_gh` so Workflow reaches it without loading Scope. | S-WF; `install.py required_gate_checks` S-INST |
| SC16 | Prerequisite walk stops at Done | Readiness rule text in the Scope docs and a changelog Migration line: a Done prerequisite whose own prerequisite was reopened no longer blocks. Call-count tests (2 + 2N before, bounded after). | S-SC |
| SC17 | Compact `replace` overlays in scope-gate and scope-brainstorm | Both scope presets `replace`; taxonomy and "applying answers" move into `github-clarification`; the four overlays (two scope, two workflow preset) become pointers of about 600 B; drop the never-active "Managed workflow precedence" paragraphs. Check the upstream Superspec Brainstorm text first and record what unmanaged users lose. Test: taxonomy appears once in the Clarify stage file set. | S-SC (owns the two workflow-preset overlay files this round) |
| SC21 | Rollback writer | `scope.py cancel <operation>` marks the journal `rolled_back` and prints the before-images for manual repair; `controls.md` names it. No automatic GitHub writes. | S-SC |
| SC8 Scope side | `GitHub`, `ProjectRest`, `rate_limited` move to `sanduq_gh`; `from scope import GitHub` keeps working by re-export | Plus round 3's leftovers: cache `workflow_policy.load` by path and mtime, `yaml.CSafeLoader` when present, cache `_workflow_module`/`_decisions_module`, remove `accept_plan.py --spec/--archify`. `test_project_rest.py` targets the module. | S-SC |
| PM5 | `extensions/project/scripts/project_init.py` (stdlib) replaces `project-init.sh` / `.ps1` | Same flags and `config.json` (`-AutoCreateColumns`, `-AllowStatusReset`, `-HooksMode`, owner type, rerun preservation, archived-item restore, round 4's B3 and board-status guards); no prompts; exit 4 with JSON `needs` for a missing choice. The shells become one-release stubs that call it, with a Migration note. `init.md` shrinks to one invocation. `smoke_project_init.py` drives it on both OSes. | S-PM |
| PM2b | Review-feedback reply and resolve | `pr_feedback.py reply|resolve --plan <approved file>`: writes only items in the approved plan; resolve is refused until the PR head contains the pushed commit; the trust rules in the command stay verbatim. | S-PM |
| SC8 PR/Project side | `project_sync.py`, `pr_publish.py` on `sanduq_gh` transport | Project keeps its GraphQL-first, REST-on-exhaustion switch and mutation dry-run (PM22); only the runner, timeout and scope parsing are shared. | S-PM |
| AU22 | Vendor `init_manual.py` | Upstream dev-tools portable accepts `--project-root` for `load_ci`, `--no-tools`, writes `lifecycle.impact_scope`; sanduq maps it in `vendor.lock.json` with one import rewrite and deletes its copy. Diff first: anything the sanduq copy has that upstream lacks goes upstream. | U-UP, then S-VEND |
| IP19 | One SVG scan module for the Illustrate verifiers | Upstream `scripts/svg_scan.py`, loaded like `theme_tokens.py`; every upstream verifier test green; transform checks untouched. | U-UP, then vendor |
| IP22 | Remove Progress v2 output and the classic layout | Upstream agent-tools: v2 `display` and `--schema v2`, `--layout classic`, classic half of `blocks.js` go; `model.build_pair` and the one-line summary are refactored so v2 numbers are internal only. Safety for old Workflow (1.16 and earlier request v2): Progress answers a v2 request with exit 2 and a message naming the Workflow upgrade, and the sanduq manifest or doctor states the Workflow minimum. `layout: classic` falls back to timeline with one notice. | U-UP, then S-VEND |
| IP24 | Progress bench tests from one source | Upstream bench reads CLI and skill paths from an env root (IP7 pattern); sanduq vendors `tests/bench` as an unpackaged input and drops its copy. | U-UP, then S-VEND |
| W9 | Split `workflow.py` phases 1-2 | Module map in `round-4-review-workflow.md` W9 (`wf_core`, `identity`, `policy`, `fingerprints`, `health`, `receipts`); every moved name re-exported; `_OPERATION` only in `wf_core`; patched names move with all callers or the patch is retargeted in the same commit; `check_docs.py` AST reads and `workflow_policy` path loading keep working; benchmark wrappers wrap defining modules. Starts after every other stream is committed. | S-W9 |
| SHARD | Memory shard weights from measured times | Rebuild `.github/scripts/shard_weights.json` from the first sharded CI run's job logs. | S-CI |
| I3 | Live check of the Plan-inputs sentence | One managed run on `samykabu/sanduq-r4-live`; pass when Execute's `complete` is not rejected with `UPSTREAM_INPUT_CHANGED_DURING_STAGE`. | L-RUN |

Deferred: X14 (owner). Unchanged from round 4: W9 phase 3 (split `Run`).

## Shared interface: `extensions/scripts/shared/sanduq_gh.py` (S-SH writes it first)

Stdlib only. Merges SC8's interface with PM22's constraint (share semantics, not every caller's policy).

```python
class GhError(Exception): returncode, stderr, timeout: bool, rate_limited: bool, reset_at: int | None
def rate_limited(text) -> bool                  # moved from scope.py
def run_gh(args, *, payload=None, timeout=60, binary=False, cwd=None) -> str | bytes
    # 127 / GH_MISSING when gh is absent; GhError(timeout=True) on timeout
    # one retry after 2 s for a GET that failed with a 5xx or a timeout; never retries a mutation
def api(endpoint, *, method='GET', payload=None, pages=False, timeout=60, cwd=None)   # parsed JSON, pages flattened
def graphql(query, *, timeout=60, cwd=None, **variables)
def token_scopes(auth_text) -> set[str]         # whole-token set, as project_sync.py:122-124
class ProjectRest: ...                          # moved from scope.py unchanged, with its masked-owner check
```

Default timeout 60 s; long paged listings pass `timeout=120` explicitly. GraphQL rate-limit exhaustion raises
`GhError(rate_limited=True, reset_at=...)`; Scope's GraphQL-to-REST switch and Project's own switch decide what to do
with it. Tests: each error shape, the retry rule (GET retried once, POST/PATCH/DELETE never), archive bytes equal the
source in every package that carries it, installed-layout import without Workflow or PyYAML.

## Streams and ownership

| Stream | Owns | Items |
| --- | --- | --- |
| **S-SH** shared and release tooling | `extensions/scripts/` (shared, `package.py`, `release.py`, `check_docs.py`, tests) except the smoke scripts' Project parts | `sanduq_gh.py` first, its injection and tests; X23; CRLF |
| **S-WF** Workflow runtime | `extensions/workflow/scripts/` except `install.py`, `upgrade.py`, `hosts.py`; workflow schemas, references, tests except the installer tests | W18, W24, W19, W25, W26, W27, PR-RES, SC8 Workflow side |
| **S-INST** installer | `install.py`, `upgrade.py`, `hosts.py` and their tests | IP21; `required_gate_checks` on `sanduq_gh` |
| **S-SC** Scope and the scope presets | `extensions/scope/`, `presets/scope-gate/`, `presets/scope-brainstorm/`, the Clarify and Brainstorm overlays in `presets/workflow/` | SC16, SC17, SC21, SC8 Scope side |
| **S-PM** PR and Project | `extensions/pr/`, `extensions/project/`, `extensions/scripts/smoke_project_init.py` | PM5, PM2b, SC8 PR/Project side |
| **S-CI** CI | `.github/` | SHARD; the `project-init` job for PM5; the X23 lint step |
| **U-UP** upstream | `D:\Projects\Personal\sanduq-skills-round5` (branch `feat/round-5`) | AU22, IP19, IP22, IP24 upstream sides |
| **S-VEND** vendored sides (after the upstream tags) | `vendor.lock.json`, `extensions/progress/`, `extensions/user-manual/`, Illustrate's vendored tree | AU22, IP19, IP22, IP24 sanduq sides |
| **S-W9** split (last) | `extensions/workflow/scripts/workflow.py` and new modules, the patch sites in workflow tests | W9 phases 1-2 |
| **L-RUN** live run (early, parallel) | `samykabu/sanduq-r4-live`, scratch clone | I3 and the IP21 gate on the released 1.17.1 set with `hook_wiring: native` set by hand |

Rules from round 4 stand: edit only owned files, requests go in `docs/internal/round-5-notes-<stream>.md`; no
tree-changing git commands; a regression test per defect; `## Unreleased` changelog entries with a `### Migration`
block where a consumer sees a change; no bumps or catalog edits by streams.

## Order

1. L-RUN starts at once on released packages (check `gh api rate_limit` first).
2. S-SH writes `sanduq_gh.py` first; S-WF, S-INST, S-SC, S-PM, S-CI and U-UP start in parallel against the interface.
3. Upstream: PR, CI, merge, tags (dev-tools, illustration-tools, agent-tools), release runs, then `vendor.py update`;
   then S-VEND.
4. IP21 lands only if L-RUN passed with native wiring.
5. Commit per stream after review; then S-W9 on the committed tree; full suites.
6. Codex reviews the round diff; fixes; AFTER measurements against BEFORE on the same machine in alternating order
   (claim time for W18/W24/W19, Scope inspect call counts for SC16, Clarify bytes for SC17, hook time for IP21).
7. Bumps, release notes, PR, CI (every job's conclusion), merge, release run and catalog promote, report page.

## Releases and consumer migration (expected)

| Change | What an installed consumer sees |
| --- | --- |
| SC16 | A Done prerequisite whose own prerequisite was reopened no longer blocks readiness. |
| SC17 | Unmanaged Clarify and Brainstorm no longer compose the upstream text under the overlay; run `specify preset add` again after the update (already the documented step). |
| PM5 | `project-init.sh` / `.ps1` still work for one release and print the `project_init.py` line; `jq` is no longer needed. |
| IP21 | New Progress installs wire hooks natively; existing installs are unchanged. |
| IP22 | `--schema v2` and `--layout classic` are gone; `layout: classic` falls back to timeline; an old Workflow asking for v2 gets a message naming the upgrade. |
| W27 | New checkpoints have no `repo_path`; old ones still load. |
| X23 | Maintainers only: lint fails when shipped behaviour changed without a version bump. |

Expected bumps: Workflow, Scope, Project, PR, Progress, Illustrate, User Manual; presets scope-gate, scope-brainstorm,
workflow. Upstream: dev-tools, illustration-tools, agent-tools.

## Risks to watch

1. W18/W24/W19 weaken evidence or containment checks: the full-hash fallback and the adversarial tests are release
   gates, and Codex reviews those diffs specifically.
2. SC8 touches four extensions at once: every caller keeps its error codes; the whole scope, workflow, project and pr
   suites must pass; GitHub mutations are never retried.
3. IP22 with an old Workflow: the v2 refusal must be actionable, never a silent empty view.
4. W9 last: no behaviour change; the full suite and the benchmark counters equal before and after.

## Amendments after the Codex plan review (`round-5-codex-plan-review.md`)

Binding on every stream; where they disagree with the tables above, these win. Scope is unchanged.

1. **`sanduq_gh.py` contract.** The module owns transport only: `run_gh`, `api`, `graphql`, `rate_limited`,
   `token_scopes`, `GhError`. Retries are opt-in: `run_gh(..., retry=False)` by default; a caller passes `retry=True`
   only for a read it knows is safe (REST GET without `-f/-F/--input`, a GraphQL query that is not a mutation).
   Never retried: any `gh project` command, any GraphQL mutation, any REST call with a method other than GET or with
   fields. A timeout after a possible write is reported, never retried. GraphQL errors on exit 0 are still detected.
   Scope's `GitHub` client class (with `masked_owner_failure`, `verify_project`, the GraphQL-to-REST switch) and
   `ProjectRest` stay in Scope's ownership; they move into a second injected file `sanduq_scope_github.py` only if
   S-SC can do so with `ScopeError`/`require` replaced by a module-local error that Scope maps back; otherwise they
   stay in `scope.py` and `decisions.py` keeps loading Scope's transport. S-SC decides and records it. Every caller
   keeps its error codes, fake runners and seams (`test_decisions_corrective.py:96`, `test_task_issues.py:386`,
   `test_ci_evidence.py:146`, `test_round4.py:182`, `test_execution_tools.py:151`, installer branch-rule tests).
   Caller inventory per stream: PR `pr_publish.py` (including `:101`, `:159`), `pr_feedback.py:45`,
   `pr_changelog.py:84`; Project `project_sync.py` `gh_raw` paths (`:109`, `:161`, `:341`, `:433`); `ci_evidence`
   keeps binary downloads with its 300 s timeout.
2. **Caches are advisory where safety is enforced (W18, W24, W25).** A cache may only skip work on a path that does
   not decide evidence, containment or claim exclusion. Full hashing (bypassing both the hash cache and the operation
   memo) is required in `complete`, `sync-amend`, `finalize`, `revalidate`, `revalidate-upstream`, migrations,
   `receipt_status` when called for acceptance, and `ci_gate`. Portable hashing (git attributes and index state) is
   unchanged. W25's index must discover new checkpoints, drop deleted ones, re-read replaced or malformed ones, and
   never trust a cached "inactive"; the claim re-reads every candidate that the index reports active or stale, under
   the dispatch lock. Tests for each case.
3. **W19.** Keep rejecting `..`, absolute, drive and UNC labels. A memoised parent is valid only while its `lstat`
   identity (device, inode or file id, mtime) is unchanged; any change, or any link in the chain, falls back to the
   full resolve. Test an ancestor replaced by a symlink or junction between two calls in one operation.
4. **W26.** Merge only primitives with equal contracts; stored digest formats stay byte-identical; `sanduq_hash.py`
   (injected into Assure and User Manual) keeps its interface.
5. **W27 checkpoint migration.** Separate the checkpoint schema version from the policy `SCHEMA` constant. Readers
   accept checkpoint versions 1 and 2 (Workflow loader, migration path, relocation-history reader, `ci_gate.py:95`,
   Scope's `workflow_policy.py:97`); the three writers write version 2 without `repo_path`; `docs/workflow/schemas.md`
   and the identity fixtures updated. S-WF owns `extensions/scope/scripts/workflow_policy.py` lines for this only and
   coordinates with S-SC through the notes file (S-SC edits other parts of that file; S-WF's change lands first).
6. **IP21.** Besides the live gate, installed-layout tests for: first install (native), existing implicit and
   explicit choices kept, upgrade, host switching, rollback.
7. **IP22 compatibility.** Spec Kit does not enforce `requires.extensions`, so the gate is at runtime: Progress 1.6
   answers a `--schema v2` or `--layout classic` request with exit 2 and one line naming the installed Workflow
   version and the upgrade command; Progress `status`/doctor flags an installed Workflow below 1.17. The text summary
   and the runs JSON Workflow 1.17 uses (`progress_bridge.py:302`, `:330`) stay byte-compatible. This is a loud break
   for Workflow 1.16 and earlier, after one deprecation release, as designed.
8. **X23.** Hash the final packaged inventory (injected helpers and bundled presets included). Exempt only
   `README.md`, top-level `CHANGELOG.md`, `LICENSE` and `docs/**`; commands, skills, references and templates
   (including nested `templates/CHANGELOG.md`) stay covered. Bootstrap: an entry without `inventory_sha256` is
   skipped with a notice until the next release writes it. A pending-release exemption counts only when it names a
   version greater than the catalog's.
9. **PM5.** A compatibility table of every Bash flag and its PowerShell counterpart, kept by the Python script (both
   spellings accepted by the stubs). Command file is `commands/speckit.project.init.md`. Replace the PowerShell
   function-intercept fixtures with a fake `gh` on `PATH`; keep every status-preservation and failure test
   (`test_project_sync.py:511` onward).
10. **PM2b.** The plan file has a schema binding repository, PR number, head commit expected after push, and the exact
    approved replies and resolves by thread and comment id, with a digest the command shows the user for approval.
    The script refuses a changed plan, another PR's threads, a head without the pushed commit, and repeats work
    idempotently. Tests for each.
11. **SC16.** Stop only where Scope's logical `status()` is Done (aliases applied; cancelled or wrongly closed still
    block). `test_scope.py:218` changes deliberately, with the Migration line. Tests: In review traversal, direct-only
    timelines, overrides, shared prerequisites, cycles, call counts.
12. **SC17.** Acceptance includes rendered unmanaged and managed Clarify and Brainstorm procedures, not only a
    taxonomy count.
13. **SC21.** `cancel` takes the journal's `<issue>-<hash>` id, refuses ambiguous or outside paths, holds the
    publication mutation lock, and prints created nodes, dependency before-images and catalog/map backups too.
14. **AU22.** Upstream keeps `--repo-root` (the command contract); `--project-root` is not added unless it already
    exists. The vendor mapping is added by S-VEND before `vendor.py update` runs; `vendor.py update` output in
    marketplaces and `delegate-task` is owned by S-VEND for this round.
15. **SHARD.** S-CI first adds per-module timing output to the sharded unittest step (one line per module), then the
    weights come from the first run with it. If that run is not available before release, SHARD ships as the logging
    change only.
16. **Ownership additions.** S-SH: `.github/scripts/ci_matrix.py` entry for `sanduq_gh.py` (coordinate with S-CI, who
    owns the file: S-SH requests it); W9 may touch `benchmark_front_half.py` (S-W9 owns it then; S-SH is done by then).
    I3 records Execute's first `complete` outcome before any recovery.
