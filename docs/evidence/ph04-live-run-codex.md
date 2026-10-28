# PH-04 live run (T06): Quick-start managed scenario on Codex

Date 2026-10-28 (UTC 2026-10-27 21:48 to 22:30). One managed feature, issue #2 "Add a wrap command that wraps
text to a given width", in the private sandbox `samykabu/sanduq-sandbox-ph04` (board #16), driven from Scope to
an open pull request entirely on Codex. This is the first Codex end-to-end live run. Redacted evidence:
`t06-codex-issue2.zip` (148 files, SHA-256 `f8fcc859ad698a4e6cf4ebfbd3ba70289a096a4494260f3a9d21a1449d3b4e96`; per-file sums in its `SHA256SUMS`).

**Verdict: PASS with defects.** PR #47 is open, not a draft and not merged (head `60e5049`, mergeable). Every
stage reached `accepted`. 24 tests pass on the PR head merged with `main`. The evidence gate passes when run
locally on a clean LF checkout. Codex hand-edited the rendered gate workflow to work around F1, which the docs
forbid (F21). The host switch, Bridge and waiver paths are recorded in live-run-claude.md: the switch ran
Codex for one stage of #1, and the waiver was attempted on a Claude-run PR.

## Versions and environment

- Same install as live-run-claude.md (same repository, committed setup): Workflow 1.21.0, Scope 1.12.0,
  Project 2.7.0, PR 4.7.0, Progress 1.7.0, Illustrate 2.7.2, Assure 2.6.2, User Manual 1.8.2, Superpowers
  Bridge 1.3.0 with Sanduq aliases, Spec Kit 1.1.3 (`0282d03`). A fresh `git clone` of `main` passed
  `doctor --project` (`ok: true`) without reinstalling, so the committed install is portable.
- Codex CLI 0.163.0, model `gpt-6.1-sol`, reasoning effort high, ChatGPT subscription (no per-run price).
  Windows 11, Python 3.14.8, Git for Windows (`core.autocrlf=true`), gh 2.103.2.
- Headless runner (`tools/run-codex.sh`): `codex exec --json --dangerously-bypass-approvals-and-sandbox
  --dangerously-bypass-hook-trust -C <checkout> "<prompt>"`. `--dangerously-bypass-hook-trust` stands in for
  the one-time `/hooks` approval that checklist step M9 asks for, which `codex exec` cannot do (F16). The
  project hooks (Sanduq guard and the five Progress hooks) therefore ran.
- Every Codex session started with host warnings: hook trust bypassed, `clamping SessionEnd hook timeout to 3s`
  (Progress writes 10 s), and `Exceeded skills context budget. All skill descriptions were removed and 41
  additional skills were not included in the model-visible skills list` (F16). The managed commands were still
  found, because the prompts name them.

## Commands and transcripts

Owner inputs between commands were GitHub comments on #2: `C1Q1: A`, `C1Q2: A`, `C1Q3: A` (the recommended
options), `SD1: A` (the recommended User Manual module map) and, in the prompt of command 5, approval to
recover seven stale receipts.

| # | Transcript | Prompt (abridged) | Tool calls | Time | Input tokens (cached) / output | Stopped at |
| --- | --- | --- | ---: | ---: | --- | --- |
| 1 | `x06-01-scope` | `$speckit-workflow-scope 2` | 21 | 172 s | 1,104,875 (1,037,568) / 5,906 | Approval request, score 3 (lite) |
| 2 | `x06-02-continue` | approval, 0 sub-issues, owner sets effort 5 (standard), through PR | 35 | 228 s | 1,964,736 (1,865,856) / 9,997 | Clarify posted 3 questions |
| 3 | `x06-03-continue` | answers posted, through PR | 70 | 654 s | 10,103,675 (9,952,000) / 26,657 | Execute and Review done; SD1 module-map decision posted (F4) |
| 4 | `x06-04-continue` | SD1 answered, through PR | 31 | 188 s | 1,533,633 (1,460,352) / 5,520 | SD1 applied; asks to recover 7 stale receipts back to Scope (F3) |
| 5 | `x06-05-continue` | recovery approved, prefer `revalidate-upstream`, through PR | 102 | 1,100 s | 17,769,888 (17,560,704) / 50,908 | **PR #47 opened** |
| | | **Total** | **259** | **2,342 s** | 32,476,807 (31,876,480) / 98,988 | |

