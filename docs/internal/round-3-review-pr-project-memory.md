# Round 3 review: pr, project and memory (stream R4, read-only)

Measured on `D:\Projects\Personal\sanduq-round3` (branch `feat/round-3`) on 2026-10-19 with `wc`, `grep`,
`sed`, `docs/internal/benchmarks/round-3-before-instructions.md` (bd4a361) and two test runs: `pr`
15 tests in 0.38 s (`python -m unittest discover -s extensions/pr/tests -q`), `memory` 191 tests in
717 s (`uv run --no-project --python 3.11 --with pyyaml python -m unittest discover -s extensions/memory/tests`).
Line references are to the files named. Nothing was changed except this file.

## Summary

1. Round 2 cut the PR stage from about 93 KB to 38.2 KB of instructions and step 6 from about nine calls to one, but `pr_publish.py` copies `<Feature>-Explained.md` into the PR body unchanged (`pr_publish.py:114-115`), so the relative image paths the document uses (`pr-image-embedding.md:43`) break in the PR body. The model still pins image URLs by hand and runs the `api` verification tier itself, with 3+N calls.
2. `speckit.pr.review-feedback` is unchanged at 5,518 B. A run with 10 comments in 6 threads takes about 35 tool calls; 8 of them are the gather step, which a script could do in one call, and its GraphQL query reads at most 100 threads and 50 comments per thread without paging (`review-feedback.md:49-51`).
3. `project_sync.py` reintroduces the remote-parsing bug that Workflow fixed in round 2 (finding N1, `workflow.py:224-240`). It uses an ad-hoc regex (`project_sync.py:371`, which rejects dotted repository names and ports) and a case-sensitive binding compare (`:156`). Init is still a 206-line bash and 257-line PowerShell pair: it needs `jq`, has three interactive prompts per shell, and is told to start with an interactive `gh auth refresh` (`init.md:22`).
4. Memory: run.md step 3 is a redundant call. `verify` and `prepare` both run `preflight` first (`archive.py:465,686`), and `preflight` raises instead of returning `ok: false` (`:436`). Memory's lifecycle hooks are not in Workflow's owned set (`reconcile.py:11`), while `memory_handoff.py:59,121` dispatches the same `session` and `prepare` commands, so a managed feature likely runs `pending` two or three times before each specify.
5. Nine options, PM1 to PM9: five S (PM3, PM4, PM6, PM7, PM8) and four M (PM1, PM2, PM5, PM9). None changes a receipt, gate, evidence file or GitHub decision, and none adds a policy key. An `archive.py` split and a shared git helper are considered and not proposed (see Lens 7).

Two corrections to the brief. Memory's prohibition density is 1.17 per 100 words, which ranks third after workflow (1.28) and scope (1.22) (benchmark summary table). Per file it is high: session 1.97, run 1.78, prepare 1.77. The init pair is 206 + 257 = 463 lines in total, not 460 lines each.

## Lens 1: model work a script does or could do

**What round 2 reduced, as an agent experiences it.** Counts are reads plus tool calls per run, from the command text.

| Run | Round 2 before | Now | Remaining model work a script could do |
| --- | --- | --- | --- |
| Managed PR stage, one diagram, QA and manual current | about 93 KB read; step 6 about 9 calls | 38,194 B read (stage-pr 4,504 inline in the claim; command 11,058; recipe 1,694; type-index 6,530; median `type-*.md` 6,254; layout-budget 4,647; image-embedding 3,507); about 32 calls | Pinning image URLs and the `api` verification tier (3+N calls); the `feature.json` read the claim already answers |
| Same, both preflights stale | about 93 KB | 51,573 B (adds assure.document 9,458 and user-manual.update 3,921) | none new |
| Project sync point (managed) | 2 calls (read command 2,719 B, run) | 1 call; the claim prints the line (`workflow.py:905-910`) | none for the model; inside the script, 1 of 5-6 `gh` calls is an unconditional rate-limit probe (`project_sync.py:411`) |
| Review feedback, 10 comments in 6 threads | 5,518 B, about 35 calls | unchanged | gather (8 calls: auth, PR resolve, metadata, diff, three REST lists, GraphQL threads) plus the join and filter; reply and resolve loops (one call per item) |
| Memory archive, one feature, format 2, small | 21,150 B run.md plus later rereads | 14,223 B (run 4,620; candidate-v2 6,854; review-and-publish 2,749); about 24 calls | step 3 `preflight` (a duplicate of what `verify` runs first) |
| Project init | 3,445 B | 2,279 B, about 7 calls | the `gh auth refresh` step (the script checks the scope itself, `project-init.sh:74`); the shell choice (`init.md:27-36`) |

