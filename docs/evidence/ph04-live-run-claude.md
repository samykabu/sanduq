# PH-04 live run (T06): Quick-start managed scenario on Claude Code

Date 2026-10-28 (UTC 2026-10-27 21:37 to 22:43). One managed feature, issue #1 "Add a stats command that
reports word, line and character counts", in the private sandbox `samykabu/sanduq-sandbox-ph04` (board #16),
driven from Scope to an open pull request. The scenario also exercised a host switch to Codex and back, the
Superpowers Bridge route, and a gate waiver. Redacted evidence: `t06-claude-issue1.zip` (165 files, SHA-256
`fb1a91dd2d09b6721166797cd084e433a28f3b7b5846cd5e1367108ab08b2833`; per-file sums in its `SHA256SUMS`).

**Verdict: PASS with defects.** PR #52 is open, not a draft and not merged (head `a8ef6fd`, mergeable). Every
stage reached `accepted` and the workflow status is `pr_open`. 42 tests pass on the PR head merged with
`main`. The host-switch and Bridge paths worked. The waiver path could not be completed (F2), and the CI gate
never ran in CI (F1). See findings.md.

## Versions and environment

- Train under test, from the published catalog on `main`: Workflow 1.21.0, Scope 1.12.0, Project 2.7.0,
  PR 4.7.0, Progress 1.7.0 (added with `--with progress`), Illustrate 2.7.2, Assure 2.6.2, User Manual 1.8.2.
  Presets from the Workflow package. Memory 2.6.0 was **not** installed: the Quick start does not add it, and
  its approval step needs a merged feature (not covered).
