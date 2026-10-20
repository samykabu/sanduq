# Round 4, stream N2: structure (merge, split, move)

Read-only research, 2026-10-20, worktree `sanduq-round4` (branch `feat/round-4`, base b482e06, Workflow
1.16.0). Spec Kit source: `D:\Projects\Personal\spec-kit` at 92b7cf7. Sizes come from `git ls-files` and
from archives built with `extensions/scripts/package.py` into a scratch folder. This builds on round 3:
SC2 (`round-3-review-scope.md`), PM6 (`round-3-review-pr-project-memory.md`, finding in
`round-3-notes.md:326`), W9 (`round-3-review-workflow.md`), SC8 (`round-3-review-scope.md`), X9
(`round-3-review-cross-cutting.md`). Rename machinery is in `round-3-naming.md` §5 and
`round-3-final-plan.md` §1. It is referenced here, not repeated.

## 1. Summary

1. The extensions overlap by **composition**, not by copied code. Workflow schedules. The domain
   extension does the work through its script or command. The domain hook is disabled in managed
   projects (`reconcile.py:11,35`). Textual similarity between the overlapping scripts is 8% to 12%
   (difflib, §3).
2. Three real duplications remain. (a) Memory's `session` and `prepare` hooks run alongside
   `workflow.py memory-handoff` (PM6, confirmed in code, `round-3-notes.md:326`). (b) In managed
   projects `scope-brainstorm` is fully shadowed, and so is `scope-gate`'s Clarify overlay, by
   `replace` templates in the `workflow` preset at higher priority. (c) A hand copy of the remote
   normaliser sits in `project_sync.py:78-103`.
3. The legacy reporter is **not dead**. Progress is opt-in (`dependencies.json` `optional`,
   `install.py:734-740`), so every managed install without `--with progress` uses it. Only the
   forwarder (`progress_shim.py`) is rarely reached.
4. Standalone use blocks most merges. Project, Memory, Progress and Illustrate require nothing.
   Assure, User Manual and PR require only Illustrate. The README marks all of them "Standalone: Yes"
   (`README.md:36-44`). Only Scope requires Workflow.
5. Recommended set: **no extension merges**. Two small structural changes: R1, PM6 ownership of
   Memory's two hooks (S). R2, SC2, three presets become two (M). Both are optional in value. Neither
   changes an extension id.

## 2. Size picture

Built archives (`package.py`, 2026-10-20). "Code" is the bytes of .py, .js and .mjs in the archive.
Lines are tracked source without tests.

| Extension | Ver | Requires (extensions) | Cmds | Hooks (mandatory) | Archive files | Zip KB | Raw KB | Md KB | Code KB | Py lines | JS lines | Test lines |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| workflow | 1.16.0 | none | 13 | 0 | 155 | 551 | 1,462 | 282 | 1,047 | 16,849 | 2,755 | 20,696 |
| scope | 1.9.0 | workflow, illustrate | 7 | 5 (5) | 43 | 97 | 264 | 67 | 182 | 3,056 | 0 | 3,533 |
| assure | 2.5.1 | illustrate | 3 | 3 (0) | 22 | 50 | 123 | 35 | 81 | 524 | 0 | 416 |
| user-manual | 1.7.1 | illustrate | 4 | 2 (0) | 46 | 70 | 159 | 46 | 93 | 818 | 0 | 577 |
| pr | 4.4.0 | illustrate (+assure, user-manual optional) | 2 | 1 (0) | 12 | 34 | 83 | 35 | 44 | 365 | 0 | 353 |
| project | 2.4.0 | none | 2 | 6 (0) | 10 | 26 | 68 | 12 | 26 | 545 | 0 | 0 |
| illustrate | 2.6.0 | none | 4 | 0 | 427 | 2,724 | 9,522 | 668 | 1,014 | 24,700* | 0 | 342 |
| memory | 2.4.0 | none | 7 | 3+1 (all) | 34 | 106 | 323 | 55 | 245 | 4,297 | 0 | 3,658 |
| progress | 1.4.0 | none | 5 | 2 (0) | 48 | 154 | 443 | 46 | 373 | 6,544 | 1,015 | 840 |
| shared (`extensions/scripts/shared`) | - | - | - | - | 5 files | - | - | - | 60 | 1,267 | 0 | (in scripts/tests) |

