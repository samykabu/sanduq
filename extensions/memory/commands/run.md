---
description: Archives selected verified feature folders into project memory through a checkpoint, a reviewed delta candidate and a scoped final commit. Use when asked to "archive the feature" or "run the memory archive", or when the session handoff returns speckit.memory.run.
---

# Archive feature specifications

User arguments: `$ARGUMENTS`.

Work only in the configured project checkout. No push, PR creation, stash, reset, clean, broad
staging, automatic rollback or implicit verification bypass; with `guard_hooks` on, a hook also
refuses those git verbs and any write under `specs/memory/` while a run is active. Helper results
are JSON with `success`; a nonzero exit is a blocker, never a successful no-op, and its `error`
names the rule that stopped you. `A` means `python .specify/extensions/memory/scripts/archive.py`.
Read each reference only at the step that names it.

## Procedure

1. **Select.** Read `.specify/memory-policy.json`. Select exact feature directories: an explicit
   list, or `--all-completed` for freshly verified features (skipped ones are reported). Retiring
   unfinished work is a separate explicit `--retire-reason` with named checks and never part of
   automatic or all mode. Never select this extension's own unfinished feature, and never infer
   completion from numbers, merge status, a plan or checked boxes alone.
2. **Confirm completion.** On the configured target branch, inspect the actual implementation,
   the required QA, review and manual results, unfinished concerns and any external or submodule
   evidence. Never assert completion for convenience. Missing infrastructure is a blocker;
   external uncommitted code is never verified.
3. **Preflight** once completion is real: `A preflight --spec <path> --check <name>` with the
   selected checks; continue when `data.ok` is true. Fix missing inputs, coverage, configuration,
   ignore and scope failures before verification; keep `repair-required` references and pending
   candidate guards as inputs to synthesis.
4. **Verify.** `A verify --spec <path> --complete --check <name>` with every relevant approved
   check; it runs the checks and binds their results to the exact evidence. Pass each enumerated
   uncommitted related implementation file as `--related` here and in step 5, never in automatic
   mode. Only when the owner explicitly asks for `--skip-verification`, read
   `.specify/extensions/memory/references/verification-override.md` and follow it instead.
5. **Prepare.** `A prepare --spec <path> --check <name>` with the same selection and check options
   (`--automatic` only for approved ready queue entries). It makes the checkpoint commit,
   inventories the content and returns `run_id`, the candidate and journal paths and
   `memory_format`. When it also returns a `reference`, read that file and author its shape in
   steps 7 and 8 instead of the delta below.
6. **Read inputs.** `A inspect --run <id> --view status`, then `inventory`, `checks` and
   `coverage` as needed; follow `next_cursor` with `--cursor`, and on `oversized_record` raise
   `--max-bytes` or read that unit from the checkpoint. Read the journal's `references`,
   `checkpoint`, `base_memory_root` and scope when needed. Read existing memory only through
   `A memory query --path <code-or-dir> --route "<VERB /path>" --error-code <code> --domain <id>
   --text "<words>" [--cursor <c>]` (ranked whole entries), `A memory show --id PM-…`,
   `A memory catalog --domain <id> [--page N]`, `specs/memory/INDEX.md` and
   `A memory provenance --id PM-…`; never load `specs/memory/` wholesale. Read implementation and
   test evidence at the checkpoint.
7. **Author.** Read `.specify/extensions/memory/references/candidate-v2.md` and write only
   `candidate.json` in the run directory, as a delta; never edit `specs/memory/`, the registry or
   feature files. For a large run (many units or domains), read
   `.specify/extensions/memory/references/large-runs.md` and draft in packets instead.
8. **Candidate guards.** `A preflight --run <id>` until `data.candidate_guards` is `passed`; each
   failure names the rule to fix.
9. **Review and publish.** Read `.specify/extensions/memory/references/review-and-publish.md`:
   arrange the independent review, then run `A status` and do what `data.next` says until the run
   is `done`.
10. **Report** the exact checkpoint and final commits and the archived or skipped features.

When a step is blocked or the run is interrupted, read
`.specify/extensions/memory/references/recovery.md`. While a run is active, `pending --gate` must
pass before any new specification, branch or broad commit workflow. An explicit manual `run`
authorizes the selected archive only; never expand its scope.
