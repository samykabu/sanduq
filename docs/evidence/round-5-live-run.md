# Round 5 live run (L-RUN): I3 and the IP21 native Progress wiring gate

Date 2026-10-21. One managed run, issue #14 in the private sandbox `samykabu/sanduq-r4-live`, using the released set.
All evidence is in the scratch folder
`C:\Users\sabus\AppData\Local\Temp\claude\d--Projects-Personal-sanduq\50da65d7-6f55-43f9-b472-62404e0ef4f0\scratchpad\r5`
(`<scratch>` below): `transcripts/` (stream-json, stderr and the Claude Code hook debug log for each command),
`upgrade-*.json`, `install-fail1-result.json`, `doctor-*.json`, `memory-*.json`, `claude-settings.*.json`,
`extensions.*.yml`, `progress-snapshot/`, `bench-native-vs-dispatcher.txt` and `tools/` (analyze.py,
hooktimes.py, bench.py, bench2.py).

**Verdict: PASS on both criteria.**

- **I3: PASS.** Execute's first `complete` was accepted. Plan gave the product files the `consulted` role.
  No stage had a rejected completion.
- **IP21: PASS.** All five Progress hooks ran through native wiring for the whole Claude Code session. The Execute
  bind handshake converted on a native PostToolUse. Both subagent runs were recorded from hook payloads. Nothing
  was double-wired (doctor clean, `spec-kit no`). All 280 hook responses had exit 0.

Two new defects, both outside the gate: D1 (medium) and D2 (low, process). Details below.

## Method

- **Clone.** A fresh `git clone https://github.com/samykabu/sanduq-r4-live.git` into `<scratch>/live`. I used
  plain git because `gh repo clone` failed on the GraphQL limit (see D2). Main was at `85c2fcf`, round 4's last
  upgrade. The registry held illustrate 2.6.0, pr 4.4.0, memory 2.4.0, project 2.4.0, scope 1.9.0 and workflow
  1.16.0, all round-4 dev builds.
- **Upgrade.** I took the consumer route, using release assets only and no local packages:
  1. Backed up `.specify/extensions/project/config.json`.
  2. Ran `specify extension add memory --from .../memory-v2.5.0/memory.zip --force`, then Memory
     `install.py --target-branch main`.
  3. Appended `progress: {hook_wiring: native}` to `.specify/workflow.yml`.
  4. Ran `upgrade.py --version 1.17.1 --with progress`, preview first, then `--apply`.
     - The first apply ran on the tested Spec Kit 1.0.11 (`8147943`, installed in scratch with `uv tool`). It
       rolled back on D1.
     - The second apply used the machine's Spec Kit **1.1.4.dev0** and succeeded.
  5. Checked `config.json`: it was byte-identical to the backup (the installer's preservation kept it, so the U2
     risk did not arise).
  6. Committed the upgrade as `a0d05e7` on main and pushed it.
  7. Ran `archive.py enable --approve-hash 2b51e889…d4a3`.
- **Installed versions after upgrade.** Workflow 1.17.1, Scope 1.10.1, Project 2.5.1, PR 4.5.1, Illustrate 2.7.0,
  Memory 2.5.0, Progress 1.5.0, plus the bundled presets. Assure and User Manual were not selected (`qa` and
  `user_manual` are off in this project).
- **Progress wiring.** `install-lock.json` records `progress: {hook_wiring: native, hosts: {claude:
  {speckit_entries_removed: 5, result: "progress: hooks installed claude project 5 entries in
  .claude/settings.json", cost_class: native}}}`. `.claude/settings.json` holds five
  `python "${CLAUDE_PROJECT_DIR}/.specify/extensions/progress/scripts/hook.py" <event> --managed-by=progress-report;
  exit 0` entries and no `speckit.progress.hook` entry. `progress hooks status` printed `progress: hooks claude
  project 5/5 user 0/5; codex project 0/5 user 0/5; spec-kit no`. `progress_bridge.py mode --host claude` printed
  `reporting: projection`.
