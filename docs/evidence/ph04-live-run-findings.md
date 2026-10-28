# PH-04 live-run findings (T06 and T08), 2026-10-28

Train under test: Workflow 1.21.0, Scope 1.12.0, PR 4.7.0, Project 2.7.0, Progress 1.7.0, Illustrate 2.7.2,
Assure 2.6.2, User Manual 1.8.2 (catalog on `main`), Spec Kit 1.1.3 (`0282d03`). Windows 11, Python 3.14.8,
Git for Windows (default `core.autocrlf=true`), gh 2.103.2, Claude Code 2.1.312, Codex CLI 0.163.0. Sandbox:
private `samykabu/sanduq-sandbox-ph04`, board #16. Local paths are written as `<sandbox>`.

Severity: **high** means the documented path is broken for every user. **Medium** means a user on the
documented path hits it and needs non-obvious recovery or loses a documented capability. **Low** means
confusing output, a doc gap or an inefficiency with an easy workaround.

| ID | Severity | Title |
| --- | --- | --- |
| F1 | high | The rendered evidence-gate workflow does not parse, so the gate never runs in CI |
| F2 | medium | A waiver can never be granted in a solo setup, and the error does not say why |
| F3 | medium | Recording a late decision (SD1) makes every receipt stale back to Scope |
| F4 | medium | "Enable User Manual" leaves the manual uninitialised; every feature stops mid-run for a module map, and parallel features each create one |
| F5 | medium | Lite tier with the manual selected always fails the documentation rule |
| F6 | medium | On the Windows default `core.autocrlf=true` the gate rejects evidence that passes on Linux |
| F7 | medium | The documented self-hosted CI command makes `install.py --apply` roll back |
| F8 | medium | `target_branch` is taken from the local branch without checking the remote default |
| F9 | medium | QA Document and manual setup outputs are Verify inputs, causing a second invalidation wave |
| F10 | medium | A Codex QA Analyze receipt listed product files as inputs; Claude's Execute was then rejected |
| F11 | low | `host --use` leaves the per-feature `migrate` as a list in the JSON with no `next` |
| F12 | low | `install.py` prints a text line before its JSON on stdout |
| F13 | low | `doctor` JSON lists every skill in the user's home and plugin folders by name |
| F14 | low | `gh project create` prints nothing in a non-TTY shell; checklist M4 says it prints the URL |
| F15 | low | After adding the Bridge, doctor names three different fixes; the one that works is not documented |
| F16 | low | Codex headless: hook approval needs a dangerous flag; Codex clamps a Progress hook and drops skills |
| F17 | low | "Standard tier" needs a hand edit of `workflow.yml`; Scope scored both T06 issues lite |
| F18 | low | Task sub-issue volume: 12 sub-issues for a four-file feature |
| F19 | low | PR body for #9 does not close the issue |
| F20 | low | Standard-tier T08 PRs do not commit `lifecycle.jsonl`; lite PRs do |
| F21 | low | An agent hand-edited the rendered gate workflow, which the docs forbid |
| F22 | low | A new repository has no self-hosted runner; gate and preview jobs queue forever |
| F23 | low | Codex read an unrelated user-global plugin skill during a managed run |
| F24 | info | Runtime and owner share one GitHub identity in a solo setup |

## F1 (high): the rendered evidence-gate workflow does not parse, so the gate never runs in CI

- Every `install.py --apply` renders `.github/workflows/sanduq-workflow-gates.yml` with
  `fetch-depth: ${{ github.event.pull_request.commits + 1 }}`. GitHub expressions have no arithmetic operators.
- `gh run view 40589077506 --repo samykabu/sanduq-sandbox-ph04`:
  ```text
  X main .github/workflows/sanduq-workflow-gates.yml · 40589077506
  Triggered via push about 20 minutes ago
  X This run likely failed because of a workflow file issue.
  ```
  Every push (runs 40589077506, 40591195656, 40591581856, 40591670954, 40591692851, 40591760121) failed with
  zero jobs, named by path. No `pull_request` gate run happened on any PR.