\* Mostly the vendored illustration-tools scripts. Memory's fourth hook (`impact` on `before_specify`)
is registered by `memory/scripts/install.py`, not the manifest (`memory/extension.yml:41-43`).

| Preset | Ver | License | Templates | Files | Bytes |
| --- | --- | --- | --- | --- | --- |
| workflow | 1.2.0 | PolyForm NC | 15 (specify, plan, tasks, analyze, implement, taskstoissues prepend; clarify, superspec.brainstorm replace; scope.run; superspec and bridge commands) | 17 | 17,974 |
| scope-gate | 1.4.0 | MIT | 2 (specify, clarify; prepend) | 5 | 7,345 |
| scope-brainstorm | 1.4.0 | MIT | 1 (superspec.brainstorm; prepend) | 4 | 4,102 |

Shared code is single-sourced already. `package.py:65-84` injects `sanduq_freshness.py`,
`sanduq_hash.py`, `sanduq_ci.py` and `deps.py` into assure and user-manual (and `deps.py` into pr), and
`check_inputs.py` and `bounded_json.py` into memory and workflow. No packaged copy is tracked
(`git ls-files` finds each shared file once). The only cost is package bytes: about 57 KB raw is
duplicated across the assure and user-manual archives.

Hooks in a managed install with both processes selected: Sanduq manifests register 22 hooks plus
Memory's extra one. `reconcile` disables 13: assure 3, user-manual 2, pr 1, project 6 and
`scope.after-specify` 1 (`reconcile.py:11,35`). Scope's other four stay on, and so do Memory's four and
Progress's two (when installed). The 13 disabled hooks exist only for standalone use.

## 3. Overlaps

### O1. Workflow project sync and `task_issues.py` vs Project

Who owns what today:

- **Workflow decides when.** Stage-to-phase map `PROJECT_SYNC_PHASES` (`workflow.py:78-85`). The
  policy key `project_sync.points` (`:972-977`). The claim field (`:1015-1020`). Retry state
  (`:1622-1634`). `Run.sync_project` (`:3004-3033`) runs Project's script as a subprocess, and its
  idempotence check avoids a second remote write. `sync-amend` (`:2989-3002`) converts receipts that
  hold raw hashes of `.specify/project-sync-state.json`. Doctor validates Project's `config.json`
  (`project_errors`, `:1245-1262`) and requires `hookMode: required`.
- **Project does the board work.** It creates the parent issue, adds the project item and sets the
  Status column (`project_sync.py:222-325`). It owns `config.json`, the state file and both commands.
- **Task sub-issues have two implementations.** Project's are `sync_sub_issues` and `sync_progress`
  (`project_sync.py:337-400`). Workflow's are parent-scoped, with markers and verification
  (`task_issues.py`, 303 lines). They do not run together: managed mode forces `--no-sub-issues`
  (`project_sync.py:461-463`), and `reconcile` disables Project's `after_tasks` hook. `task_issues.py:138-147`
  adopts sub-issues that Project created earlier (the legacy path). Similarity is 10% (difflib, 42 of
  545/303 lines).
- **Copied code.** `normalize_remote_url` is copied from Workflow (`project_sync.py:78-103`, about 40
  lines). `github_repo` loads the whole 4,137-line `workflow.py` with `exec_module` on every sync to use
  Workflow's original (`:106-119`).

