---
description: Archive selected verified specifications into current product memory
---

# Archive feature specifications

User arguments: `$ARGUMENTS`.

Operate only in the configured project checkout. No push, PR creation, stash, reset,
clean, broad staging, automatic rollback or implicit verification bypass. JSON helper
results report `success`; a nonzero exit is a blocker, never a successful no-op.
Use the command spelling registered by this agent: Codex/Claude skill names use
hyphens; Copilot commands use `speckit.memory.<command>`.
`A` below means `python .specify/extensions/memory/scripts/archive.py`.

**Memory format.** If `specs/.archive-index.json` records `"memory_format": 2`, memory
lives in `specs/memory/` and this run uses a **delta candidate** (sections below marked v2).
Otherwise follow the format-1 notes: the candidate is the full reconciled document.

## Resolve and verify

Read `.specify/memory-policy.json`. Select exact feature
directories; support explicit lists, `--all-completed`, and separate explicit
retirement with `--retire-reason`. Retirement never belongs to automatic/all mode.
Do not include this extension's own unfinished feature or infer completion from
numbers, merge status, a plan or checked boxes alone.

On the configured target branch, inspect actual implementation, required QA/review/manual results,
unfinished concerns and any external/submodule evidence. Once completion is real,
run `A verify --spec <path> --complete --check <name>` with all relevant approved
check names. This executes the checks and binds their results to the exact evidence.
Do not assert completion for convenience. For enumerated uncommitted related
implementation files, pass each exact file with `--related` to both verification and
preparation. Omit this in automatic mode. Missing infrastructure is a blocker.
External uncommitted code cannot be treated as verified.

Run `A prepare --spec <path> --check <name>` (repeat selection/check options). Use
`--automatic` only when processing approved ready queue entries. The helper creates a
real checkpoint commit before inventorying content and returns a run ID and
candidate/journal paths. `--all-completed` selects only fresh verified features and
reports skipped ones. An unfinished explicitly retired feature requires a reason and
named checks unless the owner uses the explicit verification override below.
Prepare refuses while any run is active.

## Explicit manual verification override

Only when the owner explicitly requests it, accept `--skip-verification "<reason>"`
for exact manually selected feature folders. The reason must be nonempty, printable,
single-line and at most 500 characters. It is permanently recorded in Git; use a
concise factual reason suitable for the repository's audience. Do not infer this
override from a failed check or unavailable infrastructure.

In this mode omit `verify` and `--check`, and run
`A prepare --spec <path> --skip-verification "<reason>"`. Repeat `--spec` for explicit
selections. Enumerated `--related` files remain explicit unverified checkpoint inputs;
never describe them as verified. The helper still requires the configured target
branch and completed tasks/completion boundary, unless the owner separately retires
unfinished work with `--retire-reason`. Do not mark unfinished tasks complete just to
use this override. Automatic mode and `--all-completed` reject it.

Both fresh verification evidence and external post-deletion check commands are
skipped. Checkpointing, source/provenance validation, independent critique, exact-byte
fixture migrations, consumer/reference repairs, scoped final commit and recovery
remain required. Inspect the skipped status/reason in the journal. Review runtime
consumer repairs line by line because those repairs will not be executed by checks.
Retain meaningful unresolved limits/follow-ups in memory; do not add an archive log
or claim unrun verification passed.

The reviewer must add `"verification_override": "<exact journal reason>"` to
`review.json`. `passed` means the critique passed; verification remains explicitly
`skipped`. Checkpoint and final commit messages, the committed archive index and (v2)
the new ledger header retain the same reason. The checkpoint marker prevents adding a
skip to an existing journal during recovery. For an existing failed transaction,
explicitly abandon an unpublished proposal or roll back a published one first, then
prepare and review a new override transaction. Do not edit its journal to bypass
verification. `finalize` accepts no skip flag.

## Read inputs (v2)

Read the journal's `units`, `references`, `checkpoint`, `base_memory_root` and scope.
There is no `previous_entries`. Read existing memory through budgeted helpers, never by
loading `specs/memory/` wholesale:

- `A memory query --path <code-or-dir> --route "<VERB /path>" --error-code <code>
  --domain <id> --text "<words>" [--budget 8000] [--cursor <c>]` for ranked whole entries;
- `A memory show --id PM-…` (repeatable) for exact entries;
- `A memory catalog --domain <id> [--page N]` and `specs/memory/INDEX.md` to browse;
- `A memory provenance --id PM-…` for an entry's folded sources and evidence.

