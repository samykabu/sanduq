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

## Instruction benchmark (round 2)

`extensions/scripts/benchmark_instructions.py` measures the static instruction load of `assure`,
`user-manual`, `pr`, `project`, `illustrate`, `memory` and `progress` (stream B0 of
`docs/internal/round-2-plan.md`). No model is called; it reads each `extensions/<id>/extension.yml`
and the files it points at. `instructions-before.json` and `instructions-before.md` are the BEFORE
numbers on `feat/round-2` at its base commit 6bff750.

```text
python extensions/scripts/benchmark_instructions.py --repo . --out docs/internal/benchmarks/instructions-before.json --md docs/internal/benchmarks/instructions-before.md
python extensions/scripts/benchmark_instructions.py --repo . --out docs/internal/benchmarks/instructions-after.json --md docs/internal/benchmarks/instructions-after.md --compare docs/internal/benchmarks/instructions-before.json
```

`--extensions a,b` narrows the set. `--compare` prints a delta table over every numeric total, every
per-extension total and every command's `instruction_bytes`, in the shape of `benchmark_compare.py`.

Measured files: every `provides.commands[].file`, every skill file (`skills/*/SKILL.ext.md`,
`skill/SKILL.md`, `assets/skill/SKILL.md`), and the files those tell the agent to read, one level deep.

- **Links.** Candidates are backticked tokens and Markdown link targets that end in `.md`, `.yml`,
  `.yaml`, `.json` or `.py`, or contain `references/`, `skills/`, `docs/` or `.specify/extensions/`.
  A script named right after `python`, `python3`, `node`, `bash`, `sh` or `pwsh` is an invocation, not
  a read, and is dropped. `.specify/extensions/<id>/X` resolves to `extensions/<id>/X`; other paths are
  tried against the file's own folder, the extension root and the repo root; `SKILL.md` also matches the
  source tree's `SKILL.ext.md`. Each resolved file counts once per command (`linked`, bytes);
  resolved `.py` files are listed under `scripts` but not counted; unresolved mentions go to `missing`
  (consumer files such as `tasks.md` or `manual.yml` land there by design). Linked files are not
  followed further. A bare name that happens to exist at the extension root (`CHANGELOG.md` in
  `pr.generate` means the feature changelog) is a known false positive.
- **Bytes, tokens.** `bytes` is the file size on disk; `instruction_bytes` = command bytes plus linked
  bytes; tokens = bytes / 4. A skill also records `references_bytes`, the sum of every
  `references/*.md` beside it (and their count), whether linked or not.
- **Prohibitions.** `\b(never|do not|don't|must not|not allowed|forbidden|refuse[sd]?|prohibited|under no circumstances)\b`,
  case-insensitive, over the whole file; `prohibitions_per_100_words` divides by whitespace words.
- **Script calls.** Lines inside a fence, or code spans, whose first token is `python`, `python3`,
  `node`, `bash`, `sh`, `pwsh`, `gh` or `git`. **Prose steps** are lines matching `^\s*\d+[.)]\s`
  outside fences.
- **Descriptions** (the `extension.yml` text, the catalog both hosts render): `chars`, `under_1024`,
  `third_person` (the first word is not in the script's `IMPERATIVE` set: generate, create, run,
  write, ... audit, choose, select, redraw; a heuristic, extend the set when a new verb appears),
  `has_what` (five or more words), `has_when` (`use when`, `when`, `after`, `before`), `has_triggers`
  (a double-quoted phrase or "asked to"). `failing` lists the checks that failed; `descriptions_failing`
  counts commands with any. `hook_only` is true when the command is named under `hooks:` or `events:`
  and its description has neither `has_when` nor `has_triggers`.
- **Duplicates.** Blank-line separated paragraphs of 25 or more words, normalised (lowercase,
  backticks stripped, whitespace collapsed), that appear in two or more measured files across all
  extensions; sorted by files x words.
- **Totals.** Per extension, sums over the unique set of measured files (a skill loaded by four commands
  is counted once; a file linked by two extensions is counted in each). `catalog_entries` is the number
  of `provides.commands`; `catalog_chars` the sum of their description lengths.
