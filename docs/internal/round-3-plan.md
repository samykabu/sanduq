# Optimization round 3: plan

Asked 2026-10-19: a full pass over every Spec Kit extension built so far (workflow, scope, assure,
user-manual, pr, project, illustrate, memory, progress, plus the three presets), starting with whether
each name matches what the extension does. Worktree `D:\Projects\Personal\sanduq-round3`, branch
`feat/round-3`, base fb96e41 (round 2 released). Opus 5.5 high agents do research and implementation;
the orchestrator plans, reviews, commits, publishes and releases.

Stages:

1. **Naming (decision gate).** Stream N1 writes `round-3-naming.md`. The orchestrator publishes an HTML
   report with rename options per extension, the cost of each and a selection stored in the page, then
   stops for the user's choice.
2. **Measure and review (in parallel with stage 1, read-only).** BEFORE numbers for all nine extensions
   (`benchmark_instructions.py`, `benchmark_front_half.py` full and lite) under
   `docs/internal/benchmarks/round-3-before*`. Review streams R1 to R6 write `round-3-review-<group>.md`.
3. **Implement** the chosen names and the optimizations in parallel streams with disjoint files, a
   migration path for every rename (installer, upgrade, catalog aliases, docs), measure AFTER, update
   the HTML report, bump versions and changelogs, release.

Rules for every stream: no git commands that change the tree or the index; stay inside the owned file;
evidence (file and line, or a measured number) for every claim.

## Stream N1: naming

Owns `docs/internal/round-3-naming.md`. For each extension and preset:

- What it actually does, in one sentence, from its commands, scripts and hooks (not from its
  description), and who invokes it (user, hook, dispatcher).
- Whether the id, the display name, the command prefix (`speckit.<id>.*`, host skill
  `speckit-<id>-*`) and the description agree with that sentence; where the "Sanduq" prefix is used
  and where it is not.
- Collisions: the Spec Kit community catalog (fetch it; note any extension with the same or a
  confusable id or name), built-in Spec Kit commands, common host skills.
- Constraints: what Spec Kit allows for ids (read `D:\Projects\Personal\spec-kit` source: extension id
  rules, catalog schema, how `specify extension add/update/remove` treats an id change, whether it has
  aliases, replaces or migrations).
- Rename blast radius per extension, measured: occurrences of the id across the repository
  (commands, skills, hooks, scripts, tests, docs, catalogs, `dependencies.json`, release tags, installed
  paths `.specify/extensions/<id>/`, state folders, policy keys, GitHub workflow files rendered into
  consumers), and what an installed consumer holds that would break.
- Options: keep, plus two or three rename candidates with one-line rationale, effort S/M/L, risk, and
  the migration it needs. A recommendation per item and a recommended overall set (which may be
  "keep most").

## Streams R1 to R6: optimization review (read-only)

R1 workflow; R2 scope and the three presets; R3 assure and user-manual; R4 pr, project and memory;
R5 illustrate and progress (vendored parts are upstream changes); R6 cross-cutting (shared scripts and
their packaged copies, the installer and upgrade path, release tooling, CI and test runtime, docs and
duplicated guidance across extensions). Same lenses as round 2 (model work a script could do, repeated
text, large rereads, descriptions, hook-enforceable rules, host divergence) plus code refactoring
(dead code, duplicated helpers, oversized modules, slow tests) and what round 2 left unverified.
Option ids `W`, `SC`, `AU`, `PM`, `IP`, `X` plus a number, with the round-2 record fields.
