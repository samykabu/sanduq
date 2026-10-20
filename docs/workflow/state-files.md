# Workflow state files

This page explains where Workflow keeps policy and feature state, how a checkpoint identifies its repository, how to relocate a repository legitimately, and the receipt contract each completed stage records. The JSON shapes are summarised in [Workflow schemas](schemas.md); daily recovery steps are in the [operations guide](operations.md).

Back to the [Workflow guide](../../extensions/workflow/README.md).

## State and recovery

Policy lives in `.specify/workflow.yml`. Feature state lives under
`specs/<feature>/workflow/`. Claims prevent concurrent stage ownership. Only an
explicit Specify claim can bind a new branch after verifying scope-source.json.
Use `recover` with the recorded token after inspecting possible remote writes;
use `migrate` after reviewing a dependency upgrade. Both preserve an audit trail.
A migration backs up the checkpoint, preserves still-current historical evidence and invalidates changed command selections. Use `--invalidate-from <stage>` when an upgrade changes a stage contract.
`migrate --preview` writes nothing and returns the exact `invalidated` and
`preserved_as_historical` lists the migration would record, with any blockers;
the applying `migrate` returns the saved `migrations[]` entry. Both load the
checkpoint through the bound-branch check, so run them on the feature's branch.

## Checkpoint identity and relocating a repository (1.8.0)

A checkpoint no longer identifies its repository by the absolute path it was
started from (that path was the checkpoint-identity design bug: every clone,
worktree, second machine, delegated worker or CI runner other than the one
that ran `start` failed `CHECKPOINT_IDENTITY_MISMATCH`, with no supported
fix). It now records a portable `repo_identity`: the normalised `origin`
remote URL when one is configured, and/or the repository's root commit SHA
(`git rev-list --max-parents=0 HEAD`) when it is not. The remote is
authoritative whenever both the checkpoint and the current repository have
one, so a shallow CI checkout of the same origin (whose visible root-commit
history is truncated at the shallow boundary, not the true root) still
matches — unless neither clone is shallow, in which case the root commit
must also match even though the remote does, catching a remote that was
copied into an unrelated clone. The root commit is used on its own
only when neither side has a remote.

`Run.load()` also requires the checkpoint's bound issue to name this
repository's own GitHub remote — the same binding `start` and the scope
extension's `bound_claim` already require, resolved from the remote
(any scheme, an embedded token, with or without `.git`) the same way the
portable identity is, and compared case-insensitively (GitHub repository
names are not case sensitive). Without a GitHub remote to check that
against at all, the checkpoint is refused and pointed at `relocate` rather
than trusted: a repository with no remote configured cannot load an
existing checkpoint, though `workflow.py`'s lower-level identity primitives
still support one for other purposes.

A checkpoint from before 1.8.0 recorded only `repo_path` (never read or
compared by 1.8.0+, but still written by `start`, the legacy-upgrade path
and `relocate` so a pre-1.8.0 reader does not `KeyError`; it will be removed
once no supported release still needs it) and is accepted once both checks
above pass *and* it records a full-hex commit id (its `head`, or a receipt's
`head`) that is reachable from this repository's HEAD — the one verifiable
history signal such a checkpoint carries, since origin is only local Git
config. Without one (recreated or rewritten history) it is refused, naming
`relocate --allow-history-change`. It is then upgraded to `repo_identity` on
its next write. A checkpoint
copied from a genuinely different repository is still refused, whether
legacy or new: this is the security property the design protects.

Moving a repository legitimately — a renamed remote or a migrated GitHub
org (both keep the same issue numbers), or a fork (which does not: its
issue numbering is independent of what it forked from) — changes that
identity and is refused the same way, since it is indistinguishable from a
checkpoint that does not belong here without a human saying so. Run:

```
workflow.py relocate --feature specs/<feature> --preview --reason "<why>"
workflow.py relocate --feature specs/<feature> --reason "<why>"
```

The preview reports the old and new identity, the old and new GitHub
repository, and the current branch binding, without changing anything; the
applying call rebinds the checkpoint and appends a `relocations[]` entry
(`actor`, `at`, `reason`, `old_identity`, `new_identity`, and — only when the
GitHub repository itself changed — `repository_renamed`, `old_repository`,
`new_repository`, `new_issue`). No receipt is touched and no stage is
invalidated — relocate never revisits what evidence means. A branch
mismatch is refused unless `--allow-branch-rebind` is also passed; a
checkpoint whose bound issue names a different GitHub repository than this
one now resolves to is refused unless `--allow-repository-rename` is also
passed — this is the check that stops `relocate` itself from being used to
launder a foreign checkpoint into an unrelated repository, and either
flag's effect is logged in the same entry regardless. A checkpoint whose
recorded root history is not this repository's (the root commit is neither
equal nor reachable on a non-shallow clone, or a legacy checkpoint records
no reachable commit) is also blocked unless `--allow-history-change` is
passed, and `history_changed` is recorded in the entry. Relocate also needs
a resolved GitHub remote to apply (otherwise `load` would refuse the result),
and `--issue`/`--keep-issue-number` are refused with
`RELOCATE_ISSUE_NOT_APPLICABLE` when the repository did not change.

