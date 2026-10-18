# Front-half benchmark

Reproducible before/after cost of the managed workflow for one small feature (stream S0 of
`docs/internal/rebuild-front-half-plan.md`).

## Method

`extensions/scripts/benchmark_front_half.py` loads the runtime from
`<repo>/extensions/workflow/scripts/workflow.py` with importlib, so the same script measures any checkout.
For each run it:

1. Builds a throwaway consumer exactly as `extensions/workflow/tests/test_workflow.py` `setUp` and
   `configure` do (git repo with an `acme/app` origin, `default_policy(qa=True, manual=True)`, project
   config, preset and extension registries, fake command skills), then commits a synthetic source tree
   of `--source-files` small `.py`/`.ts` files (default 750) so Verify, Review and Ready inventory a
   realistic tree.
2. Drives one scripted feature through the runtime's own `main()` in-process (the same code path and
   stdout as `python workflow.py ...`): `start`, then `claim` and `complete` for every stage the runtime
   offers, with the tests' unreliable usage JSON (`{"session_id": "host-without-telemetry"}`) and the
   minimal receipt the tests' `receipt()` helper builds.
3. After Execute completes, appends one line to `spec.md`, runs `next`, and takes the cheapest recovery
   the runtime offers: `revalidate-upstream` when the loaded runtime has it (plan first, then one
   receipt file), otherwise re-claiming and completing each invalidated stage. `meta.recovery_path`
   records which ran (and `recovery_error` if `revalidate-upstream` refused and the harness fell back).
4. Runs one `pause` (produces `handoff.md`), then Verify, Review, the QA/manual documentation stages,
   Ready, and PR (claimed with `--finalize`).

Recorded per command: wall-clock ms, stdout bytes, and counters from wrapping module functions:
`doctor`, `fingerprint_files`, `source_fingerprints`, `git` (the runtime's `git()` helper), plus
`git_subprocess` (every `git` `subprocess.run`, including those in sibling modules).
Totals add stages run, model passes, final `checkpoint.json`, `handoff.md` and `lifecycle.jsonl` bytes.

Static instruction load per stage (from the checkout's files): the workflow `SKILL.ext.md`, the stage
reference, `receipt-rules.md`, the preset overlay for the stage's command when one exists, and the
stage extras (Scope: `run.md`, scope-analyst skill, analysis contract; Specify: `specify-gate.md`,
`guard.md`, `bind.md`; Clarify: github-clarification skill; Execute: execution-assign, execution-report,
reporting). The pointer set (`dispatcher-operations.md`, `delegation-and-decisions.md`) is counted once
per run, and every `references/*.md` file named by a counted file (one level, not counted elsewhere)
is counted once per run.

## Tiers

`--tier lite|standard|full` (default `full`) only applies when the loaded `workflow.py` mentions
`effort_score`: the fixture policy then gets `profiles: {enabled: true, lite: {max_score: 3},
standard: {max_score: 8}}` and the scope receipt gets `effort_score` 2, 5 or 13 for lite, standard or
full. On a runtime without profiles the flag is ignored and `meta.tier_note` says so; that is why
`before-full.json` and `before-lite.json` are the same workload.

## Assumptions

- Tokens = bytes / 4.
- No model is called. Receipts and artifacts are the unit-test fixtures, so the numbers measure
  runtime overhead and instruction size, not model work. `model_passes` counts claimed stages whose
  command does not start with `workflow:`; a `revalidate-upstream` operation counts as one pass.
- Wall time depends on the host (these files were produced on Windows 11, Python 3.13); compare runs
  from the same machine only.
- On a runtime that prints `reference_text` in `claim`, the stage reference is counted both in the
  claim stdout bytes and in the static instruction bytes; read them as separate costs.

## Reproduce

```text
python extensions/scripts/benchmark_front_half.py --repo ../sanduq-baseline --out docs/internal/benchmarks/before-full.json
python extensions/scripts/benchmark_front_half.py --repo ../sanduq-baseline --tier lite --out docs/internal/benchmarks/before-lite.json
python extensions/scripts/benchmark_front_half.py --repo . --out docs/internal/benchmarks/after-full.json
python extensions/scripts/benchmark_front_half.py --repo . --tier lite --out docs/internal/benchmarks/after-lite.json
python extensions/scripts/benchmark_compare.py --before docs/internal/benchmarks/before-full.json --after docs/internal/benchmarks/after-full.json --md docs/internal/benchmarks/compare-full.md
python extensions/scripts/benchmark_compare.py --before docs/internal/benchmarks/before-lite.json --after docs/internal/benchmarks/after-lite.json --md docs/internal/benchmarks/compare-lite.md
```

`../sanduq-baseline` is the read-only worktree of `main` at 105508f. Each run takes a few minutes with
750 source files; `--source-files 50` is enough for a smoke check.
