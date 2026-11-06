# When each extension runs

Sanduq's extensions run in one of two ways. On a plain Spec Kit project, each extension hangs
[hooks](../reference/glossary.md#hook) on the Spec Kit phases and runs when the phase does. Under
the [managed Workflow](../reference/glossary.md#managed-workflow), the dispatcher turns off the hooks it
owns and runs the same commands as numbered stages, one claim at a time. Same extensions either way.
The difference is who starts them, and what happens when work has to be redone.

This page shows both views, then follows one feature from issue to merge.

## On a plain Spec Kit project: hooks

![Hooks on the Spec Kit lifecycle: Specify, Clarify, Plan, Tasks, Analyze and Implement, with the mandatory and optional extension hooks before and after each phase, the Memory archive and User Manual release commands after merge, and two loops: Analyze back to Plan when it finds a gap, and Implement back to itself when a fix after review feedback or a failed check is run through Implement again.](../diagrams/lifecycle-overlay.animated.svg)

[Editable source](../diagrams/lifecycle-overlay.html). The [hooks reference](../reference/hooks.md)
has the same data as a table.

Solid chips run without asking. Dashed chips are optional: your agent asks before it runs them, unless
an init command made them mandatory. Assure Init does that for QA analysis in integrated mode, and
Project Init does it for board sync in required mode.

Two things send you back up the diagram:

- **Analyze finds a gap.** `/speckit-analyze` reports; it does not fix. You correct the spec, plan or
  tasks and run it again. Memory's impact hook runs again with it.
- **Review feedback or a failed check after Implement.** Hooks only fire when their phase runs. A fix
  made by hand, or with `/speckit-pr-review-feedback`, does not run them. Run `/speckit-implement`
  again so the after-implement hooks refresh the QA walkthrough, the manual pages and the PR text, or
  run the commands you need yourself, such as `/speckit-assure-document` and
  `/speckit-user-manual-update`. PR checks that the installed QA and manual documentation is current
  before it touches the pull request, so a skipped refresh shows up there.

## Under the managed Workflow: stages

![Managed Workflow stages from Scope to After merge, with the command or extension that does each stage's work, and seven numbered paths that send work back: Clarify waits for answers; Analyze returns a gap to Plan; revalidate-upstream after a mid-build spec edit; failed checks and blocking review findings return to Execute; failed CI and PR review comments are fixed on the branch and revalidated from Verify; and a change after Verify revalidates Verify, Review and Ready.](../diagrams/workflow-stages.animated.svg)

[Editable source](../diagrams/workflow-stages.html). Stage details are in [stages](../workflow/stages.md);
the dashed QA and manual stages run only when you selected them at init, and never on the `lite`
tier. When a GitHub Project board is configured, Project sync moves the feature's card after a stage
completes, and before implementation starts. When Memory is installed and its policy approved, the
dispatcher runs its session step at every claim, its impact check before Analyze, and its archive
steps when Execute completes and after merge.

Each stage needs recorded results before the next one starts. A stage passes on its
[receipt](../reference/glossary.md#receipt). Edit one of the receipt's inputs later and it goes stale.
The numbered paths:

| Path | What happened | What runs again |
| --- | --- | --- |
| 1 | Clarify asked questions | With GitHub clarification, nothing until they are answered on the issue; `/speckit-workflow-clarify` rereads it, edited comments included. With local clarification, the questions are asked in the session. |
| 2 | Analyze found a blocking gap | The owning Specify, Plan or Tasks stage fixes it, then Analyze runs again. A real ambiguity becomes a decision question on the issue and the stage waits for the answer. |
| 3 | The spec or plan was edited after its stage passed | With no active claim, `workflow.py revalidate-upstream --through <stage> --plan` lists the stale stages and their changed inputs. You review each change, give evidence per stage, and one `--receipt` call re-records them in order. A change to Scope's inputs needs a new Scope claim instead. |
| 4 | Verify failed | Execute fixes it, then Verify runs again. |
| 5 | Review found a blocking issue | Execute fixes it, then Verify and Review run again. |
| 6 | Code changed after Verify | Verify, Review and Ready are revalidated before Finalize opens the PR. A change the affected-lane hook maps to no lane, such as Markdown, leaves them current. |
| 7 | CI failed, or a reviewer left comments | `/speckit-pr-review-feedback` sorts the comments first: some need only a reply, and a product question needs your answer. Approved fixes are made on the branch, the affected checks run again, Verify, Review and Ready are revalidated, and the PR is updated. |

Going back to an earlier stage can remove the receipts of the stages after it. When it would, the
claim stops and lists them, and you confirm before that rework starts. The
[recovery reference](../../extensions/workflow/skills/workflow/references/recovery.md) has the exact
commands for each case. The `lite` [tier](../workflow/stages.md#profiles-and-tiers) runs Scope,
Specify, Clarify, Plan, Execute, Verify and PR only, so paths 2, 5 and 6 fold into Plan and Verify.

## One feature, start to merge

The feature below is made up. It uses the [synthetic booking application](../README.md#example-conventions)
the rest of these pages use: issue 412, **Refund approval**, in `example-org/booking-app`. The point is
the order things happen in, and where the work goes back.

The project is set up for the full stage list: profiles off, a GitHub Project board in `full` mode
with task sub-issues, QA and the user manual selected, the manual already initialized, and Memory
installed with its policy approved. It ran Workflow init once:

```text
/speckit-workflow-init Enable QA and User Manual. Use our existing GitHub Project and an advisory managed-only evidence gate.
```

**1. Start from the issue.**

```text
/speckit-workflow-scope 412 Assess refund approval and continue through implementation. Stop before PR creation.
```

Scope reads the issue, checks prerequisites and decides whether 412 is one feature or several. Specify
writes `specs/412-refund-approval/spec.md`. Before it does, Memory's session step finishes any archive
work an earlier feature left behind. After each stage completes, Project sync moves the card on the
board.

**2. Clarify stops and waits (path 1).** The spec cannot say whether an operator may approve a refund
they requested themselves. Workflow posts the question on issue 412 and stops; it does not guess.
The product owner answers on the issue the next morning:

```text
/speckit-workflow-clarify Reread issue 412's answers and continue.
```

**3. Plan, tasks and the two analyses.** Plan designs the approval endpoint and the settlement call.
Tasks produces phased task IDs. Because QA was selected, `assure.analyze` adds the tests the task list
was missing: a second approval must not settle twice, a rejection needs a reason, and the approval
screen needs keyboard access. Because the manual was selected, `user-manual.analyze` adds a task to
update the operator guide's refund page.

**4. Analyze passes, task issues appear.** Analyze checks spec, plan and tasks against each other, and
Memory's impact step checks them against current project memory. Then each task becomes a sub-issue
under 412.

**5. Execute, then review sends it back (path 5).** The orchestrator hands tasks to workers in
conflict-free batches and keeps the [progress report](../extensions/progress.md) live. Verify runs the
tests and they pass. Review then finds that two operators approving the same refund at the same moment
can both reach the payment provider. That is a blocking finding. The feature goes back to Execute, a
worker adds an idempotency key, and Verify and Review run again on the new code.

**6. QA walkthrough, manual page, Ready.** `assure.document` writes the tester walkthrough from the
recorded test results. `user-manual.update` rewrites the operator's refund page and
builds a private preview. Ready confirms every required task is done, the evidence is current, and no
blocking finding is open.

**7. The pull request.**

```text
/speckit-workflow-finalize Create the PR for issue 412 with the verified results and inline diagrams.
```

PR writes the description from the feature's own files and the recorded checks, with Illustrate
diagrams rendered inline.

**8. A reviewer asks for a change (paths 7 and 3).** The reviewer wants the rejection reason to be a
fixed list, not free text. First, sort the open comments:

```text
/speckit-pr-review-feedback example-org/booking-app#438 Classify the open feedback and show me the fix and reply plan before changing anything.
```

The plan marks the rejection-reason comment as a spec change and another comment as needing only a
reply. You approve it. The spec edit makes the later stages stale, so `revalidate-upstream` lists them
and re-records them once you have reviewed each change. The code fix is made on the branch, the
affected checks run again, the walkthrough and manual page are refreshed, Verify, Review and Ready are
revalidated, and the PR is updated.

**9. Merge and after.** The scope prompt stopped before the PR, so merging needs its own instruction:

```text
Continue on this PR: fix failing checks, address review findings, and merge when required checks and approvals pass.
```

Your agent fixes failing checks and merges once required checks and approvals pass. Workflow's part
is narrower: it reads CI on the exact PR head, reports when the PR is ready to merge, and verifies the
merge afterward. After the merge, Memory archives the feature into project memory. At the next application release,
`/speckit-user-manual-release` builds the approved manual editions in the formats your renderer is
set up for: Markdown by default, or an MkDocs site and PDF.

If the session ends partway, `/speckit-workflow-continue` picks up from the last receipt after checking
which worker results already landed.

## Limits

- A hook only runs when its phase runs. If you edit code outside Spec Kit, run the extension's command
  yourself, or use the managed Workflow, which notices the drift.
- Product questions are yours. Clarify waits for the answer.
- Memory and Project sync do something only when they are installed and configured. Workflow never
  turns them on for you.
- Merge and deployment each need your explicit permission. Local tests passing does not count as CI
  passing.

## Related

- [Commands](../reference/commands.md), with an example for each one
- [Worked managed lifecycle](../workflow/lifecycle.md), with a prompt for every stage
- [Operating guide](../workflow/operating-guide.md): resume, upgrade and recover
