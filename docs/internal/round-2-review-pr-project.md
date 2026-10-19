# Round 2 review: pr and project (stream R2, read-only)

Measured on worktree `D:\Projects\Personal\sanduq-round2` (branch `feat/round-2`) with `wc`, `grep` and `sed`
on 2026-10-19. Byte counts are file sizes; words are `wc -w`; prohibitions use the plan's regex.

## Summary

1. `speckit.pr.generate` is 18,060 B / 2,493 words and makes the model do four deterministic jobs by hand: the PR body marker splice, the pr-lint receipt (`pr_body_file`, `pr_lint_file`, `pr_body_sha256`), the CHANGELOG fact collection, and `gh pr create|edit`; `workflow.py:1308-1320` then rejects any hand-computed mismatch.
2. A managed PR run with one diagram and QA selected reads about 93 KB of instruction text, of which 44.5 KB is the whole Illustrate skill plus `export.md`, loaded for a selection guide the command already restates (1,947 B, lines 139-165) and a one-line export command.
3. Two blocks are read twice in the same claim: the pr-lint procedure (1,686 B in the command, 462 B in `stage-pr.md`, which `claim` inlines as `reference_text`) and the managed preflight paragraph (739 B).
4. `project`'s two command files have no frontmatter, so both hosts list them as "Extension command: speckit.project.init/sync" (Spec Kit fallback); the sync body (2,719 B) is reread at six dispatcher points per feature to produce one script line each, and its managed-mode prose repeats what the scripts already do.
5. Nine options, PR1 to PR6 and PJ1 to PJ3 plus PJ4 (host convergence, large): all keep receipts, evidence gates, the pr-lint recomputation, inline PR diagrams and GitHub decisions; the only policy keys are opt-in with unchanged defaults.

## Lens 1: model work a script does or could do

- PR body assembly is prose: detect PR (`gh pr view`), build the marked section, replace between `<!-- speckit-pr:start -->` markers or append, `gh pr edit --body-file` (`extensions/pr/commands/speckit.pr.generate.md:234-269`). All deterministic string work.
- The pr-lint receipt is hand-made: write the exact body to a tmpfile, run `execution_tools.py pr-lint`, copy `body_sha256` into the receipt, list both files as evidence, "never change the body after linting" (`speckit.pr.generate.md:248-263`). The dispatcher recomputes everything and refuses on any mismatch (`extensions/workflow/scripts/workflow.py:1296-1322`: `PR_LINT_EVIDENCE_REQUIRED`, `PR_LINT_RECEIPT_MISMATCH`, `PR_SENT_BODY_SHA_MISMATCH`). No script writes those three fields: `grep -n pr_body extensions/workflow/scripts/*.py` hits only the validation lines 1308-1320.
- CHANGELOG facts are gathered by reading `git log`, `tasks.md`, `progress.yml`, `scope-source.json` by hand (`speckit.pr.generate.md:123-130`, `193-199`); the Keep-a-Changelog header (spec path, branch, tracking issue, PR) and the Tests & quality section are facts a script can emit.
- `deps.py ensure illustrate` already prints the recipe and the "newer release" note itself (`extensions/scripts/shared/deps.py`, packaged by `extensions/scripts/package.py:43-47`), yet the command spends 1.5 KB (lines 42-69) restating what the script does and how to re-run it with `--approve`.
- `project.init.md:20-25` tells the model to "preserve reconciled hook entries and use required board synchronization without a second hook-mode question" in managed mode; both scripts already do exactly that (`scripts/bash/project-init.sh:68-72` sets `HOOKS_MODE=required` and calls `workflow.py project-defaults`; `scripts/powershell/project-init.ps1:78-82,199,219`).
- `project.init.md:68` asks the model to "store owner and project number in the Spec Kit memory file"; `config.json` already stores `owner` and `projectNumber` (`config.default.json` keys), and no file named "memory file" exists in the extension (`grep -rn "memory file" extensions/project` hits only that line).