| Option | Saves | Breaks for an installed consumer | Migration | Effort, risk |
| --- | --- | --- | --- | --- |
| J1 keep | - | - | - | - |
| J2 merge Project into Workflow | 1 package (26 KB zip), 1 install step, 2 commands, 6 hooks (all disabled in managed projects anyway), 1 `dependencies.json` pin | Standalone Project users lose the product (`README.md:38`). The `project` registry entry, the 6 hook entries in `extensions.yml`, and the `speckit-project-*` skill folders on each host go away. `config.json` moves out of `.specify/extensions/project/`. The `required.project` lock entry is dropped. | Full id retirement (naming §5 steps 2-8, plus a standalone final release). `config.json` must be carried across. | L, high |
| J3 shared remote normaliser | About 40 duplicate lines. No more loading `workflow.py` on each sync (time not measured). | Nothing. The file is injected the same way `deps.py` is. | None | S, low |
| J4 drop the legacy sub-issue adoption in `task_issues.py:138-147` after a support window | About 10 lines | Features whose sub-issues Project created before Workflow's adapter stop being adopted | CHANGELOG notice, one window | S, low (small value) |

### O2. Workflow `progress.py`, `progress_bridge.py`, `progress_shim.py` vs Progress

- `progress_bridge.py` (403 lines) chooses the mode: `projection`, `refresh` or `legacy`
  (`:1-17`, `mode` at `:348-354`). It is needed in every option.
- `progress.py` (554 lines, 30.6 KB) is the legacy reporter. The coordinator calls it from
  `references/execute/reporting-legacy.md` (5,751 B, 17 calls). The claim prints that file only in
  legacy mode (`round-3-notes.md:319`).
- **Reach:** Progress is optional (`dependencies.json` `optional.progress`). `install.py` adds it
  only with `--with progress` or when it is already installed (`install.py:734-740`). So legacy
  mode is the **default** for a managed install. There is no telemetry on the share, but every
  consumer who followed the plain `install.py --apply` route is on it.
- `progress_shim.py` (360 lines, 16.3 KB; tests 874 lines) forwards a legacy call to the Progress CLI
  when Progress is installed (`progress.py:467-473`). Nothing in the shipped instructions makes such a
  call in projection or refresh mode. `reporting.md` names only Progress's own CLI
  (`reporting.md:22`). It is reached only when a coordinator still runs a call from a legacy text it
  read earlier (`reporting.md:38`).
- Code similarity between `workflow/scripts/progress.py` and `progress/scripts/progress.py` is 8%.
  They are different reporters, not copies.

| Option | Saves | Breaks | Migration | Effort, risk |
| --- | --- | --- | --- | --- |
| G1 keep | - | - | - | - |
| G2 make Progress required and retire the legacy reporter | `progress.py`, `progress_shim.py`, most of `usage.py` (about 1,000 lines, 54 KB), `reporting-legacy.md` (5.7 KB, read only in legacy mode), about 1,200 test lines | The Python floor rises from 3.10 to 3.11 (Progress manifest). Each tool call pays a hook: about 1.4 s through Spec Kit's dispatcher, about 0.13 s native (`install.py:599-600`). Progress on Claude Code is unverified (`README.md:44`). Existing `specs/<f>/workflow/progress` legacy reports stop updating mid-feature. | `dependencies.json` moves progress to `required`. Upgrade installs it. A legacy report gets a one-off import or a frozen copy. | L, high |
| G3 retire only the forwarder: a legacy call with Progress installed exits 2 and names the Progress verb | 16 KB, 360 lines, 874 test lines | Only a session that runs legacy calls after Progress was installed. The claim reprints the protocol when the mode changes (the digest rule, `round-3-notes.md:327`). | CHANGELOG line, plus the `reporting.md:38` sentence | S, low (maintenance value only) |

### O3. Workflow `memory_handoff.py` vs Memory

- `memory_handoff.py` (184 lines) is an adapter. It runs Memory's `archive.py` (`:16-25`) and never
  archives itself (`:1`). Memory is not in `dependencies.json`, so Workflow never installs it
  (`memory-lifecycle.md:3-5`).