- **Doctor after the upgrade** (`doctor-after-install.json`, and `doctor-final.json` after the run, identical
  apart from the timestamp): `ok: true`, `errors: []`. The only warnings were `INSTRUCTION_FILES_DUPLICATED` and
  two `SKILL_INVENTORY_LARGE`. **`PROGRESS_HOOKS_DOUBLE_WIRED` did not fire.**
- **Spec Kit hooks after the upgrade.** `speckit.memory.prepare` and `speckit.memory.session` are
  `enabled: false`, and `impact` is enabled (unchanged from round 4). Progress's `after_tasks` init and
  `after_implement` refresh command hooks are enabled.
- **Host.** Claude Code 2.1.306. The runner script `run.sh` unsets every `CLAUDE*` variable, then runs
  `claude -p "<cmd>" --output-format stream-json --verbose --permission-mode bypassPermissions
  --strict-mcp-config`. It adds `--include-hook-events --debug hooks --debug-file <name>.debug.log`, which only add
  observation: hook events in the stream, and per-hook durations in the debug log. User plugins (ponytail, azure,
  codex, comfy) load their hooks as normal.
- **Issue.** I created #14, "Add a --repeat flag to the greet CLI", with `gh issue create`.

## Commands and transcripts

| # | Transcript | Prompt | Tool calls | Turns | Time | Cost | Tokens: input / cache write / cache read / output |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | `01-scope.jsonl` | `/speckit-workflow-scope #14` | 21 (Bash 18, Skill 2, Write 1) | 24 | 205 s | $0.74 | 42 / 49,698 / 1,039,457 / 6,599 |
| 2 | `02-continue.jsonl` | `/speckit-workflow-continue #14 Owner approval: yes, publish #14 as one issue with 0 sub-issues and effort 2. Then continue … through … the PR stage: open the pull request but do not merge it.` | 92 (Bash 90, Agent 2) | 85 | 1,033 s | $3.94 | 166 / 148,905 / 8,638,782 / 35,083 |

Command 1 scored the issue 2 (lite tier, 0 sub-issues) and stopped for publication approval, which is correct.

In command 2, the lifecycle log for #14 (`specs/14-add-a-repeat-flag-to-the-greet-cli/workflow/lifecycle.jsonl`)
records 22 events, every one either `claim` or `accepted`, with one `skipped` (tasks merged into plan). It has
**no `rejected-completion` event at any stage**. Stage by stage:

- Scope accepted at 16:23:03.
- Specify accepted on its first completion. Runs 2 to 4 each had one rejected Specify completion.
- Clarify had no questions.
- Plan; Tasks was skipped because it was merged into Plan.
- Analyze.
- Tasks-to-Issues created #15 and #16.
- Execute ran with a `sanduq-worker` subagent; commit `555912a`.
- Verify.
- Review ran with a `sanduq-reviewer` subagent.
- Ready.
- **PR accepted at 16:36:25.**

**PR #17** is open, not a draft and not merged, with head `996f05c`.

## I3: Execute's first `complete`

**PASS.** Execute's `complete` was called once, at transcript line 671 (`receipt-execute-14.json`, then
`workflow.py complete`). It returned at line 680:

```json
{"ok": true, "stage": "execute", "next": {"stage": "verify", "command": "workflow:verification", "reason": "pending"}}
```

The lifecycle log records `claim execute` at 16:29:04 and `accepted execute` at 16:31:43, with nothing in
between. Plan's receipt in `checkpoint.json` still lists the product files under `inputs`, but now with roles:

```text
inputs: [spec.md, plan.md, tasks.md, greet.py, test_greet.py]
input_roles: {"greet.py": {"role": "consulted", "because": "current CLI structure read for planning; Execute changes it"},
              "test_greet.py": {"role": "consulted", "because": "current tests read for planning; Execute changes it"}}
```