The 4.3.0 CHANGELOG gives "22.7 KB of instructions" for one PR run. That figure covers the command, recipe, image rules and one type reference only. The recipe also tells the model to read `type-index.md` (6,530 B, `pr-diagram-recipe.md:8`) and `layout-budget.md` (4,647 B for one row, `:21-22`), and the claim inlines `stage-pr.md` (4,504 B). The measured figure is 38.2 KB.

- **Image pinning and verification.** `pr-image-embedding.md:16-30` requires commit-pinned `blob/<sha>/<path>?raw=true` URLs in the PR body, followed by the rendered `body_html` and a contents-API call per path. `pr_publish.py` already knows the head and the repository and already calls `gh`, but it neither rewrites nor verifies images (no image test in `tests/test_pr_publish.py`, cases at lines 83-157). The model has two choices. It can write absolute URLs into the repository document, which ties repository Markdown to a remote commit. Or it can edit the body after publishing, which breaks the lint sha that `PR_SENT_BODY_SHA_MISMATCH` checks.
- **Review gather.** All of `review-feedback.md:31-60` is deterministic: one GraphQL query can return threads (`isResolved`, `isOutdated`), comments, reviews and the PR author, and the "PR-author, resolved, outdated, LGTM or emoji-only" filter (`:59-60`) is string work. Replies (`:111-112`) and thread resolution (`:134-136`) are one call per item.
- **Managed hook duplication (memory).** `memory_handoff.py:68` calls `pending` and returns `speckit.memory.session` or `speckit.memory.prepare` actions (`:59,121`). The memory hooks `before_specify: session` and `after_implement: prepare` stay enabled in managed projects because `reconcile.py:11` `OWNED` and `workflow.py:1258` do not list `memory`. The SESSION block also runs `pending` at session start (`install.py:29`). Verify before acting: `presets/` has no `before_specify` text except `scope-gate/commands/specify-gate.md`, so whether the managed specify fires extension hooks needs one run to confirm.

## Lens 2: repeated text

| Block | Copy A | Copy B | Note |
| --- | --- | --- | --- |
| `pending` at session start, gate before new work, lock rules | `session.md:7-25` | `install.py:28-34` SESSION block; `memory-lifecycle.md:31-43` | three wordings, read at each specify in managed projects |
| Preflight-then-verify | `run.md:27-30` (step 3) | `archive.py:465` (`verify` runs `preflight`) | the prose step is a duplicate call |
| Default-branch rule | `pr_publish.py:94-98` (origin/HEAD, else `gh repo view`) | `pr_changelog.py:70` (origin/HEAD, else `main`); `workflow/hooks/guard.py:57` (origin/HEAD, else allow) | three behaviours for one fact |
| GitHub remote parsing | `project_sync.py:371` (regex) | `workflow.py:236-240` (`normalize_remote_url`, case rule `same_github_repository`) | the copy in project repeats a fixed bug |
| PR dependency ranges | `pr/extension.yml:15-24` | `pr/dependencies.yml:3-13` | two sources; `deps.py` reads the second |
| Guard tokenizer and `command_text` | `memory/hooks/guard.py:45-69` | `workflow/hooks/guard.py:84-108` | about 25 identical lines; the two packages are installed separately (see Lens 7) |
| Host registration constants | `memory/scripts/install.py:24` `HOOK_FILES` | `workflow/scripts/hosts.py:45` | same dict; memory writes its own wrappers for `.agents`, `.claude` and `.github` (`install.py:190-229`) |

## Lens 3: large rereads