- **Duplication (PM6):** `before_specify: speckit.memory.session` and `after_implement:
  speckit.memory.prepare` are mandatory (`memory/extension.yml:44-53`). `reconcile.py:11` does not
  disable them. `complete` then runs the handoff again, and the handoff returns `MEMORY_ALREADY_QUEUED`.
  The result is idempotent. The cost is one more prepare body read, one more model step, and 2 to 3
  helper processes per transition (`round-3-notes.md:326`).

| Option | Saves | Breaks | Migration | Effort, risk |
| --- | --- | --- | --- | --- |
| M1 (= PM6) Workflow owns `session` and `prepare` in managed projects; `impact` stays a hook | 30-60% of Memory's managed lifecycle reads and 30-50% of its calls (PM6 estimate) | Doctor reports `DUPLICATE_STAGE_OWNER` when Memory is installed after Workflow, until `reconcile --apply` runs. The generated hooks page changes (`check_docs.py` derives it from `OWNED`). | reconcile's existing backup and restore journal. No state path or policy key change. | S, low |
| M2 merge Memory into Workflow | 1 package (106 KB) | Memory is standalone (no `requires`), has its own installer with guard patches (`memory/scripts/install.py`) and needs 3.11. Standalone users lose it. | Full id retirement | L, high |

### O4. Scope hooks vs `scope-gate` vs the `workflow` preset

- Install order and priority: `scope-gate` 2, `scope-brainstorm` 2, `workflow` 1 (`install.py:771`).
  A lower number wins (`spec-kit presets/__init__.py:500`). A top-layer `replace` skips composition
  (`:637-643`).
- So in a managed project:
  - **Specify:** the `workflow` prepend sits over the `scope-gate` prepend, over core. All layers run.
  - **Clarify:** the `workflow` preset uses `replace` (`presets/workflow/preset.yml:26-29`), so
    `scope-gate/commands/clarify-github.md` (2,107 B) never renders.
  - **Brainstorm:** the `workflow` preset uses `replace` (`:56-59`), so `scope-brainstorm` (2,060 B)
    never renders. The `workflow` version says "In every case execute `github-clarification`"
    (`presets/workflow/commands/speckit.superspec.brainstorm.md`), so it also covers unmanaged runs.
- The Scope guard is asked for in three places: the `scope-gate` Specify overlay (`specify-gate.md:6-14`),
  the mandatory `before_specify` hook, and the managed stage (`stage-specify.md`). The instructions
  reuse a single result (`specify-gate.md:17-19`). Each place is a deliberate safeguard, because hooks
  can be disabled.
- `scope-brainstorm` vs Scope's `github-clarification` skill: no overlap. The preset is a 2 KB
  entry point that calls the skill (`brainstorm-github.md:14`).
- The `scope-gate` and `scope-brainstorm` presets are MIT, Scope is MIT, the `workflow` preset is
  PolyForm (`docs/reference/licenses.md`). Both MIT presets ship in the scope archive
  (`package.py:11`).

| Option | Saves | Breaks | Migration | Effort, risk |
| --- | --- | --- | --- | --- |
| P0 keep | - | - | - | - |
| P1 (= SC2) fold `scope-brainstorm` into `scope-gate` | One package unit, registry entry, doctor check (`workflow.py:1473`) and README. 4 files in the preset; 24 files name it. One fewer name for N1. Install time: little, since unchanged presets are already skipped (`install.py:777-782`). | The `scope-brainstorm` registry entry and its `install-lock.json` `presets` entry go away. The lock is rebuilt from the registry (`install.py:916-918`). The `speckit-superspec-brainstorm` skill is re-rendered from the remaining layers, so nothing visible disappears. Unmanaged Scope users run one manual remove. | Upgrade step: remove `scope-brainstorm` when its registry `repository` is Sanduq, then re-add `scope-gate`. Doctor accepts its absence. | M, low |
| P3 stop installing `scope-brainstorm` in managed projects only | Same for managed projects. The repo keeps 3 presets. | Same upgrade removal | Same | S, low |
| P2 fold `scope-gate` and `scope-brainstorm` into the `workflow` preset | 2 packages | The MIT license for those overlays is lost. Scope-only installs lose their Specify gate. | - | rejected |

