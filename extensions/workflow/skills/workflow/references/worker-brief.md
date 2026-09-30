# worker-brief

Not a claimed stage; a utility entry point (B13, retrospective F10, F11, T0,
T1, T7, S6) that generates one task's brief instead of handing a worker the
full spec/plan/tasks/contracts set (measured at ≈44K tokens of orientation
per worker, T1).

Run:

```text
python .specify/extensions/workflow/scripts/worker_brief.py --root <repo> \
  --feature specs/<feature> --task T### [--class implementation|qa_author|documentation|review] \
  [--output <path>] [--allow-oversized]
```

An oversized brief (still over 5 KB after the contract excerpt is dropped) is
refused before anything is written and exits 1 (`WORKER_BRIEF_OVERSIZED`);
`--allow-oversized` writes it anyway and reports `oversized: true`.

Without `--class`, the work type is classified from the task's own
description the same way delegation routing already does
(`delegation.task_type`), so the brief and the delegated route never
disagree. `--class` never accepts `qa_collect` (review round 1, finding 10):
that route is light-tier eligible only behind an explicit `[Collect]` task
marker (standing rule 5), never an ad hoc CLI override; the brief's work
type still comes out `qa_collect` automatically when the marker is present.
The brief (default `specs/<feature>/workflow/briefs/T###.md`, targeted at
3-5 KB -- the contract excerpt is dropped first if that would push it over,
and the result carries `oversized: true` if it is still over without one)
carries:

- The task's exact line from `tasks.md`.
- Owned paths extracted from backtick-quoted file paths in the task's own
  description; when none are extracted, the worker is told to confirm scope
  with the orchestration agent rather than guessing at it.
- Verbatim lines from `spec.md`, `plan.md`, `data-model.md` and
  `research.md` that name a requirement id (`[A-Z]{2,10}-\d+`, e.g. `EXEC-06`,
  `SC-004`) the task's description references (F10: workers had the task text
  but not the verbatim requirement).
- A contract excerpt, when a file under `contracts/` shares a word with the
  task's description (best-effort; omitted, not guessed, when nothing matches).
- The turn budget (T0) for the task's class, read live from
  `execution-assign.md`'s table -- never a copy that could drift from it.
- The F1/F2 spawn-and-wait rules (route results straight to whoever spawned
  you; never end a turn owning running background work), the F3
  report-only-on-state-change rule and the T8 read-summary-first rule, all
  read live from the same two reference files.
- The forbidden-commands rule (S6), reusing `delegate_dispatch.py`'s own
  `NO_DISPATCHER_COMMANDS` (plus `QA_COLLECT_ADDENDUM` for a `qa_collect`
  task) rather than a second, hand-scraped copy -- the same text a real
  delegated worker's own brief already carries.
- The consumers checklist (F11) as a pointer, and the exact ten-line
  structured result template (T7), read live from `execution-report.md`.

Give the rendered file to the worker instead of the spec set; the worker
still reads its own owned-path source files, just not the discovery
artifacts a brief already quotes from.
