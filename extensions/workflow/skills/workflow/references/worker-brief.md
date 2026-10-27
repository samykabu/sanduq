# worker-brief

A utility entry point, not a claimed stage: it writes one task's brief so a worker does not load
the whole spec, plan, tasks and contracts set.

```text
python .specify/extensions/workflow/scripts/worker_brief.py --root <repo> \
  --feature specs/<feature> --task T### [--class implementation|qa_author|documentation|review] \
  [--output <path>] [--allow-oversized]
```

Without `--class`, the work type comes from the task description as delegation routing reads
it. `--class` never accepts `qa_collect`; that type comes only from a `[Collect]` task marker.
The brief (default `specs/<feature>/workflow/briefs/T###.md`, targeted at 3-5 KB) carries the
task line, owned paths from backtick-quoted paths in the task (or an instruction to confirm
scope with the orchestration agent), verbatim spec, plan, data-model and research lines naming
the task's requirement ids, a matching contract excerpt when one exists, the class turn budget,
the spawn-and-wait, report-on-state-change and read-summary-first rules, the forbidden commands,
the consumers checklist pointer and the eleven-line result template, all read live from
execution-assign.md and execution-report.md. A brief still over 5 KB without the contract
excerpt exits 1 with `WORKER_BRIEF_OVERSIZED` unless `--allow-oversized`. Give the worker the
brief instead of the spec set; it still reads its own owned source files.