### O5. Assure and User Manual

They share freshness, hashing, CI rendering and dependency checks through injected copies
(`package.py:65-84`). The only code left in each is a thin wrapper: `assure_state.py` is 52 lines and
`manual_state.py` is 24 (AU4, `round-3-notes.md:223`). The two audits share 12% (`audit_qa.py` vs
`audit_manual.py`). They are separate policy choices: `selected.qa` and `selected.user_manual` in
`dependencies.json`, and `processes.qa` and `processes.user_manual` in `.specify/workflow.yml`. Each is
standalone.

| Option | Saves | Breaks | Effort, risk |
| --- | --- | --- | --- |
| A1 keep (shared code is already one source) | - | - | - |
| A2 merge into one extension | 1 package, about 57 KB of duplicated injected bytes, 1 install step | Two ids, five hooks, two policy groups and keys, config paths (`assure-config.yml`, the manual's config), and standalone use of each | L, high |

### O6. PR vs Workflow finalize

These are not duplicates. `finalize.md` reads Workflow's SKILL, and the PR stage publishes through PR's
script (`stage-pr.md:22`, `pr_publish.py`). `COMMANDS['pr'] = 'speckit.pr.generate'` (`workflow.py:52`).
PR's `after_implement` hook is disabled in managed projects (`reconcile.py:35`). The confusion is in the
names only (round-3-naming F3), which is N1's question. Option: keep.

### O7. Scope vs Workflow (the only extension that is not standalone)

Scope requires Workflow (`scope/extension.yml` `requires`). It imports Workflow's policy through
`workflow_policy.py` (`scope.py:23`, `clarification.py:453-966`). Its five hooks are the enforcement
layer in managed projects too: four stay enabled.

| Option | Saves | Breaks | Effort, risk |
| --- | --- | --- | --- |
| S1 keep | - | - | - |
| S2 merge Scope into Workflow | 1 package (97 KB), 1 pin, the `workflow_policy.py` bridge. It would replace N1's `scope` to `issue-scope` rename question. | The MIT license for Scope's code. `speckit.scope.*` commands (they would need aliases). Five hook entries owned by `scope`. `HOOK_ONLY_SKILLS` (`hosts.py:43`). Paths the presets name (`.specify/extensions/scope/commands/guard.md`, `.../skills/github-clarification/SKILL.md`). 3,533 test lines to move. Scope's release lineage. | L, high |

If the user picks the `issue-scope` rename in N1, S2 is the only structural alternative to it. Both use
the same machinery (naming §5).

### O8. Code-level items (no consumer-visible structure)

- **W9 split of `workflow.py`.** The file is now 4,137 lines. It was 3,719 in round 3
  (`round-3-review-workflow.md:81`). 1.16.0 added project-sync and sync-amend (`:2963-3033`). It
  changes no id, path or hook, so it does not gate naming. It stays a Phase 2 maintenance item (L).
- **SC8 and X9 transport and I/O.** GitHub clients live in four places: `scope.py` (`GitHub`,
  `ProjectRest`), `project_sync.py` (`gh_raw`, `rest`), `task_issues.py` (`api`) and `pr_publish.py`.
  `def git(` appears in `workflow.py`, `project_sync.py` and `memory/git_state.py`. A shared module
  injected by `package.py`, like `deps.py`, is the cross-extension form of SC8 and X9. It is internal.
  Defer, as round 3 did. J3 is the one-function start of it.

## 4. Standalone use

| Extension | Manifest `requires.extensions` | README "Standalone" | Installed by Workflow | Merge into Workflow removes standalone use? |
| --- | --- | --- | --- | --- |
| scope | workflow, illustrate | No (`docs/extensions/scope.md:13,58`) | required | No, but it changes the MIT license |
| project | none | Yes | required | Yes |
| pr | illustrate | Yes | required | Yes |
| illustrate | none | Yes | required | Yes |
| assure | illustrate | Yes | selected (`qa`) | Yes |
| user-manual | illustrate | Yes | selected (`user_manual`) | Yes |
| progress | none | Yes | optional (`--with progress`) | Yes |
| memory | none | Yes | never | Yes |

`docs/start/install-by-host.md:101-117` documents installing all nine one by one, and the
standalone route for each.

## 5. Recommended structural set

**No extension merges, splits or moves of ownership between extensions.** For every merge candidate,
the cost (standalone users lost, id retirement, a license change for Scope) is far larger than the
saving (one package and one install step; 13 of the hooks are already disabled in managed projects).
The overlaps found are composition by design: Workflow schedules, the extension acts.

Two small changes, both optional in value, and neither changes an extension id:

**R1. PM6: Workflow owns Memory's `session` and `prepare` in managed projects (S).**
Sketch:
1. In `reconcile.py:35`, the managed predicate adds `extension == 'memory'` with command in
   {`speckit.memory.session`, `speckit.memory.prepare`}. `impact` stays.
2. Doctor's owned list (`workflow.py:1471`) gets the same entries. Its `DUPLICATE_STAGE_OWNER` message
   names `reconcile --apply`, which `upgrade.py` already runs inside its rollback boundary.
3. `reconcile --restore` brings the hooks back from the existing journal
   (`.specify/workflow/integration-backup.json`).
4. Regenerate the hooks page (`check_docs.py`).
5. In Memory, trim `session.md` to what the handoff does not return (PM6 text).
6. Gate: the one managed run that round 3 asked for.
7. Consumer impact: two `enabled: false` flags in `.specify/extensions.yml`. No state, policy or lock
   change.

**R2. SC2: three presets become two (M), or P3 (S) if only managed installs matter.**
Sketch:
1. Move `brainstorm-github.md` into `scope-gate`. Update `MANAGED_PRESETS` (`hosts.py:29`),
   `install.py:771`, `workflow.py:1473`, `package.py:10-11`, `benchmark_front_half.py` and the rest of
   the 24 files that name `scope-brainstorm` outside `docs/internal` and changelogs (grep, 2026-10-20).
2. Upgrade (inside the `install.py` snapshot, lock and rollback boundary): when the registry holds
   `scope-brainstorm` and its `repository` is Sanduq, run `specify preset remove scope-brainstorm`
   before re-adding `scope-gate`.
3. Doctor accepts its absence and reports a leftover with the fix.
4. Unmanaged Scope users get a CHANGELOG Migration block and a `docs/start/upgrades.md` line. This
   follows the same pattern as naming §5 "Catalog and release continuity" and final-plan §1 item 1.
5. No policy key or state path changes.

Value is small: it saves no tokens in managed runs (SC2 tok [0, 0.002]). Do it only if Phase 2 already
releases the installer.

**Optional maintenance, not structural:** J3 shared remote normaliser (S). G3 retire the progress
forwarder (S). W9, SC8 and X9 stay deferred to Phase 2.

**Explicitly not recommended:** G2 (Progress required) adds a cost to every tool call and raises the
Python floor. J2, M2, A2 and S2 remove standalone products or a license, for one package each.

**Effect on N1:** only S2 (Scope into Workflow) and R2 (`scope-brainstorm` disappears) touch names.
R2 removes one preset name. It does not rename anything, so N1 can decide every other name
independently of this file.

## 6. Not verified

- The share of managed consumers on legacy reporting. No telemetry exists. The default route implies
  most.
- The time cost of `project_sync.py` loading `workflow.py` per sync (J3) was not measured.
- The PM6 confirmation run (R1) was not made. The duplication is shown in code only.
- How many unmanaged Scope users install the presets by hand (R2 migration audience) is unknown.
