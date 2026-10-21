# Round 4: final plan (reviews R1-R6 and Codex, reconciled)

Inputs: `round-4-review-{workflow,scope,assure-user-manual,pr-project-memory,illustrate-progress,cross-cutting}.md`
and the independent cross-check by Codex gpt-6.1-sol (`round-4-codex-review.md`, at 977e17b). Names stay as decided
(`round-4-plan.md`, D1-D5). Codex verified 26 of the 29 fix-first claims against the code and marked AU8, X20 and the
hand-drawn claim (IP18) as partly right; the wording below follows its qualifications. Where Codex disagreed with a
review, the resolution is stated.

## 1. Fix first

| Group | Items | Notes |
| --- | --- | --- |
| F1 Workflow | W10 reconcile accepts a fresh re-registration of an owned hook and still refuses an edited disabled entry; W11 CRLF-normalised hash in `sync-amend` and `migrate`; X21 timeouts on the three `gh` calls | W10 gates D3 |
| F2 Shared remote (D4) | `extensions/scripts/shared/sanduq_remote.py`, injected into Workflow, Project and Scope; Project stops loading `workflow.py`; Scope parses through it (W12/SC11/X10), compares case-insensitively, turns a missing origin into a message, and refuses the look-alike `evil.example/github.com/...` | one origin-reading policy (`remote.origin.url`) for all three; archive-byte and installed-layout import tests |
| F3 Scope | SC10 find rewire candidates before any write and parse unrelated issues leniently; SC12 tracebacks, timeout and the two text errors; SC18 split `specify-gate.md` so managed Specify no longer asks for the disabled after-Specify chain | SC20 gap tests ship with each |
| F4 Assure, User Manual | AU8 gate checks out the PR head (re-render consumer CI files on upgrade); AU9 init keeps consumer config and rewrites `extensions.yml` only on change; AU10 init never overwrites an authored page (both copies, upstream too); AU11 scan skips git-ignored folders; AU12 named task marker; AU13a text that survives Spec Kit's path rewrite | |
| F5 PR, Project | PM10 never edit a closed or merged PR, push when behind; PM11 one default-branch rule; PM12 owner type and rerun preservation in both init scripts; PM13 docs truth; P1 (Codex) Project refuses malformed state and recovers task identities before creating sub-issues | |
| F6 Illustrate | IP11 the hook fails closed with an actionable message when its setting cannot be read (Codex: no partial YAML fallback that leaves inline config off); IP12 import runs the required checks; IP13 CI runs Workflow's hook tests when Illustrate's hook changes | |
| F7 Docs | X12/D2 fix the reversed priority sentence and add the community `scope`/`memory` note; X18 three `check_docs.py` rules for version drift | |

## 2. Do

**D1 descriptions.** W17 and PM17 texts (finalize keeps "open the PR", `pr.generate` says "write the PR description",
status and Project say what they do in managed mode). Catalog grows by about 244 characters, still under 8,000.

**D3 Memory hooks, one gated migration with one owner** (R1 and R4 together; Codex amendments applied):