Read implementation/test evidence at the checkpoint. Edit only `candidate.json` in the
run directory, never `specs/memory/`, the registry or feature files.

## Author the delta candidate (v2)

Write only changes, never a full document. Shape (`prepare` writes the skeleton; keep
`schema_version`, `base_memory_root` and `checkpoint` unchanged):

```json
{"schema_version": 2, "base_memory_root": "…", "checkpoint": "<sha>",
 "additions":  [{"id": "PM-…", "domain": "<taxonomy id>", "kind": "behavior", "title": "…", "text": "…",
                 "summary": "optional", "relations": [], "selectors": [{"kind": "route", "value": "POST /api/v1/x"}]}],
 "updates":    [{"id": "PM-…", "expected_hash": "<sha256>", "entry": {"…": "full entry, same shape"}}],
 "removals":   [{"id": "PM-…", "expected_hash": "<sha256>", "reason": "…", "source_unit": "specs/…/spec.md:L42", "replacement": "PM-…"}],
 "provenance": [{"entry": "PM-…", "units": {"specs/…/spec.md": ["L12", "L30"]}, "evidence": ["src/…/X.cs"]}],
 "tombstones": [{"entry": "PM-…", "record": "<record hash>", "reason": "…"}],
 "taxonomy_changes": [{"op": "add", "id": "kebab-id", "label": "Label", "definition": "…"}],
 "coverage":   [{"units": {"specs/…/tasks.md": ["L1", "L9"]}, "action": "omitted", "reason_code": "structural-context", "reason": "…"},
                {"units": {"specs/…/spec.md": ["L42"]}, "action": "merged", "memory_ids": ["PM-…"]}],
 "migrations": [], "repairs": []}
```

- **Top level.** Only the keys shown above; unknown top-level keys are rejected.
- **Entries.** Exactly the keys `id` (`PM-<slug>`), `domain`, `kind` (`behavior`,
  `decision`, `limit`, `follow-up`, `dependency`, `lesson`), `title` (one line, the
  claim), `text`, `relations`, `selectors`, and optional `summary`. Selector kinds:
  `route`, `path`, `error_code`, `config_key`. An update carries the complete new
  entry, not a patch. New ids must not exist or be retired. Every updated id must be
  anchored: it appears in a `provenance` record with `units` from this run, or in a
  coverage group's `memory_ids`. An evidence-only record does not anchor an update. A
  reviewed correction that no unit of this run supports (stale wording, a claim the code
  contradicts) instead carries `"reason": "<why>"` on the update; the integration review
  lists every update with its reason. Never use a reason to rewrite an entry wholesale.
- **expected_hash.** sha256 of the current `specs/memory/entries/<id>.md` bytes, for
  every update and removal:
  `python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" specs/memory/entries/PM-x.md`.
  A mismatch means memory moved; never copy a hash you did not compute.
- **Provenance (compact).** One record per entry you add, update or cite from coverage:
  `units` maps a path to unit items. A unit id splits at its last `:`, so
  `specs/x/spec.md:L42` is `{"specs/x/spec.md": ["L42"]}` and `specs/x/a.png:binary`
  is `{"specs/x/a.png": ["binary"]}`. The commit is the checkpoint, implied by the
  ledger header. `evidence` lists code/test paths (never under `specs/`) present at the
  checkpoint. Every behavior in the result, including untouched ones, needs an evidence
  path present at the checkpoint; if validate reports one missing, add fresh evidence or
  update/remove the entry. An evidence-only record `{"entry", "units": {}, "evidence":
  [...]}` re-anchors a behavior whose old evidence files were renamed or deleted.
  Specifications do not establish shipped behavior. External uncertainty belongs to
  limits/follow-ups. Prior provenance stays in earlier ledgers; do not repeat it.
- **Tombstones.** Supersede one obsolete `add` record of an entry. `memory provenance
  --id PM-x` emits per-record objects `{"ledger", "record_hash", "record"}`; put that
  `record_hash` in the tombstone's `"record"`. Use only to drop provenance that is
  wrong; ledgers are append-only.
- **Removals and retirement.** A removal deletes the entry file and appends a `retire`
  record; the id joins the registry's `retired_memory_ids` and can never be reused. It
  needs a reason, an inventoried `source_unit` that justifies it, and a `replacement`
  that is live in the result, or `null`. Do not update and remove the same id, or
  update one twice. Prefer pointing `PM-` references at the replacement; references to
  retired ids remain valid.
