# Round 3, stream N1: naming

Read-only research, 2026-10-19, worktree `sanduq-round3` (branch `feat/round-3`). Spec Kit source:
`D:\Projects\Personal\spec-kit` at 92b7cf7. Community catalogs fetched live on 2026-10-19 from
`https://raw.githubusercontent.com/github/spec-kit/main/{extensions,presets,workflows}/catalog{,.community}.json`
(the URLs are hard-coded in `src/specify_cli/extensions/__init__.py:2006-2008` and
`presets/__init__.py:1825-1826`). Counts come from a scan of `git ls-files -co --exclude-standard`
without `dist/`, `__pycache__` and binary files.

## 1. Summary

1. Fit: assure, user-manual, illustrate, progress and pr fit their ids. Scope, memory and project
   fit only in part, and workflow is a generic word that Spec Kit itself now uses.
2. Misleading display names: "Speckit Scope" (it reads like an upstream product and is the only name that says "Speckit"), "Pull Request Workflow" (easy to mix up with the Workflow extension), and "Sanduq Progress Report", "GitHub Project Lifecycle Sync", "Assure", "User Manual" and "Illustrate", which use the Sanduq prefix inconsistently.
3. Exact id collisions in the community catalog: `scope` ("Spec Scope", effort and scope-creep tracking, a close purpose) and `memory` ("Spec Kit Memory", recalls prior specs, a close purpose).
4. Concept collision: Spec Kit ships `specify workflow run|resume|status`, `.specify/workflows/` and a workflow catalog, so our `workflow` id, preset `workflow`, `.specify/workflow/` and `.specify/workflow.yml` sit one letter away from the upstream concept.
5. Spec Kit has no extension id alias, no `replaces` or `renamed_from`, and no migration step. `specify extension update` refuses an id change. Spec Kit does support free-form command aliases, which can carry old command names forward.
6. An id rename touches 38 to 129 files per id on the id-derived surface alone. For workflow, memory and project it also needs consumer-side edits that Spec Kit cannot make.
7. Recommended set: give every display name the "Sanduq" prefix and fix the four misleading ones (S); rename `scope` to `issue-scope` (M), because Sanduq's own installer can migrate it automatically; keep every other id, including `memory` (collision documented, rename kept in the full set).
8. Total effort for the recommended set: about 1 S batch plus 1 M. Display names only: 1 S. Full rename: about 3 M plus 2 L.

## 2. Inventory

| Item | id | Display name | Command prefix | What it actually does (from commands, scripts, hooks) | Fit |
| --- | --- | --- | --- | --- | --- |
| Extension | `workflow` | Sanduq Workflow | `speckit.workflow.*` (13) | A dispatcher that takes one GitHub issue through 16 stages (scope to PR) with checkpoints, receipts, GitHub decisions, delegation and an evidence CI gate, and installs the extensions it uses (`scripts/workflow.py` `BASE_STAGES`, `install.py`). The user invokes it; the `workflow` preset routes core commands to it. | partly: "workflow" is generic and is now an upstream Spec Kit noun (`specify workflow`) |
| Extension | `scope` | Speckit Scope | `speckit.scope.*` (7) | Sizes and splits a GitHub issue into approved sub-issues. It also guards Specify (`before_specify`), binds the spec to its issue (`after_specify`), gates Plan on the issue being Ready (`before_plan`) and reconciles parent progress. Five of its seven commands are hook-only (`hosts.py:43`). | id partly (the gates and binding go beyond "scope"); name misleading ("Speckit") |
| Extension | `assure` | Assure | `speckit.assure.*` (3) | Adds missing QA tasks to `tasks.md` before Implement and writes the QA test manual afterwards, through hooks or on request. | fits (the name lacks the Sanduq prefix) |
| Extension | `user-manual` | User Manual | `speckit.user-manual.*` (4) | Scaffolds, updates per feature and releases an audience-aware MkDocs and PDF application manual. | fits (no prefix) |
| Extension | `pr` | Pull Request Workflow | `speckit.pr.*` (2) | Writes the feature CHANGELOG and details doc, opens or updates the PR, and processes review comments after approval. | id fits; name misleading ("Workflow") |
| Extension | `project` | GitHub Project Lifecycle Sync | `speckit.project.*` (2) | Moves a parent feature issue across GitHub Project (v2) Status columns as lifecycle hooks fire, and creates or closes one sub-issue per task (`scripts/project_sync.py`). | id partly ("project" means the repository everywhere in Spec Kit); name fits (no prefix) |
| Extension | `illustrate` | Illustrate | `speckit.illustrate.*` (4) | Draws, imports and exports 44 themed diagram and chart types. An opt-in `post_tool_use` hook self-checks written SVG HTML (`hooks/self_check_hook.py`). | fits (no prefix; the generic verb is safe inside the `speckit-illustrate-*` namespace) |
| Extension | `memory` | Sanduq Memory | `speckit.memory.*` (7) | Archives verified, merged feature specs into `specs/memory/` capability entries through scoped Git commits, and consults that memory before Specify and Analyze (mandatory hooks). | partly: it is spec archive plus product memory, and the id collides exactly |
| Extension | `progress` | Sanduq Progress Report | `speckit.progress.*` (5) | Maintains a live, deterministic per-feature progress report from host hooks and feature files. | fits |
| Preset | `workflow` | Sanduq managed workflow | overlays 15 core and extension commands | Prepends or replaces `speckit.specify/clarify/plan/tasks/analyze/taskstoissues/implement`, `speckit.scope.run` and Superspec/bridge commands so the dispatcher owns transitions. | partly: same id as the extension it belongs to |
| Preset | `scope-gate` | Scope before Specify | overlays `speckit.specify`, `speckit.clarify` | Requires a scoped issue before Specify, and GitHub clarification. | fits (no prefix) |
| Preset | `scope-brainstorm` | GitHub Brainstorm clarification | overlays `speckit.superspec.brainstorm` | Runs Superspec Brainstorm unattended through GitHub question comments, using scope's `github-clarification` skill. | fits (no prefix) |

