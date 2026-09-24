# Sanduq Delivery: installation and operation

This guide covers the Sanduq-managed, GitHub-issue-bound workflow. Ordinary
Spec Kit `speckit.specify` without a GitHub issue remains available. The native
Spec Kit workflow in `prototypes/sanduq-delivery/` is an isolated experiment;
Sanduq's receipt-based dispatcher is the production scheduler.
The choices below require workflow 1.3.0. Check the repository catalog for the
currently published version. Before the 1.3.0 release asset is published, use
the local package procedure in the root README for a disposable preview.

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
   because another catalog may publish the same extension ID:

   ```powershell
   specify extension catalog add --name sanduq --priority 10 --install-allowed https://raw.githubusercontent.com/samykabu/sanduq/main/catalog.json
   specify extension add workflow
   ```

3. In the agent session, invoke `/speckit-workflow-init`. It records the three
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

5. For an issue-bound feature, invoke `/speckit-workflow-scope <issue-number>`.
   The initial spec folder and branch derive from the issue number and title,
   for example `specs/42-fix-checkout-timeout` and `42-fix-checkout-timeout`.
   The Git extension hook creates that branch when installed; otherwise Sanduq
   creates it during `workflow.py prepare --issue 42`.
   An existing feature retains its saved identity after an issue title edit.

## Existing codebase without Spec Kit

Use an isolated branch or worktree and a reviewed backup of `.specify/`, agent
skills, and `.github/workflows/` before initialization. Inspect the working tree
and existing CI/project conventions. Then initialize in place with
`specify init --here --integration codex` or `claude`. The interactive CLI may
ask to merge into a nonempty directory; use `--force` only after reviewing its
overwrite scope. Inspect `git diff` afterward, then follow greenfield steps
2–4. Do not discard a constitution, custom CI workflow, agent skills, or
existing project metadata just to make the installer pass. Use
`install.py --preserve-ci` when the existing workflow-evidence file is project
owned, and select the gate mode that matches that decision.

## Existing Sanduq installation

Inspect active feature checkpoints and outstanding GitHub writes before an
upgrade. Resolve active claims, then use the transactional upgrade path:

```powershell
python .specify/extensions/workflow/scripts/upgrade.py --version 1.3.0 --preserve-ci
python .specify/extensions/workflow/scripts/upgrade.py --version 1.3.0 --preserve-ci --apply
python .specify/extensions/workflow/scripts/workflow.py doctor --project
```

Replace `1.3.0` with the verified published version. `--preserve-ci` retains
a customized gate file and is inappropriate if the selected mode is disabled
while that file still runs. Preview, backup, and compare before any managed
reset. If an older install has no active claims or unmapped project data, a
clean Spec Kit reinitialization may be simpler; remove managed files only after
the backup and ownership diff are complete. Preserve feature artifacts, Project
IDs, manual audience maps, QA evidence, and customized workflows. Review and
migrate existing checkpoints; installation alone does not certify old receipts
against new policy or code.

## Issue decisions and Project status

Material questions raised by Tasks, Analyze, or another managed stage are
posted to the bound GitHub issue with stable IDs such as `SD1`. A reviewer
answers in a new comment, e.g. `SD1: A`. The issue creator, an authorized
reviewer named in policy, or a repository owner/member/collaborator may answer.
Conflicting answers, edits, missing application evidence, or a failed GitHub
read block a passed stage. The agent applies the chosen answer to actual
artifacts and records their hashes in `workflow/decisions.json`; future changes
reopen the check. `decisions.py sync --project-field` refreshes the issue record
and its separate Project Decision field. It does not move Project Status.

Operators can update the reviewer list or field name in policy:

```powershell
python .specify/extensions/workflow/scripts/workflow.py decisions --owner reviewer1 --owner reviewer2
python .specify/extensions/workflow/scripts/workflow.py decisions --show
```

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

Run `/speckit-assure-init` only after QA is selected and no valid QA configuration
exists. Run `/speckit-user-manual-init` only after the manual is selected and no
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