That is the second option the `stage-plan.md` sentence offers ("leave them out, or give them `{"role":
"consulted", …}`"). Execute changed both files, and its completion was not treated as an upstream change. Runs 3
and 4 had one `UPSTREAM_INPUT_CHANGED_DURING_STAGE: greet.py, test_greet.py` each.

## IP21: native Progress hooks in the Claude Code session

**PASS.**

**The hooks fired, with native wiring only.** Command 2's debug log shows only the native commands. Its stream has
280 hook runs (280 `hook_started`, 280 `hook_response`), every response `outcome: success`, and no non-zero hook status in either debug log.

| Progress hook (command 2) | Calls | Median (Claude Code reported) | Mean | Min / max |
| --- | ---: | ---: | ---: | --- |
| PostToolUse, before the bind (fast unbound exit) | 51 | 626 ms | 671 ms | p90 876 ms |
| PostToolUse, after the bind (full path) | 38 | 661 ms | 694 ms | p90 918 ms |
| PreToolUse (`Task\|Agent\|spawn_agent`) | 2 | 854 ms | 854 ms | 557 / 1,152 ms |
| SessionStart / Stop | 1 / 1 | 1,049 / 919 ms | | |
| *For comparison: Workflow `guard.py` PreToolUse (python hook on Bash)* | 90 | 618 ms | 670 ms | 383 / 1,215 ms |

**The bind and what the hooks recorded.**

- At Execute the model ran `progress init --feature … --statusline no`, which printed `bind=2569df12b111`, then
  `progress lane L1 … --workstream`.
- The next native PostToolUse converted the pending bind. `.specify/progress/bindings.json` has
  `claude:2d11046e-f355-4487-8279-e2280da2ce21` with `bound_at 16:29:38Z`, and `pending: []`. That is the real
  host session id from the stream.
- The host record `progress/.host/claude-2d11046e….json` holds two children, from the two PreToolUse
  `Task|Agent` events plus PostToolUse:
  - `sanduq-worker` "Implement T001-T002 repeat flag": 16:29:53 to 16:30:53, `effort: high (hook, exact)`,
    `done`.
  - `sanduq-reviewer`: 16:32:32 to 16:33:23, `done`.
  - The orchestrator's `effort: high (hook, exact)` was last observed at 16:37:17.
- `report.json` has `collection: {automatic: true, hosts: [claude], dirty: false, last_event_at:
  "2026-10-21T16:37:18Z", diagnostics: 0}` and two `runs` with source `hook`.
- `progress status` printed `2/2 tasks, 0 lanes active, 0 blocked, 0 decisions pending (rev 46)`.
- No `diagnostics.log` was written.

**Per-call cost.**

- Inside the session, Claude Code reports about 0.63 to 0.66 s per Progress hook, the same as the Workflow guard's
  python hook (0.62 s). This machine runs every hook alongside four plugins' hooks. Process spawn under that
  concurrency dominates, not Progress. The bound full path adds about 35 ms at the median.
- Outside the session, the same commands run through `bash -c`, the way Claude Code runs them, on the same
  machine. Twelve rounds, alternating order, in a scratch copy of the clone. The copy was given Spec Kit's own
  entries (`python3 "${CLAUDE_PROJECT_DIR}/.specify/events.py" speckit.progress.hook post_tool_use 10`) for the
  dispatcher rows.

| Wiring | Unbound session | Bound session |
| --- | ---: | ---: |
| Native `hook.py` | 181 ms (130-310) | 205 ms (146-239) |
| Spec Kit dispatcher | 306 ms (214-408) | 403 ms (250-593) |

Round 4 measured 0.19-0.22 s native and 0.54 s dispatcher. Native matches round 4. Bare `python hook.py` without
the shell is 99 ms, and `python -c pass` is 92 ms, so hook.py's own work is under 10 ms on the unbound path.

## Defects and observations

- **D1, medium, new: on Workflow's tested Spec Kit, `upgrade.py --with progress` fails and its error hides the
  cause.**
  - Workflow 1.17.1's `dependencies.json` names `tested_spec_kit` 1.0.11 (`8147943`) and offers optional Progress
    1.5.0. Progress 1.5.0's `extension.yml` requires `speckit_version: ">=1.1.1.dev0,<2.0.0"`.
  - Repro: Spec Kit 1.0.11, then `upgrade.py --version 1.17.1 --with progress --apply`.
  - Result: `WORKFLOW_UPGRADE_ROLLED_BACK: INSTALL_COMMAND_FAILED: <python> …/install.py --root … --apply
    --upgrade-owner 43400 --with progress`. The rollback was clean.
  - The cause appears only two backup levels down, in
    `.specify/workflow/backups/installs/07e7…/result.json` (copied to `<scratch>/install-fail1-result.json`):
    `Compatibility Error: Extension requires spec-kit >=1.1.1.dev0,<2.0.0, but 1.0.11 is installed.`
  - Fix:
    - Raise `tested_spec_kit`, or have `install.py` check optional packages' `speckit_version` in preview.
    - Have `command()` include the last stderr or stdout lines in `INSTALL_COMMAND_FAILED`.
  - Consequence: this run used Spec Kit 1.1.4.dev0, not round 4's 1.0.11.
- **D2, low, process: `gh api rate_limit` does not show the GraphQL bucket that limits `gh`.**
  - At the start, `gh api rate_limit` and the in-query `rateLimit` both reported GraphQL 4,993 of 5,000 remaining.
    At the same moment, `gh repo clone`, `gh release list` and `gh issue list` failed with "API rate limit already
    exceeded for user ID 1850884".
  - The `X-RateLimit-*` headers on a GraphQL call showed the real state: `Remaining: 0`, `Used: 5000`, reset
    16:13:53 UTC.
  - The handoff's rule "check `gh api rate_limit` first" is not enough. Check the headers instead
    (`gh api -i graphql -f query='{viewer{login}}'`, script `<scratch>/gqlcheck.sh`).
  - This is also relevant to SC8's shared client: a rate-limit guard should read the response headers.
  - I waited for the reset before running.
- **I2, known, still present.** Every claim recorded `session_id: 50da65d7-…`, which the model took from the
  scratch path in the working directory (the parent orchestrator's id). The real session was `2d11046e-…`.
  Progress bound the correct id because it reads it from the hook payload.
- **O1, low: the orchestrator's model is unknown in the Progress report.**
  - `orchestrator.model` reads `source: none`. Under Workflow, the bind happens at Execute, and SessionStart, the
    only Claude Code payload that carries the model, fired about 10 minutes earlier while the session was
    unbound.
  - Effort is captured from PostToolUse. The two child runs also show `actual_model: unknown`.
  - Possible fix: capture the model at bind time from the transcript, or keep the last unbound SessionStart model
    per session.
- **O2, low: the lane and the host run are not joined.** Lane L1 (`owner worker-1`, tasks T001-T002) shows
  `run_ids: []`. The worker's host run shows `workstream: null`, `tasks: []`. The page shows both, but not as one
  workstream.
- **O3, cosmetic.** In Tasks-to-Issues the model passed `--parent samykabu/sanduq-r4-live#14`, and argparse
  refused it ("invalid int value"). It retried with `14`. `--help` names the argument only `PARENT`; "PARENT
  (issue number)" would prevent the slip. This cost one tool call.
