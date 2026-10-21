# Round 4 live run (L-RUN): the D3 Memory hook gate

Date 2026-10-21. Worktree HEAD `788cd252de07db65ee21f41bd8e410c118796393`. The scratch folder holds all
evidence: `C:\Users\sabus\AppData\Local\Temp\claude\d--Projects-Personal-sanduq\0a19d7d1-3e58-4f33-890f-c489950eba24\scratchpad\live-run`
(`transcripts/`, `extensions.*.yml`, `install-*.json`, `memory-*.json`, `status-final.json`, `tools/analyze.py`).

**Verdict: FAIL. The gate is not met.** The run stopped at Specify on a Sanduq bug in Scope and Workflow
(B1 below), before Implement, so `complete`'s queueing and the prepare side of D3 were never exercised. The parts
that did run behaved as D3 intends. Reconcile disabled both Memory hooks. Each claim ran the session handoff
itself. No `speckit.memory.session` or `speckit.memory.prepare` ran.

## Setup

- Packages: `extensions/scripts/package.py` for illustrate, project, scope, pr, assure, user-manual, progress,
  memory and workflow, extracted to `packages/`. The workflow package carries the presets workflow, scope-gate and
  scope-brainstorm. Archive hashes are in `build.json`.
- Spec Kit `specify-cli @ git+https://github.com/github/spec-kit.git@8147943512404afb9d99c6252cb9bf84369fd0b0`
  (1.0.11), installed with `uv tool install` into a scratch `UV_TOOL_DIR`.
- Repository: private `samykabu/sanduq-r4-live`, containing `greet.py`, `test_greet.py` and a README. Main holds
  the initial commit plus `0fedec7` (the installed Spec Kit, Workflow and Memory).
- Commands run in the clone, in order:
  1. `specify init --here --force --ignore-agent-tools --integration claude`.
  2. `specify extension add --dev packages/workflow`.
  3. `workflow.py init --qa off --manual off --delegate off --gate-mode disabled --decision-owner samykabu`, then
     `profiles: {enabled: true}` added so a lite tier is possible.
  4. `specify extension add --dev packages/memory` and `memory/scripts/install.py --target-branch main`.
  5. The Memory policy got the check `tests` (`{python} -m unittest`, covering `greet.py` and `test_greet.py`) and
     `default_checks: [tests]`.
  6. `install.py --packages <scratch>/packages`, previewed first, then `--apply`.
  7. After the commit: `archive.py policy`, then `archive.py enable --approve-hash 26e84c7b…36ba`.
