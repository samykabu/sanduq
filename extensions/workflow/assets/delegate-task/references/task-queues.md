# Running a queue of tasks

The single-task loop scales to a queue, and that is where delegation pays off most — a migration,
a mechanical refactor, a removal split across layers. What makes a queue trustworthy is sequencing
and bookkeeping, not parallelism.

## Run sequentially, land each before the next

Resist fanning the whole queue out at once. Run tasks **one at a time, in dependency order**,
reviewing each before dispatching the next:

- **Later tasks assume earlier ones landed.** Task 3's brief can say "the helper added in the
  previous step exists" only if it actually does.
- **One reviewable change per task** keeps history legible and any single step revertible.
- **Each measurement stays honest.** The driver fingerprints the tree at dispatch, so
  `dirty_paths_changed` shows only *this* task's changes. Pile three tasks into one dirty tree and
  the delta still works, but the review no longer maps to one brief.

Parallelism is occasionally worth it for genuinely independent tasks on separate files — the
background model makes it easy: several `start` calls, then `list`. It costs the
clean-tree-per-task property, so default to sequential.

## Two ways to carry context, and they are not interchangeable

| Mechanism | Carries | Use when |
|---|---|---|
| `--resume <run_id>` | the delegate's own session | reworking **the same** task |
| a restated line in the next brief | one decided fact | a **different** task depends on it |

Implementation surfaces facts the plan did not have: a helper got named, a fixture landed
somewhere, an interface was chosen. When a later task depends on one, fold it into that task's
brief explicitly.

Do not reach for `--resume` to avoid restating a constraint across different tasks. It drags the
entire prior context along — the resume run in this skill's own verification cost 136,935 tokens
against 66,576 for the fresh one — and it couples two tasks that should review independently.

## Keep a progress file

For anything longer than two or three tasks, maintain one progress file alongside the work. It is
the durable record that survives your own context limits:

- **Status table** — each task: queued / dispatched (`run_id`) / reviewed and landed.
- **Per-task notes** — what landed, what you verified, the gate outcome.
- **"Needs your eyes"** — decisions the delegate made, nitpicks, anything to be overruled. This is
  the section a human reads first.
- **End-of-run checklist** — what happens after the last task.

Update it as each task lands, not in a batch at the end. If the run is interrupted, the file is
still accurate.

Record the `run_id` for every dispatch. `node "$DELEGATE" list` then gives you status, provenance and
token totals across the whole queue — which is also how you find out what it cost.

## Close with a coherence check

Per-task review proves each step in isolation; it does not prove the steps cohere.

- Run the full test and build once more on the final tree, not just the last task's slice.
- Do a repo-wide check for the thing the queue was about: after a removal, grep for survivors;
  after a rename, confirm no stragglers.
- For schema work, replay all new migrations from a clean state and check for drift.

## When to stop and ask

Proceed without asking on anything that follows from the agreed plan — that is the point of the
queue. Stop and surface when:

- A task cannot be completed correctly within its brief's scope. A scope change is the human's call.
- A review calls the **plan** into question, not just the implementation.
- The gates reveal a problem affecting tasks already marked done.
- Any run returns `head_changed: true`, `files_mismatch: true`, or a non-zero `records_dropped` —
  stop the queue and look before dispatching anything else into that tree.

Then report where you are, what has landed, and what the open question is — and wait. A queue that
quietly works around a broken assumption produces a lot of changes in the wrong direction.
