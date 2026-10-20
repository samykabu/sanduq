# Round 4, stream N1: naming (delta review)

Read-only research, 2026-10-20, worktree `sanduq-round4` (branch `feat/round-4`, b482e06). This is a delta on
`round-3-naming.md` (cited as R3). R3's method, findings F1 to F10 and its migration design (R3 §5,
`round-3-final-plan.md` §1) are not repeated. Decision being revisited: 2026-10-19, keep every id and every
display name.

Sources: Sanduq at b482e06. Spec Kit upstream `github/spec-kit` main at f68ffca (2026-10-19 20:18 UTC, version
`1.2.3.dev0`), fetched read-only into `FETCH_HEAD` of `D:\Projects\Personal\spec-kit`; the CI pin 8147943
(1.0.11, 2026-09-24). Catalogs fetched 2026-10-20 13:45:03 UTC. Blast-radius method: §5.

## 1. Summary

1. **Nothing has changed that strengthens an id rename.** The catalogs have no new collision (§3). Spec Kit
   upstream still has no id alias, `replaces`, `renamed_from` or migration step. `extension update` still
   refuses an id change (§4). The id-derived surface is about the same size as yesterday (§5).
2. **No purpose drift.** Workflow 1.16.0's `project-sync` is a recording wrapper around Project's script.
   Project still does every board write. Workflow had already disabled Project's hooks (since 2026-09-18) and
   its per-task sub-issues in managed projects (since round 2). The same holds for `progress.py`,
   `progress_bridge.py` and `memory_handoff.py`: all three predate round 3, and each is an adapter that calls
   the other extension's CLI (§2).
3. **New finding: Project's description is wrong in managed projects.** It promises "one native sub-issue
   per task". Under Workflow that part is switched off (`project_sync.py:461-463`), and Workflow's
   `task_issues.py` creates the sub-issues. This is a description fix, not a rename.
4. **New finding: duplicate triggers.** `speckit.workflow.finalize` and `speckit.pr.generate` both say "open
   the PR" (`workflow/commands/finalize.md:2`, `pr/commands/speckit.pr.generate.md:2`). `speckit.workflow.status`
   says "Use when checking progress", which overlaps with `speckit.progress.status`. Fix the descriptions.
5. **Command names (first review, 47 commands, §6):** 37 fit. 10 are weak, but none is misleading enough to
   pay for a migration. The weakest are `memory.run`, `memory.session`, `scope.plan`, and the two
   `analyze` commands in Assure and User Manual, which write to `tasks.md`.