1. W10 first (Spec Kit's `register_hooks` re-creates entries with `enabled: true`; that is normal, not tampering).
2. Memory's approval hash binds each hook's event, command, condition and priority, and leaves out `enabled:` only for
   the two Workflow-owned hooks. Unparseable hook blocks refuse instead of being skipped (Codex found that the event
   heading is not hashed today).
3. Memory's `install.py` keeps an existing `enabled: false`; a tested restore, re-register, reconcile sequence covers a
   legitimate change to a managed entry.
4. W13 one `managed_hook` rule for reconcile and doctor; W14 the runtime runs the session handoff inside claim, using the
   lock it already holds, and stops on every `blocked` result. PM24 `pending` carries the policy facts the handoff needs.
   `session.md` honours `--run`/`--spec`; `prepare.md` gets a managed branch that returns the selected checks.
5. Queued and active archives: doctor and upgrade refuse while an archive run is active; old queue entries keep their
   approval and are documented, never silently re-stamped.
6. Only then `reconcile` disables `speckit.memory.session` and `speckit.memory.prepare` in managed projects.
7. Gate: a scripted pinned-Spec-Kit lifecycle (Memory before and after Workflow, re-init, update, restore, automatic mode
   off, interrupted archive) and one live managed run counted from its transcript.

**D5 forwarder.** W16: delete `progress_shim.py`; a legacy call with enabled Progress exits 2 and names the Progress
command; absent or disabled Progress keeps the legacy reporter. Keep the 35 bridge tests from `test_progress_shim.py`
(`ReportingModes`, `ProgressWiring`, `AbsentProgress`) and add IP23 contract tests for the seven verbs `reporting.md`
names. W21 reads Progress's text status line, not v2. IP22: deprecation notice only.

**Scope.** SC13 compact `inspect` stdout (largest token saving: about 53 KB to 22 KB per typical issue), SC14 one issue
listing per process, SC15 reconcile only the implemented issue's ancestors, SC19 gate, bind and render text out of the
analyst contract.

**Assure and User Manual.** AU13b `--show-block`, AU14 archives only when something publishes them, AU15 quiet builds
(upstream dev-tools), AU16 the rerun skip survives the manual hook (normalise both the input and the output hash of
`tasks.md`, per Codex), AU17 one-line dependency handling, AU18 Assure skill trim, AU19 status without a manual walk, AU20
remove config keys nothing reads, AU21 PR reads the gate through the script.

**PR, Project, Memory.** PM16 fewer `gh` calls in `project_sync.py`, PM23 PR URL from `gh pr create`, PM2a read-only
review-feedback gather script, PM19 Project tests move to `extensions/project/tests` plus five new (and `ci_matrix.py`
stops treating Workflow as Project's runner), PM20 memory fixture template (confirm on one class first), PM21 one
`pr_lint` source.

**Workflow runtime and tests.** W6 delegation health cache (measure first call, hit and invalidation; claim the saving
only for hits), W20 `sync-amend` text out of the once-per-session reading, W22/X25 fixture once per class in the slow
modules, W23 small cleanups.

**Illustrate and Progress.** IP14 Playwright only for vendored steps, IP15 no nightly rerun of upstream's identical block,
IP16 references only when needed, IP17 and IP18a upstream text and hand-drawn route (upstream illustration-tools), IP20
doctor reports doubled Progress wiring.

**CI, packaging, release.** X13 Playwright gating, X15 shards weighted by measured time (memory sharded too), X16 tooling
path filter and `actionlint`, X17 promote returns what it wrote and a test checks the release job stages it, X19 keep the
three newest install backups, X20 changelogs out of packages and LF for `LICENSE`/`*.txt`, X24 pin actions by SHA (at
least the two write workflows). X14 (Python in the self-hosted runner tool cache) is a cluster setting: the owner's action.

## 3. Defer

W9 split of `workflow.py` (patch sites, module globals and the AST docs reader make it a separate change), W18 and W19
(they weaken source-drift and containment checks), W24, W27, SC8 shared GitHub transport (D4 and the timeouts do not
need it), SC16 (needs a rule decision), SC17 wholesale overlay replacement, SC21, PM2b reply automation, PM5 init rewrite,
IP19 verifier scan module, IP21 native Progress wiring by default, IP22 removal of v2 (older installed Workflow still
asks for it; Progress declares no Workflow minimum), IP24, X22, X23 (needs a maintainer policy), AU22.

## 4. Drop

W25, W26, a generic shared `git()` or I/O module, deleting the whole shim test module, a fail-open YAML fallback, SC2
(decided), and any added-together or guaranteed savings. Every saving is remeasured on the same machine as its BEFORE.

## 5. Releases and consumer migration

All nine extensions and the scope-gate preset change (scope-brainstorm and the workflow preset get text fixes).
Upstream: dev-tools (AU10 portable copy, AU15, AU20 template), illustration-tools (IP12 references, IP17, IP18a).

| Change | What an installed consumer sees | Carried by |
| --- | --- | --- |
| D3 | Two Memory hooks become `enabled: false`; the claim runs the session check; Memory approval stays valid | Memory release first, then Workflow upgrade (`reconcile`); upgrade refuses during an active archive |
| AU8 | The rendered `documentation-gates.yml` checks out the PR head | re-rendered by `assure init` and the Workflow upgrade |
| D5 | A legacy reporting call with Progress installed exits 2 and names the Progress command | changelog Migration block; the claim reprints the protocol on a mode change |
| X19 | Only the three newest install backup zips are kept | doctor reports count and bytes |
| X20 | No `CHANGELOG.md` inside `.specify/extensions/<id>/` | none |
| P1 | A malformed `project-sync-state.json` stops the sync with a message instead of being reset | message names the fix |
| D4 | No visible change; Project syncs about 0.3 s faster | three package bumps |

## 6. Risks to watch (Codex's three, agreed)

1. Memory migration integrity: approval renewal can disable automation, strand queues and block prepared archives.
2. Partial upgrades: packages updated one by one can re-enable hooks or drop a schema an older Workflow still needs.
3. Remote mutation recovery: Scope and Project write to GitHub before local completion; retries must recover, not duplicate.
