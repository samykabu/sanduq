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

## Resolve and verify

Read `.specify/memory-policy.json`. Select exact feature
directories; support explicit lists, `--all-completed`, and separate explicit
retirement with `--retire-reason`. Retirement never belongs to automatic/all mode.
Do not include this extension's own unfinished feature or infer completion from
numbers, merge status, a plan or checked boxes alone.

On the configured target branch, inspect actual implementation, required QA/review/manual results,
unfinished concerns and any external/submodule evidence. Once completion is real,
run `python .specify/extensions/memory/scripts/archive.py verify --spec <path>
--complete --check <name>` with all relevant approved check names. This executes
the checks and binds their results to the exact evidence. Do not assert completion
for convenience. For enumerated uncommitted related implementation files, pass
each exact file with `--related` to both verification and preparation. Omit this in
automatic mode. Missing infrastructure is a blocker. External uncommitted code
cannot be treated as verified.

Run `python .specify/extensions/memory/scripts/archive.py prepare --spec <path>
--check <name>` (repeat selection/check options). Use `--automatic` only when
processing approved ready queue entries. The helper creates a real checkpoint
commit before inventorying content and returns a run ID and candidate/journal
paths. `--all-completed` selects only fresh verified features and reports skipped
ones. An unfinished explicitly retired feature requires a reason and named checks
unless the owner uses the separate explicit verification override below.

## Explicit manual verification override

Only when the owner explicitly requests it, accept `--skip-verification "<reason>"`
for exact manually selected feature folders. The reason must be nonempty, printable, single-line
and at most 500 characters. It is permanently recorded in Git; use a concise factual
reason suitable for the repository's audience. Do not infer this override from a
failed check or unavailable infrastructure.

In this mode omit `verify` and `--check`, and run:
`python .specify/extensions/memory/scripts/archive.py prepare --spec <path>
--skip-verification "<reason>"`. Repeat `--spec` for explicit selections. Enumerated
`--related` files remain explicit unverified checkpoint inputs; never describe them
as verified. The helper still requires the configured target branch and completed
tasks/completion boundary, unless the owner separately retires unfinished work with
`--retire-reason`. Do not mark unfinished tasks complete just to use this override.
Automatic mode and `--all-completed` reject it.

Both fresh verification evidence and external post-deletion check commands are
skipped. Checkpointing, source/provenance validation, independent critique, exact-byte
fixture migrations, consumer/reference repairs, scoped final commit and recovery
remain required. Inspect the skipped status/reason in the journal. Review runtime
consumer repairs line by line because those repairs will not be executed by checks.
Retain meaningful unresolved limits/follow-ups in memory; do not add an archive log
or claim unrun verification passed.

The reviewer must add `"verification_override": "<exact journal reason>"` to
`review.json` alongside the existing candidate hash and critique fields. `passed`
means the critique passed; verification remains explicitly `skipped`. Checkpoint and
final commit messages and the committed archive index retain the same reason.
The checkpoint marker prevents adding a skip to an existing journal during recovery.
For an existing failed transaction, explicitly abandon an unpublished proposal or
roll back a published one first, then prepare and review a new override transaction.
Do not edit its journal to bypass verification. `finalize` accepts no skip flag.

## Reconcile the candidate

Read the run journal's complete `units`, `previous_entries`, `references`,
checkpoint and scope. Read implementation/test evidence at that checkpoint.
Edit only the local `candidate.json`, never the central memory or feature files.

Candidate fields:

- `entries`: the complete reconciled current document. Each entry has stable
  `id` (`PM-<slug>`), `domain`, `kind` (`behavior`, `decision`, `limit`, `follow-up`,
  `dependency`, `lesson`), `title`, `text`, `sources` and `evidence`.
- Each source is `{ "commit": "<checkpoint SHA>", "path": "<artifact>",
  "unit": "<inventory unit ID>" }`. Keep valid previous provenance too.
  Implementation evidence is `{ "commit": "<SHA>", "path": "<code/test>" }`.
  A behavior entry always needs implementation evidence. Specifications do not
  establish shipped behavior. External uncertainty belongs to limits/follow-ups.
- `coverage`: exactly one disposition per inventory unit, keyed by its ID:
  `{ "action": "retained|merged|superseded|omitted", "memory_ids": ["PM-..."],
  "reason": "..." }`. Omitted units need a reason and an empty ID list. Each
  referenced memory entry must retain the corresponding checkpoint source.
- `removed`: each previous memory ID absent from the new entries, mapped to
  `{ "reason": "...", "source_unit": "...", "replacement": "PM-... or null" }`.
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

Organize by product capability, not archive date or feature. Merge duplicate facts;
replace obsolete rules; remove resolved follow-ups. Keep only rationale that still
explains a constraint. Do not append feature summaries or a changelog. Account for
gotchas, implementation captures, decisions and meaningful unbuilt work as well as
formal requirements. Do not convert all inputs to omissions simply to pass checks.

## Independent review and publication

Have an independent local reviewer inspect the candidate, all input units and
evidence, supersessions and fixture/consumer repairs. The reviewer must compare
content, not just validate JSON. Use a separate read-only agent/delegate when
available; if independent review is unavailable, stop before deletion. The archive
workflow authorizes this review. Never let the reviewer change repository files.
Do not claim review independence if you reviewed your own synthesis in the same
agent context.

Write `review.json` beside the candidate with `candidate_sha256` of its exact bytes,
`reviewer`, `summary`, `passed: true`, and `findings: []` only after all findings are
resolved. Any candidate edit invalidates that review and needs a new critique.
Coverage/provenance checks cannot prove semantic correctness; independent review
is an additional requirement.

Run `python .specify/extensions/memory/scripts/archive.py validate --run <id>`.
Then run `... archive.py finalize --run <id>`. It writes memory and fixture repairs,
deletes every selected folder, runs required checks (or records the explicit manual
override) and makes the scoped final commit. Under
approved automatic policy there is no extra human prompt. Explicit manual `run`
authorizes the selected archive; do not silently expand its scope.

Do not use level 1 or 2 headings inside entry text; those levels belong to the
document and its domains. Every current behavior needs an implementation evidence
path that still exists at this checkpoint, including carried-forward entries.

If interrupted or blocked, use `status`, inspect the journal and rerun `finalize`
only after resolving the reported condition. Preserve user edits and the checkpoint.
For a stale unpublished proposal, `... archive.py abandon --run <id>` explicitly
retires that proposal without changing files or deleting its checkpoint. Prepare
and independently review a fresh candidate. Abandonment is forbidden after publication.
For permanent failures after publication, explicitly run `... archive.py rollback
--run <id>`. It restores recorded original bytes and the scoped index only when
outputs remain at their recorded original/final hashes, preserves the checkpoint,
and removes that run's queue entry. It refuses rollback after the final commit or
unexpected user edits. Interrupted rollback resumes with the same command.
While any transaction is active, do not start another specification, branch or
broad staging/commit workflow; `pending --gate` must pass first.
Do not delete the active journal to make a failure disappear. Report the exact
checkpoint/final commit and archived/skipped features. Assets remain recoverable
using `git show <checkpoint>:<original-path>`.