6. **Recommended set:** keep every id, every display name and every command name. Make three description
   fixes (Project, finalize/generate, workflow status) in the optimization phase. Add a docs note about the
   community `scope` and `memory`. Two display-name fixes remain the cheapest real improvement ("Speckit
   Scope", "Pull Request Workflow"). They are optional, and nothing new forces them.

## 2. What each item does today, and drift since round 3

Commits since R3 (`git log --oneline 1688cf7..HEAD -- extensions/<id>`): workflow 12, user-manual 6, assure 4,
illustrate 4, progress 3, scope 2, pr 2, project 2, memory 2, presets 1. All except Workflow's #99 commits
(319e1b7, 450b370, 79eacab) are round 3 optimization (fae9340 and the S-* commits). No commit added a command
or changed an id, a display name or a hook event. `extension.yml` still shows the R3 names.

| Item | Today, in one sentence (evidence) | Drift since R3 | R3 fit verdict |
| --- | --- | --- | --- |
| `workflow` "Sanduq Workflow" | Takes one GitHub issue through the stages from Scope to a merged PR with claims, receipts, evidence CI, and now also records each Project Sync call with retry state (`workflow.py:3004-3033`, `project-sync` and `sync-amend` at `:3943`). | More orchestration (1.16.0). It already owned the order of Project calls (`project_sync` in the claim since 1.13/1.14). Same purpose. | Holds: fits partly ("workflow" is also a Spec Kit noun, R3 F8) |
| `scope` "Speckit Scope" | Sizes and splits an issue into approved sub-issues, gates Specify and Plan, binds the spec, starts clarification, reconciles parent progress; 1.9.0 makes fewer GitHub calls (`scope/CHANGELOG.md` 1.9.0). | None | Holds: id fits partly, name misleading (F2) |
| `assure` "Assure" | Adds QA tasks to `tasks.md` before Implement and writes the QA manual after it (`extension.yml` commands and hooks). | None | Holds: fits |
| `user-manual` "User Manual" | Scaffolds, updates per feature and releases the MkDocs and PDF manual. | None | Holds: fits |
| `pr` "Pull Request Workflow" | Writes the CHANGELOG and details doc, opens or updates the PR, and handles review comments. Workflow's PR stage runs `speckit.pr.generate` (`workflow.py:47-53`). | None | Holds: name misleading (F3) |
| `project` "GitHub Project Lifecycle Sync" | Moves the feature issue across Project (v2) Status columns. Standalone, it also creates and closes per-task sub-issues. Managed, it does Status only, because `project_sync.py:461-463` forces `--no-sub-issues` when `.specify/workflow.yml` exists. Workflow disables all of its hooks (`reconcile.py:11` `OWNED`) and calls the script through `workflow.py project-sync`. | 1.16.0 adds a wrapper with retry state. The board write stays in Project. Not new: the managed-mode cut predates R3 (9e560e7, 2026-10-19 round 2; `OWNED` since 445bcc6, 2026-09-18). R3's inventory missed it. | Holds for the id. The description is wrong for managed use (new finding) |
| `illustrate` "Illustrate" | Draws, imports and exports 44 themed diagram types. The post-write hook is now installed per policy (a01aa7f). | Hook wiring only | Holds: fits |
| `memory` "Sanduq Memory" | Archives verified, merged specs into `specs/memory/` and consults that memory before Specify and Analyze through mandatory hooks. Workflow's `memory_handoff.py` only queues a feature through Memory's `archive.py` ("Never verifies, synthesizes or archives a feature", `memory_handoff.py:1`, `:126`). | None (the handoff dates from 00d0578, 2026-10-18) | Holds: fits partly, exact id collision |
| `progress` "Sanduq Progress Report" | Keeps a live, deterministic report per feature from host hooks. Workflow's `progress.py` is the legacy reporter, which forwards to Progress when it is installed (`progress.py:1-8`, `progress_bridge.py`). | None (bridge from 2fb34cf, 2026-10-15) | Holds: fits |
| preset `workflow` "Sanduq managed workflow" | Overlays 15 commands so the dispatcher owns transitions (`preset.yml`, 1.2.0). | None | Holds |
| preset `scope-gate` "Scope before Specify" | Overlays `speckit.specify` and `speckit.clarify` to require a scoped issue. | One overlay text edit (9b3b418) | Holds |
| preset `scope-brainstorm` "GitHub Brainstorm clarification" | Runs Superspec Brainstorm through GitHub question comments. | None | Holds |

Overlap and drift questions (project into workflow, progress and memory adapters, task sub-issues) are about
structure, not names. They belong to N2 (`round-4-structure.md`). For naming: if N2 merges Project into
Workflow, the `project` id goes away and every Project naming option below is void.

## 3. Live catalogs (fetched 2026-10-20 13:45:03 UTC)

URLs as in R3's header. All six returned HTTP 200.

| Catalog | Entries | `updated_at` |
| --- | --- | --- |
| extensions/catalog.json | 5 | 2026-09-28 |
| extensions/catalog.community.json | 182 | 2026-10-19 |
| presets/catalog.json | 2 | 2026-08-04 |
| presets/catalog.community.json | 42 | 2026-10-12 |
| workflows/catalog.json | 3 | 2026-09-10 |
| workflows/catalog.community.json | 2 | 2026-07-29 |

- **No new entry since R3.** The only catalog commit since 2026-10-18 is e21d4e3 (2026-10-19 14:43, "Update
  SpecKit Grill Me extension to v1.0.2", `gh api repos/github/spec-kit/commits?path=...`). No entry has a
  `created_at` after 2026-10-15. The newest entry, `gh-address-cr` (2026-10-15), was already listed when R3 ran.
- **Exact collisions are unchanged:** `scope` "Spec Scope" (Quratulain-bilal, 1.0.0, 4 commands, 1 hook,
  updated 2026-04-17) and `memory` "Spec Kit Memory" (zaytsevand, 0.3.0, 2 commands, 3 hooks, updated
  2026-07-10).
- **Confusables are as in R3's table.** One addition that R3 did not list: `openproject` (extension and
  preset, 2026-10-09) is a sync engine for another board. It is not close to `project`.
- **Candidate ids checked, none taken:** `issue-scope`, `sanduq-scope`, `issue-flow`, `issue-to-pr`,
  `sanduq`, `delivery`, `project-sync`, `github-project`, `board-sync`, `spec-memory`, `product-memory`,
  `spec-archive`, `feature-memory`, `pull-request`, `workflow-overlay`, `sanduq-workflow`. The community
  `archive` exists ("Archive merged features into main project memory"), so a bare `archive` id is ruled
  out. `triage` is still confusable with `gh-triage`.
- **Display names:** no catalog name starts with "Sanduq". "Spec Scope" and "Spec Kit Memory" remain the
  closest to "Speckit Scope" and "Sanduq Memory".

## 4. Spec Kit upstream

- Upstream main is 185 commits past the CI pin. Only 10 of them touch `src/specify_cli/extensions/` or
  `presets/` (`git log 8147943..FETCH_HEAD`): exact catalog release selection (d2ddd910), config templates on
  update (244e752), listing commands per agent (1beafe5) and others. None adds an id alias, `replaces`,
  `renamed_from` or a migration hook. A `git grep -i` for `renamed_from|replaced_by|previous_id|supersede|legacy_id|former_id`
  in `src/` at 92b7cf7, 8147943 and f68ffca finds only two unrelated comments.
- `extension update` still aborts on `Extension ID mismatch` (`extensions/_command_update_artifacts.py:141-145`,
  the same at 8147943 and f68ffca).
- Command aliases are still free-form (`extensions/__init__.py:501-523` at f68ffca). They now also pass
  `relative_extension_path_violation`. Install still refuses a name that another extension already provides
  (`:1242`) or that sits in a core namespace (`:1112`, `:1160`). The core names now load dynamically, with
  the R3 list as fallback (`:59-70`, `:127-130`). The primary command pattern is unchanged:
  `^speckit\.([a-z0-9-]+)\.([a-z0-9-]+)$` (`:73`). The id pattern is `^[a-z0-9-]+$` (`:327`).
- `extension add` still has no catalog selector, only `--from` (`command_add.py:24`). With the default
  catalogs kept, the higher-priority community `scope` or `memory` still wins (R3 "When a catalog collision
  actually bites"; d2ddd910 keeps "the winning extension source").
- **CI pin:** `.github/workflows/ci.yml:298,329,385` installs `specify-cli @ git+https://github.com/github/spec-kit.git@8147943…`.
  `workflow/dependencies.json` `tested_spec_kit` gives 1.0.11 at the same commit.
- **Correction to R3:** R3 cites line numbers from the local clone at 92b7cf7 (2026-07-06). That commit is
  older than the CI pin, so R3's file:line references point at code that CI does not run. Its conclusions
  still hold on 8147943 and f68ffca (above), but its line numbers do not match the CI version. Use the
  references in this section.

## 5. Blast radius (only ids with a live rename option)

Method, as in R3 §4: all files from `git ls-files -co --exclude-standard`, minus `dist/`, `__pycache__/` and
binary files (1,319 files, 1,265 readable text files). Count the files and occurrences that match
`speckit.<id>.`, `speckit-<id>-`, `.specify/extensions/<id>` or `<id>-v<digit>`. Buckets: own folder, other
extensions, presets, docs (`docs/` and `*.md`), tests (any `tests/`), other. The `docs/internal/` folder has
grown with the round reports, so the table also gives counts without it.

| id | Files / occurrences (all) | Without `docs/internal` | Buckets without internal (own/other/presets/docs/tests/misc) | R3 | Tags |
| --- | --- | --- | --- | --- | --- |
| `scope` | 70 / 212 | 47 / 113 | 21/7/6/5/7/1 | 54 / 126 | 10 |
| `project` | 50 / 151 | 32 / 93 | 8/8/0/5/10/1 | 42 / 126 | 10 |
| `memory` | 53 / 312 | 34 / 185 | 21/4/0/3/5/1 | 45 / 233 | 10 |
| `workflow` | 141 / 482 | 124 / 338 | 42/14/18/29/19/2 | 129 / 366 | 40 |

The product surface (without `docs/internal`) is the same size as yesterday or a little smaller. State paths
and consumer-side files are as R3 lists them. No migration code exists yet: there is no `RENAMED` and no
`renamed_from` in `workflow/scripts/`.

## 6. Command names, one by one (47)

Verdicts: **fits**, **weak** (a better name exists, but the description makes the meaning clear), **misleading**
(a user would guess wrong). "Hook-only" means hidden on Claude Code (`hosts.py:43`).

| Command | Does | Verdict |
| --- | --- | --- |
| workflow.init | Sets up policy, reviewers, delegation, CI | fits |
| workflow.scope | Scopes an issue and runs the lifecycle through Specify, Clarify and Plan | weak: it does more than Scope, and it overlaps `scope.run`, which the preset routes into the dispatcher (`presets/workflow/commands/speckit.scope.run.md`). `workflow.start` would say what it does. |
| workflow.clarify | Applies GitHub answers, continues | fits (namespaced, distinct from core `clarify`) |
| workflow.continue | Resumes at the earliest unfinished stage | fits |
| workflow.finalize | Readiness, the single PR, merge check | fits; the trigger "open the PR" duplicates `pr.generate` (description fix) |
| workflow.status | Stage, claim, receipts, blockers | fits; the trigger "checking progress" overlaps `progress.status` (description fix) |
| workflow.doctor | Diagnoses setup | fits |
| workflow.reconcile | Repairs managed hooks and presets | fits; same verb as `scope.reconcile`, which means something else (see below) |
| workflow.verify-affected | Runs affected test lanes locally | fits |
| workflow.ci-report | Summarizes Actions runs | fits |
| workflow.gate-explain | Explains a failing evidence gate | fits |
| workflow.worker-brief | Writes a task card for a worker | fits |
| workflow.apply-pending | Applies queued artifact updates | fits |
| scope.run | Scopes, sizes, splits, publishes | fits |
| scope.guard | before_specify gate, hook-only | fits |
| scope.bind | after_specify bind, hook-only | fits |
| scope.reconcile | Refreshes parent progress, hook-only | weak: `refresh-parent` says it, but the command is hidden |
| scope.plan | Redraws the dependency plan after a split | weak, borderline misleading: core `speckit.plan` and `scope.plan-guard` both mean the implementation plan. `scope.dependency-plan` or `scope.split-plan` would be clearer. |
| scope.after-specify | Starts clarification, hook-only | weak: it is named after the event, not the action (`start-clarification`); hidden |
| scope.plan-guard | before_plan Ready gate, hook-only | fits |
| assure.init | Sets QA gates | fits |
| assure.analyze | **Adds** QA tasks to `tasks.md` (`speckit.assure.analyze.md:111` "Patch tasks.md") | weak: core `analyze` is a read-only check, and this one writes. It is mitigated by `--report-only` and the description. |
| assure.document | Writes the QA manual | fits |
| user-manual.init | Scaffolds the manual | fits |
| user-manual.analyze | Adds manual tasks to `tasks.md` | weak, for the same reason as `assure.analyze` |
| user-manual.update | Updates affected modules | fits |
| user-manual.release | Release notes, PDFs | fits |
| pr.generate | CHANGELOG, details doc, PR | fits |
| pr.review-feedback | Fixes or answers review comments | fits |
| project.init | Board mapping | fits |
| project.sync | Moves Status, sub-issues (standalone) | fits; Workflow's `workflow.py project-sync` is a script subcommand, not a command, so there is no command collision |
| illustrate.generate / export / theme / import | as named | fit (4) |
| memory.init | Hooks, guards, archiving off | fits |
| memory.prepare | **Queues** a feature for archive | weak: `queue` is the helper's own verb (`memory_handoff.py:126`) |
| memory.run | **Archives** verified features | weak, the vaguest name in the set; `archive` says it |
| memory.session | Processes merged pending archives and resumes runs (before_specify) | weak, close to misleading: "session" names when it runs, not what it does (`process-pending`) |
| memory.enable | Records archive-policy approval | weak: it enables auto-archiving, not Memory itself |
| memory.impact | Consults product memory | fits |
| memory.status | Archive status | fits |
| progress.init / refresh / status / theme / export | as named | fit (5) |

Same verbs across namespaces (`status` x3, `init` x7, `analyze` x2 plus core, `reconcile` x2) are normal
Spec Kit style. Each one is namespaced, and none collides.

## 7. Options and recommendation per item

Effort: S under 2 h; M 0.5 to 2 days with tests; L more. Id-rename options keep R3's candidates unless noted.
Command-level renames keep the old name as a Spec Kit alias. Each alias is an extra skill or command file per
host and extra description text (`round-3-final-plan.md` §1 point 5, and the 8,000-character catalog budget
in §3.4).

**workflow.** Keep (as on 2026-10-19). Display name: keep. Id candidates, each L with a bridge release (R3):
`issue-flow`, `issue-to-pr` (new candidate: it says the scope exactly, but it is long in skill names, as in
`speckit-issue-to-pr-continue`), `sanduq`. Command option: add `workflow.start` as an alias of `workflow.scope`
(S, purely additive). Not recommended: one extra skill, small gain. **Recommend:** keep everything. Fix the
`finalize` and `status` triggers (S).

**scope.** The collision is unchanged. Display name: "Sanduq Issue Scope" (S, no migration). It is the most
misleading name in the set (F2), and it is still unaddressed. Id: `issue-scope` (M; the R3 §5 migration is
still unbuilt), `sanduq-scope` (M). Command options: rename `scope.plan` to `scope.split-plan` (M: the old name
must stay as an alias because Workflow references and the plan-pending marker name it; hook-only skill lists
are unaffected), and `scope.after-specify` to `scope.start-clarification` (M: it is a managed hook command, the
`reconcile.py:36` special case names it, and the reconcile journal keys hooks by `event:command`, `:33`).
**Recommend:** keep the id. The display-name fix is optional, and the case for it is as strong as yesterday,
no stronger. Do not rename commands now.

**assure, user-manual.** Keep the id and name. Command option: rename `analyze` to `plan-tasks` (or
`add-tasks`), with `analyze` kept as an alias (M each). The managed hooks `after_tasks` and `before_implement`,
the reconcile journal keys, `COMMANDS` in `workflow.py:47-53` and historical receipts all name
`speckit.assure.analyze`. Not worth a break. **Recommend:** keep.

**pr.** Keep the id. Display name: "Sanduq Pull Requests" (S, optional; F3 unchanged). **Recommend:** keep the
id and commands. Fix the `generate` trigger with the `finalize` one (S).

**project.** The id still fits (a GitHub Project). The "project means the repository" ambiguity (F4) is
unchanged. 1.16.0 does not make the id wrong: Workflow orchestrates, Project writes. Id candidates:
`project-sync` (M), `github-project` (M), `board-sync` (M, it hides "GitHub"). All are void if N2 merges
Project into Workflow. **Recommend:** keep. Fix the description so that sub-issues are standalone only (S).

**illustrate, progress.** Keep everything (no finding).

**memory.** The exact collision is unchanged. Id: `spec-memory` (L), `product-memory` (L), `feature-memory`
(new: it names the unit archived, L). All have the same consumer-file risk as R3. Display name: "Sanduq Memory
and Archive" (S, optional). Command options, the only cluster where several names are weak at once: `run` to
`archive`, `session` to `process-pending`, `prepare` to `queue`, each with the old name as an alias. M in
total, because Memory's own `install.py` writes hook entries and wrapper paths by command name
(`install.py:97,112,190-234`, `archive.py:129-131`) and Spec Kit cannot change them. Before acting, check
whether `extension update` rewrites the `before_specify` binding that `init` adds by hand (`extension.yml:45`).
That is unverified. **Recommend:** keep for now. If the user wants one command-level change in the whole set,
this cluster gives the most clarity for the cost.

**Presets.** Keep the ids. The display-name fixes ("Sanduq Scope Gate", "Sanduq GitHub Brainstorm") are S and
optional.

### Overall sets

| Set | Contents | Effort | Consumer impact |
| --- | --- | --- | --- |
| **A. Keep (recommended)** | No renames. Three description fixes (Project managed mode; finalize/generate trigger; workflow.status trigger). One README and extension-page note about the community `scope` and `memory` and how to install from Sanduq's catalog or `--from`. | S | None |
| B. A + display names | Set A plus R3's display-name batch, or only "Speckit Scope" and "Pull Request Workflow" | S | None (the registry refreshes on the next update) |
| C. B + memory commands | Set B plus `memory.archive`, `memory.process-pending` and `memory.queue`, with the old names as aliases for the R3 support window | S + M | Memory users run `memory init` again or upgrade. Old names keep working. |
| D. B + `scope` to `issue-scope` | As in R3's recommended set | S + M (+ migration tests) | One `upgrade.py` run |

**Cost of doing nothing (set A without the docs note):** a user who keeps the default catalogs and runs
`specify extension add scope` or `add memory` gets the community "Spec Scope" or "Spec Kit Memory". Both are
`install_allowed: false` when installed from the community catalog, so the install fails or `search` and `info`
show the other product. The Workflow installer is not affected (`--from` plus the repository check, R3).
Users who install Memory standalone are the exposed group. "Speckit Scope" keeps reading like an upstream
product. "Open the PR" keeps matching two skills in a managed project. None of these costs grew since
2026-10-19.

**What changed since the decision:** facts only. Project's managed-mode description is wrong. Two trigger
phrases are duplicated. R3's Spec Kit line numbers come from a pre-pin checkout. None of these calls for an id
rename. The user's reasons for keeping every name (no alias support, migration risk, low gain) still hold.

## 8. Migration sketches (only what is new beyond R3 §5 and final-plan §1)

**Description fixes (set A):** edit the `description:` in the command file or manifest, add a patch version
bump, and the catalog regenerates on release (`release.py`). Workflow's COMMANDS map and receipts are untouched
because the command names stay the same. Check the catalog description budget (final-plan §3.4).

**Display names (set B):** as R3 §4 "Cheap fixes". Nothing new.

**Command rename inside an id (set C, new):**
1. In `extension.yml`, give the new name as the primary `name` and list the old one under `aliases` for the
   R3 support window. Point hooks at the new name. Spec Kit renders both and refuses only a clash with another
   extension (`__init__.py:1242`).
2. Memory's `install.py`: write hook entries with the new name, recognize and replace entries with the old
   name (`:97`, `:112`), and list both wrapper sets for removal checks (`:190-191`, `archive.py:129-131`).
3. Hooks that Workflow manages (not Memory, but this applies if Scope, Assure or User Manual commands are
   renamed later): `reconcile.py` journal keys are `event:command`. Migrate the journal key, or else
   `HOOK_CHANGED_SINCE_RECONCILE` fires (`reconcile.py:33-45`). Also update `COMMANDS` in `workflow.py:47-53`.
   Receipts that store the old command stay valid as history.
4. Tests: an install over a consumer with old hook entries, an old name invoked through the alias, and an idempotent re-run.

**`scope` to `issue-scope` (set D):** no change to R3 §5 and final-plan §1. Run the tests against 8147943 (the
CI pin). Check the line numbers again: R3's references are from the 92b7cf7 checkout (§4).

Not checked: whether `specify extension update` re-registers hook entries that an extension's own `init`
added outside its manifest (this matters for set C). Whether a preset overlay applies to an alias-only command
is still unverified, as in R3.
