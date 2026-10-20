**The direction is sound, but the implementation plan needs amendments before approval.** Most defect claims are supported. D3 needs a coordinated migration, D5 must retain unrelated tests, and retiring the shim does **not** make Progress v2 safe to remove from installed consumers.

I read all eight inputs and checked the current code at `977e17b` on `feat/round-4`. I made no file changes. Verification used source tracing, the pinned Spec Kit source, official GitHub CLI sources, and in-memory probes.

**1. Defect verdicts**

Paths below are relative to the repository. “Verified” means the defect follows from the current code; it does not imply a live consumer reproduction.

| ID | Verdict | Evidence and qualification |
|---|---|---|
| **W10** | **Verified** | `extensions/workflow/scripts/reconcile.py:42` and `:46` require whole-dictionary equality with the disabled journal copy. Re-enabling the entry makes both apply and restore fail; I reproduced both in memory. Install restores first at `scripts/install.py:829`; host switching reconciles at `scripts/hosts.py:562`. |
| **W11** | **Verified** | `extensions/workflow/scripts/workflow.py:1104` hashes historical blob bytes directly, while `scripts/sanduq_hash.py:45–49` normalizes CRLF. An in-memory CRLF history probe produced `SYNC_BINDING_MISMATCH`. Project writes through `write_text` at `extensions/project/scripts/project_sync.py:423`. |
| **W12 / SC11 / X10 / C1** | **Verified** | Scope’s unanchored regex at `extensions/scope/scripts/scope.py:525–528` rejects the reported valid forms and accepts `https://evil.example/github.com/acme/app`. I checked these against Workflow’s parser. Board and dependency comparisons are case-sensitive at `:553`, `:564`, and `:674`. |
| **SC10** | **Verified** | `scope.py:689–690` parses declared dependencies on unrelated issues; `:657` rejects unresolved prose. This occurs through `rewire` at `:1161`, after child creation and receipt writes at `:1104–1159`. The journal is not marked published until `:1164`. |
| **SC12: exceptions and timeout** | **Verified** | `clarification.py:1012` omits subprocess exceptions; missing-origin `check_output` is at `scope.py:525`, and neither main catches `CalledProcessError` (`scope.py:1534`). `accept_plan.py:202` has no timeout. |
| **SC12: text** | **Verified** | `presets/scope-brainstorm/README.md:3–4` promises conditional installation, but Workflow requires that preset (`workflow.py:1473–1477`). The “no question count limit” statement at `presets/workflow/commands/speckit.superspec.brainstorm.md:30` contradicts enforcement at `clarification.py:573–578`. |
| **SC18** | **Verified** | `presets/scope-gate/commands/specify-gate.md:27–40` explicitly demands after-Specify chaining. Workflow’s overlay continues into those instructions (`presets/workflow/commands/speckit.specify.md:7`), while reconciliation disables `speckit.scope.after-specify` (`reconcile.py:36`). The conflicting instructions are real; an actual agent chaining Clarify was not demonstrated. |
| **AU8** | **Partly** | Checkout lacks `ref:` at `extensions/assure/assets/github/documentation-gates.yml:17–19`; freshness diffs the recorded base against the checkout at `extensions/scripts/shared/sanduq_freshness.py:72–90`. This can falsely fail when base changes introduce included inputs. “Whenever the base moved” is too broad: excluded or irrelevant changes need not fail. GitHub documents the [head-SHA checkout alternative](https://github.com/actions/checkout#checkout-pull-request-head-commit-instead-of-merge-commit). |
| **AU9** | **Verified** | `extensions/assure/scripts/assure_init.py:89–91` always rewrites both files and replaces config with the template. In unmanaged projects, `update_hooks` re-dumps YAML even when `changed == 0` (`:47–50`). |
| **AU10** | **Verified** | `extensions/user-manual/scripts/init_manual.py:178` overwrites the language home page. Module pages have an existence guard at `:183`. This affects initialization when `manual.yml` is absent; an existing `manual.yml` stops init at `:165–166`. |
| **AU11** | **Verified** | `extensions/assure/scripts/assure_scan.py:135–148` walks ignored directories unless explicitly excluded. `.venv` and the other named directories are absent from `assure-config.template.yml:11–24`. |
| **AU12** | **Verified** | `extensions/user-manual/commands/speckit.user-manual.analyze.md:42–43` requests marker-delimited blocks without defining markers. Assure defines its markers explicitly at `extensions/assure/skills/assure/references/analysis.md:24–29`. Actual duplicate task generation remains untested. |
| **AU13a** | **Verified** | The bare token exists at `extensions/assure/commands/speckit.assure.document.md:124` and `extensions/user-manual/commands/speckit.user-manual.update.md:51`. At Spec Kit pin `8147943`, `src/specify_cli/agents.py:219–243` rewrites it into the current extension’s scripts path; rendering invokes that function at `:543`. |
| **AU13b** | **Verified** | `assure_scan.py:224–226` prints the whole block under `--check`. This is output reduction, not a correctness defect. |
| **PM10** | **Verified** | `extensions/pr/scripts/pr_publish.py:177–180` requests no PR state; `:206–207` edits any returned PR. GitHub CLI’s [finder](https://raw.githubusercontent.com/cli/cli/trunk/pkg/cmd/pr/shared/finder.go) prefers open PRs but can return closed or merged matches. Also, `ensure_branch` pushes only when upstream is missing (`:153–156`), so an existing upstream can remain behind. No live PR was edited during this review. |
| **PM11** | **Verified** | `extensions/pr/scripts/pr_changelog.py:70–73` defaults to `main`, converts a failed log lookup into empty output, then asserts “no commits.” That is false on the reported `master` case. |
| **PM12a** | **Verified** | Automatic owner detection treats successful `gh project list` as evidence of a user: Bash `project-init.sh:79–80`, PowerShell `project-init.ps1:95–98`. The CLI explicitly supports [organization owners](https://cli.github.com/manual/gh_project_list). Project then chooses the wrong REST namespace at `project_sync.py:449–450`. Explicit owner-type arguments avoid this. |
| **PM12b** | **Verified** | Bash takes the three settings from defaults at `project-init.sh:199–201`; PowerShell does likewise at `project-init.ps1:243–245`. Existing custom settings are not preserved. |
| **PM13** | **Verified** | `extensions/project/README.md:29` promises automatic `done`; `project_sync.py:411–417` stops automatic task completion at `in-review`. Explicit `done` does run task progress at `:493–494`. |
| **PM14** | **Verified** | Approval hashes include the hook’s `enabled:` line (`extensions/memory/scripts/archive.py:119–122`), while initialization recreates enabled hooks (`scripts/install.py:96–114`). Both interactions are reproducible without writing files. |
| **IP11** | **Verified** | `extensions/illustrate/hooks/self_check_hook.py:59–63` returns false when PyYAML cannot import. `main` consequently returns success without checking at `:143–144`. The launcher uses PATH Python at `:164`. |
| **IP12** | **Verified** | `extensions/illustrate/commands/speckit.illustrate.import.md:36–38` runs theme operations only. The required mechanical checks are in `skill/SKILL.md:61–63`; the import route does not load that procedure. |
| **IP13** | **Verified** | `extensions/workflow/tests/test_install_hooks.py:21` consumes Illustrate’s hook. `.github/scripts/ci_matrix.py:43–44` has no Illustrate dependency. Running its selection function in memory selected only Illustrate’s two jobs, with `install_smoke=false`. |
| **R5 hand-drawn defect / IP18** | **Partly** | The documented generator cannot convert arbitrary consumer input: `generate-hand-variants.cjs:582–586` processes fixed examples and the template; `primitive-sketchy.md:9–17` gives an upstream path. “A consumer cannot make one” is stronger than this evidence; the concrete defect is the missing supported arbitrary-file conversion route. |
| **X12 / C2** | **Verified** | `docs/start/install-speckit.md:39–40` reverses priority. At pin `8147943`, `src/specify_cli/catalogs.py:190` sorts ascending, and `extensions/__init__.py:4126` keeps the first ID. |
| **X18 / C3–C5** | **Verified** | Scope’s documented minimum is 1.8 (`docs/extensions/scope.md:12`) versus manifest `>=1.13.0` (`extensions/scope/extension.yml:14`); README says 1.8.0 (`README.md:8`) versus manifest 1.9.0 (`extension.yml:5`). Old unreleased headings remain in Assure `CHANGELOG.md:102`, Project `:50`, and User Manual `:149`. |
| **X21 / C6** | **Verified** | No subprocess timeout at Workflow `scripts/task_issues.py:92–93`, `scripts/ci_evidence.py:48–49`, or `scripts/install.py:307–308`. |
| **X20 / C7** | **Partly** | `.gitattributes:1–27` has no general `*.txt` or `LICENSE` rule. This checkout has `core.autocrlf=true`, and `git ls-files --eol LICENSE` reports LF in the index and CRLF in the working tree. `package.py:53` packages working-tree bytes. I did not independently compare the nine published archives or zlib versions. |

One additional distinction: **X17 is preventive work, not a remaining release-staging defect.** `release.py:224–229` writes both catalogs, pending releases and the root changelog; `release-extensions.yml:84` already stages those paths.

**2. D3: correct direction, incomplete migration**

The three reviews identify the right dependencies, but their combined instructions are not yet a complete release sequence.

1. **Land W10 before ownership changes and dependency updates.** Re-registration is normal behavior, not corruption. At the pinned Spec Kit commit, `register_hooks` removes and recreates an extension’s entries with `enabled=True` (`src/specify_cli/extensions/__init__.py:5132–5156`). Memory preserving disabled flags handles its own initializer only; it cannot prevent Spec Kit from re-enabling them.

   Accepting fresh enabled registrations is reasonable under managed ownership. Continue refusing disabled entries edited after reconciliation. Document that deliberately re-enabling an owned hook is reversed by reconcile. Do not describe this as reliably distinguishing user intent from registration—the current dictionary contains no provenance.

2. **Fix the approval hash before disabling Memory hooks.** Otherwise reconciliation invalidates approval, and `pending()` reports automatic mode disabled (`archive.py:563–568`).

   Removing `enabled:` from the hash can support D3, but the plan should explicitly define whether that exception applies only to the two Workflow-owned hooks or every Memory hook. Keep command, event, condition, priority and other execution settings bound.

   **Missed defect:** the current regex hashes hook blocks without their event headings (`archive.py:121`). I confirmed that moving an unchanged block from `before_specify` to `after_implement` leaves that hashed slice unchanged. Bind the event as part of the new representation, and refuse unsupported parsing rather than silently omitting hooks.

3. **Do not freeze hook descriptions indefinitely.** R4 recommends keeping disabled entries byte-identical and never changing descriptions while a journal exists. That preserves today’s journal equality, but becomes an undocumented restriction on future releases (`memory/scripts/install.py:19–22`, `reconcile.py:42–50`).

   Preserve existing disabled entries during re-init; define a tested restore, re-register, reconcile sequence when their managed fields legitimately change. W10 and this preservation rule complement each other.

4. **Implement runtime replacement before disabling either hook.** W14 correctly notices the non-reentrant lock: claim holds `dispatch.lock` (`workflow.py:3383`), and handoff acquires it again (`memory_handoff.py:62`; lock implementation `workflow.py:2460–2471`). Pass explicit existing-lock ownership internally; retain locking for standalone handoff calls.

   Also, stopping on only the two named Memory reasons is insufficient. Handoff can return `blocked` for unavailable commands, a missing helper, or malformed output (`memory_handoff.py:49–55`, `:66–82`, `:183–184`). A claim must stop on **every blocked result** and return required dispatch actions before granting new work. Persist session-check completion only after successful handling.

5. **Keep the semantic changes visible.** The runtime uses `default_checks` when checks were not supplied (`memory_handoff.py:116`); the current prepare command asks the agent to choose coverage checks and runs preflight (`memory/commands/prepare.md:15–18`). Queueing checks coverage, but does not perform the whole preflight (`archive.py:162–180` versus `:375–418`).

   The fallback command must return selected checks through Workflow’s handoff, as R4 proposes. Removing the early preflight delays some failures until verification; it is a behavior change, not merely duplicate-call removal.

6. **Add a migration for queued and active work.** “Re-approve once” is incomplete. `enable()` creates a new `enabled_at` (`archive.py:150`); pending entries retain the old value and are then blocked (`:178`, `:577–578`). Existing completion evidence binds `policy_hash` (`:549`), and prepared runs refuse changed implementation hashes (`:895–896`).

   Finish or explicitly recover active archives before the release. Explain how owners handle old queued entries after renewal. Never silently rewrite their approval timestamp.

7. **Keep D3’s live-run gate.** Source tracing establishes the duplicate routes, but does not prove actual host execution or token savings. Run the pinned Spec Kit lifecycle before and after, including Memory installed before and after Workflow, re-init, update, restore/uninstall, disabled automatic mode, and an interrupted archive.

**Installed-consumer failures to prevent:** automatic mode stopping after reconciliation; install/host-switch refusal after registration; disabled hooks with no replacement session gate; old queue entries stranded after renewal; and Memory processing a broader feature set because `session.md` ignores returned arguments (`memory_handoff.py:172–179`, `memory/commands/session.md:27–33`).

**3. D4 and D5**

**D4 should proceed as a narrow extraction.**

- Ship the stdlib helper in **Workflow, Project and Scope**. Scope is required to fix W12/SC11/X10. Inject before inventory generation (`extensions/scripts/package.py:65–86`).
- Preserve Workflow’s importable normalization names and error contracts. Its root-aware `github_repository` must still distinguish missing origin from non-GitHub origin (`workflow.py:326–330`).
- Pick one origin-reading policy. Scope uses `git remote get-url` (`scope.py:525`), while Workflow and Project read `remote.origin.url` (`workflow.py:455–459`, `project_sync.py:445`). Sharing only string normalization leaves their `insteadOf` behavior inconsistent.
- Fix Scope’s case-sensitive comparisons with the extraction. Normalization deliberately preserves repository-path case (`workflow.py:391–396`).
- Require archive-byte equality, inventory membership, isolated installed-layout imports without Workflow/PyYAML, and all remote/security cases. Existing packaging tests demonstrate the pattern (`extensions/scripts/tests/test_package_deps.py:23`).
- Restrict X11’s “no script loads installed workflow.py” assertion to **Project’s normalization route**. Taken literally, it contradicts Scope’s intentional checkpoint-identity loader (`extensions/scope/scripts/workflow_policy.py:62–78`).
- Bump all three consumers and update release dependencies. The helper will be copied into each archive; already-installed copies do not update themselves.

**D5 should proceed, with these corrections.**

- Reject old Workflow reporting calls when enabled Progress is installed, with exit 2 and a replacement. Keep absent/disabled Progress on the legacy route. The current forwarding branch is `extensions/workflow/scripts/progress.py:467–473`.
- Update old prompts and migration documentation: this deliberately breaks calls currently forwarded successfully.
- **Do not delete all of `test_progress_shim.py`.** It contains **35 tests** in `ReportingModes`, `ProgressWiring`, and `AbsentProgress` (`:88`, `:377`, `:439`) that remain relevant. Move them, then delete shim-specific coverage. Add the real-CLI reporting contract tests proposed by IP23.
- W21 must request the ordinary text status line directly. Reusing `progress_bridge.status()` would retain a v2 dependency (`progress_bridge.py:325–345`).
- **Defer IP22’s v2 removal.** Released Workflow still requests v2 and its shim fails when that status is unavailable (`progress_shim.py:100–112`). Progress declares no minimum Workflow version (`extensions/progress/extension.yml:14–19`). One warning release does not prevent incompatible independent updates.
- Keep the internal v2 construction until separately refactored: `model.build_pair()` builds v2 and passes it into v3 (`sanduq_progress/model.py:251–263`). Classic also receives v2 during refresh (`refresh.py:35–37`). Removing public v2 output does not remove these internal dependencies.

**4. Conflicts, estimates and missed work**

| Surface | Required resolution |
|---|---|
| `workflow.py`, `reconcile.py`, `memory_handoff.py`, Memory install/hash | One D3 integration owner; R1 and R4 cannot land independently. |
| `package.py` and shared helper injection | One packaging owner for D4, PM21, AU17 and exclusions; one consumer/version checklist. |
| `.github/scripts/ci_matrix.py`, `ci.yml` | Combine IP13, AU23, PM19 and X13–X16. PM19 also needs removal or revision of `build()`’s “Workflow already runs Project” suppression at `ci_matrix.py:111–112`. |
| Workflow and Scope presets | R1/R2 must agree on SC12, SC17 and SC18. Fix the explicit Specify conflict before replacing whole upstream procedures. |
| Shared GitHub transport | R2 recommends a large `Client` extraction; R4 and R6 recommend deferral. Follow R4/R6: D4 and timeout fixes do not require a shared transport class. |
| D5 and Progress upstream | R1’s wholesale test deletion conflicts with R5’s retained bridge coverage; R5’s schema-removal schedule misses older installed Workflow. |
| W9 module split | Keep last or defer. Re-exports alone do not preserve patches, mutable module globals, or the AST-based documentation reader (`extensions/scripts/check_docs.py:77–92`). |

Several savings need correction or qualification:

- **W16/X D5:** deleting the entire shim test module’s runtime is not available while retaining its 35 relevant tests. Measure the reduced module.
- **IP12:** adding mechanical checks costs runtime; its “about 1 s saving” has the sign wrong (`round-4-review-illustrate-progress.md:229–237`).
- **PM20:** the reported 438 seconds of setup is about **30%** of its 1,441-second run. It does not substantiate a 35–55% wall-time reduction without further measurement (`round-4-review-pr-project-memory.md`, PM20).
- **W6:** cache misses still pay the probe. Measure hits, first calls and invalidations; the same claim path also performs installation/compatibility work (`workflow.py:3423–3429`, `delegation.py:1009–1018`). Do not turn its full current cost into guaranteed savings.
- **X14/X15 and CI history:** the observed bottlenecks are plausible, but the runner capacity, download history and predicted wall-time reductions are **Not checkable from repository code alone**.
- **W18/W19:** defer until their tradeoffs are justified. W18 weakens source-drift detection; W19 changes a path-containment check (`workflow.py:215–239`). Neither should be bundled as a routine low-risk cleanup.
- **IP18:** the archive-saving estimate is plausible. My in-memory compression check found roughly 1.08 MB of compressed hand assets including the template; this was not a full archive rebuild.

Two further issues deserve explicit work:

1. **Project can recreate remote task issues after losing state.** Invalid JSON is silently replaced with `{}` (`project_sync.py:473–479`); sub-issue creation trusts only that local mapping (`:348–376`). State is saved only after all remote work (`:500–501`). A malformed file, or interruption after creating children but before saving, can cause duplicates on retry. Refuse malformed existing state and recover existing task identities before creating more issues.

2. **AU16 needs both input and output normalization.** Assure records `tasks.md` as an output as well as an input. Status compares output hashes independently (`sanduq_freshness.py:117–130`), and `inputs()` overwrites the task hash again at `:93–97`. Ignoring the manual block only in the first input fingerprint pass will not fix the rerun. Apply a kind-specific rule consistently, preserve document/manual behavior, and define old-state handling.

Also amend **IP11’s proposed fix**: its fallback explicitly leaves flow mappings and anchors off, including the inline configuration shown in the hook’s own documentation (`self_check_hook.py:4–5`). That preserves a version of the defect. Unsupported enabled configurations need an actionable failure or a reliable interpreter/configuration strategy.

**5. Recommended final plan**

| Decision | Work |
|---|---|
| **Fix first** | W10, W11; shared D4 with W12/SC11/X10; SC10, SC12 and SC18, each with its regression case. |
| **Fix first** | AU8–AU12 and AU13a, including migration of previously rendered CI files and preservation of consumer settings/pages. |
| **Fix first** | PM10–PM12; PM13’s factual docs; Project malformed-state and interrupted-creation recovery. |
| **Fix first** | IP11 with a complete configuration strategy, IP12, IP13, and X21 timeout/error mapping. |
| **Do** | D1/D2 descriptions and catalog guidance; keep every ID, command name and preset as decided. |
| **Do** | D3 as one gated migration: hash/event binding, registration recovery, runtime replacement, queue/active-run handling, then ownership changes. |
| **Do** | D5 with retained bridge tests, explicit compatibility errors, migration text and IP23 CLI checks. |
| **Do** | SC13/SC14 output and listing reductions; PM16/PM23 redundant-call removal; AU13b/AU14/AU15/AU19 output/build reductions. |
| **Do** | AU12 then corrected AU16; AU17/AU18/AU21 as one coordinated instruction pass. |
| **Do** | CI dependency fixes and Playwright gating first; fixture reuse and measured shard balancing afterward. |
| **Defer** | W9, W18/W19/W24, SC8 transport extraction, SC16 readiness changes, SC17 wholesale replacements, PM5 rewrite and public v2 removal. |
| **Drop** | Wholesale shim-test deletion, unconditional fail-open YAML fallback, generic shared `git()`/I/O abstractions, and additive or guaranteed savings claims. |

The **three risks I would watch most** are:

1. **Memory migration integrity:** approval renewal can disable automation, strand queues and block prepared archives.
2. **Partial upgrades:** independently updated packages can re-enable hooks or remove a schema still required by older Workflow.
3. **Remote mutation recovery:** Scope and Project can leave durable GitHub changes before local completion; retries must recover identities rather than create duplicates.

Not checked: full suites, live managed sessions, archive builds, hosted CI history or destructive recovery; those require writes. Working tree unchanged.  
Risk: approve the amended plan; D3 and Progress schema retirement are not ready to ship as currently combined.