- `layout-budget.md` (4,647 B) is read for one row (`pr-diagram-recipe.md:21-22`). This is the R5 Illustrate lens: if the type references carry their own budget row, the recipe line goes away. Count it once, with IP.
- `pr-image-embedding.md` (3,507 B) carries history and maintenance text the model never acts on. `:5-6` reads "unchanged from the command's previous inline instructions (B9 moved them…)" and `:43-44` reads "Apply this same contract to every generated agent skill… never maintain divergent installed edits".
- In managed projects, memory's hook bodies `session.md` (2,176 B), `impact.md` (2,573 B) and `prepare.md` (1,723 B) are reread at every specify, analyze and implement, on top of `memory-lifecycle.md` (3,818 B), which covers the same transitions.
- Review feedback reads five raw API payloads (`:34-56`) to keep only the unresolved, substantive rows.

## Lens 4: descriptions and catalog slots

All 11 descriptions pass the round-2 rules (benchmark: 0/2, 0/2, 0/7 failing). Catalog cost: pr 276, project 280, memory 983 characters.

- Memory has seven entries of 138 to 143 characters each. Three spend about 24 characters on wiring a user never types: "(after_implement hook)", "(before_specify hook)", "(before_analyze hook)" (`extension.yml:28,34,40`).
- Merging is not recommended. `enable` is the owner's policy-hash review and must come after the policy is committed (`init.md:17-18`, `enable.md:14-19`). `session` acts: it runs automatic archives (`session.md:31-35`). `status` is read-only (`status.md:7-13`). Merging any two would mix an approval gate or a side effect into a read-only entry.
- Hiding: `prepare` and `session` are `user-invocable: false` on Claude only (`install.py:220`). Codex lists all seven. No Codex hide mechanism exists in this repository (`grep -rn "allow_implicit\|openai.yaml"` finds nothing in `hosts.py` or `docs/reference`), so the Codex budget pays 983 characters until shorter text lands.

## Lens 5: rules a hook could enforce

- `workflow/hooks/guard.py:67` checks only `--body-file|-F`. In a managed project, `gh pr edit 12 --body "…"` or `gh pr create -b "…"` publishes an unlinted body that the guard allows, and the mismatch surfaces only at receipt time (`PR_SENT_BODY_SHA_MISMATCH`). `test_guard_hook.py:99-118` has no `--body` case.
- `review-feedback.md:99-100`, "Do not modify files, post replies, commit, push, or resolve threads before the user approves", depends on an approval the host does not record, so it stays prose (unchanged from round 2).
- The memory guard is opt-in (`archive-policy.json` `guard_hooks: false`) and denies Write or Edit under `specs/memory/` but not shell writes (`guard.py:72-83`). That is acceptable: finalize's `memory_result_guard` refuses drift anyway (round-2 notes, S6).

## Lens 6: Claude Code versus Codex