- **Memory (not a criterion).** `archive.py pending` lists `specs/14-…` under `blocked` with "Awaiting local
  merge/check-out of the configured target branch.", the normal state before merge. No `speckit.memory.*` command
  ran, and the model made no Memory calls.

## Rate limit used

- **GraphQL.** The user-level bucket, read from the headers, was 4,999 at 16:14:13, after the reset and before
  the issue was created. It was 3,489 at about 16:39, after the run: 1,510 points in that window. The bucket is
  shared with the owner's other sessions running at the same time (it was already exhausted before this run
  started), so this run's own share cannot be separated. Round 4's run 4 used 134.
- **REST core.** 4,774 at the start and 4,759 at the end.

## State left in place

- `samykabu/sanduq-r4-live` main is at `a0d05e7`, the released-set upgrade with native Progress wiring, pushed.
- Issue #14 is In review on Project #12. Task sub-issues #15 and #16 are closed.
- **PR #17 is open, not a draft and not merged**, from `14-add-a-repeat-flag-to-the-greet-cli` (head `996f05c`).
  PRs #5, #9 and #13 from round 4 are still open.
- The clone is on the #14 branch with a clean tree, apart from Spec Kit's untracked `.cache` and
  `.dependency-checks.json`.
- Memory is approved with `2b51e889…d4a3`, and the queue holds #14.
- `<scratch>/bench-copy` is a scratch copy with dispatcher wiring, used only for timing.