- Spec Kit **1.1.3**, commit `0282d03` (the `tested_spec_kit` in Workflow's `dependencies.json`), installed
  with `uv tool install specify-cli --from git+https://github.com/github/spec-kit@0282d03...` into a
  sandbox-local tool folder placed first on `PATH`, so Workflow's installer also used 1.1.3. The machine's own
  `specify` (1.2.3) was not used.
- Superpowers Bridge 1.3.0 (`specify extension add speckit-superpowers-bridge --from
  .../releases/latest/download/speckit-superpowers-bridge.zip`) and Superpowers 7.0.0 (Claude Code plugin,
  project scope), then `install.py --apply --with-aliases`.
- Claude Code 2.1.312, model `claude-opus-5-5` (the host default). Codex CLI 0.163.0 for the switched stage.
  Windows 11, Python 3.14.8, Git for Windows (`core.autocrlf=true`, its default), gh 2.103.2.
- Headless runner (`tools/run-claude.sh` in the bundle): unsets every `CLAUDE*` variable, then
  `claude -p "<cmd>" --output-format stream-json --verbose --permission-mode bypassPermissions
  --setting-sources project,local`. User-level plugins and hooks were therefore not loaded. Account-level
  connectors still appeared in the init event; they are removed from the published digests.

## Setup (first-run checklist M1 to M10)

| Step | Command | Outcome |
| --- | --- | --- |
| M3 | `gh repo create samykabu/sanduq-sandbox-ph04 --private --clone`, seed commit, `specify init --here --integration claude` (answered y), `specify integration install codex`, catalog add at priority 1 | OK. The y/N prompt said "(5 items)". Both integrations installed, default claude |
| M4 | `gh project create --owner samykabu --title ...`, `gh project link 16 ...` | Board #16. `gh project create` printed nothing in a non-TTY shell (F14) |
| M5 | `specify extension add workflow` | Workflow 1.21.0 |
| M6 | `workflow.py init --qa on --manual on --gate-mode advisory --gate-scope managed-only` | 22 expected doctor errors; `DEPENDENCY_UNAVAILABLE` now names `install.py` (PH-03 fix confirmed) |
| M6 | `workflow.py ci --policy self-hosted-required --linux self-hosted,<runner-label> --system-packages preinstalled --python preinstalled` (from managed-workflow.md), `install.py`, `install.py --apply` | Apply **rolled back**: `CI_HOSTED_RUNNER_UNDOCUMENTED: ... windows on windows-latest` (F7). Fixed with `workflow.py ci --windows none`; second apply OK |
| M7 | `project_init.py --number 16 --hooks-mode required --auto-create-columns` | Seven statuses created and mapped |
| M8 | `workflow.py doctor --project` | `ok: true`; warnings `GUARD_HOOK_UNAPPROVED` (Codex), two `SKILL_INVENTORY_LARGE` |
| Extra | Bridge and Superpowers install, then `install.py --apply --with-aliases --with progress` | Doctor `ok: false` after the Bridge add (`LEGACY_ALIAS_RECONCILIATION_REQUIRED`, five `DUPLICATE_STAGE_OWNER`, `PROGRESS_HOOKS_DOUBLE_WIRED`); `ok: true` after the reinstall (F15) |
| Extra | appended `profiles: {enabled: true}` to `.specify/workflow.yml` | Needed for tiers at all (F17) |
| M10 | `gh issue create` #1 | |

CI selection: the rendered gate job runs on `[self-hosted, <runner-label>]`, following the owner's runner
policy. Those runners are registered to another repository only, so no job of this sandbox could run on them
(F22). No GitHub-hosted runner was used.

## Commands and transcripts

Owner inputs between commands were GitHub comments on #1: `C1Q1: A` to `C1Q4: A` (the recommended options)
and `SD1: A` (the recommended User Manual module map).

| # | Transcript | Prompt (abridged) | Tool calls | Time | Cost | Stopped at |
| --- | --- | --- | ---: | ---: | ---: | --- |
| 0 | `c06-01-scope` | `/speckit-workflow-scope 1` | 21 | 107 s | 0.83 USD | Discarded: `target_branch: master` (F8); feature reset, branch renamed to main |
| 1 | `c06-02-scope` | `/speckit-workflow-scope 1` | 22 | 104 s | 0.84 USD | Approval request, score 2 (lite) |
| 2 | `c06-03-continue` | approval, 0 sub-issues, owner sets effort 5 (standard), stop after Plan | 40 | 342 s | 1.57 USD | Clarify posted 4 questions |
| 3 | `c06-04-continue` | answers posted, stop after Plan | 53 | 341 s | 2.26 USD | Plan accepted; tier fixed `standard`, score 5 |
| - | (script) | `workflow.py host --use codex --preview`, `host --use codex`, `migrate --feature ... --reason "Host switched from claude to codex"` | | | | Doctor ok; migrate kept scope, specify, clarify, plan as historical, invalidated none |
| 4 | `x06-s1-qa-analyze` (Codex) | `$speckit-workflow-continue #1`, one stage only | 18 | 132 s | subscription, 1.07 M input tokens | QA Analyze accepted on Codex |
| - | (script) | `host --use claude`, `migrate ... --reason "Host switched from codex back to claude"` | | | | Doctor ok, invalidated none |
| 5 | `c06-05-bridge` | `/speckit-superpowers-bridge #1` resume through PR | 139 | 689 s | 4.45 USD | Verify accepted; paused for `--confirm-invalidation` |
| 6 | `c06-06-continue` | owner confirms | 46 | 398 s | 1.94 USD | QA Document accepted; Verify stale again (F9) |
| 7 | `c06-07-continue` | standing approval for invalidations | 35 | 190 s | 1.26 USD | Manual Update: SD1 module map posted (F4) |
| 8 | `c06-08-continue` | SD1 answered, standing approval | 137 | 1,063 s | 6.90 USD | **PR #52 opened** |
| | | **Total (Claude Code, rows 0 to 8 without row 4)** | **493** | **3,234 s** | **20.05 USD** | |

Wall time from the first lifecycle event to PR accepted: 21:46:57 to 22:41:09 (54 min), including owner
turnaround.

## Lifecycle

`specs/1-.../workflow/lifecycle.jsonl`: 27 claims, 29 accepted, 1 skipped (Tasks merged into Plan, standard
tier), 21 invalidated, 13 revalidate-upstream, 5 paused, 4 resume, 2 recovered and **1 rejected completion**:

- Execute, 22:11:27, `UPSTREAM_INPUT_CHANGED_DURING_STAGE: README.md, textkit/cli.py, textkit/core.py`. Codex's
  QA Analyze receipt had listed the product files as dependencies. The documented recovery (recover, then
  `revalidate-upstream` of qa_analyze, then resume) cleared it in 57 s (F10).

Final stage outcomes: scope, specify, clarify, plan, qa_analyze, manual_analyze, analyze, taskstoissues,
execute, verify, review, qa_document, manual_update, ready and pr are all `accepted`. Verify was accepted
5 times, and Review and QA Document 4 times each, because of the invalidation waves in F3 and F9.

## Scenario paths

- **Host switch: PASS.** `host --use codex` re-registered both hosts and printed a per-feature `migrate`
  plan, but the apply result has no `next` pointing at it; I ran `migrate` by hand (F11). Codex then took and
  completed exactly one stage. Switching back worked the same way. Neither migrate invalidated a receipt.
- **Superpowers Bridge: PASS.** `/speckit-superpowers-bridge #1` ran Sanduq's alias: the transcript shows
  `speckit-workflow-doctor`, then `speckit-workflow-continue`, then the normal stages with `sanduq-worker`
  subagents. No `superpowers:*` skill ran and no `.specify/superpowers-handoff.json` was written, so exactly
  one executor ran. Superpowers itself was installed but, as designed, never invoked in the managed project.
- **CI waiver: FAIL (documented behaviour blocks it).** The gate never runs in CI (F1), so I ran the same
  command the workflow runs (`ci_gate.py --base-ref <base sha> --check-index` with `PR_NUMBER` and a token) in a
  clean LF clone. PR #52 passes and needs no waiver. The first natural waiver case was managed PR #23 (T08,
  lite tier with the manual selected): `DOCUMENTATION_GATE_FAILED` (F5). I posted the documented
  `sanduq-gate-waiver` comment (rule `documentation`, exact head SHA, expiry 2026-11-30). The gate still
  reported `WAIVER_NOT_VERIFIED`, because the commenter is the PR author: every PR in a solo setup is opened
  with the owner's own token. Replaying the same comment through `waivers.verify` with only the login changed
  returns an accepted waiver, so the format was right (F2).