## Lens 2: repeated text

| Block | Copy A | Copy B | Bytes |
| --- | --- | --- | --- |
| Diagram type selection list | `speckit.pr.generate.md:139-165` | `extensions/illustrate/skill/SKILL.md:101-140` (selection guide, 4,891 B) | 1,947 |
| pr-lint procedure | `speckit.pr.generate.md:248-263` | `extensions/workflow/skills/workflow/references/stage-pr.md:19-24` | 1,686 + 462 |
| Managed preflight rules (checkpoint binding, "selected but unavailable blocks Finalize", receipts) | `speckit.pr.generate.md:82-90` | dispatcher-owned claim fields (`workflow.py:3097-3099`: `feature`, `issue`, `reference_text`, `side_effects`) | 739 |
| Managed init behaviour | `project.init.md:20-25` | `project-init.sh:68-72`, `project-init.ps1:78-82,199` | 448 |
| Flags and hook of `pr.generate` | `speckit.pr.generate.md:27-32` | `extensions/pr/README.md:42-55` (not agent-loaded; maintenance only) | about 600 |
| Description of `pr.generate` | frontmatter 160 chars | `extension.yml:7` (195), `:37` (169), `:47` hook (146) | four wordings |

Both copies of the pr-lint block and the preflight paragraph are in the model's context at once: `claim` inlines
`stage-pr.md` (4,141 B) as `reference_text` (`workflow.py:3097`) and the model then opens the command.

## Lens 3: large rereads

- Illustrate: `skill/SKILL.md` is 34,739 B and `references/export.md` 9,737 B; `speckit.pr.generate.md:136,169,174-176` loads both plus one `type-*.md` (1,079 to 6,780 B) to pick a type the command already enumerated and to run one line, `python scripts/export_diagram.py <file>` (`export.md:24-27`).
- Ground truth: step 3 reads `spec.md`, `plan.md`, `data-model.md`, `tasks.md`, `quickstart.md`, `research.md`, `contracts/*` and `git log` whole (`speckit.pr.generate.md:125-128`). The Explained doc needs spec and plan; the CHANGELOG needs tasks, log and progress, which a script can reduce to a fact list.
- Preflights pull in `speckit.assure.document.md` (14,620 B) and `speckit.user-manual.update.md` (3,487 B) when selected (`speckit.pr.generate.md:96-116`).
- Instruction set of one managed PR run with one diagram and QA selected: 18,060 + 4,141 + 3,191 + 34,739 + 9,737 + about 5,000 + 14,620 + 3,487 = about 93 KB (about 23k tokens); unmanaged minimum 70.7 KB.
- Project sync: `speckit.project.sync.md` (2,719 B) is reread at each of the six points `PROJECT_SYNC_POINTS = ('specify','plan','analyze','taskstoissues','execute','pr')` (`workflow.py:79`), 16.3 KB per feature, each time to run one script line whose phase the dispatcher already knows (`references/dispatcher-operations.md:48-51`).

## Lens 4: catalog descriptions

Spec Kit takes the host description from the command file's frontmatter only and falls back to
`Extension command: <name>` (`D:\Projects\Personal\spec-kit\src\specify_cli\extensions\__init__.py:1083-1084`);
`extension.yml` `provides.commands[].description` never reaches a host.

| Skill | Source | Chars | Third person | What | When | Triggers |
| --- | --- | --- | --- | --- | --- | --- |
| speckit-pr-generate | frontmatter line 2 | 160 | no ("Generate ...") | yes | no | no |
| speckit-pr-review-feedback | frontmatter line 2 | 92 | no ("Process ...") | yes | no | no |
| speckit-project-init | none (file starts `# Initialise` at line 1) | fallback | no | no | no | no |
| speckit-project-sync | none (file starts `# Sync` at line 1) | fallback | no | no | no | no |