A repository change never rebinds the issue automatically: pass
`--keep-issue-number` to assume the number carries over (a GitHub rename or
transfer only — never a fork) or `--issue <owner/repo#n>` (which must name
the repository this one now resolves to) to bind the exact new issue
instead; passing neither leaves the repository change blocked, and passing
both is refused. `scope-source.json` is rebound together with
the checkpoint (restored to its original bytes if the checkpoint write fails), so a later `start` for the same issue does not fail
`FEATURE_BINDING_MISMATCH` against a source file still naming the old
repository. Relocate is refused inside any delegated worker or
orchestrator context (`DELEGATION_WORKER_CONTEXT`) and while a claim is
active; it reaches the checkpoint directly, bypassing the identity and
branch checks `load` enforces everywhere else, because that gate is exactly
what it exists to get past, and every decision it makes is recomputed from a
fresh read taken under the per-feature lock rather than trusted from before
it.

**Threat model.** This identity check defends against an *accidental*
cross-repository mix-up: the same feature directory name reused in an
unrelated project, a checkpoint file copied by habit instead of by intent, a
CI runner that resolved the wrong checkout. It is not a defence against an
*adversarial* process running inside this repository's own working tree: a
remote URL, a root commit, and the branch a checkpoint claims to be on are
all read from local Git state that a delegated worker (or anything else with
filesystem access here) could edit before this runtime ever reads it, the
same way it could edit `.git/config` directly. Nothing in this design is
meant to resist that; a process already trusted to run commands in this
working tree is already trusted with everything in it. What actually
protects the integrity of recorded work is the receipt contract itself: each
stage's evidence is bound by byte-exact SHA-256 fingerprints
(`fingerprints`, `source_fingerprints`), checked again on every later load,
independent of which repository or machine is asking.
Likewise, merging a foreign history into HEAD in a clone whose `origin` was
copied from the recorded one is accepted (the recorded root commit is then
still an ancestor of HEAD); that is by design, since the merge is a
deliberate act inside the working tree, not an accidental mix-up.

## Lifecycle events, stage plan and next action (1.12.0)

A receipt tells you what a stage produced. It does not tell you how the run got there: which claim
was recovered, which completion was turned down, which receipts a claim threw away. Workflow 1.12.0
records that history in `specs/<feature>/workflow/lifecycle.jsonl`, one JSON object per line.

```json
{"v": 1, "event_id": "…", "workflow_run_id": "…", "generation": 14, "at": "2026-10-17T09:30:00+00:00",
 "stage": "clarify", "event": "rejected-completion", "episode_id": "claim:c-…", "claim_id": "c-…",
 "caused_by_claim_id": null, "candidate_run_id": null, "delegation_run_ids": ["codex-12"],
 "reason": "CLARIFICATION_UNRESOLVED"}
```

| `event` | Written when |
| --- | --- |
| `claim` | A stage is claimed. |
| `resume` | A stage is claimed while the checkpoint was paused. |
| `accepted` | `complete` validated the receipt and stored it. Never written before validation passes. `candidate_run_id` names the delegation run that validation accepted. |
| `rejected-completion` | `complete` authenticated the claim and then refused the receipt. The claim stays active and nothing is stored, so the same claim can complete again. The CLI still prints the same error and exits 1. |
| `recovered` | `recover` is about to clear the claim. The event keeps the claim's `claim_id`. |
| `paused` | A checkpoint was written for a pause or a recovery. With no claim held (the context-budget pause before a claim, or the pause that follows a recovery) it is a feature-level event: `stage`, `claim_id` and `episode_id` are `null`. |
| `invalidated` | A receipt was removed or marked stale: by the claim that replaces it, by `migrate`, by `refresh`, or by a `changed` amendment. One event per stage, with the cause in `reason`. |
| `revalidated`, `revalidation-stale` | `revalidate` made a receipt current, or recorded a lane gap that left it stale. |
| `skipped` | The profile tier skips the stage; `reason` names the tier. |

`claim_id` identifies a claim without being the claim token. It is a one-way hash of the token, so it
is safe to show and to copy into reports, and it cannot be used to complete or recover anything.
Ids that do not apply are written as `null`, never left out. `episode_id` is `claim:<claim_id>` for a claim and
`revalidation:<event_id>` for a revalidation.

Three fields answer different questions, and a reader should not merge them:

- `delegation_run_ids` is claim membership: every run the delegation ledger links to the claim,
  including a failed attempt that a later one replaced.
- `candidate_run_id` is the stage attempt that the exact-claim check validated, so a failed predecessor
  under the same claim is a member but not the candidate. `accepted` always carries it, and
  `rejected-completion` carries it when the refusal came after that check passed. It is `null` when the
  claim had no delegation route, when a rejection happened at or before the check, and on every other event.
- `caused_by_claim_id` is set only on the `invalidated` events that a claim writes for the downstream
  receipts it removes. Those receipts belong to no claim and no episode, so `claim_id` and `episode_id`
  are `null` and the new claim is named here. Every other event writes `null`.

`stage` is `null` only on `paused`, as described above. Every other event names a stage.

Each event is queued in the checkpoint (`lifecycle_outbox`) in the same write that changes the state,
then appended to the file under the feature lock. If the process stops between the two, the next
write replays the queue and skips every `event_id` that is already in the file. A reader should
ignore a torn final line. `scripts/lifecycle.py` has `read_events(path)` for that: it returns the
complete events and says whether it skipped a damaged line. Before the next append deduplicates, it
repairs the tail: a complete record that only lacks its final newline is kept and terminated, and an
unparseable fragment is dropped. A crash right before the newline therefore loses no event.

The same write also stores two small facts in the checkpoint, so a report does not have to guess them.
`stage_plan` is the selected stage order after policy filtering. `next_action` is Workflow's own
`next` result at that moment, with `evaluated_at` and the checkpoint `generation` it was computed for.
It is a cache. If the generation is older than the checkpoint's, treat it as stale.

Delegation attempts in `delegations.json` carry matching links when they are known: `intent_id`,
`claim_id` (stage attempts only), `parent_run_id` and `replaces_run_id`. A replacement or a
reassignment names the run it replaces; a repeated start does not.

## Profiles, skipped stages and runtime caches

These fields and files exist only when the matching policy key is set or the command runs.

| Where | What |
| --- | --- |
| Scope receipt `effort_score` | The approved effort score (1, 2, 3, 5, 8, 13 or 21). Required when `profiles.enabled`. |
| Checkpoint `profile` | `{tier, score, fixed_at}`, frozen when Plan is first claimed. |
| Checkpoint `skipped` | `{stage: reason}` for each stage the tier skips; `lifecycle.jsonl` has a matching `skipped` event, and `next` and `status` list them. |
| Plan claim `merged` | `['tasks']` on the lite and standard tiers; the Plan receipt then lists `tasks.md` in `inputs`. |
| Analyze receipt `command: workflow:lint` | Written by `lint.py --record` when lint is clean and needs no model Analyze. |
| Tasks-to-Issues receipt `lazy: true` | With `issue_sync.taskstoissues: phase-lazy`: only the first phase is mapped; Ready requires every task mapped. |
| `lifecycle.jsonl` episode `revalidate-upstream` | One locked `revalidate-upstream --receipt` call that re-recorded stale stages in order. |
| Verify, Review and Ready `source_inventory` | `{path: 'workflow/inventory/<stage>-<claim_id>.json', sha256}` instead of inline `source_fingerprints`; older receipts with the inline form stay readable. |
| `.specify/workflow/runtime/doctor-cache.json` | The last green project doctor result. `claim` reuses it for up to 600 seconds while the dependency digest, policy digest and registry and config files are unchanged; `doctor` always runs fresh and refreshes it. |
| `.specify/scope/board-cache.json` | `{fetched_at, repo, items}`, kept for `scope.board_cache_seconds` and cleared by every Scope or clarification write. |
| `handoff.md` | The runtime rewrites only the block between `<!-- sanduq-handoff:begin -->` and `<!-- sanduq-handoff:end -->`; notes outside it are kept. |

A spec that Scope rendered from the approved analysis starts with
`<!-- sanduq-scope:rendered <sha256 of the analysis file> -->`; the Specify claim then returns
`mode: bind-only`.

## Linking checkpoint records to lifecycle events (1.12.0)

A reader should not match a checkpoint record to a lifecycle event by stage and time. Two fields name the link:

- A stored receipt carries `claim_id`, the claim that produced it. Its `completed_at` is the same instant
  as the `at` of the `accepted` event for that claim.
- A `recoveries[]` entry keeps the recovered claim in `claim`, and `claim.claim_id` is that claim's id. The
  entry's `at` is the same instant as the `at` of the `recovered` event.

Receipts and recoveries written before 1.12.0 have no `claim_id`. They stay separate evidence: a reader never matches or deduplicates them against events by stage or time.

## Clarification records (Scope 1.7.0)

