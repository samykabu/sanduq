# Sanduq Delivery: installation and operation

This guide covers the Sanduq-managed, GitHub-issue-bound workflow. Ordinary
Spec Kit `speckit.specify` without a GitHub issue remains available. Sanduq's
receipt-based dispatcher is the production scheduler.
For prerequisites and current installation, see [Getting started](../start/install-by-host.md). Published versions live in the [catalog](../../catalog.json); local package testing is in [Contributing](../../CONTRIBUTING.md#test-a-local-package).

## Choose processes and gate policy

The project makes three independent choices at initialization:

| Choice | Values | Fresh project default |
| --- | --- | --- |
| QA Assure | `on`, `off` | Explicit choice required |
| User Manual | `on`, `off` | Explicit choice required |
| Workflow evidence CI gate | `disabled`, `advisory`, `required` | `advisory` |

`managed-only` is the gate's default scope. A PR without changed `specs/<feature>/`
evidence or an explicit feature mapping returns `not_applicable` successfully.
An ordinary source-only bug fix therefore does not need a spec or feature receipt.
Choose `all-prs` only when every PR must have a feature mapping. A required gate
can block a managed PR; advisory prints findings and succeeds; disabled installs
no Sanduq workflow-evidence job. These modes do not control your project's build,
test, security, or review jobs.

Rule names for repeated `--gate-rule NAME=on|off` selections:
`receipts`, `decisions`, `tasks`, `task_links`, `documentation`, `portability`,
`candidate_merge`, `live_answers`. `task_links` requires `tasks`;
`portability` and `candidate_merge` require `receipts`; `live_answers` requires
`decisions`. A fresh policy selects receipts, decisions, documentation,
portability, and live answers. Existing policies without a `ci.gate` section
retain the prior required, all-PR evidence behavior until deliberately changed.

## Greenfield project

1. Create a Git repository with a GitHub origin and initialize Spec Kit using
   the actual agent integration:

   ```powershell
   specify init --here --integration codex
   # or: specify init --here --integration claude
   ```

2. Add Sanduq's catalog, then its workflow package. Check the selected source
   because the community catalog publishes unrelated `scope` and `memory` extensions
   ([which catalog wins](../start/install-speckit.md#if-you-keep-spec-kits-default-catalogs)):

   ```powershell
   specify extension catalog add --name sanduq --priority 1 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
   specify extension add workflow
   ```

3. In the agent session, invoke `$speckit-workflow-init`. It records the three
   selections, runner labels and capabilities, and any explicit decision-reviewer
   GitHub logins. The equivalent policy command is:

   ```powershell
   python .specify/extensions/workflow/scripts/workflow.py init --qa off --manual off --gate-mode advisory --gate-scope managed-only
   ```

   To select individual rules, add e.g. `--gate-rule tasks=on`. To select team
   decision authority, repeat `--decision-owner LOGIN`. The issue creator and
   repository owners, members, and collaborators are accepted by default.

4. Preview and apply the supported installer, then configure the Project board
   and verify it:

   ```powershell
   python .specify/extensions/workflow/scripts/install.py
   python .specify/extensions/workflow/scripts/install.py --apply
   python .specify/extensions/workflow/scripts/workflow.py doctor --project
   ```

   The installer supplies only selected QA/manual dependencies, backs up
   managed files, and rolls back on a failed install. Run Project Init when
   no valid board configuration exists. Project Status stays the lifecycle
   column; Sanduq uses a separate single-select Decision field with `None`,
   `Waiting`, `Needs review`, and `Applied` options.

5. For an issue-bound feature, invoke `$speckit-workflow-scope <issue-number>`.
   The initial spec folder and branch derive from the issue number and title,
   for example `specs/412-refund-approval` and `412-refund-approval`.
   The Git extension hook creates that branch when installed; otherwise Sanduq
   creates it during `workflow.py prepare --issue 412`.
   An existing feature retains its saved identity after an issue title edit.

## Existing codebase without Spec Kit

Use an isolated branch or worktree and a reviewed backup of `.specify/`, agent
skills, and `.github/workflows/` before initialization. Inspect the working tree
and existing CI/project conventions. Then initialize in place with
`specify init --here --integration codex` or `claude`. The interactive CLI may
ask to merge into a nonempty directory; use `--force` only after reviewing its
overwrite scope. Inspect `git diff` afterward, then follow greenfield steps
2–4. Do not discard a constitution, custom CI workflow, agent skills, or
existing project metadata to make the installer pass. Use
`install.py --preserve-ci` when the existing workflow-evidence file is project
owned, and select the gate mode that matches that decision.

## Existing Sanduq installation

Inspect active feature checkpoints and outstanding GitHub writes before an
upgrade. Resolve active claims, then use the transactional upgrade path:

```powershell
python .specify/extensions/workflow/scripts/upgrade.py --version <published-version> --preserve-ci
python .specify/extensions/workflow/scripts/upgrade.py --version <published-version> --preserve-ci --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

Replace `1.4.0` with the verified published version. `--preserve-ci` retains
a customized gate file and is inappropriate if the selected mode is disabled
while that file still runs. Target 1.4.0 or later with `--preserve-ci`: on a
clone or worktree without the local `install-receipt.json`, a 1.3.0 target
rolls back with `CI_WORKFLOW_STALE` (#22). Preview, backup, and compare before any managed
reset. If an older install has no active claims or unmapped project data, a
clean Spec Kit reinitialization may be simpler; remove managed files only after
the backup and ownership diff are complete. Preserve feature artifacts, Project
IDs, manual audience maps, QA evidence, and customized workflows. Review and
migrate existing checkpoints; installation alone does not certify old receipts
against new policy or code.

## Issue decisions and Project status

Material questions raised by Tasks, Analyze, or another managed stage are
posted to the bound GitHub issue with stable IDs such as `SD1`, as a task list
with every box unticked. A reviewer ticks the box (one for a single-choice
question, one or more for a multiple-choice one) or replies in a new comment,
e.g. `SD1: A` or `SD1: A, C`. A ticked box records no author, because GitHub
does not say who ticked it. The recommended option carries a `(Recommended)`
suffix and is never pre-ticked. The issue creator, an authorized
reviewer named in policy, or a repository owner/member/collaborator may answer.
On a public repository that default is unsafe: anyone who opened the issue can
answer the decisions on it, so set `decisions.authorized_users` there and
treat the creator rule as a private-repository convenience. A comment a Sanduq
process posted through the shared `gh` transport (logged in
`.specify/workflow/runtime/posted-comments.jsonl`) is never an answer, nor is a
comment older than the question; both are listed under the decision's
`unparsed` with the reason. `SD1: B.`, `SD1 - B`, `SD1 = B` and `SD1: B - a
note` all count; a reply that names a question without such a line (for
example `I pick B for SD1`) is reported under `unparsed` with its URL instead
of being ignored.
Conflicting answers, edits, missing application evidence, or a failed GitHub
read block a passed stage. The agent applies the chosen answer to actual
artifacts and records their hashes in `workflow/decisions.json`; future changes
reopen the check. Each receipt depends only on the decisions that existed when
it was recorded, so a decision raised late (for example the User Manual module
map at Execute) stales no earlier stage; a changed answer to a decision a stage
already saw still does. Receipts recorded before this rule keep a byte hash of
the whole ledger until their stage is recorded again. `decisions.py sync --project-field` refreshes the issue record
and its separate Project Decision field. While a decision is pending or in
conflict, an issue in mapped Backlog or Feature Specification status moves to the mapped
Need Clarifications status. When nothing is pending it moves back only if
Decisions moved it and `clarification.resume_on_reinvoke` is `reread-answers`.
Any other status is never changed. Set `decisions.lifecycle_status: false` to
turn this off. Questions posted by an earlier release can be made selectable
with `decisions.py upgrade-questions`; it keeps IDs, options and replies and
never ticks a box.

With `clarification.transport: local` (frozen on the feature's checkpoint at
Scope start), `decisions.py ask` writes the question to
`specs/<feature>/clarifications.md` instead of the issue, the agent asks the
user in the conversation and records only their reply there (`SD1: B`), `sync`
reads that file with the same grammar and writes the ledger only (`source:
local`, the answer line kept as `quote`), and the Project field and status are
never touched. The Clarify stage records its `C<round>Q<n>` questions and
replies in the same file and lists it in the receipt; the receipt carries
`self_attested` and the CI gate warns `CLARIFICATION_SELF_ATTESTED`, because
no GitHub record vouches for a reply the agent transcribed.

Operators can update the reviewer list or field name in policy:

```powershell
python .specify/extensions/workflow/scripts/workflow.py decisions --owner reviewer1 --owner reviewer2
python .specify/extensions/workflow/scripts/workflow.py decisions --show
```

## Optional hook keys

Two optional sections in `.specify/workflow.yml` control extension hooks. Leave them out to keep
the current behaviour; an unknown key or a wrong type stops the workflow with
`PROGRESS_POLICY_INVALID` or `ILLUSTRATE_POLICY_INVALID`.

```yaml
progress:
  hook_wiring: speckit      # speckit runs through Spec Kit's dispatcher; native runs scripts/hook.py directly
                            # unset: new Progress installs get native; existing installs keep their wiring
  post_tool_matcher: ""     # tools the per-tool-call hook matches; "" (default) matches every tool
illustrate:
  hooks:
    self_check: false       # true checks every written diagram HTML (self_check, geometry, theme)
```

The Workflow installer applies the `progress` keys; see [Progress](../extensions/progress.md) and
[Illustrate](../extensions/illustrate.md). These keys change no stage, so editing them never
invalidates receipts.

## Small bug fixes and other work outside Sanduq features

Use a normal Git branch, run the relevant product tests, and open a normal PR.
No `specs/` folder, task sub-issues, QA walkthrough, or manual update is
required merely because Sanduq is installed. A required `managed-only` gate
reports `not_applicable`; your other CI and review policies still apply. If the
change genuinely belongs to an existing managed feature but edits source only,
commit `.specify/workflow/pr-features.json` with the exact affected feature
paths, refresh its receipts, and run the selected checks. Do not use that map to
hide changed spec evidence. If the project opted into `all-prs`, change the
project policy through review or provide a valid feature mapping before the PR.

## QA Assure and User Manual later in the lifecycle

Use `init --replace` for a reviewed process selection change, preview installer
changes, apply, then migrate active feature checkpoints after resolving claims:

```powershell
# Add both later
python .specify/extensions/workflow/scripts/workflow.py init --qa on --manual on --replace
python .specify/extensions/workflow/scripts/install.py
python .specify/extensions/workflow/scripts/install.py --apply

# Opt out of QA while keeping the manual
python .specify/extensions/workflow/scripts/workflow.py init --qa off --manual on --replace
python .specify/extensions/workflow/scripts/install.py
python .specify/extensions/workflow/scripts/install.py --apply
```

Run `$speckit-assure-init` only after QA is selected and no valid QA configuration
exists. Run `$speckit-user-manual-init` only after the manual is selected and no
approved module map exists; its audience/language interview remains a human
decision. Each selection can be reversed independently. Opting out removes its
future workflow stages and selected checks; historical artifacts are preserved,
and installed domain commands may remain available for standalone use. Review
the policy migration's invalidation list before resuming a feature.

## Changing the CI gate later

Use `workflow.py ci` to change mode, scope, rules, runner labels, or Python
provisioning; preview and apply `install.py` to render the selected workflow.
For example:

```powershell
python .specify/extensions/workflow/scripts/workflow.py ci --gate-mode required --gate-scope managed-only --gate-rule tasks=off --gate-rule task_links=off
python .specify/extensions/workflow/scripts/install.py
python .specify/extensions/workflow/scripts/install.py --apply
```

Disabling a previously installed job checks active GitHub branch rules for a
stale required `workflow-evidence` check and stops if it would strand PRs.
Update the branch rule through repository governance first, then rerun the
installer. Runner-only policy changes have a separate digest and do not
invalidate feature delivery receipts. The optional `candidate_merge` rule runs
against GitHub's PR merge ref and checks both parents against the base and head
SHAs; `live_answers` rereads the GitHub issue during CI. A successful
`not_applicable` status never certifies feature evidence.

### One-off rule waiver

An applicable managed PR may waive one failing evidence rule through a current
GitHub PR comment from a configured decision reviewer or repository
owner/member/collaborator other than the PR author. The comment must name the
exact PR number, feature path, rule, current 40-character PR head SHA, reason,
and UTC expiry date. Example:

```text
<!-- sanduq-gate-waiver {"version":1,"pr":7,"feature":"specs/7-bug","rule":"tasks","head_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","expires":"2026-10-01","reason":"Known split task"} -->
Reason: Known split task
```

The CI job reads the PR discussion and reports every accepted waiver. An
author-only, expired, wrong-feature, or old-head comment cannot waive a rule.
Identity and issue binding checks cannot be waived. A new commit changes the
head SHA and requires fresh approval. Ordinary non-managed PRs need no waiver.
When no waiver is accepted, `WAIVER_NOT_VERIFIED` lists each rejected waiver
comment and why, for example `waiver is for head <old>, the PR head is now <new>`.
A comment by the PR author is rejected with `written by the PR author`.

#### Waivers in a one-person setup

When you work alone, the agent opens every PR with your GitHub token, so you
are always the PR author and the author rule refuses every waiver you post. To
waive your own PRs, list your login on the target branch:

```yaml
decisions:
  self_waivers: [your-login]
```

The gate then accepts a waiver comment from a listed login on a PR that login
authored. All other checks still apply: exact PR, feature, rule, current head
and expiry.

Threat model. GitHub cannot tell you from an agent that uses your token, so
this opt-in trusts every waiver comment written under your login. Sanduq keeps
the agent from using it in three ways:

- The gate reads `self_waivers` from the base branch policy (`--trusted-root`),
  so a PR cannot add its author to the list. You add it in a change you merge
  yourself.
- The guard hook refuses any `gh`, `curl` or `wget` command that carries a
  `sanduq-gate-waiver` marker, inline or in a `gh --body-file`, in every
  session. Post waivers yourself in the GitHub web page.
- A waiver binds the current head SHA, so any later commit needs a new one.

The guard is advisory: it sees only the host's shell tools, so a script the
agent writes and runs another way is not covered. If that risk matters, leave
`self_waivers` empty and give waivers from a second account (a reviewer or a
bot identity that the agent's token cannot use).