- `actionlint 1.7.7` on the rendered file:
  ```text
  sanduq-workflow-gates.yml:20:62: got unexpected character '+' while lexing expression, expecting 'a'..'z', ... [expression]
  ```
- Source: `extensions/workflow/assets/github/workflow-gates.yml:22`, introduced in `937a319` (#33). Every
  consumer since then has an inert gate in both `advisory` and `required` mode. The docs and SECURITY.md say
  the CI gate checks receipts, but it has not been running.
- Fix: `fetch-depth: 0` (Codex chose exactly this in PR #47, F21), or fetch the base by SHA in the next step.
  Add an actionlint step over the rendered template to Workflow's CI.

## F2 (medium): a waiver can never be granted in a solo setup, and the error does not say why

- `waivers.authorized` requires `login != pr.user.login`. In a solo setup the agent opens every PR with the
  owner's token, so the owner is always the PR author and no one else can comment.
- Repro on PR #23: posted the documented comment
  `<!-- sanduq-gate-waiver {"version":1,"pr":23,"feature":"specs/7-add-a-reverse-command-t08-lite-managed-1","rule":"documentation","head_sha":"42a696909986d654d0526f258c40ed2cab47470b","expires":"2026-11-30","reason":"Lite tier skips the manual stages; no manual exists yet"} -->`
  plus `Reason: ...`, then ran `GH_TOKEN=... PR_NUMBER=23 python .specify/extensions/workflow/scripts/ci_gate.py
  --base-ref <base sha> --check-index`:
  ```text
  {"ok": true, "status": "advisory_findings", "error": "DOCUMENTATION_GATE_FAILED: {\"current\": false, \"reason\": \"missing\"}\n; WAIVER_NOT_VERIFIED: require one current authorized PR comment for documentation on specs/7-add-a-reverse-command-t08-lite-managed-1", "feature_verified": false}
  ```
- Replaying the same comment through `waivers.verify` with only the commenter's login changed returns an
  accepted waiver, so the format was right and the author rule is the only blocker.
- The owner uses waivers (Q-08). Fix: either document that waivers need a second account (a reviewer or bot
  identity) and say so in `WAIVER_NOT_VERIFIED` (for example `... 1 comment ignored: written by the PR author`),
  or let the configured decision owner waive when the PR was opened by the runtime on their behalf.

## F3 (medium): recording a late decision (SD1) makes every receipt stale back to Scope

- `workflow/decisions.json` is an input of every receipt, Scope included. The User Manual module map decision
  SD1 is raised at Manual Update or Execute, so recording the owner's answer stales the whole chain.
- Codex #2, after `SD1: A`: `workflow.py next --feature specs/2-...` returned
  `{"stage": "scope", "reason": "inputs-or-evidence-changed", "recovery": ["An input changed, which no amendment
  covers; re-record: ... claim ... (it claims scope ...)"]}`. The run asked approval to invalidate seven
  receipts (Specify, Clarify, Plan, QA Analyze, Manual Analyze, Analyze, Tasks-to-Issues).
- The fingerprints confirm only `decisions.json` changed: with the runtime's own `fingerprint_files`, every
  Scope and Specify input matched except `specs/2-.../workflow/decisions.json`.
- Seen in all four standard features: #1 (Scope re-recorded with `--confirm-invalidation`, Specify to
  Tasks-to-Issues revalidated), #2, #8 and #10 (Execute's first completion rejected with
  `UPSTREAM_INPUT_CHANGED_DURING_STAGE: .../workflow/decisions.json`).
- Cost: on #1 this was part of the 6.90 USD final session. Fix: fingerprint only the decision records a stage
  consumed, or treat a new decision that no earlier stage cited as an amendment, not an input change.

## F4 (medium): "Enable User Manual" leaves the manual uninitialised; every feature stops for a module map

- The Quick start says `$speckit-workflow-init Enable QA and User Manual`, and the script equivalent is
  `init --manual on`. Neither runs `speckit-user-manual-init`. The first manual-touching stage of every feature
  then posts decision SD1 (approve a module map) and stops: #1 at Manual Update, #2 at Manual Update, #8 and
  #10 during Execute.