- **Taxonomy.** `op: add` creates a governed domain (unique kebab-case `id`, unique
  nonempty `label`, optional `definition`); `op: update` relabels or redefines one.
  Ids must not be Windows-reserved names (`con`, `prn`, `aux`, `nul`, `com1`-`com9`,
  `lpt1`-`lpt9`).
  Prefer existing domains; a new domain is reviewed like any other change.
- **Coverage, grouped by path.** Every inventoried unit appears in exactly one group;
  no gaps, overlaps or unknown units. `omitted` groups need a `reason` (optional
  `reason_code`) and no `memory_ids`. `retained|merged|superseded` groups need
  `memory_ids` live in the result, and each target must carry that unit at the
  checkpoint in its provenance (existing ledgers plus this candidate's).
- **Budgets** (policy `memory_budgets`, tokens = chars/4 rounded up): entry text ≤ 1024,
  `INDEX.md` ≤ 3000, each catalog page ≤ 1500. Split an oversized entry into related
  entries rather than trimming facts. Catalogs and INDEX are regenerated by validate;
  never write them.
- **Text rules.** Trimmed; no level-1 or level-2 headings; no TODO/TBD/NEEDS
  CLARIFICATION/conflict markers; every `PM-` reference resolves to a live or retired id.
- `migrations` and `repairs` are as in format 1 (below).

Organize by product capability, not archive date or feature. Merge duplicate facts by
updating the existing entry; replace obsolete rules; remove resolved follow-ups. Keep
only rationale that still explains a constraint. Do not append feature summaries or a
changelog. Account for gotchas, implementation captures, decisions and meaningful
unbuilt work as well as formal requirements. Do not convert inputs to omissions simply
to pass checks.

Small runs draft one candidate as above. For large runs (v2), draft in parallel packets:

1. `A packets --run <id> [--by domain|spec] [--max-units 2500]` partitions the units into
   `packets/pNN.json`. Each packet lists its units, references, owned domains, the
   existing `entries` it owns (with `expected_hash`) and `related` entries owned elsewhere.
   Re-packeting is refused once fragments exist.
2. One drafter per packet, in parallel. A drafter writes only `fragments/<pkt>.json`
   (candidate v2 keys plus `packet` and `proposals`), reads memory only through
   `A memory query/show`, and covers exactly its packet's units. It may update or remove
   only entries its packet owns; for any other entry it adds a proposal
   `{"id", "action": "update"|"remove", "reason", "entry": {full entry}|null}`. It runs
   `A fragment-check --run <id> --fragment <path>` until it is valid (read-only, safe to
   run concurrently).
3. `A merge --run <id>` checks every fragment and the cross-fragment rules and writes
   `merge.json`. On conflicts it writes them there and leaves `candidate.json` untouched:
   fix the fragments named and re-merge. On success it writes `candidate.json`, and
   `merge.json.proposals` lists proposals per owner packet: the owner folds accepted ones
   into its fragment, then merge again. Proposals never enter the candidate directly. A
   folded-in update still needs an anchor in this run (the proposer keeps the coverage and
   provenance that cite the entry) or a `reason`. Tombstones follow ownership like updates.
4. `A validate --run <id>` until there are no mechanical problems (see below).
5. `A review-packets --run <id>` cuts each fragment's review into parts of at most 40k
   tokens, `review/partition-<pkt>-NN.json`, plus one `review/integration.json` (shared
   selectors and relations, near-duplicate titles, taxonomy changes, updates with their
   reasons, removals and proposals), each with its `packet_sha256`. A part holds the full
   text of the units it disposes into memory, the first line of each omitted unit under its
   group's reason, the delta items citing those units and the existing entries they touch.
   Check that omitted units really are structure or boilerplate; read the full text in the
   journal when a first line is not enough.
6. Partition reviewers run in parallel; one reviewer may take several parts in turn. One
   integration reviewer reviews the combined result. `review.json` then carries the
   top-level bindings below, plus
   `"partitions": {"<pkt>-NN": {"packet_sha256", "reviewer", "passed": true, "findings": []}}`
   and `"integration": {…same keys}`.
7. `A validate --run <id>`, then `A finalize --run <id>`.

A partition approval whose `packet_sha256` is unchanged may be carried over after an
unrelated fragment edit (`review-packets` reports each approval as `valid`, `stale` or
`missing`). Any change to the merged result invalidates the integration approval and the
top-level bindings; re-review those.

## Format 1 candidate

For `memory_format` 1, read the journal's `previous_entries` and author
`candidate.json` as the complete reconciled document:

- `entries`: every entry with `id`, `domain`, `kind`, `title`, `text`, `sources`
  (`{"commit": "<checkpoint>", "path": "…", "unit": "<unit id>"}`, keeping valid
  previous provenance) and `evidence` (`{"commit": "<sha>", "path": "<code/test>"}`).
- `coverage`: one disposition per unit id, `{"action", "memory_ids", "reason"}`.
- `removed`: each previous id absent from `entries`, mapped to
  `{"reason", "source_unit", "replacement"}`.

The content rules above (kinds, evidence, text rules, capability organization) apply.

## Migrations and repairs (both formats)

- `migrations`: machine-required artifacts only, each `{ "source":
  "specs/<feature>/<file>", "destination":
  "tests/Fixtures/spec-memory/<feature>/<file>" }`. Preserve exact committed bytes.
  Do not copy other assets or keep an on-disk feature archive.
- `repairs`: one per preflight reference path, each `{ "path": "...",
  "replacements": [{ "before": "exact text", "after": "replacement",
  "count": 1 }] }`. Update runtime consumers to the permanent fixture path without
  weakening assertions. Update passive documentation citations to immutable
  `git:<checkpoint>:specs/<feature>/<file>` references or valid memory IDs.
  Repair active pointers. All reference paths must be handled; do not edit vendor
  extension files. The helper also checks after deletion for remaining consumers.

## Independent review and publication

Run `A validate --run <id>` until the candidate has no mechanical problems. For v2 it
materializes the result in a temporary copy (entries, new ledger, regenerated views,
taxonomy) and checks it as a whole. Its `data` fields are `valid`, `candidate_sha256`,
`base_memory_root`, `result_memory_root`, `outputs_sha256`, `summary`,
`review{status, problems}` and `paths`. It exits 1 only on mechanical problems; it
exits 0 even when the review is missing or mismatched. Stray files under
`specs/memory` are refused.

Have an independent local reviewer inspect the candidate, all input units and
evidence, supersessions, removals and fixture/consumer repairs. The reviewer must
compare content, not just validate JSON. Use a separate read-only agent/delegate when
available; if independent review is unavailable, stop before deletion. The archive
workflow authorizes this review. Never let the reviewer change repository files.
Do not claim review independence if you reviewed your own synthesis in the same
agent context.

Write `review.json` beside the candidate only after all findings are resolved:

- both formats: `candidate_sha256` (sha256 of the exact candidate bytes), nonempty
  `reviewer` and `summary`, `passed: true`, `findings: []`, and `verification_override`
  when skipped;
- v2: the reviewer copies `candidate_sha256`, `base_memory_root`,
  `result_memory_root` and `outputs_sha256` exactly as validate reported them.

Any candidate edit invalidates the review and needs a new critique. Coverage and
provenance checks cannot prove semantic correctness; independent review is an
additional requirement.

Run `A validate --run <id>` again; v2: finalize only when `data.review.status ==
"passed"`. Then run `A finalize --run <id>`. Finalize writes the
memory outputs (v2: changed/new entry files, deleted removed entries, the new
`provenance/<seq>-<checkpoint8>-<run8>.jsonl`, regenerated views, taxonomy) and fixture
repairs, deletes every selected folder, runs required checks (or records the explicit
manual override) and makes the scoped final commit. Under approved automatic policy
there is no extra human prompt. Explicit manual `run` authorizes the selected archive;
do not silently expand its scope. If memory changed since prepare (v2: `memory_root`
differs from `base_memory_root`), validate and finalize refuse; there is no automatic
rebase. Abandon and prepare again. Finalize also refuses if project memory differs from
the reviewed result at any later phase.

## Recovery, rollback and abandon

If interrupted or blocked, use `status`, inspect the journal and rerun `finalize`
only after resolving the reported condition. Preserve user edits and the checkpoint.
For a stale unpublished proposal, `A abandon --run <id>` explicitly retires that
proposal without changing files or deleting its checkpoint. Prepare and independently
review a fresh candidate. Abandonment is forbidden after publication.
For permanent failures after publication, explicitly run `A rollback --run <id>`. It
restores recorded original bytes and the scoped index only when outputs remain at
their recorded original/final hashes, deletes files the run created (v2: new entries
and its ledger), preserves the checkpoint, and removes that run's queue entry. It
refuses rollback after the final commit or unexpected user edits. Interrupted rollback
resumes with the same command.
While any transaction is active, do not start another specification, branch or
broad staging/commit workflow; `pending --gate` must pass first.
Do not delete the active journal to make a failure disappear. Report the exact
checkpoint/final commit and archived/skipped features. Assets remain recoverable
using `git show <checkpoint>:<original-path>`.
