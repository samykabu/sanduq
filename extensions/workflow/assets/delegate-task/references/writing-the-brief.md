# Writing the brief

The text you pass to `--task` is the whole job as the delegate will see it. It runs in a fresh
process with no memory of your conversation and no access to your notes — only your text and what
it can read from the working tree.

The driver wraps that text in an envelope: objective, working directory, policy constraints,
deliverable, and the required result block. **The envelope is scaffolding, not the brief.** It
cannot know your project. You supply the substance.

If a constraint is not in the brief or discoverable in the repo, it does not exist for the
delegate. Nearly every disappointing delegation traces back to assumed context.

## Name the real gate commands

The single highest-value thing you can put in a brief is the project's *actual* test, lint and
build commands. Read `CLAUDE.md` / `AGENTS.md` / `Makefile` / `package.json` and copy them in
verbatim. "Run the tests" produces a delegate that guesses, or skips.

Pair that with the inverse: what to **leave untouched**. Scope creep is the most common quality
problem in delegated work, and a named exclusion list is the cheapest defence.

## A shape that works

Agent CLIs respond better to short labelled blocks than to flowing prose:

```text
The job: one or two sentences — what is broken, where it lives, what "fixed" means.
Current state: what exists now, and anything surprising about it.
Change: what to do.
Leave alone: the files, modules or behaviours that must not move.
Gates: <the project's real commands>, run them and fix what they surface.
Report: what changed and why, files touched, gate output with counts, anything you decided
        that the brief did not settle.
```

Add more only when the task needs it:

- **Debugging** — say "resolve it fully; do not stop at the first plausible fix", and "if a repo
  fact is missing, find it or say it is unknown — do not guess".
- **Read-only review** — pass `--sandbox` and ask for every claim to be tied to evidence, with
  inferences labelled as inferences.
- **Research** — ask for observed facts, inferences and open questions kept separate.

## One task per dispatch

*"Review this, fix what you find, update the docs, and suggest a roadmap"* produces a muddled run
and an unreviewable change. Split it. One brief → one run → one reviewable diff keeps `files_mismatch`
meaningful and lets a later task assume the earlier one landed.

## Premises freeze at dispatch

There is no steering channel mid-run. Audit the facts in the brief before sending — the branch, the
ownership, the constraints, anything a judgment call rests on.

If a premise turns out wrong while the run is live, **stop it and re-dispatch** rather than
discounting the output afterwards. For a write-capable run, inspect the working tree first and
reconcile any partial or premise-contaminated edits.

## What the envelope already covers — don't repeat it

The envelope already tells the delegate to finish without asking, stay in the working directory,
not commit, run the project's gates, and close with the result block. Restating those costs tokens
and buys nothing.

**One exception.** If the repo forbids something in code — particular comment conventions, process
language, test idioms — restate the load-bearing rules. Compliance is only as good as what is in
front of the model.

## Expect noise around the report

The final message may carry more than you asked for: a banner from the repo's own agent
instructions, output from an MCP tool the delegate has configured. That comes from the delegate's
environment, not the driver. The result block is the defence — it is found regardless of what
wraps it.

## A worked example

```bash
node "$DELEGATE" start \
  --harness codex --cwd /path/to/repo --timeout 1800 \
  --deliverable "Apply the change in the working tree. Do not commit." \
  --constraint "Touch only services/billing/refund.py and its tests." \
  --task 'The job: in services/billing/, the refund path double-charges when a refund is retried
after a network timeout. The idempotency key is not checked before re-submitting.

Change: make refund submission idempotent — look up an existing refund by idempotency key
before creating a new one.

Leave alone: the charge path, the API routes, and the data models.

Gates: run `pytest tests/billing/ -q` and `ruff check services/billing/` and make both green.
Confirm git status shows only refund.py and its test file changed.

Report: root cause and your fix, files touched, pytest and ruff counts, and anything you
decided that this brief did not settle.'
```

Then review what comes back — see [reviewing-the-result.md](reviewing-the-result.md).
