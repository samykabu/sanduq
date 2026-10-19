# Optimization round 2: plan

Second round of the method that produced Workflow 1.13.0, now over `assure`, `user-manual`, `pr`,
`project`, `illustrate`, `memory` and `progress` (`workflow` and `scope` only where a change is
cross-cutting). Work happens in the worktree `D:\Projects\Personal\sanduq-round2` on branch
`feat/round-2`; the main checkout is busy with issue #94. Fable agents measure, review, implement
and validate; the orchestrator plans, reviews, commits, publishes the report and releases.

Phase 1 (this page): measure BEFORE, review, publish the options report, stop for the user's choice.
Phase 2 (after the choice): implement in parallel streams, measure AFTER, update the report page,
bump versions and changelogs, release, update `README.md` and `docs/start/upgrades.md`.

Rules for every stream: no git commands that change the tree or the index (no add, commit, stash,
checkout, switch, reset, clean); stay inside the owned files; write findings to your own file.

## Stream B0: measurement harness

Owns `extensions/scripts/benchmark_instructions.py`, `docs/internal/benchmarks/instructions-before.json`,
`docs/internal/benchmarks/instructions-before.md` and a new section in `docs/internal/benchmarks/README.md`.

`python extensions/scripts/benchmark_instructions.py --repo <checkout> --out <json> [--md <file>]
[--extensions a,b] [--compare <before.json>]`. Stdlib plus PyYAML. For each extension (default: the
seven above) it reads `extension.yml` and records:

- per command (`provides.commands[]`): `bytes` of the command file; `linked` = every file the body
  tells the agent to read, one level deep (paths under the extension, `references/`, `skills/*/SKILL*.md`,
  `docs/`, `.specify/extensions/<id>/...` resolved to the source tree), each with its bytes;
  `instruction_bytes` = command bytes plus linked bytes; `words`; `prohibitions` and
  `prohibitions_per_100_words` (never, do not, don't, must not, not allowed, forbidden, refuse,
  prohibited, under no circumstances; one regex, documented in the README); `script_calls`
  (lines that invoke `python`, `node`, `bash`, `pwsh`, `gh` or `git` in code spans or fences) and
  `prose_steps` (numbered list items); `description` checks: `chars`, `under_1024`, `third_person`
  (does not open with an imperative verb), `has_what`, `has_when` ("use when", "when", "after",
  "before"), `has_triggers` (quoted phrases or "asked to"); `hook_only` (listed under `hooks:` or
  `events:` and not meant for a user).
- per skill file (`skills/*/SKILL.ext.md`, `skill/SKILL.md`, `assets/skill/SKILL.md`): the same
  fields plus `references_bytes` (every `references/*.md` beside it) so a skill loaded whole shows
  its real weight.
- per extension: `version`, `catalog_entries` (commands rendered to both hosts), `catalog_chars`
  (sum of description lengths, the listing budget each host pays), `hooks`, `events`, totals.
- across all measured files: `duplicates`, paragraphs of 25 words or more that appear (after
  whitespace and case normalisation) in more than one file, with the file list.

`--compare` prints a before/after delta table in the shape of `benchmark_compare.py`. The README
section states the regexes, the one-level rule and that tokens are bytes / 4. Commit the BEFORE
numbers measured on this worktree at its base commit before any change.

## Streams R1 to R5: review (read-only)

Each writes exactly one file: `docs/internal/round-2-review-<group>.md`.

- R1 `assure-user-manual`, R2 `pr-project`, R3 `illustrate`, R4 `memory`, R5 `progress`.

Lenses, in this order, with evidence (file and line or a measured number) for every claim:
1. Where the model is told to do work a script already does or could do deterministically.
2. Where text repeats inside the extension, across its commands, or against the workflow dispatcher.
3. Where a stage rereads large inputs (whole skills, docs, generated files) it does not need.
4. Where a description fails the catalog rules (third person, what, when, trigger phrases,
   under 1,024 characters, key use case first) or a hook-only command still occupies a catalog slot.
5. Where a hook could enforce a rule the prose repeats.
6. Where Claude Code and Codex diverge (paths, hooks, agents, skill loading).
Then a defects table (defect, effect, where) and the candidate options.

Option record (one per candidate, ids `AS`, `UM`, `PR`, `PJ`, `IL`, `ME`, `PG` plus a number):
`title`; `what` (three to five sentences naming the files); `effort` S (up to a day), M (two to
four days), L (one to two weeks, tests, docs and release included); `tok` and `time` as `[lo, hi]`
fractions of that extension's cost per run; `obs` (unchanged, improved or reduced, and why);
`policy` (none, or the opt-in key with its unchanged default); `pros`; `cons`; `files`; `tests`.
Observability, evidence gates, receipts and GitHub decisions stay intact in every option.

## Stream B9: report page

Owns one file in the orchestrator's scratchpad: `round-2-report.html`, built from the saved HTML of
the first report (same CSS, layout, option cards, sticky bar, three presets, `selection/current`
db document) with the new verdict, evidence (BEFORE numbers), areas (one per extension plus a
cross-cutting area), options from R1 to R5, three presets (tighten, recommended, everything) and a
short standards recap that links to the first report. The orchestrator publishes it.

## Orchestrator

Review B0's harness and numbers, commit them; review R1 to R5 for evidence and double counting;
brief B9; publish; update memory; stop and ask the user to choose a path.