- Lifecycle of #1: `22:25:02 Manual Update T010: User Manual module map needs owner approval; decision SD1
  posted ... Claim fcd6e41e... held.`
- Four features in flight each proposed and created their own `User-Manual/` tree and two workflows
  (`user-manual-preview.yml`, `user-manual-release.yml`), so PRs #47, #52, #54 and #63 will conflict with each
  other on merge.
- Fix: have `workflow init --manual on` (or the checklist) run the manual init once, on the target branch,
  before the first feature; document the one-time SD1 stop in the managed-workflow scenario.

## F5 (medium): lite tier with the manual selected always fails the documentation rule

- The lite tier skips manual analysis and manual update (stages.md), but the gate's `documentation` rule still
  requires the selected manual. With no `User-Manual/manual.yml` on `main`, every lite PR fails:
  `DOCUMENTATION_GATE_FAILED: {"current": false, "reason": "missing"}` (PR #23 above; PR #53 reported the same).
- Combined with F2, a solo owner cannot waive it. Fix: the gate should accept a lite tier's skipped manual
  stages as "not applicable", or the lite profile should keep a manual no-op check.

## F6 (medium): on the Windows default `core.autocrlf=true` the gate rejects evidence that passes on Linux

- PR #52 head `a8ef6fd`, same command (`ci_gate.py --base-ref <base> --check-index`, `PR_NUMBER=52`):
  ```text
  core.autocrlf=true : {"ok": true, "status": "advisory_findings", "error": "SOURCE_INVENTORY_INVALID: specs/1-.../workflow/inventory/verify-c-f51c42577045a15901c3.json does not match its recorded sha256", "feature_verified": false}
  core.autocrlf=false: {"ok": true, "status": "passed", ...}
  ```
- On Codex #2 the same conversion made `evidence/sd1-approved.md` report `DECISION_APPLICATION_STALE`. Codex
  added an LF rule to `.gitattributes`, which itself staled Verify (`STALE_RECEIPT: verify; changed paths:
  [".gitattributes"]`) and forced Review through PR to be re-run. Claude added
  `specs/1-.../evidence/.gitattributes` for the same reason; the inventory file above is outside it.
- runner-policy.md says "UTF-8 text fingerprints normalize CRLF across checkout platforms". That holds for
  receipt inputs (I verified Scope and Specify inputs match on a CRLF checkout), but not for the inventory
  files and decision evidence. Fix: hash those through the same portable reader, or have the installer write a
  `.gitattributes` for `specs/*/workflow/**` and `specs/*/evidence/**`.

## F7 (medium): the documented self-hosted CI command makes `install.py --apply` roll back

- managed-workflow.md gives `workflow.py ci --policy self-hosted-required --linux self-hosted,<label>
  --system-packages preinstalled --python preinstalled`. The selection keeps `windows: [windows-latest]`.
- `install.py` (preview) passed. `install.py --apply`:
  ```text
  {"ok": false, "error": "INSTALL_ROLLED_BACK: CI_HOSTED_RUNNER_UNDOCUMENTED: sanduq-workflow-gates.yml runs windows on windows-latest; record why the self-hosted runner cannot serve it under ci.exceptions; backup: <sandbox>/...", "next": "Read the cause in the message, fix it, then python .specify/extensions/workflow/scripts/install.py --apply"}
  ```
- `workflow.py ci --windows none` fixed it. Fix: add `--windows none` (or a Windows label) to the documented
  command, make `self-hosted-required` drop hosted defaults it was not given, and catch this in the preview.

## F8 (medium): `target_branch` is taken from the local branch without checking the remote default

- `gh repo create --private --clone` of an empty repository leaves the clone on Git's default `master`; I
  pushed to `main`. Scope then recorded `"target_branch": "master"` in the checkpoint (`previous_branch()` in
  `workflow.py`), and its own summary warned "the workflow recorded the target branch as `master`, but the
  remote's main branch is `origin/main`".
- Recovery was a manual reset of the untracked feature (cost one 0.83 USD Scope run). Fix: compare with
  `origin/HEAD` (or `gh repo view --json defaultBranchRef`) and refuse or ask when they differ; mention it in
  checklist M3.

## F9 (medium): QA Document and manual setup outputs are Verify inputs, causing a second invalidation wave

- #1 lifecycle: `22:21:34 QA Document outputs (qa/*.html, .github/memory/project-memory.md) staled Verify;
  claiming Verify returns confirm_invalidation for review and qa_document; awaiting owner approval`.
- The rerun converged (QA outputs byte-identical the second time), but cost one extra Verify, Review and QA
  Document. The manual setup's new workflows (`.github/workflows/user-manual-*.yml`) staled Verify again on
  #1 at Manual Update.
- Fix: exclude stage outputs that later stages produce (QA pages, project memory, generated workflows) from
  Verify's source inventory, or order QA Document's writes before Verify.

## F10 (medium): a Codex QA Analyze receipt listed product files as inputs; Claude's Execute was rejected

- After the host switch, Codex ran QA Analyze for #1 and recorded `README.md`, `textkit/cli.py` and
  `textkit/core.py` as inputs. Claude's Execute changed them, and its completion was refused:
  `22:11:27 execute rejected-completion UPSTREAM_INPUT_CHANGED_DURING_STAGE: README.md, textkit/cli.py,
  textkit/core.py`.
- Recovery (recover, `revalidate-upstream` qa_analyze, resume) took 57 s. This is round 5's I3 issue
  (fixed for Plan with `input_roles: consulted`) appearing at QA Analyze. Fix: give `stage-qa-analyze`
  (Assure) the same "consulted" rule for product files, and enforce it in `complete`.

## F11 (low): `host --use` leaves the per-feature `migrate` as a list in the JSON with no `next`

- `workflow.py host --use codex` applied, and the result's `checkpoints_to_migrate` listed `git switch ...`,
  `migrate --preview` and `migrate --reason "Host switched from claude to codex"` for #1. The result has no
  `next` field, so a user can switch and continue without migrating. It also leaves `.claude/settings.json`
  and `.codex/hooks.json` modified and uncommitted.
- Fix: return `next` naming the migrate command, or migrate the current branch's feature in the same apply.

## F12 (low): `install.py` prints a text line before its JSON on stdout

- The first line of `install.py` and `install.py --apply` output is `Codex runs project hooks only in a
  trusted project and after you approve them: open Codex here, run /hooks and approve the Sanduq guard
  (.codex/hooks.json).`, followed by the JSON. `json.load` on the output fails (`Expecting value: line 1
  column 1`). Fix: send the notice to stderr or into the JSON (`codex_hook_approval` already carries it).

## F13 (low): `doctor` JSON lists every skill in the user's home and plugin folders by name

- `workflow.py doctor --project` includes a `skill_inventory` object with each skill name and its source
  folder for both hosts (312 Claude Code and 303 Codex skills in this run). Users asked to paste doctor output into an issue
  would publish their whole skill and plugin list. Fix: report counts by default and names only with a flag.

## F14 (low): `gh project create` prints nothing in a non-TTY shell

- `gh project create --owner samykabu --title "sanduq-sandbox-ph04"` (gh 2.103.2, Git Bash) printed nothing;
  checklist M4 says it "prints the board URL". I found the number with `gh project list --owner samykabu
  --format json`. Fix: document `gh project create ... --format json --jq .number`.

## F15 (low): after adding the Bridge, doctor names three different fixes

- After `specify extension add speckit-superpowers-bridge --from .../speckit-superpowers-bridge.zip`, doctor
  reported `LEGACY_ALIAS_RECONCILIATION_REQUIRED: run the workflow installer`, five `DUPLICATE_STAGE_OWNER: ...;
  run "python .specify/extensions/workflow/scripts/reconcile.py --apply"`, `ALIAS_NOT_RESTORED: ...; run
  "python .specify/extensions/workflow/scripts/workflow.py host --use claude"` and `PROGRESS_HOOKS_DOUBLE_WIRED`
  (Spec Kit re-registered Progress's hooks).
- `install.py --apply --with-aliases --with progress` cleared all of them. prerequisites.md's Bridge section
  says only "Follow each project's README". Fix: say "then run `install.py --apply --with-aliases`" there, and
  have the doctor codes name that one command.

## F16 (low): Codex headless needs a dangerous flag for hooks; Codex clamps a hook and drops skills

- Checklist M9 asks to approve the guard in `/hooks`; `codex exec` cannot. `--dangerously-bypass-hook-trust`
  works, and doctor keeps warning `GUARD_HOOK_UNAPPROVED`. Document the flag for automation.
- Every Codex session reported `clamping SessionEnd hook timeout to 3s in <sandbox>/codex/.codex/hooks.json`.
  Progress writes `timeout: 10`. Write 3 for Codex.
- Every Codex session reported `Exceeded skills context budget. All skill descriptions were removed and 41
  additional skills were not included in the model-visible skills list.` Doctor's `SKILL_INVENTORY_LARGE`
  warns about this, but does not say managed commands may become invisible to Codex. The runs worked because
  the prompts named the command.

## F17 (low): "standard tier" needs a hand edit; Scope scored both T06 issues lite

- `.specify/workflow.yml` from `init` has no `profiles` section, so every feature runs the full stage list.
  Tiers need `profiles: {enabled: true}` added by hand (stages.md); `init` and `ci` have no flag for it.
- Scope scored #1 at 2 and #2 at 3 (lite); I set effort 5 as the owner to get the standard tier. Fix: an
  `init --profiles on` flag, and mention it in the Quick start if the README configuration assumes tiers.

## F18 (low): task sub-issue volume

- `full` board mode created 12 task sub-issues (#24 to #35) for #1, a four-file change, 6 for #2 and 4 for
  the lite #7. Each adds GitHub calls and board noise. Consider `minimal` as the Quick-start default for small
  repositories, or grouping tasks per phase.

## F19 (low): PR body for #9 does not close the issue

- PR #53 (managed #9) has no "Closes #9"; the other managed PRs do. The run's own summary noted it: "The PR
  body doesn't say "Closes #9", so merging won't close the issue automatically." PR Generate should always add
  the closing keyword for the bound issue.

## F20 (low): standard-tier T08 PRs do not commit `lifecycle.jsonl`

- `git ls-tree -r HEAD specs` on each PR head: PRs #23, #47, #52 and #53 contain `workflow/lifecycle.jsonl`;
  PRs #54 and #63 (managed standard, T08) contain `checkpoint.json` but not `lifecycle.jsonl`. The file is
  not ignored. The evidence record in the PR is incomplete for those two.

## F21 (low): an agent hand-edited the rendered gate workflow

- In PR #47 Codex changed `.github/workflows/sanduq-workflow-gates.yml` (`fetch-depth: ${{ ... + 1 }}` to
  `fetch-depth: 0`). managed-workflow.md says "Never edit the rendered workflow file by hand", and a later
  `install.py --apply` or `reconcile` would revert it. It fixed F1 for that PR only. The guard hook does not
  cover this file.

## F22 (low): a new repository has no self-hosted runner

- The `<runner-label>` runners are registered to one other repository, so this sandbox's `workflow-evidence`
  (PR #47) and `preview` jobs stay queued. The docs explain selecting self-hosted labels but not that a
  repository-scoped runner set must be registered for each new repository. No GitHub-hosted runner was used.

## F23 (low): Codex read an unrelated user-global plugin skill during a managed run

- In `x06-02` and `x06-04` Codex opened `~/.codex/plugins/cache/<third-party>/.../SKILL.md` and, in `x06-03`,
  reported checking that integration before continuing. User-global plugins are outside Sanduq's control, but
  an isolation note in install-by-host (Codex) would help reproducible runs.

## F24 (info): runtime and owner share one GitHub identity in a solo setup

- Clarify questions, SD1 decisions and the owner's answers are all comments by `samykabu`. The runtime told
  them apart correctly in every run (markers and answer syntax). Noted because it is the root of F2.

## Confirmed fixed from earlier rounds

- Walkthrough item 5: `DEPENDENCY_UNAVAILABLE` now names `install.py ... --apply` on a fresh install.
- Walkthrough items 3, 4 and 6: the checklist now gives `gh repo create`, the board commands and the
  `project_init.py --number ... --auto-create-columns` command, and they worked as written.
- A fresh clone of the committed install passes `doctor --project` without reinstalling.