## Gate checks on PR #52

| Checkout | Result |
| --- | --- |
| Clean clone, `core.autocrlf=false` (what a Linux runner sees) | `status: passed`; rules receipts, decisions, documentation, portability, live_answers |
| Clean clone, `core.autocrlf=true` (the Git for Windows default) | `SOURCE_INVENTORY_INVALID: .../inventory/verify-....json does not match its recorded sha256` (F6) |
| GitHub Actions | No gate run: the workflow file does not parse (F1). Only `preview` (User Manual) is queued, without a runner |

## State left in place

- Issue #1 is In review on board #16; sub-issues #24 to #35 were created and closed.
- PR #52 open, not merged, from `1-add-a-stats-command-that-reports-word-line-and-character`.
- The checkout keeps the uncommitted `.claude/settings.json` and `.codex/hooks.json` changes from the host
  switch.

## Proposed compatibility.md rows (for the integrator)

- Hosts table, Workflow row, Live run column: append "PH-04, 2026-10-28: Workflow 1.21.0, Scope 1.12.0,
  Spec Kit 1.1.3, Claude Code 2.1.312, QA and User Manual on, advisory gate, standard tier, PR opened; host
  switch to Codex and back, Bridge route. The gate did not run in CI (workflow file invalid)".
- Scope, Project, PR, Progress rows: "PH-04, 2026-10-28, as Workflow (Claude Code and Codex)".
- Assure, Illustrate, User Manual row: now **Tested** through Workflow on Claude Code and Codex (QA Analyze,
  QA Document, Manual Analyze and Manual Update ran in both PH-04 runs).
- "In use, without a live-run record": move **Host switch** and **Superpowers Bridge route** to tested (this
  record). Keep **CI rule waivers** untested: the waiver was posted but cannot verify in a solo setup (F2).
- Platforms, Windows row: add "PH-04 (Claude Code and Codex)".