No hook-only command in scope: `speckit.project.sync` is hook-driven in managed mode but a legitimate user
command (`/speckit-project-sync <phase>`), so it keeps its slot.

## Lens 5: rules a hook could enforce

Prohibitions: `pr.generate` 21 in 2,493 words (0.84/100), `pr-image-embedding.md` 7 in 447 (1.57/100),
`review-feedback` 3 in 780, `project.init` 2 in 449, `project.sync` 2 in 362.

- "Never run `gh pr create` or `gh pr edit` after a nonzero exit, and never change the body after linting" (`speckit.pr.generate.md:254-256`) and "Never create a PR from the default branch itself" (`:271`): both are checkable from the command line and the files beside it. The repository already ships a PreToolUse guard on both hosts (`extensions/workflow/hooks/hooks.json`, `hooks/guard.py`, `hosts.py:45` `HOOK_FILES` for `.claude/settings.json` and `.codex/hooks.json`).
- "Do not modify files, post replies, commit, push, or resolve threads before the user approves" (`review-feedback.md:99-100`) depends on an approval the host does not record; stays prose.
- `pr-image-embedding.md:24-25` (no `raw.githubusercontent.com`, no tokens in URLs, no data URLs) is a body-file lint, not a tool hook: it belongs in the same script that lints closing references.

## Lens 6: Claude Code versus Codex

- Browser verification: `pr-image-embedding.md:31-34` requires "actual image loading in an authenticated browser"; `stage-pr.md:14-15` requires `images_verified: true` in the receipt. Codex has no browser tool; the API check (`body_html` and the contents API, lines 26-30) is the only host-neutral verification. The receipt does not say which tier was used.
- Scripts: `project.init.md:38` ("PowerShell primary, bash twin on non-Windows") leaves the shell choice to the model; the bash twins require `jq` (`project-sync.sh:3`, `project-init.sh:55`), which Claude Code's Git Bash on Windows often lacks. `project.sync.md:37-41` shows `pwsh` inside a `bash` fence. Two 1,250-line twins (`wc -l extensions/project/scripts/*/*`) implement one contract; only `extensions/workflow/tests/test_project_sync_summary.py` exercises them.
- Hooks: a guard extension works on both hosts, but Codex needs the per-hash approval in `/hooks` (`hosts.py:48`, standards table row "Hooks").
- Invocation names differ only by prefix (`/speckit-pr-generate` versus `$speckit-pr-generate`, `extensions/pr/README.md:19-20`); skill bodies and the path-loaded Illustrate skill are identical on both hosts.

## Defects

| Defect | Effect | Where |
| --- | --- | --- |
| Project command files have no frontmatter | Both hosts list "Extension command: speckit.project.init" and "... .sync"; Codex shortens or drops such entries first | `extensions/project/commands/*.md:1`; fallback at spec-kit `extensions/__init__.py:1083-1084` |
| Heading numbering: "### 5. Write ..." contains "#### 4a." and "#### 4b." | Step references ("step 4", "step 6") are ambiguous | `speckit.pr.generate.md:188,193,201` |
| pr-lint receipt fields are hand-computed | A copy error fails `PR_LINT_RECEIPT_MISMATCH` or `PR_SENT_BODY_SHA_MISMATCH` after the PR is already published | `speckit.pr.generate.md:248-263`; `workflow.py:1308-1320` |
| Four wordings of the `pr.generate` description | Drift; only the frontmatter one is seen by hosts | `extension.yml:7,37,47`; command frontmatter |
| `images_verified: true` has no host tier | On Codex the receipt either lies or the stage stalls | `pr-image-embedding.md:31-34`; `stage-pr.md:15` |
| "Spec Kit memory file" is undefined | Model may write owner and number into `constitution.md`; `config.json` already holds them | `project.init.md:68` |
| `sync.md` omits `--summary` and shows `pwsh` under a bash fence | The dispatcher prefers `--summary` (`execution-report.md:36-39`); model picks the verbose form or the wrong shell | `project.sync.md:35-43` |
| Step 0 restates `deps.py` behaviour (1.5 KB) | Loaded on every run; the script prints the same recipe | `speckit.pr.generate.md:42-69` |
| Diagram type list duplicates the Illustrate selection guide | Two sources to keep in step; 1,947 B per run | `speckit.pr.generate.md:139-165`; `illustrate/skill/SKILL.md:101-140` |