Wall time from the first lifecycle event to PR accepted: 21:50:05 to 22:28:56 (39 min), including owner
turnaround.

## Lifecycle

`specs/2-.../workflow/lifecycle.jsonl`: 34 claims, 34 accepted, 1 skipped (Tasks merged into Plan), 34
invalidated, 16 revalidate-upstream, 10 paused, 6 recovered, 6 resume and **4 rejected completions**:

- Clarify, 21:58:08, `EVIDENCE_SNAPSHOTS_INVALID`.
- Clarify, 21:58:18, `UPSTREAM_INPUT_CHANGED_DURING_STAGE: .../workflow/decisions.json`.
- Review, 22:17:21, `INPUT_MANIFEST_REQUIRED`.
- Verify, 22:21:55, `STAGE_NOT_PASSED`.

Each was resolved by the next command the runtime named (recover, `revalidate-upstream`, or re-claim with
`--confirm-invalidation`); none needed outside help. The PR stage was accepted once at 22:25:21, then
invalidated: on the Windows (CRLF) checkout the gate reported `DECISION_APPLICATION_STALE` for
`evidence/sd1-approved.md`, Codex added an LF rule to `.gitattributes`, and that new input made Verify stale
(`STALE_RECEIPT: verify; changed paths: [".gitattributes"]`), which removed Review through PR. It re-ran them
and PR was accepted again at 22:28:56 (F6). Codex also hit the GraphQL limit and switched to REST on its own
(`[scope] GraphQL rate-limited ...; using the REST Projects API`).

Stage outcomes: scope, specify, clarify, plan, qa_analyze, manual_analyze, analyze, taskstoissues, execute,
verify, review, qa_document, manual_update, ready and pr are all `accepted`. Task sub-issues #17 to #22 were
created and closed.

## Errors met and how the documented next command resolved them

| Error | Where | Resolution |
| --- | --- | --- |
| Codex host warnings (hook trust, SessionEnd clamp, skills budget) | every session | None needed for the run; recorded as F16 |
| SD1 module map required before manual pages | Manual Update | Owner answered `SD1: A` on the issue, as the comment asked |
| Seven stale receipts after SD1 (`next`: "Re-run scope: inputs or evidence changed") | after SD1 | Owner approved recovery; Codex used `revalidate-upstream` for unchanged stages and re-recorded Scope with `--confirm-invalidation` (F3) |
| `INPUT_MANIFEST_REQUIRED`, `STAGE_NOT_PASSED` | Review, Verify | Re-recorded with an input manifest, then Verify re-run |

## Gate checks on PR #47

| Checkout | Result |
| --- | --- |
| Local, the run's own checkout | `ci_gate.py --base-ref f1f7a90 --check-index` with `PR_NUMBER=47`: `status: passed`, no waivers |
| GitHub Actions | `workflow-evidence` is **queued** with no runner (F22). It parses only because Codex changed `fetch-depth: ${{ github.event.pull_request.commits + 1 }}` to `fetch-depth: 0` in the rendered file (F1, F21) |

## State left in place

- Issue #2 is In review on board #16. PR #47 open, not merged, from
  `2-add-a-wrap-command-that-wraps-text-to-a-given-width`.
- PR #47 and PR #52 each add their own `User-Manual/` tree and manual workflows, so whichever merges second
  will conflict (F4).

## Proposed compatibility.md rows (for the integrator)

- Hosts table, Workflow row, Codex cell: change "End to end: **Untested**" to "End to end: **Tested** (one
  live run, PH-04)". Live run column: "PH-04, 2026-10-28: Workflow 1.21.0, Scope 1.12.0, Spec Kit 1.1.3,
  Codex CLI 0.163.0, QA and User Manual on, advisory gate, standard tier, PR opened".
- Scope (Codex): "Through Workflow only. **Tested** (PH-04 live run)". Memory (Codex): still untested.
- Remove the sentence "Codex has no end-to-end live run yet".