- Project board: Scope cannot run without one. `Scope.__init__` requires `.specify/extensions/project/config.json`
  with a `projectId` ("Run /speckit-project-init first."), so turning project sync off in the policy does not
  remove the need. I created user Project **#12 "sanduq-r4-live"**
  (https://github.com/users/samykabu/projects/12), linked it to the repository, and ran `project-init.ps1` with
  `-HooksMode required`. Its Status options were then set to Backlog, Todo, Feature Specification, Need
  Clarifications, Ready, In Progress, In review and Done, and `scope.statuses: {In progress: In Progress}` was added
  to the policy. `doctor --project` then returned `ok: true` (see B3 for why this was needed).
- Host: Claude Code 2.1.306, run as
  `claude -p "<cmd>" --output-format stream-json --verbose --permission-mode bypassPermissions --strict-mcp-config`
  with the parent's `CLAUDE*` variables unset. `--strict-mcp-config` only skips MCP servers; user settings and
  plugins load as normal.

## Hook entries (`.specify/extensions.yml`)

After Memory init (`extensions.after-memory-init.yml`): `after_implement: speckit.memory.prepare enabled: true`,
`before_specify: speckit.memory.session enabled: true`, and `speckit.memory.impact` enabled under both
`before_specify` and `before_analyze`.

After the Workflow install's reconcile (`extensions.after-install.yml`):

```yaml
  after_implement:
  - extension: memory
    command: speckit.memory.prepare
    enabled: false
  before_specify:
  - extension: memory
    command: speckit.memory.session
    enabled: false
  - extension: memory
    command: speckit.memory.impact
    enabled: true
```

`impact` stays enabled under `before_specify` and `before_analyze`, as planned. Both entries were still
`enabled: false` after the two `project-init` runs ("preserving reconciled hook entries"). `settings` came before
`hooks` in this file, so the S-WF `add_hook` key-swallow case did not arise.

## Commands and transcripts

| # | Transcript | Prompt | Tool calls | Turns | Time | Cost | Tokens: input / cache write / cache read / output |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | `01-scope.jsonl` | `/speckit-workflow-scope #1 Add a --version flag to the greet CLI.` | 22 (Bash 19, Skill 2, Write 1) | 25 | 210 s | $0.79 | 46 / 50,988 / 1,178,141 / 7,271 |
| 2 | `02-continue.jsonl` | `/speckit-workflow-continue #1` plus the owner's approval (0 sub-issues, score 1, publish) | 26 (Bash 26) | 27 | 222 s | $1.05 | 54 / 65,375 / 1,612,107 / 10,340 |

Run 1 ran `prepare`, `start` and the Scope claim, did the analysis (score 1, lite tier, 0 sub-issues) and stopped
to ask for publication approval. That stop is correct: the run is headless and Scope needs owner approval. Run 2
approved and published the scope (labels `effort:1` and `scope:small`), completed Scope, ran
`render-spec --apply`, claimed Specify (`mode: bind-only`), failed the bind, and paused with the claim kept.

## Memory evidence

- **Memory-related tool calls: 1 in total.** In run 1 the model ran
  `python .specify/extensions/memory/scripts/archive.py pending --gate` itself before `workflow.py prepare` ("Check
  the memory gate before creating a branch"). Run 2 made none. Neither run invoked a `speckit.memory.*` command or
  skill, or `memory_handoff.py`, or `workflow.py memory-handoff`.
- **The session handoff ran inside the claims, once per claim.** The checkpoint's `memory_session` record was
  written at the Scope claim (`at` 09:47:14.990, claim at 09:47:14.990) and rewritten at the Specify claim (`at`
  09:54:04.539, `claimed_at` 09:54:04.539), each time with `status: pending`. The one state file under
  `.specify/workflow/runtime/memory-handoffs/` was updated at 09:47:14.26 and 09:54:04.22. It reads `transition:
  session`, `status: pending`, `actions: []` and "Awaiting local merge/check-out of the configured target branch.",
  and its `pending` carries PM24's `policy` and `policy_hash`. Neither claim returned `memory_blocked` or
  `memory_dispatch`, which is correct with an empty queue. No `memory_*` field appears in the claim JSON the model
  saw: the handoff result is saved only to the checkpoint when it does not block.
- **Prepare and queueing: not reached.** Implement and `complete` never ran.
- **Memory queue after the run** (`archive.py pending`): `enabled: true`, with `ready`, `needs_verification` and
  `blocked` all empty, no active run, no writer, and no `specs/memory/`.

## Issues found

- **B1, blocking Sanduq bug: a rendered spec can never bind.** Workflow `Run.claim` sets `active.mode =
  'bind-only'` when `spec.md` has the render marker (`workflow.py:3377-3379`). Scope's `bind` with the
  claim flags calls `workflow_policy.fresh_claim`, which requires `active.get('mode') != 'initial'` to be false
  (`extensions/scope/scripts/workflow_policy.py:133-139`). It refuses every bind-only claim:

  ```text
  $ python .specify/extensions/scope/scripts/scope.py bind 1 --feature specs/1-add-a-version-flag-to-greet --token ba28b8418d044d679b0df015e8bfabbc --session 0a19d7d1-3e58-4f33-890f-c489950eba24 --analysis specs/1-add-a-version-flag-to-greet/scope-analysis.json --apply
  SCOPE_WORKFLOW_BINDING_MISMATCH
  EXIT=2
  ```

  `stage-specify.md` "Bind-only mode" tells the model to run Scope bind. In lean mode the claim's `scope_command`
  passes `scope_mode` (the pre-override mode), but `fresh_claim` reads the checkpoint, which says `bind-only`. The
  only test, `test_front_half_runtime.BindOnlyAndLazyIssueTests`, checks the claim mode and never runs Scope's
  bind. The bug predates round 4 (`6235a2d`).
- **B2, Sanduq bug: the fresh gate assumes a parent.** When the gate gets the claim flags, its fresh path
  (`scope.py:868-874`) calls `GET issues/<n>/parent` and does not handle 404. For a root issue kept whole with 0
  sub-issues it fails:

  ```text
  GitHub request failed (api repos/samykabu/sanduq-r4-live/issues/1/parent -H): gh: No parent issue found (HTTP 404)
  ```

  It would then require a retained parent approval as well. `ancestors()` at `scope.py:1453` handles the same 404.
  `scope-binding.md` "Printing the command" tells the model to use `--mode initial` with all four flags for the
  initial claim. In run 2 the model fell back to the plain `scope.py gate 1`, which passed. I expect an
  initial-mode (not rendered) Specify bind of a root leaf to hit B2 as well, but I did not test it.
- **I1, a duplicate Memory read (D3 scope).** The SESSION block's second line, "Before a new specification, branch
  or broad staging or commit workflow, `archive.py pending --gate` must pass.", is not exempted in Workflow
  projects. So the model runs the gate itself before `prepare`, although the claim's handoff runs straight after.
  It is read-only and harmless, but it is a second Memory step per new feature. Line one of the block already says
  "do not run it separately"; line two should say the same, or state that the claim covers it.
- **I2, session_id provenance (D3 scope).** Claude Code does not expose its session id to the model.
  `dispatcher-operations.md` says "Supply a usage JSON with `session_id`". In both runs the model used
  `0a19d7d1-3e58-4f33-890f-c489950eba24`, which it took from the scratch path in the working directory. That is
  the parent orchestrator's id; the real ids were `2ac6d23b-…` and `68ea15e2-…`. Two different host sessions
  therefore recorded the same `session_id`, so W14's trigger ("the first claim of a new session") depends on a
  value the model guesses. It worked here only because Scope and Specify always run the handoff.
- **B3, Project init bug (outside D3).** `project-init.ps1 -AutoCreateColumns` created the column "Ready" three
  times, once each for analysis, engineer-review and ready. It also wrote stale option IDs to `config.json` for
  Todo, In Progress and Done (`config.json` had `f75ad846`, `47fc9ee4` and `98236657`; the live IDs were
  `47fd34ad`, `fa2a4064` and `384cd2b3`). It did not create Scope's logical statuses either, so `doctor --project`
  failed straight after init with `PROJECT_SCOPE_STATUS_MISSING: Backlog`, `Need Clarifications` and
  `In progress`. The first-init file is kept as `project-config.first-init.json`.
- Minor: run 1 lost one tool call to Git Bash `/tmp` versus Windows Python paths (`FileNotFoundError`
  `/tmp/sanduq/claim-scope.json`). Doctor warns `INSTRUCTION_FILES_DUPLICATED`, because `specify init` writes both
  CLAUDE.md and AGENTS.md.

## What is still needed for the gate

Fix B1 and, if my reading holds, B2. Then rerun this repository from a fresh issue, or from #1 after
`workflow.py` resume, through Implement and `complete`. Check that the queue then shows one entry with
`default_checks` and that `speckit.memory.prepare` never runs.

## State left in place

- The repository `samykabu/sanduq-r4-live` is private and has not been deleted.
- Project #12 is still in place.
- Issue #1 is open, published, and in Backlog on the board.
- In the clone, the feature branch `1-add-a-version-flag-to-greet` exists locally only, uncommitted. It holds the
  Specify claim, with token `ba28b841…`. The lifecycle log records `paused` for it, while `status` still shows the
  claim as active.
- No PR was opened.

## Run 2 (worktree HEAD 32ffcc4)

**Verdict: FAIL.** The D3 queue step after Implement did not queue anything, because of B4 below. Everything
else D3 needs held up:

- Both hooks stay disabled through an upgrade.
- Every claim ran the session handoff.
- Neither `speckit.memory.session` nor `speckit.memory.prepare` ran.
- No `memory_blocked` or `memory_dispatch` came back from a claim.

The lifecycle reached an open, unmerged PR (#5). It stopped at recording the PR stage, on B5. B1, B2, I1 and the
B3 init fixes worked live.

Evidence is in `<scratch>/run2/`, where `<scratch>` is the run 1 scratch folder: `transcripts/`, `extensions.*.yml`,
`upgrade-*.json`, `board-*.json`, `initcheck-*.json` and `memory-*.json`.

### Upgrade, as a consumer would do it

1. Before upgrading, I committed feature #1's run-1 state on its branch (commit "WIP: feature #1 state…") and
   checked out main. There is no abandon or reset command (the subcommands are `pause`, `recover`, `relocate` and
   the rest), so run 2 used a new issue, #2.
2. Memory first: `specify extension add --dev run2/packages/memory --force`. Spec Kit's `register_hooks` set both
   Memory hooks back to `enabled: true` (`extensions.after-memory-update.yml`), which W10 expects. `install.py`
   re-init changed nothing. `archive.py pending` then reported `enabled: false`, "needs policy/implementation review
   and renewal", which is the documented renewal.
3. Workflow: `upgrade.py --version 1.16.0 --packages run2/packages`, preview then `--apply`. Reconcile set both
   entries back to `enabled: false`.
4. **Finding U1, not a Sanduq bug:** the round-4 fixes leave every version number unchanged. The installer
   therefore skips any dependency whose installed version equals the lock (`install.py:805`), so Scope and Project
   kept their run-1 code after the upgrade. I updated them with `specify extension add --dev <pkg> --force`, then
   ran `install.py --packages run2/packages --apply` (reconcile again). After that, every installed extension was
   byte-identical to the run-2 packages, ignoring CRLF.
5. **Finding U2 (Spec Kit):** `specify extension add --force project` deletes
   `.specify/extensions/project/config.json`. `doctor --project` then listed every `PROJECT_CONFIG_REQUIRED` error.
   I restored the file from git. A consumer who has not committed it loses the board binding.
6. Memory re-approval: `archive.py enable --approve-hash 3ce2533f…9373`. `pending` then reported `enabled: true`
   with PM24's `policy` and `policy_hash`.
7. Hooks after the upgrade (`extensions.after-upgrade.yml`): `speckit.memory.prepare` and `speckit.memory.session`
   are both `enabled: false`, and `impact` is still enabled. `doctor --project` returned `ok: true`. The upgrade
   commit is `d1ecc9f` on main, pushed.

### Board check: init replaces option ids, and items lose their Status

**Project init needs a guard.**

On board #12 every column already existed. The one item was #1, in Backlog with option `72ea95e7`. Running
`project-init.ps1 -AutoCreateColumns` created nothing and made no field mutation, and #1 stayed in Backlog with
the same id. Board #12 therefore did not exercise the risk.

To exercise it I used a scratch board, user Project **#13 "sanduq-r4-initcheck"**, which I left in place. It had
the default Todo, In Progress and Done columns. I added issue #1 to it, set it to **In Progress** (option
`47fc9ee4`), and ran the same init from a scratch copy of the clone's `.specify` against board #13:

```text
[project-init] board Status columns: Done, Todo, In Progress
[project-init]   created & mapped open             -> Feature Specification
[project-init]   created & mapped analysis,engineer-review,ready -> Ready
[project-init]   created & mapped in-review        -> In review
[project-init]   created & mapped                  -> Backlog
[project-init]   created & mapped                  -> Need Clarifications
```

Before the run, #1 had `{"name":"In Progress","optionId":"47fc9ee4"}`. After it, #1's `fieldValueByName` was
**`null`**, and all eight option ids were new: Todo `bdc9669e`, In Progress `fde8ffdb`, and so on.

What the B3 fix got right: each column was created once, the `statusOptions` in `config.json` match the live ids,
and Backlog and Need Clarifications were created. The flaw is that `updateProjectV2Field` with
`singleSelectOptions` replaces every option, which **clears the Status of every item on the board**.

Init should refuse to change columns, or warn and ask for confirmation, when the board has items. Alternatively,
it could save each item's Status by option name and set it again afterwards.

### Commands and transcripts

| # | Transcript | Prompt | Tool calls | Turns | Time | Cost | Tokens: input / cache write / cache read / output |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | `run2/transcripts/01-scope.jsonl` | `/speckit-workflow-scope #2 Add a --name flag to the greet CLI.` | 22 | 25 | 153 s | $0.81 | 44 / 50,988 / 1,111,138 / 8,891 |
| 2 | `run2/transcripts/02-continue.jsonl` | `/speckit-workflow-continue #2` plus the owner's approval, then "continue … to the pull request without merging" | 105 (Bash 97, Agent 2, Write 3, Read 2, Edit 1) | 98 | 906 s | $4.25 | 192 / 156,023 / 10,115,252 / 37,628 |

The lifecycle log for #2 records these claims:

- Scope (score 1, lite tier).
- Specify, in `bind-only` mode. B1 is fixed: the bind passed. One completion was rejected first, then the next was
  accepted.
- Clarify, with zero questions.
- Plan. Tasks was merged into Plan and recorded as `skipped`.
- Analyze.
- Tasks-to-Issues, which created #3 and #4.
- Execute (commit `f27c0ee`, with a worker subagent).
- Verify, Review (with a reviewer subagent) and Ready.
- PR. PR #5 is open and not merged. Its completion was rejected, and the run paused there.

### Memory evidence

- **Memory tool calls per command.** Run 2/1 made 0. Run 2/2 made 0 calls to Memory scripts, `speckit.memory.*`
  commands or skills, or `memory-handoff`. Its only Memory-related calls were three reads, made after the failure:
  `memory-lifecycle.md`, the handoff state file and `archive.py` source. I1 is fixed: the model no longer runs
  `pending --gate`.
- **Session handoff.** All ten claims ran it in-claim (I2), each with `status: pending`. The session state file
  was last updated at 11:02:18.86, the PR claim. No claim returned `memory_blocked` or `memory_dispatch`. The model
  still made up `session_id` from the scratch path, which no longer matters because every claim now runs the
  handoff.
- **Queue after Implement's `complete`: empty.** `complete` saved the Execute receipt (`execute:accepted`), then
  returned `ok: false` and exit 1, with this `memory_handoff`:

  ```json
  {"transition": "execute", "feature": "specs/2-add-a-name-flag-to-greet", "status": "blocked", "ok": false,
   "actions": [], "reason": "MEMORY_HELPER_FAILED (1): Select a full feature directory directly under specs/.",
   "state_file": ".specify/workflow/runtime/memory-handoffs/8c6de25f….json"}
  ```

  `archive.py pending` at the end reports `ready`, `needs_verification` and `blocked` all empty. `prepare` never ran
  as a hook or a command.

### New bugs

- **B4 (blocks D3 queueing):** Memory rejects every feature directory Workflow names for an issue below 100.
  `archive.py` `spec()` (`extensions/memory/scripts/archive.py:183`) requires
  `re.fullmatch(r"\d{3,}[a-z]?(?:-[a-zA-Z0-9]+)+", name)`. Workflow's `prepare --issue 2` names the feature
  `specs/2-add-a-name-flag-to-greet`, using the unpadded issue number. So `memory_handoff`'s
  `queue --spec <feature>` fails on every managed feature for issues 1 to 99. The Memory tests use
  `specs/412-refund-approval`, so they never exercise this. The fix belongs on one side: Memory accepts `\d+`, or
  Workflow pads the number. A test is needed with an issue number below 100.
- **B5 (blocks the PR receipt):** `complete` for the PR stage fails with `{"ok": false, "error":
  "PR_LINT_SCOPE_PREREQUISITES_REQUIRED"}`. `pr_lint_binding` (`extensions/workflow/scripts/workflow.py:1454`)
  requires `dependencies` in `scope-source.json`. Scope's `bind` writes `dict(checked, repo=...)` from `gate()`
  (`extensions/scope/scripts/scope.py:1444`), and `gate()` never returns `dependencies`: its base result is
  `{issue, score, prompt, fingerprint}`, plus the fresh-path fields. The `scope-source.json` for #2 has no
  `dependencies` key. The model would not add `"dependencies": []` by hand, which is correct. I have not checked
  whether any earlier release wrote the key.
- The model handled `memory_handoff: blocked` reasonably. It reported the failure, did not claim anything was
  queued, and went on to Verify, because the Execute receipt stays passed. It did not retry `memory-handoff
  --transition execute`, because the failure is not repairable in place. That matches `memory-lifecycle.md`.

### State left in place after run 2

- The repository `samykabu/sanduq-r4-live` is private and has not been deleted.
- Project #12 shows #2 in In review. #3 and #4 are closed task sub-issues.
- Project #13 ("sanduq-r4-initcheck", the scratch board) is left in place. #1 is on it with no Status.
- **PR #5 is open and not merged**, from branch `2-add-a-name-flag-to-greet` (head `9a99ef8`).
- The clone's #2 branch has uncommitted workflow state: the checkpoint and lifecycle files, plus the paused PR
  claim.
- #1's run-1 state is committed locally on its own branch.