## Options

Derivation, one line: `tok` = bytes the option removes from what the stage reads (or no longer has the model
write), over the stage's measured instruction set (PR run: 93 KB managed with one diagram and QA selected,
70.7 KB unmanaged; project sync: 2,719 B command plus the claim line; project init: 3,445 B); `time` = tool
calls or model-written bytes removed over the step's current count (PR step 6: about nine calls from
`gh pr view` to the contents-API checks; a sync point: two calls).

### PR1. `pr_publish.py`: deterministic PR body, lint receipt and publication

- what: Add `extensions/pr/scripts/pr_publish.py` (packaged like `deps.py`). Inputs: `docs/<slug>/<Feature>-Explained.md`, `--heading`, `--repo/--issue` from `scope-source.json`, `--no-pr`. It fetches the existing body with `gh pr view --json body`, splices between the markers or appends, writes the UTF-8/LF body file, runs `execution_tools.pr_lint` when Workflow is installed (imports it; otherwise checks closing keywords against the selected issue), writes `lint.json`, refuses on findings, then `gh pr create` or `gh pr edit`, and prints the receipt fragment (`pr_url`, `pr_body_file`, `pr_lint_file`, `pr_body_sha256`, `evidence`). Steps 6 and the receipt sentences in `speckit.pr.generate.md:230-276` shrink to one command and its exit codes; `stage-pr.md:19-24` points to the script.
- effort: M
- tok: [0.04, 0.08]
- time: [0.15, 0.25]
- obs: improved. The receipt fields come from one script output; `workflow.py:1308-1320` keeps recomputing and refusing.
- policy: none.
- pros: removes the most failure-prone hand work in the stage; same body bytes on both hosts; standalone and managed share one path; no change to what the PR contains.
- cons: a new script with `gh` calls to test under mocks; `review-feedback` is untouched; the Explained document is still model-written.
- files: `extensions/pr/scripts/pr_publish.py` (new), `extensions/scripts/package.py:43-47` (ship it), `extensions/pr/commands/speckit.pr.generate.md:230-276`, `extensions/workflow/skills/workflow/references/stage-pr.md:19-24`, `extensions/pr/README.md`, both CHANGELOGs.
- tests: `extensions/pr/tests/test_pr_publish.py` (marker replace, append, create path, lint refusal, sha equals file), `extensions/scripts/tests/test_package_deps.py` extended for the second packaged script, an existing workflow test for `pr_lint_binding` fed the script's receipt.

### PR2. `pr_changelog.py`: seed the CHANGELOG from facts

- what: A script in `extensions/pr/scripts/` that writes `docs/<slug>/CHANGELOG.md` skeleton: header (spec path, branch, bound issue and PR from `scope-source.json` and `gh pr view`, base feature), `Added`/`Changed` seeded from `git log <base>..HEAD` subjects and the checked tasks in `tasks.md` by phase, `Tests & quality` from `progress.yml` and `specs/<feature>/evidence/` receipts, `Open items` from unchecked tasks. The model edits wording and adds Architecture, Migration and Scope sections from spec and plan. Step 3 of the command no longer asks the model to read `git log`, `tasks.md` and `progress.yml` whole.
- effort: M
- tok: [0.05, 0.10]
- time: [0.05, 0.10]
- obs: improved: every number in the CHANGELOG traces to a file the script names; the "never fabricate test counts" rule (`speckit.pr.generate.md:130`) becomes structural.
- policy: none.
- pros: the technical record stops depending on the model's reading of long logs; reruns stay idempotent (fixed path, regenerated skeleton, model edits preserved inside a marked block).
- cons: a feature without `scope-source.json` or `progress.yml` gets a thinner skeleton; the marked-block merge needs care so manual edits survive a rerun.
- files: `extensions/pr/scripts/pr_changelog.py` (new), `extensions/scripts/package.py`, `speckit.pr.generate.md:121-130,193-199`, `extensions/pr/README.md`, CHANGELOGs.
- tests: fixture repo with tasks, log and progress; rerun preserves edits; missing inputs produce a valid skeleton.