Scope writes `specs/<feature>/workflow/clarifications.json` as `{"v": 1, "items": [...]}` after a
clarification round is published. A reader can show the questions without calling GitHub. These two
shapes are pinned, and `extensions/scope/tests/fixtures/clarifications-vector.json` is a test vector
that Scope's own `clarification_items` produces and a test regenerates.

`evidence` is a list of objects, one per reference, always with the same four keys:

| Key | Value |
| --- | --- |
| `kind` | `comment` (a published question or a reply), `selection` (a ticked box), `closure` (the creator closed clarification), `disposition` (the reviewer's verdict on the question) or `in-session` (an answer the issue creator gave in the conversation, mirrored to GitHub in one managed comment of kind `round-in-session`). |
| `url` | The comment URL, or `null`. |
| `comment_id` | The GitHub comment id, or `null`. |
| `explanation` | Free text, or `null`. A `disposition` carries `<disposition>: <explanation>`. |

`applied` is `null` or `{"at": "<time>", "evidence": ["<string>", ...]}`. `applied.evidence` is always a
list of strings, even when it holds one entry. A reader that sees a bare string is looking at a file
written before the shape was pinned and should wrap it.

If a later publication finds `clarifications.json` unreadable or malformed (not an object with `v: 1`, an item
that is not an object, a missing `source_id`, or a `revision` that is not a positive integer), Scope moves it to
`clarifications.json.unreadable-<batch>`, writes a fresh file and prints a warning. The specification and
the board have already moved by then, so failing would repeat the same failure on every rerun.

A retry of a publication that stopped after the board moved repairs only the records. It does not compare the
live thread with the stored baseline, so a human reply that arrived after the crash does not block it. It builds
the records from the stored snapshot and analysis and the journaled comment ids, and requires that those
comments still exist. A dry run reports `unfinished: true`.

## Receipt contract (1.6.0)

Receipts stay backward-compatible: `inputs` is still a list of paths, and every
new field is optional (`input_roles`, `amendments`, `head`, `source_key`,
`ci_evidence`, `diff_reviewed`; see `schemas/receipt-v1.schema.json`). Reading a
1.3.0-1.5.x checkpoint needs no migration; continuing it after the upgrade needs
the reviewed `migrate` above, which invalidates nothing when no semantic policy
changed.

- **Input roles.** `input_roles: {"<path>": {"role": "dependency" | "consulted",
  "because": "<text>"}}` declares why each input is listed. Only dependencies
  decide whether a receipt is current and whether a later stage fails with
  `UPSTREAM_INPUT_CHANGED_DURING_STAGE`. A consulted input needs a `because`,
  keeps its recorded hash (it is never re-stamped) and, when it changes, is
  reported by `next` as `advisory_drift`. Evidence and a stage's required
  artifacts cannot be consulted. A receipt without roles is read as
  all-dependency, exactly as before. The policy key
  `receipts.require_input_roles` (default `false`) makes `complete` refuse an
  undeclared role for any input outside `specs/<feature>/` and
  `.specify/memory/`. Changing it is a policy change that invalidates no
  completed receipt; run `migrate` once to record the new policy digest.
- **Assessed amendments.** `workflow.py amend --feature specs/<feature> --stage
  <stage> --evidence <path> --reason "<why>" --assessment unchanged|changed`
  re-hashes that one evidence entry of that receipt and appends
  `{path, old_hash, new_hash, reason, assessment, actor, at}` to its
  `amendments[]`; every other hash is kept and the checkpoint is backed up.
  `unchanged` keeps the receipt current; `changed` marks Verify, Review and
  Ready (from the amended stage on) stale so they are re-recorded. A path that
  is not listed as that receipt's evidence is refused, as is an active claim.
  `ci_gate.py` accepts amended receipts and lists each amendment in its result.
- **Project Sync binding (1.16.0).** A receipt dependency on the configured Project Sync state
  file (`stateFile`, default `.specify/project-sync-state.json`) is recorded as
  `sync-binding:v1:<sha256>` of the bound feature's entry without `status` and timestamp fields, so
  a board status write never stales it while an issue, node, item or sub-issue change does. This
  holds for a state file under `.specify/` (the default); a state file elsewhere is also source for
  Verify, Review and Ready, so a status write there is source drift. A raw hash recorded before
  1.16.0 stays byte-exact until `migrate` or `workflow.py sync-amend --feature specs/<feature>
  --reason "<why>"` checks the entry against `scope-source.json` and `workflow/task-issues.json`,
  finds the recorded bytes (working tree, HEAD or the last 50 commits that touched the file) with
  only `status` or timestamp fields changed since, and replaces it, appending an
  `administrative-amendment` record (old and new value, changed fields) to the checkpoint's
  `lineage`. Otherwise it refuses and the stage is re-recorded. `workflow.py project-sync` records the last sync as `project_sync: {phase,
  state: pending|done|failed, at, summary}`; `next` and `status` report a pending or failed one.