## 3. Findings

**F1. Inconsistent "Sanduq" prefix.** Three of the nine extension names have it (Workflow, Memory,
Progress Report), one preset has it, and six extensions and two presets do not. The README product table
uses the bare names ("Workflow", "Scope", "PR"), so display names, docs and catalog disagree.
"Sanduq Workflow" appears in 21 files, "Sanduq Memory" in 12, and every other name in 5 files or fewer.

**F2. "Speckit Scope"** is the only name that uses the upstream brand ("Speckit", spelled unlike
"Spec Kit"). It reads like an official Spec Kit product and shares its first word with the community
"Spec Scope". It occurs 6 times in 5 files.

**F3. "Pull Request Workflow" vs "Sanduq Workflow".** Both names end in "Workflow" and both open PRs
(`speckit.workflow.finalize` and `speckit.pr.generate`). The upstream default catalog uses the same
pattern for unrelated things ("Bug Triage Workflow", "Git Branching Workflow"). 5 files.

**F4. `project` means the repository in Spec Kit** (`_require_specify_project`, "project-level
catalog config", `.specify/` is "the project"). The extension syncs a GitHub Project board. The name is
right and the id is ambiguous. Workflow's own policy key is already `project_sync`, and the state
file is `.specify/project-sync-state.json`, so the code already calls it "project sync".

**F5. `memory`** does two things: archives verified features (`run`, `prepare`, `session`, `enable`)
and queries product memory (`impact`). The id is an exact collision. It is also close to Spec Kit's
own `.specify/memory/` (the constitution folder, `agents.py:181`), and the community `archive`
extension ("Archive merged features into main project memory") does the same job under another name.

**F6. `progress`** fits. The community `status` ("Project Status") and `status-report` ("Status
Report") are confusable by purpose, but they do not share the id or command names.

**F7. `illustrate` as a generic name.** The host skills are `speckit-illustrate-*`, so the extension
cannot shadow a host skill. The vendored `skill/SKILL.md` is named `illustrate`, the same as the
portable sanduq-skills skill and the `illustration-tools` plugin. This is deliberate (one skill, three
deliveries) and the extension does not install it as a top-level host skill. No catalog entry uses
`illustrate`. The confusable entries are `diagram`, `ascii-diagram` and `data-model-diagram`. Keep.

**F8. `workflow` and Spec Kit Workflows.** Spec Kit 1.x has `specify workflow
run|resume|status|add|remove|search|info` (`workflows/_commands.py:304-914`), installs to
`.specify/workflows/`, and its catalog bundles a workflow `speckit` ("Full SDD Cycle"). We ship
`speckit.workflow.continue` and `speckit.workflow.status`, `.specify/workflow/`, `.specify/workflow.yml`,
and a preset also called `workflow`. A user who reads "workflow status" cannot tell which one is meant.
Spec Kit does not register any `speckit.workflow.*` command (grep of `src/` finds none), so there is
no hard collision.

**F9. Legacy policy key from the last rename.** `.specify/workflow.yml` still uses `processes.qa`
for Assure (`schemas/policy-v1.schema.json`), and `dependencies.json` groups `selected.qa.assure`.
The qa-to-assure rename (Assure 2.0.0 CHANGELOG) kept policy keys and changed only the id. That is
the precedent for keeping state and policy names stable through a rename.

**F10. README count drift.** The badge and product map say "8 extensions", while the table and
`extensions/README.md` list nine, because Progress was added later. This is a docs-only fix.

**Collisions in the live catalogs (2026-10-19):**

| Our id | Catalog | Entry | Kind |
| --- | --- | --- | --- |
| `scope` | extensions community | `scope` "Spec Scope" (Quratulain-bilal), effort estimation and scope creep, 4 commands | exact id, close purpose |
| `memory` | extensions community | `memory` "Spec Kit Memory" (zaytsevand), recalls prior specs and decisions before SDLC stages | exact id, close purpose |
| `memory` | extensions community | `archive`, `memory-loader`, `memory-md`, `memorylint`, `dubsar`, `adrkit` | confusable |
| `pr` | extensions community | `pr-bridge` "PR Bridge", which generates PR descriptions from spec artifacts | confusable (same job) |
| `project` | extensions community | `tasks-to-project` "Tasks to GitHub Project", `maqa-github-projects` | confusable (same job) |
| `assure` | extensions community | `qa` "QA Testing Extension", `maqa` | confusable by purpose only (the reason for the earlier `qa` rename) |
| `progress` | extensions community | `status`, `status-report` | confusable by purpose |
| `illustrate` | extensions community | `diagram`, `ascii-diagram`, `data-model-diagram` | confusable by purpose |
| `workflow` | workflows catalog | `speckit` "Full SDD Cycle"; the `specify workflow` CLI | concept and noun |
| `workflow` (preset) | presets community | `workflow-preset`, `lean` "Lean Workflow" | confusable |
| `scope-gate`, `scope-brainstorm` | presets | none | clear |
| `user-manual` | all | none | clear |

Built-in command namespaces that Spec Kit reserves are `analyze`, `checklist`, `clarify`,
`constitution`, `converge`, `implement`, `plan`, `specify`, `tasks` and `taskstoissues`
(`extensions/__init__.py:37-50`). An extension id equal to one of them is refused at install
(`:722`). None of ours, current or proposed, is in that list.

Host skill namespaces: every Sanduq command renders as `speckit-<id>-<cmd>`, so nothing shadows
Claude Code built-ins (such as `/memory` and `/review`) or common skills (`pr-review`, `illustrate`).
The only short names Sanduq writes are the managed aliases `speckit-scope` and
`speckit-superpowers-bridge` (`hosts.py:39`), which are opt-in with `--with-aliases`.

**When a catalog collision actually bites.** `specify extension catalog add` writes
`.specify/extension-catalogs.yml`. A project-level file replaces the built-in default and community
stack completely (`extensions/__init__.py:2110-2150`, `catalogs.py:87`), so the README quick start
sees only Sanduq. A user who keeps or re-adds the defaults gets the community entry (priority 2 wins
over our 10), which is `install_allowed: false`, so `specify extension add scope` or `add memory`
then fails or shows the other product in `search` and `info`. The Workflow installer is immune
because it installs with `--from <release URL>` and checks the repository of any installed package
with the same id (`install.py:669`, `EXISTING_EXTENSION_SOURCE_CONFLICT`).

**Spec Kit id rules and rename support (read from source):**

- Id: `^[a-z0-9-]+$` (`extensions/__init__.py:220`). It must not be a core command namespace
  (`:722`). Primary commands must be `speckit.<id>.<cmd>` with the namespace equal to the id
  (`:51`, `:748-762`).
- Command aliases: `provides.commands[].aliases` takes free-form strings with no pattern and no
  namespace check (`:338-353`, `:747-749`). Spec Kit renders each alias as an extra command or skill
  file for every host (`agents.py:701-771`). Install refuses an alias that another installed
  extension already provides (`:808-823`). This means a renamed extension can keep
  `speckit.scope.run` and the other old names as aliases.
- No extension-level alias, `replaces`, `renamed_from` or migration hook exists. grep for
  `renamed_from|replaced_by|supersede|previous_id` in `src/` finds nothing relevant. The preset
  `replaces:` field in our `preset.yml` files is not read by Spec Kit; overrides match on `name`.
- `specify extension update` looks the installed id up in the catalog and aborts on `Extension ID
  mismatch` (`extensions/_commands.py:1240-1246`), so a catalog cannot move users to a new id.
- `specify extension remove <id>` unregisters the commands and the default-agent skills, removes
  the hooks whose `extension:` is that id from `.specify/extensions.yml`, deletes
  `.specify/extensions/<id>/`, and backs up only top-level `*-config.yml` and `*-config.local.yml`
  to `.specify/extensions/.backup/<id>/`. `--keep-config` keeps only those files
  (`extensions/__init__.py:1533-1607`). State inside the folder, such as `assure/state/`,
  `project/config.json` and `pr/config.json`, is lost unless something copies it out first.
- Catalog schema: only `schema_version` and an `extensions` mapping are validated (`:2071-2106`).
  Extra keys on an entry are tolerated, so a `replaced_by` note is readable by our tooling and
  ignored by Spec Kit.

## 4. Options per item

Effort: S under 2 h; M 0.5 to 2 days including tests and migration; L more. "Id-derived surface"
counts files and occurrences that match `speckit.<id>.`, `speckit-<id>-`,
`.specify/extensions/<id>` or `<id>-v` (own folder / other extensions / presets / docs / tests).
"State" lists paths that a rename can leave unchanged.

### Cheap fixes (display name and description only, id unchanged)

Each one is a manifest `name:` edit, a patch version bump, catalog regeneration on release
(`release.py` copies the name) and docs text. No consumer migration is needed: the registry entry
refreshes on the next `add`/`update`, and command and skill names do not change. Risk: none, apart
from users who resolve an extension by display name (`_resolve_installed_extension` accepts names).

| Item | Now | Proposed | Occurrences | Effort |
| --- | --- | --- | --- | --- |
| scope | Speckit Scope | **Sanduq Issue Scope** | 6 in 5 files | S |
| pr | Pull Request Workflow | **Sanduq Pull Requests** | 5 in 5 files | S |
| project | GitHub Project Lifecycle Sync | **Sanduq GitHub Project Sync** | 4 in 4 files | S |
| assure | Assure | **Sanduq Assure** (keep "QA" in the description) | catalog and manifest | S |
| user-manual | User Manual | **Sanduq User Manual** | catalog and manifest | S |
| illustrate | Illustrate | **Sanduq Illustrate** | catalog and manifest | S |
| memory | Sanduq Memory | **Sanduq Memory and Archive** (the description already says archive) | 13 in 12 files | S |
| progress | Sanduq Progress Report | keep | 0 | none |
| workflow | Sanduq Workflow | keep the name; open the description with "Issue-to-PR" and add one line in the README and the workflow docs saying it is not `specify workflow` | 23 in 21 files | S |
| preset workflow | Sanduq managed workflow | keep | 0 | none |
| preset scope-gate | Scope before Specify | **Sanduq scope gate** | 1 | S |
| preset scope-brainstorm | GitHub Brainstorm clarification | **Sanduq GitHub brainstorm** | 1 | S |
| README | "8 extensions" badge and map | "9" | 2 to 3 | S |

### Id renames (expensive)

**workflow.** Id-derived surface: 129 files and 366 occurrences (58/15/18/29/18). The union with state
is 195 files, 116 of them outside its folder. State: `.specify/workflow/` and `.specify/workflow.yml`
(283 occurrences in 120 files), `specs/*/workflow/checkpoint.json`, and the rendered CI file
`.github/workflows/sanduq-workflow-gates.yml` in consumers. 38 release tags.
- Keep (recommended). The collision is conceptual, and the display name plus a disambiguating
  description handle it.
- `issue-flow` / "Sanduq Issue Flow" / `speckit.issue-flow.*`: names the actual unit (one issue to
  a PR). Effort L. Risk high: `upgrade.py` bootstraps by `registry(root).get('workflow')` and
  hard-checks `meta['id'] == 'workflow'` (`upgrade.py:22-34`), so the change needs a bridge release
  `workflow-v1.15.0` whose upgrader knows the new id, and every installed consumer must pass through it.
- `sanduq` / "Sanduq" / `speckit.sanduq.*`: brand as the flagship id (`/speckit-sanduq-continue`).
  Effort L. Same bridge requirement. It also suggests that the other extensions are not part of Sanduq.
- `delivery` / "Sanduq Delivery": effort L, same bridge requirement. The word is vaguer than "issue-flow".
- Migration if chosen: the bridge release, state paths kept, all 13 commands aliased for one minor
  release, host guard hook and role agent files rewritten by `reconcile`, and the CI file name kept.

**scope.** Id-derived surface: 54 files and 126 occurrences (20/12/6/15/6). The union with state is 98
files. State: `.specify/scope/`, `scope-source.json` (126 occurrences, filename only) and policy key
`scope:`. 9 tags. Consumers hold hooks `speckit.scope.guard`, `.bind`, `.after-specify` and
`.plan-guard` in `.specify/extensions.yml`; hidden hook-only skill folders `speckit-scope-*` in
each host (`hosts.py:43`); the optional alias `speckit-scope`; the preset overlay for
`speckit.scope.run`; and inventory entries in `.specify/workflow/install-lock.json`.
- Keep the id and only fix the display name. Effort S, and the collision stays.
- `issue-scope` / "Sanduq Issue Scope" / `speckit.issue-scope.*` (recommended). It says what the
  extension scopes and leaves the collision behind. Effort M, risk medium. Scope is never installed
  on its own (it requires workflow, and the README tells users to go through Workflow's installer),
  so `install.py` can carry out the whole migration.
- `sanduq-scope` / "Sanduq Scope" / `speckit.sanduq-scope.*`: unique by brand. Effort M. Longer
  skill names (`speckit-sanduq-scope-plan-guard`), and it sets a pattern that the other ids do not follow.
- `triage` / "Sanduq Issue Triage": effort M. It collides by purpose with community `gh-triage` and
  the upstream `bug` extension ("Bug Triage Workflow"). Not advised.

**assure.** Id-derived surface: 52 files and 204 occurrences. Keep. It was already renamed twice
(how-to-test, then qa, then assure), and there is no collision left. Candidates for completeness:
`qa-gate` (M) or `sanduq-qa` (M). Neither is worth a third break.

**user-manual.** 41 files and 148 occurrences, 14 tags. Keep. It fits, has no collision, and matches
the portable skill names.

**pr.** 46 files and 123 occurrences, 11 tags; consumer state `.specify/extensions/pr/config.json`.
- Keep the id (recommended) with the cheap name fix.
- `pull-request` / "Sanduq Pull Requests": clearer, effort M, and it gains little.
- `pr-docs` / "Sanduq PR Docs": stresses the CHANGELOG and details doc, but leaves out review
  feedback. Effort M.

**project.** 42 files and 126 occurrences (8/18/0/15/10). It touches more other extensions than any
other id, because Workflow drives it. State: `.specify/project-sync-state.json`,
`.specify/extensions/project/config.json` (21 files), and six hooks in consumers. 9 tags.
- Keep the id (recommended) with the cheap name fix.
- `project-sync` / "Sanduq GitHub Project Sync" / `speckit.project-sync.*`: matches the policy key
  `project_sync` and the state file. Effort M, risk medium. Workflow installs it, so `install.py`
  migrates Workflow consumers. Standalone users must remove and add it by hand, and `config.json`
  must be copied before `remove`.
- `github-project` / "Sanduq GitHub Project": effort M. Close to `tasks-to-project` and
  `maqa-github-projects`.
- `board-sync` / "Sanduq Board Sync": host-neutral wording. Effort M, but it hides "GitHub".

**illustrate.** 38 files and 137 occurrences, 12 tags; it is a required dependency of four
extensions (`id: illustrate` appears in 10 manifests). Keep. Candidates: `diagram` (taken in the
community catalog), or `sanduq-illustrate` (M, no gain).

**memory.** 45 files and 233 occurrences (25/5/0/14/5), 9 tags. Consumers hold files that Spec Kit
never touches: the `SANDUQ MEMORY SESSION` block in `AGENTS.md`, `CLAUDE.md` and
`.github/copilot-instructions.md`, which names `.specify/extensions/memory/...` paths
(`install.py:28-33`); guard entries `memory/hooks/guard.py` in `.claude/settings.json` and
`.codex/hooks.json` (`install.py:24-25`); patched `create-new-feature.sh` and `.ps1` scripts;
mandatory (`optional: false`) hooks; and `.specify/memory-policy.json`. Workflow does not manage
it (absent from `MANAGED_EXTENSIONS` and `dependencies.json`), so there is no automated path.
- Keep the id (recommended) with the cheap name fix and a note in the README and the extension page
  about the community `memory`.
- `spec-memory` / "Sanduq Spec Memory" / `speckit.spec-memory.*`: memory built from specs, and no
  collision. Effort L, risk high: consumer-committed files must be rewritten, and a missed guard
  path blocks `create-new-feature`.
- `product-memory` / "Sanduq Product Memory": matches the `impact` wording ("product memory").
  Effort L, same risk.
- `spec-archive` / "Sanduq Spec Archive": names the archive half and loses the memory half. Effort L.

**progress.** 40 files and 183 occurrences, 8 tags. Keep. Candidates: `progress-report` (M) or
`feature-progress` (M). Neither fixes a real problem.

**Preset `workflow`.** The id shares its name with the extension. The installed path
`.specify/presets/workflow/` is used in 23 files (66 occurrences). It is bundled inside the workflow
package (`package.py:10`) and installed by `install.py:690`, which removes an old preset only under
the same name.
- Keep (recommended). The registries are separate and users never type the preset id.
- `workflow-overlay` / "Sanduq managed workflow overlay": effort S to M. `install.py` must also
  `specify preset remove workflow` when present.
- `sanduq-workflow`: effort S to M, same migration.

**Presets `scope-gate` and `scope-brainstorm`.** 33 and 28 files. Keep with the cheap name fix.
If `scope` becomes `issue-scope`, keep these ids anyway: they describe the gate, not the
extension id, and renaming them adds churn for no gain.

## 5. Migration design for an id rename

Principle (from the qa-to-assure precedent, F9): change only what Spec Kit derives from the id, such
as the folder, command and skill names, registry key, hook owner, catalog key and tag prefix. Keep
every state path, policy key, state file name, config file name and marker unchanged. That removes
most of the state blast radius (scope: 98 files fall to 54; workflow: 195 fall to 129).

**What Spec Kit can do:** install the new id; render old command names as aliases (free-form,
conflict-checked against installed extensions, so this works only after the old id is removed);
remove the old id with its hooks and default-agent skills; keep top-level `*-config.yml` files with
`--keep-config`.
**What it cannot do:** rename in place, alias an id, redirect a catalog id, update across ids,
preserve non-config state in the folder, clean skills of non-default hosts on its own, or edit
consumer files outside `.specify/` such as `AGENTS.md` and host hook settings.

**Steps in `install.py` (run by `upgrade.py --version X --apply`, already inside the snapshot,
lock and rollback boundary):**
1. Add `RENAMED = {'scope': 'issue-scope'}` next to `dependencies.json`. Update
   `dependencies.json.required`, `RANGES` (`workflow.py:42`), `MANAGED_EXTENSIONS` and
   `HOOK_ONLY_SKILLS` (`hosts.py:28,43`), the `order` tuple (`install.py:661`), the `COMMANDS` map
   (`workflow.py:47`), and `package.py` `PRESETS`.
2. Preflight with the existing checks: no active checkpoint, no live delegation, no upgrade lock.
   Then require that the old registry entry's `repository` is Sanduq. A community `scope` is never
   touched.
3. `preserved = preservation(root, old)` (`install.py:285`, which already captures `config.json`,
   `*-config.yml` and `state/`).
4. `specify extension remove <old> --force`. This drops the registry entry, the hooks owned by
   `<old>`, the default-agent skills and the folder.
5. `specify extension add <new> --from <repo>/releases/download/<new>-v<ver>/<new>.zip --force`,
   then write `preserved` into `.specify/extensions/<new>/`. The new manifest declares the old
   command names as `aliases` for one minor version, so muscle memory, hand-written prompts and any
   overlay still naming `speckit.scope.run` keep resolving.
6. Hosts: the existing `register_hosts` re-registers every installed host. After that, delete
   `<host>/skills/speckit-<old>-*` folders whose content matches a Spec Kit render, using the
   alias review approach (`review_aliases`, hash-checked; anything edited locally is refused unless
   `--replace-unrecognized-aliases`). Rename the managed alias `speckit-scope` to
   `speckit-issue-scope` and keep the old alias file as a recognised Sanduq alias for one minor version.
7. `reconcile(root, apply=True)` reapplies mandatory hook flags and hidden-skill settings from
   policy. Policy keys stay the same, so `.specify/workflow.yml` needs no edit.
8. `install-lock.json`: record the new id and `renamed_from: <old>`. Doctor learns to report a
   leftover `<old>` (registry entry or folder) as `RENAMED_EXTENSION_LEFTOVER` with the exact fix.
9. Per-feature receipts that store command names (`speckit.scope.run` in receipts and checkpoints)
   are historical. Readers accept both names for one minor version, then `workflow.py migrate`
   rewrites them.

**Standalone extensions (memory, project outside Workflow):** ship a final old-id release, for example
`memory-v2.4.0`, whose `init`, `status` and `doctor` print the migration. Add a
`scripts/migrate_id.py --apply` in the new package that performs steps 2 to 8 for that extension,
and also rewrites the consumer-file references it owns: the `AGENTS.md` and `CLAUDE.md` block, host
guard entries and the patched feature scripts. A missed edit is a hard blocker and the change is
rolled back.

**Catalog and release continuity:**
- The new id starts at the next major of the old series (scope 1.8.1 becomes `issue-scope` 2.0.0)
  so the changelog lineage reads straight through. The new tag prefix `<new>-v` is produced
  automatically, because `release.py:74` builds `{name}-v{version}`. Old tags stay.
- Keep the old catalog entry, frozen at the last old-id release, for one minor cycle, with
  `"name": "<Old> (renamed to <new>)"`, a description that opens with the migration command, and a
  tolerated `"replaced_by": "<new>"` key. `specify extension update <old>` then reports "up to
  date", which does no harm, and `search` and `info` show the pointer. After that, remove the entry.
- Docs: the README adoption section and `docs/start/upgrades.md` get a "Renamed extensions" table.
  The extension CHANGELOG gets the same Breaking and Migration block as Assure 2.0.0.

**Order for Workflow consumers:** the user runs `upgrade.py --version <next>` once. The new
`install.py` performs the rename inside the same rollback boundary. A failure restores the snapshot,
which covers `.specify/extensions`, `.specify/presets`, `extensions.yml` and host files
(`install.py:33-35`).

## 6. Overall presets for the user

| Preset | Items | Total effort | Consumer impact |
| --- | --- | --- | --- |
| **Display names only** | Sanduq prefix on all nine extensions and three presets; fix "Speckit Scope", "Pull Request Workflow" and "GitHub Project Lifecycle Sync"; disambiguate the workflow description from `specify workflow`; README "9 extensions"; collision notes for `scope` and `memory` | 1 S batch (about 13 manifest and docs edits plus patch bumps) | none |
| **Recommended** | Everything above, plus `scope` to `issue-scope` with the automated `install.py` migration, command aliases for one minor version, a frozen old catalog entry, and doctor reporting of leftovers | S + M (about 1.5 to 2 days) | Workflow consumers: one `upgrade.py` run. No standalone users exist (scope requires Workflow). |
| **Full rename** | Recommended, plus `memory` to `spec-memory` (L, standalone migrator), `project` to `project-sync` (M), the `workflow` preset to `workflow-overlay` (S to M), and `workflow` to `issue-flow` (L, bridge release first). `assure`, `user-manual`, `illustrate`, `pr` and `progress` stay. | S + 3 M + 2 L (about 7 to 10 days) | Every consumer goes through the workflow bridge release; memory and project standalone users must run a migrator; consumer `AGENTS.md`, `CLAUDE.md` and host hook files are rewritten |

Unverified: whether Spec Kit preset overrides (`name: speckit.scope.run`) apply to a command that
exists only as an alias of a renamed extension (step 5 relies on aliases for prompts and hooks, not
for preset overlays; the overlay must move to the new primary name). Also unverified: whether
`specify integration use <host>` removes skills of a removed extension on non-default hosts (step 6
cleans them explicitly in either case).