### PR3. Trim `speckit.pr.generate.md` to its procedure

- what: Delete the diagram type list (lines 139-165, 1,947 B; the Illustrate selection guide owns it), the managed preflight paragraph (82-90, 739 B; the claim carries binding and the dispatcher owns receipts), the pr-lint block (248-263; `stage-pr.md` owns it, or PR1's one line), and cut step 0 (42-69) to the command plus "exit 0 continue, nonzero report the line and skip diagrams". Fix the 4a/4b numbering. Target 18,060 B to about 11,500 B.
- effort: S
- tok: [0.06, 0.09]
- time: [0.01, 0.02]
- obs: unchanged; no step or receipt changes.
- policy: none.
- pros: the cheapest cut in the stage, repeated on every rerun and every `--finalize` revalidation; one source for each rule.
- cons: standalone users (no Workflow) lose the inline pr-lint description unless the "Workflow absent" sentence stays; needs a careful pass against `stage-pr.md` so no gate sentence is dropped.
- files: `extensions/pr/commands/speckit.pr.generate.md`, `extensions/pr/CHANGELOG.md`.
- tests: `python extensions/scripts/validate_skills.py extensions presets`; the B0 harness after-number for `pr`.

### PR4. Load the diagram recipe, not the whole Illustrate skill

- what: Add `extensions/pr/references/pr-diagram-recipe.md` (about 2 KB): the type-to-reference table copied from `illustrate/skill/SKILL.md:101-140` in short form, the output path rule, the one-line `export_diagram.py` call and the complexity budget sentence. Step 4 of the command loads this recipe plus the one `type-*.md`, and `export.md` only when export fails. `SKILL.md` (34,739 B) and `export.md` (9,737 B) are no longer loaded in the PR stage. Coordinate with the R3 `IL` options: if R3 shrinks the Illustrate entry file, count this once.
- effort: S
- tok: [0.30, 0.45] when a diagram is generated, 0 otherwise
- time: [0.02, 0.05]
- obs: unchanged; diagrams, PNG export and inline embedding stay mandatory.
- policy: none.
- pros: the single largest read in the stage goes away; the Illustrate skill keeps owning styling, which the type reference carries.
- cons: a second copy of the selection table (must be regenerated when Illustrate adds a type; a test can diff them); theme rules in `SKILL.md` not restated in `type-*.md` may be missed.
- files: `extensions/pr/references/pr-diagram-recipe.md` (new), `speckit.pr.generate.md:132-186`, `extensions/pr/README.md`.
- tests: a test that every `type-*.md` named in the recipe exists in the pinned Illustrate range; `validate_skills.py`.

### PR5. Descriptions and a host-aware image verification tier

- what: Rewrite both frontmatter descriptions in third person with what, when and trigger phrases ("Generates the feature CHANGELOG and plain-English feature-details document with inline diagrams, then creates or updates the branch's pull request. Use when asked to 'open the PR', 'update the PR description' or after implementation finishes; never merges."; the review-feedback one with "address review comments", "process reviewer feedback", "resolve the threads"). Make `extension.yml` `provides.commands[].description` and the hook description the same sentence. In `pr-image-embedding.md:26-34` define two tiers: `api` (rendered `body_html` and contents API per pinned commit, both hosts) and `browser` (when a browser tool exists); the receipt records `images_verified: true` plus `image_verification: api|browser`; `stage-pr.md:15` names both.
- effort: S
- tok: [0.00, 0.01]
- time: [0.00, 0.02]
- obs: improved: the receipt says how visuals were verified instead of a bare boolean.
- policy: none.
- pros: fixes catalog routing on both hosts at zero risk; removes an instruction Codex cannot follow without weakening the evidence.
- cons: the receipt gains one field; `check_docs.py --write` regenerates `docs/reference/commands.md`.
- files: `extensions/pr/commands/*.md` frontmatter, `extensions/pr/extension.yml:7,37,40,47`, `extensions/pr/references/pr-image-embedding.md`, `extensions/workflow/skills/workflow/references/stage-pr.md:14-15`, `docs/reference/commands.md`.
- tests: `validate_skills.py` description checks; the B0 harness description columns for `pr`.

### PR6. Guard hook for PR publication

- what: Extend `extensions/workflow/hooks/guard.py` with two PR rules: deny `gh pr create|edit --body-file <f>` when `<f>.lint.json` (or the sibling PR1 writes) is missing or its `body_sha256` differs from the file's hash, in a managed project only (`.specify/workflow.yml` present); deny `gh pr create` when the current branch equals the repository default branch. Delete the three prohibition sentences at `speckit.pr.generate.md:254-256,271`. Both hosts already run the guard (`hooks/hooks.json`).
- effort: S
- tok: [0.01, 0.02]
- time: [0.00, 0.01]
- obs: improved: a refused publish is logged by the host as a hook denial with the reason.
- policy: none (the managed condition is the existing `workflow.yml` presence).
- pros: a rule that must always hold stops relying on prose; standalone use is unaffected.
- cons: Codex users must approve the changed hook hash in `/hooks` (`hosts.py:48`); the guard runs `git` to find the default branch, so it needs a timeout-safe path; a user who publishes with a custom body file name must follow the sibling convention.
- files: `extensions/workflow/hooks/guard.py`, `extensions/workflow/tests/test_guard_hook.py`, `speckit.pr.generate.md`, `extensions/workflow/README.md` hook list.
- tests: `test_guard_hook.py` cases for sha match, missing lint, default branch, unmanaged project allowed.

### PJ1. Claim carries the exact sync command; shrink `speckit.project.sync.md`

- what: `claim` prints `project_sync: {"phase": "open", "command": "<pwsh or bash line> --phase open --summary"}` instead of `true|false` (`workflow.py:3099`, the stage-to-phase map already in `dispatcher-operations.md:48-51`), choosing the twin by host and shell. The command file keeps the phase table, the one invocation line with `--summary`, the precondition sentence and the report line (about 1,000 B); the hook prompts in `extension.yml:38-63` reference the same line. Fix the `pwsh` under a bash fence.
- effort: S
- tok: [0.50, 0.65] per sync point (2,719 B to about 1,000 B, read six times per feature); the managed model need not open the file at all once the claim carries the line
- time: [0.20, 0.40] per sync point (one read fewer of two calls)
- obs: unchanged; `--summary` output (`ok|error|skipped`) is already the dispatcher's contract (`execution-report.md:36-39`).
- policy: none; `project_sync.points` keeps its default.
- pros: the dispatcher stops making the model rediscover a line it already knows; the `--summary` preference becomes the default form.
- cons: touches `workflow.py` (cross-cutting; one-line field change plus a host-shell choice); the hook prompts for unmanaged projects must keep naming the slash command.
- files: `extensions/workflow/scripts/workflow.py:889-891,3099`, `extensions/workflow/skills/workflow/references/dispatcher-operations.md:46-54`, `extensions/project/commands/speckit.project.sync.md`, `extensions/project/extension.yml:38-63`.
- tests: a workflow claim test asserting the command string per host; `test_project_sync_summary.py` unchanged.

### PJ2. `speckit.project.init.md`: drop what the scripts do, fix the memory sentence

- what: Delete lines 20-25 (managed behaviour the scripts implement at `project-init.sh:68-72` and `project-init.ps1:78-82,199,219`), keep the one sentence "finish with `workflow.py doctor --project`", replace step 6 with "owner and project number are in `config.json`; nothing else to record", and shorten step 4's bullet list to what the script prints. 3,445 B to about 2,200 B.
- effort: S
- tok: [0.25, 0.35] of an init run
- time: [0.00, 0.05]
- obs: unchanged; `doctor --project` (`workflow.py:1022-1043`) still validates the written config.
- policy: none.
- pros: removes an instruction that sends the model to edit an undefined memory file; one source for managed behaviour.
- cons: none beyond a README sentence update.
- files: `extensions/project/commands/speckit.project.init.md`, `extensions/project/README.md`, `extensions/project/CHANGELOG.md`.
- tests: `smoke_project_init.py` unchanged; `validate_skills.py`.

### PJ3. Frontmatter descriptions for both project commands

- what: Add YAML frontmatter with a third-person description to `speckit.project.init.md` and `speckit.project.sync.md` (today both render as "Extension command: ..." on both hosts). Init: "Sets up GitHub Project sync once per repository: discovers the board, maps lifecycle phases to its Status columns, chooses required or optional hooks and writes the config. Use when asked to 'connect the project board', 'set up project sync' or before the first managed feature." Sync: "Advances the feature's parent issue on the configured GitHub Project to a lifecycle phase and creates or closes task sub-issues. Use when asked to 'move the card', 'sync the board' or when a lifecycle hook names a phase." Mirror the sentences in `extension.yml:24-27`.
- effort: S
- tok: [0.00, 0.01]
- time: [0.00, 0.00]
- obs: unchanged.
- policy: none.
- pros: restores routing by description on both hosts; under the Codex 8,000-character budget a fallback entry is the first to be shortened.
- cons: `docs/reference/commands.md` regenerates.
- files: `extensions/project/commands/*.md`, `extensions/project/extension.yml:24-27`, `docs/reference/commands.md`.
- tests: `validate_skills.py`; the B0 harness description columns for `project`.

### PJ4. One `project_sync.py` instead of two shell twins

- what: Replace `scripts/bash/project-sync.sh` (374 lines, needs `jq`) and `scripts/powershell/project-sync.ps1` (413 lines) with one stdlib Python script that keeps the `--phase`, `--dry-run`, `--no-sub-issues`, `--force`, `--json`, `--summary` contract and the GraphQL-to-REST fallback; do the same for init later. `python` is already required by Workflow and by `pr` (`extensions/pr/extension.yml:26-27`). Host divergence (shell choice, `jq`) disappears.
- effort: L
- tok: [0.00, 0.02] (the command line gets shorter; no instruction bytes otherwise)
- time: [0.00, 0.05]
- obs: unchanged; the `--summary` line keeps its exact shape (`test_project_sync_summary.py`).
- policy: none.
- pros: halves the maintenance surface (1,250 lines to about 450), ends "PowerShell primary, bash twin" prose, same behaviour on every host and OS.
- cons: a rewrite with GitHub calls to mock; standalone users without `python` lose the extension (none are known: Spec Kit itself is Python); not a token saving, so only worth it if the user wants host convergence this round.
- files: `extensions/project/scripts/project_sync.py` (new), both twins deleted, `speckit.project.sync.md`, `extension.yml`, `README.md`, `extensions/workflow/tests/test_project_sync_summary.py`, `docs/extensions/project.md`.
- tests: port `test_project_sync_summary.py`; add a mocked `gh` fixture for create, advance, no-regress, sub-issue close, in-review on open PR.