- Project init: `read -r -p` appears 3 times in `project-init.sh` and `Read-Host` 3 times in `project-init.ps1`. The command's example lines omit `--non-interactive` (`init.md:31,35`). Agent shell tools on both hosts have no interactive stdin: the bash `read` returns EOF and `set -e` exits (`project-init.sh:9,92,130,172`). Step 1, `gh auth refresh -h github.com -s project,read:project` (`init.md:22`), starts a device flow the agent cannot finish.
- Shell choice: init still says "PowerShell on Windows, bash elsewhere" (`init.md:27`), and the twins differ (`bash` calls `gh project view` twice, `:98-99`; PowerShell once, `:119`).
- Hook prompts hard-code the Claude spelling `/speckit-project-sync <phase>` (`project/extension.yml:123,128,133,138,143,148`). Codex invokes `$speckit-project-sync`. Memory solved the same problem with a `SKILL_NAMES` line (`install.py:27`).
- Memory hides hook-only commands on Claude only (`install.py:220`). Codex shows seven entries.
- Guards: Workflow's matcher is `Bash`, and memory's is `Bash|Write|Edit|MultiEdit|apply_patch`. Both guards resolve the project root from `CLAUDE_PROJECT_DIR`, else the payload `cwd`, else `.`. Codex therefore depends on `cwd` in the payload (`memory/hooks/guard.py:93`; Workflow's hook command line uses `CLAUDE_PROJECT_DIR or '.'`, `workflow/hooks/hooks.json`).

## Lens 7: code refactoring, dead code, tests

- **`archive.py`:** 1,498 lines. The `Archive` class covers lines 81-1268 (52 methods; finalize 123 lines, materialize 95, prepare 83, preflight 71), and `main` is 200 lines (1298-1498) of `if/elif` over 22 verbs. `main` contains business logic: the `--all-completed` selection loop (`:1430-1450`) belongs in `Archive`. No agent reads this file (the commands call it), so a split saves no tokens. A refactor would have to keep the 191-test suite green, and that suite takes 717 s per run here. **Not proposed** beyond moving the selection loop, which is listed under PM7.
- **Dead code:** a scan of every `def` in `memory`, `pr` and `project` scripts and hooks against all references found no function referenced only at its definition. One dead field exists: `preflight` returns `ok: True` on every path that returns (`archive.py:436`), yet `run.md:28` says to "continue when `data.ok` is true".
- **Duplicated git helpers:** there are seven wrappers with different contracts. `workflow.py:216` returns text and raises `WorkflowError`. `git_state.py:52` returns bytes and takes `ok` codes and stdin. `project_sync.py:47` returns `''` on failure, with no timeout. `pr_publish.py:45` has a 120 s timeout and raises `Failure(3)`. `pr_changelog.py:34` has a 60 s timeout and returns `None`. The guards have 5 s timeouts (`workflow/hooks/guard.py:46`, `memory/hooks/guard.py:35`). Sharing a four-line wrapper across separately installed extensions costs a packaging dependency for no behaviour gain. **Not proposed.** What is worth sharing is *semantics*: the default-branch rule and remote parsing (PM3, PM4).
- **Project shell pair against `project_sync.py`:** sync is one stdlib script (472 lines). Init is 463 lines of shell plus `jq`, smoke-tested per shell by its own CI job (`ci.yml:347-366`, `smoke_project_init.py:41,69`). The pair is the last `jq` dependency in the three extensions.
- **Tests and CI:** `project` is not in `SUITES`. A change under `extensions/project/**` falls to the "other" branch and runs all eight suites on two OSes (`.github/scripts/ci_matrix.py:19,56-59`), while project's tests live in `extensions/workflow/tests/test_project_sync_summary.py`. The memory suite averages 3.75 s per test: each `ArchiveIntegrationTests.setUp` makes a fresh repository with 8 `git` subprocesses before the test's own archive flow (`test_archive.py:26-47`; 110 `git`/`subprocess` call sites in that file). `review-feedback` has no test.

## Defects

| Defect | Effect | Where |
| --- | --- | --- |
| The PR body copies Explained.md unchanged | Relative image paths do not resolve in a PR body; the model must hand-pin URLs or edit after the lint | `pr_publish.py:114-115`; `pr-image-embedding.md:16-19,43` |
| Any `gh pr view` failure is read as "no PR" | An unauthenticated or offline run pushes the branch (`:146`) before `gh pr create` fails | `pr_publish.py:118-119,145-148` |
| A start marker without an end marker appends a second section | Duplicate PR section after a hand edit | `pr_publish.py:60-64` |
| Three default-branch rules | The changelog uses `main..HEAD` on a `master` repository; the guard allows when origin/HEAD is unset | `pr_changelog.py:70`; `pr_publish.py:94-98`; `workflow/hooks/guard.py:57` |
| The guard skips inline `--body`/`-b` | An unlinted body is published in a managed project and refused only after publication | `workflow/hooks/guard.py:67` |
| Review threads are not paged | Threads past 100 or comments past 50 are silently skipped | `review-feedback.md:49-51` |
| The CHANGELOG understates the PR read set | It states 22.7 KB; the measured figure is 38.2 KB | `pr/CHANGELOG.md` 4.3.0; `pr-diagram-recipe.md:8,21-22` |
| Runtime-loaded history and maintenance sentences | About 400 B of noise per visual PR | `pr-image-embedding.md:5-6,43-44` |
| Remote regex and case-sensitive binding | `acme/my.app` becomes `acme/my`; a case difference fails with "Managed parent binding mismatch" at every sync | `project_sync.py:156,371`; fixed for Workflow at `workflow.py:224-240` |
| The scope check matches a substring | A `read:project`-only token passes, and the writes fail mid-run | `project_sync.py:368`; `project-init.sh:74` |
| No subprocess timeout in sync | A hung `gh` blocks the stage | `project_sync.py:40,48` |
| Init prompts and `gh auth refresh` are interactive | Agent runs exit or hang on multi-project owners, missing columns or hook mode | `init.md:22,31,35`; `project-init.sh:92,130,172`; `project-init.ps1` (3 `Read-Host`) |
| Hook prompts use Claude spelling | A Codex user is told a command name that host does not use | `project/extension.yml:123-148` |
| The claim emits a sync command without checking the script exists | Without the project extension, the printed `python …project_sync.py` fails, and the prose asks the model to check "when configured" | `workflow.py:905-910`; `dispatcher-operations.md:51` |
| Redundant preflight step and constant `ok` | One wasted call per feature; prose implies an `ok: false` path that does not exist | `run.md:27-30`; `archive.py:436,465,686` |
| Memory lifecycle hooks are not dispatcher-owned | Likely double `pending`/`prepare` per managed feature (to confirm) | `reconcile.py:11`; `workflow.py:1258`; `memory_handoff.py:59,68,121` |
| Project changes run every CI suite | 16 matrix jobs for a project-only change | `ci_matrix.py:19,56-59` |
| PR dependency ranges in two files | The two can drift | `pr/extension.yml:15-24`; `pr/dependencies.yml:3-13` |

## Options

Derivation, one line each. `tok` = bytes removed from what the run reads, over the run's measured set:
PR 38,194 B; review feedback 5,518 B plus payloads; project init 2,279 B; memory archive 14,223 B; memory
managed lifecycle reads 6,472 B (session 2,176 + impact 2,573 + prepare 1,723); catalog where stated.
`time` = tool calls removed, over the run's count: PR about 32, review feedback about 35, sync point
5-6 `gh` calls, init about 7, archive about 24, memory hooks per managed feature 6-9.

### PM1. `pr_publish.py`: pinned image URLs and the `api` verification tier

- what: Add `--pin-images` to `extensions/pr/scripts/pr_publish.py`. It rewrites relative image links in the spliced section to `https://github.com/<repo>/blob/<head-sha>/<path>?raw=true`, after checking each path exists at the pushed head (`git cat-file -e`, and the head on the remote). It does this before writing `pr-body.md`, so the lint sha covers the final bytes. Add `--verify-images` (or run it by default after publication): fetch `body_html` with `application/vnd.github.full+json`, reconcile it against the image inventory, call the contents API per path and pinned sha, and print `images_verified`, `image_verification: "api"` and a per-image list into the receipt fragment. `Explained.md` keeps relative paths. `pr-image-embedding.md` shrinks to the browser tier, the "no raw.githubusercontent/tokens/data URLs" rules and the failure report (3,507 B to about 1,300 B), and drops lines 5-6 and 43-44.
- effort: M
- tok: [0.06, 0.12]
- time: [0.10, 0.18]
- obs: improved. A per-image verification result sits beside the lint receipt instead of a bare boolean; `workflow.py` recomputation is unchanged.
- policy: none.
- pros: fixes the broken-image path for every PR with visuals, keeps repository Markdown portable, and gives one verification method on both hosts.
- cons: two more `gh api` shapes to mock; private-repository rendering still needs a `browser`-tier check where a host offers one; images must be committed before publication (as today).
- files: `extensions/pr/scripts/pr_publish.py`, `extensions/pr/references/pr-image-embedding.md`, `extensions/pr/commands/speckit.pr.generate.md:112-116,160-177`, `extensions/workflow/skills/workflow/references/stage-pr.md:14-17` (R1 owns it; one sentence), `extensions/pr/README.md`, CHANGELOG.
- tests: `tests/test_pr_publish.py`: relative-to-pinned rewrite; a missing path at head exits 2; the sha equals the rewritten file; verification with mocked `body_html` and contents responses; one image missing yields `images_verified: false` and exit 3.

### PM2. `pr_feedback.py`: gather, reply and resolve for review feedback

- what: Add `extensions/pr/scripts/pr_feedback.py` with three verbs. `gather` checks `gh auth`, resolves the PR from a number, URL, `owner/repo#n` or the current branch, runs one paged GraphQL query for threads, comments and reviews plus the issue comments, filters resolved, outdated, author-only and chatter rows, and prints compact JSON per thread: thread id, comment database id, author, path, line and body. `reply --file plan.json` posts the drafted replies. `resolve --file plan.json` resolves the listed threads only after it confirms the head contains the pushed commit. Steps 1, 5 (reply part) and 7.2 of `speckit.pr.review-feedback.md` become one line each; the untrusted-content section, the classification and the approval gate stay prose (5,518 B to about 2,800 B).
- effort: M
- tok: [0.30, 0.50]
- time: [0.25, 0.40]
- obs: improved. `gather` output can be saved as the plan's input, and the counts in the final report come from it.
- policy: none.
- pros: removes the most repetitive calls in the extension, fixes unpaged threads, and gives the same behaviour on both hosts.
- cons: a new script with GraphQL mocks; the approval gate still relies on the model; the reviewer-content trust rules must stay verbatim.
- files: `extensions/pr/scripts/pr_feedback.py` (new), `extensions/pr/commands/speckit.pr.review-feedback.md`, `extensions/pr/README.md`, CHANGELOG.
- tests: `extensions/pr/tests/test_pr_feedback.py`: identifier forms, paging across two pages, filters, reply payload, resolve refused before push.

### PM3. PR script and guard hardening, one default-branch rule

- what: In `pr_publish.py`, run `gh auth status` before any side effect and treat only "no pull requests found" from `gh pr view` as "create" (`:118-119`); refuse a start marker without an end marker with exit 2 (`:60-64`); take the URL `gh pr create` prints instead of a second `gh pr view` (`:151`). In `pr_changelog.py:70`, use the same default-branch resolution (origin/HEAD, else `gh repo view`, else leave the commits line out) instead of `main`. In `workflow/hooks/guard.py:67`, extend the managed rule to `--body`/`-b` (deny an inline body in a managed project and name `pr_publish.py`). In `speckit.pr.generate.md` step 1, say a managed claim's `feature` is the directory (skip `feature.json`). Make `dependencies.yml` the only version source, or have a test assert both files agree.
- effort: S
- tok: [0.00, 0.01]
- time: [0.03, 0.06]
- obs: improved. No push happens before auth is known; inline bodies are refused before publication rather than after.
- policy: none.
- pros: closes two real failure paths and one guard gap at small cost.
- cons: the guard change touches R1's file and changes its hash (Codex users re-approve in `/hooks`, `hosts.py:48`).
- files: `extensions/pr/scripts/pr_publish.py`, `extensions/pr/scripts/pr_changelog.py`, `extensions/pr/commands/speckit.pr.generate.md:51-57`, `extensions/workflow/hooks/guard.py`, `extensions/workflow/tests/test_guard_hook.py`, `extensions/pr/dependencies.yml` or a new consistency test.
- tests: `test_pr_publish.py` auth-failure case (no `git push` call recorded) and unmatched-marker case; `test_pr_changelog.py` with no origin/HEAD; `test_guard_hook.py` `--body`/`-b` cases.

### PM4. `project_sync.py` correctness and one probe fewer

- what: Parse the remote with Workflow's `normalize_remote_url` when Workflow is installed (import by path, as `pr_publish.py:69-75` does), else with a stdlib port of it. Compare the bound repository case-insensitively (`:156`), and require the `project` scope as a token in the `Token scopes` line, not as a substring (`:368`). Give `gh_raw` and `git` a 120 s timeout that maps to `error exit=1 reason=timeout` (`:40,48`), and make a missing `git` a `skipped` instead of an error. Delete the unconditional `self.use_rest()` probe (`:411`); `call()` already switches to REST on a failed GraphQL call (`:110`). In `workflow.py:905-910` (R1), print `false` when the script is absent, so `dispatcher-operations.md:51` loses its "when configured" check.
- effort: S
- tok: [0.00, 0.01]
- time: [0.15, 0.20] (one of 5-6 `gh` calls per sync point; the model's own call count is unchanged)
- obs: improved. Dotted or case-differing repositories sync instead of erroring, and a hang becomes a reported error.
- policy: none; `project_sync.points` keeps its default.
- pros: removes a known-bad regex that Workflow already retired; small diff.
- cons: importing Workflow's function couples the two packages (with a fallback copy); the probe removal means the first rate-limited GraphQL call costs one failed request.
- files: `extensions/project/scripts/project_sync.py`, `extensions/project/scripts/bash/project-init.sh:74` and `powershell/project-init.ps1` (the scope check), `extensions/workflow/scripts/workflow.py:905-910`, `extensions/workflow/tests/test_project_sync_summary.py`.
- tests: summary tests for `acme/my.app`, `ssh://git@github.com:443/…`, a case-differing binding, a read-only scope, a timed-out `gh` and the absence of a rate-limit call on the happy path.

### PM5. `project_init.py`: one init that an agent can run

- what: Replace `scripts/bash/project-init.sh` and `scripts/powershell/project-init.ps1` (463 lines, `jq`) with stdlib `extensions/project/scripts/project_init.py`, keeping the flags and the `config.json` shape. It never prompts. When a choice is needed (several projects, a missing column, no hook mode), it exits 4 with JSON naming `needs` and the options. The command asks the user and reruns with `--number`, `--auto-create-columns` or `--hooks-mode`. A missing `project` scope is reported with the refresh command for the user to run, which replaces step 1. `speckit.project.init.md` becomes one invocation, the exit-4 loop, doctor and dry-run (2,279 B to about 1,400 B). The CI `project-init` matrix by shell (`ci.yml:347-366`) becomes one Python job, and `smoke_project_init.py` drives it.
- effort: M
- tok: [0.30, 0.40]
- time: [0.15, 0.30]
- obs: unchanged. The same config and the same `doctor --project` check (`workflow.py:1022-1048`).
- policy: none.
- pros: ends the last shell pair and `jq` in these extensions, gives identical behaviour on both hosts, and removes an interactive auth step from agent runs.
- cons: a rewrite with `gh project` mocks; existing users of `project-init.sh/.ps1` need a CHANGELOG migration line (the files can stay one release as stubs that call Python).
- files: `extensions/project/scripts/project_init.py` (new), both shell scripts (deleted or stubbed), `extensions/project/commands/speckit.project.init.md`, `extensions/project/README.md`, `extensions/scripts/smoke_project_init.py`, `.github/workflows/ci.yml:347-366`, `docs/extensions/project.md`, CHANGELOG.
- tests: a new `extensions/project/tests/test_project_init.py` (single project, multi-project exit 4, fuzzy column match, auto-create, managed defaults from `workflow.py project-defaults`, dry run writes nothing); the smoke script on both OSes.

### PM6. Managed projects: the dispatcher owns memory's session and prepare hooks

- what: First confirm with one managed specify and one implement run that `before_specify: speckit.memory.session` and `after_implement: speckit.memory.prepare` fire alongside `workflow.py memory-handoff`. If they do, add those two memory entries (not `impact`) to the managed set in `reconcile.py:11`/`:35` and `workflow.py:1258`, so `reconcile --apply` disables them with the existing backup and restore journal, and `memory-handoff` stays the single path. In memory, trim `session.md` to what `memory-handoff` does not return (the stale-lock rule and the processing loop), and point the SESSION block's session-start `pending` to the same text.
- effort: S (if confirmed); otherwise drop the option
- tok: [0.30, 0.60] of memory's managed lifecycle reads
- time: [0.30, 0.50] of memory calls per managed feature (`pending` once per transition, one `prepare` path)
- obs: unchanged. The handoff already records `pending` results and actions; unmanaged projects keep their hooks.
- policy: none.
- pros: one owner per transition, as Workflow already does for assure, user-manual and project.
- cons: touches R1's files; needs the confirmation run; `restore` must bring the hooks back unchanged on uninstall.
- files: `extensions/workflow/scripts/reconcile.py`, `extensions/workflow/scripts/workflow.py:1258`, `extensions/memory/commands/session.md`, `extensions/memory/scripts/install.py:28-34`, `extensions/workflow/skills/workflow/references/memory-lifecycle.md`.
- tests: a reconcile test that disables and restores the two memory entries; `test_install.py` SESSION facts updated; a workflow doctor test with no `DUPLICATE_STAGE_OWNER` for memory.

### PM7. Memory: drop the duplicate preflight and the constant `ok`

- what: Delete `run.md` step 3 and renumber, because `verify` runs `preflight` before its checks (`archive.py:465`) and `prepare` runs it again (`:686`). Name what step 3 gave the model, the `repair-required` references, as a journal field already read in step 6. Make `queue` call `preflight` itself, so `prepare.md` step 4 goes too. Remove `ok` from the `preflight` result, or document it as always true (`:436`). Move the `--all-completed` selection loop from `main` (`:1430-1450`) into `Archive.select_completed()` with a test.
- effort: S
- tok: [0.02, 0.04] of an archive run; [0.15, 0.25] of the prepare hook
- time: [0.04, 0.08] of an archive run; [0.25, 0.33] of the prepare hook (1 of 3-4 calls)
- obs: unchanged. The same errors are raised by the same guards; the journal still records references.
- policy: none.
- pros: one fewer call per archived feature and per queued feature; removes misleading prose.
- cons: a model that wanted a read-only early check loses it for `run` (`verify` raises the same error before running checks, so nothing runs first); the queue change makes `queue` slower by one preflight.
- files: `extensions/memory/commands/run.md`, `extensions/memory/commands/prepare.md`, `extensions/memory/scripts/archive.py`, `extensions/memory/tests/test_archive.py`, CHANGELOG.
- tests: `queue` refuses a missing declared input; `select_completed` returns the same skipped list as today; `test_install.py` reference checks unchanged.

### PM8. Memory catalog: shorter descriptions, no merges

- what: Rewrite the seven frontmatter descriptions to 90-105 characters, removing the "(… hook)" wiring text and keeping what, when and one trigger phrase. For example: `run` "Archives verified features into project memory through a checkpoint, a reviewed delta and a scoped commit. Use for 'archive the feature'." `install.py` copies them as it does today (ME2). Keep seven entries: the reasons not to merge are in Lens 4. Record in `docs/extensions/memory.md` that Codex lists all seven until it offers a non-implicit flag.
- effort: S
- tok: catalog [0.25, 0.30] (983 to about 700 characters on both hosts); per-run 0
- time: [0.00, 0.00]
- obs: unchanged.
- policy: none.
- pros: the cheapest catalog saving in the three extensions, paid by every session on Codex.
- cons: `check_docs.py --write` regenerates `docs/reference/commands.md`; trigger phrases must stay distinct from Workflow's.
- files: `extensions/memory/commands/*.md` frontmatter, `extensions/memory/extension.yml:25-43`, `docs/reference/commands.md`.
- tests: `validate_skills.py`; `test_install.py` description equality; the benchmark catalog column for `memory`.

### PM9. Test and CI cost for memory and project

- what: (a) Build the memory test repository once per class (`setUpClass`: `git init`, config, the initial commit) and copy the directory per test with `shutil.copytree`, instead of 8 `git` subprocesses per `setUp` (`test_archive.py:26-47`); apply the same to `test_archive_v2.py` and `test_orchestration.py`. (b) Move `extensions/workflow/tests/test_project_sync_summary.py` to `extensions/project/tests/`, add `project` to `SUITES`, and map `project -> workflow` in `DEPENDENTS` (`ci_matrix.py:19,34-35`), so a project-only change runs 4 jobs instead of 16.
- effort: M (a), S (b)
- tok: [0.00, 0.00]
- time: memory suite [0.20, 0.40] of 717 s (estimate; measure on one class first); CI for project changes [0.70, 0.75] of jobs
- obs: unchanged. The same assertions; per-test isolation is kept by copying.
- policy: none.
- pros: makes later memory refactors (including any future `archive.py` split) affordable to verify.
- cons: a copied `.git` must not share hooks or locks between tests; the CI change is in R6 territory (coordinate).
- files: `extensions/memory/tests/test_archive.py`, `test_archive_v2.py`, `test_orchestration.py`, `.github/scripts/ci_matrix.py`, `extensions/project/tests/` (new home), `.github/workflows/ci.yml` (suite list if hard-coded).
- tests: the suites themselves; `ci_matrix` tests for a project-only path.

## Considered and not proposed

- **Split `archive.py`:** no agent-facing gain (no command reads it), and verification costs 717 s per suite run today. Revisit after PM9.
- **One shared git helper:** seven wrappers with different contracts and timeouts across separately installed packages. Share the default-branch and remote semantics instead (PM3, PM4).
- **One guard hook for memory and Workflow:** it would save one Python start per tool call when both are on, but memory's guard is opt-in and ships without Workflow. Keep two guards.
- **Merge memory `status` into `session` or `enable` into `init`:** this would mix a read-only entry with side effects or an owner gate (Lens 4).
