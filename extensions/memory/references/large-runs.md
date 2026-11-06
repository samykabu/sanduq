# Large runs: parallel packets

Read when a format-2 run is too large for one drafter (many units or domains). Small runs draft one
candidate as `.specify/extensions/memory/references/candidate-v2.md` describes; large runs draft in parallel packets:

1. `A packets --run <id> [--by domain|spec] [--max-units 2500]` partitions the units into
   `packets/pNN.json`. Each packet lists its units, references, owned domains, the existing
   `entries` it owns (with `expected_hash`) and `related` entries owned elsewhere.
2. One drafter per packet, in parallel. A drafter writes only `fragments/<pkt>.json` (candidate
   v2 keys plus `packet` and `proposals`), reads memory only through `A memory query/show`, and
   covers exactly its packet's units. It may update or remove only entries its packet owns; for any
   other entry it adds a proposal `{"id", "action": "update"|"remove", "reason", "entry": {full
   entry}|null}`. It runs `A fragment-check --run <id> --fragment <path>` until the fragment is
   valid (read-only, safe to run concurrently).
3. `A merge --run <id>` checks every fragment and the cross-fragment rules and writes
   `merge.json`. On conflicts it records them there and leaves `candidate.json` untouched: fix the
   fragments named and merge again. On success it writes `candidate.json`, and
   `merge.json.proposals` lists proposals per owner packet: the owner folds accepted ones into its
   fragment, then merge again. Proposals never enter the candidate directly. A folded-in update
   still needs an anchor in this run (the proposer keeps the coverage and provenance that cite the
   entry) or a `reason`. Tombstones follow ownership like updates.
4. `A preflight --run <id>` until the candidate guards pass.
5. `A review-packets --run <id>` cuts each fragment's review into parts of at most 40k tokens,
   `review/partition-<pkt>-NN.json`, plus one `review/integration.json` (shared selectors and
   relations, near-duplicate titles, taxonomy changes, updates with their reasons, removals and
   proposals), each with its `packet_sha256`. A part holds the full text of the units it disposes
   into memory, the first line of each omitted unit under its group's reason, the delta items citing
   those units and the existing entries they touch. Check that omitted units really are structure
   or boilerplate; read the full text in the journal when a first line is not enough.
6. Partition reviewers run in parallel; one reviewer may take several parts in turn. One
   integration reviewer reviews the combined result. `review.json` then carries the top-level
   bindings from `.specify/extensions/memory/references/review-and-publish.md` plus
   `"partitions": {"<pkt>-NN": {"packet_sha256", "reviewer", "passed": true, "findings": []}}`
   and `"integration": {…same keys}`.
7. Continue with `.specify/extensions/memory/references/review-and-publish.md` (`A status` names the next command).

A partition approval whose `packet_sha256` is unchanged may be carried over after an unrelated
fragment edit (`review-packets` reports each approval as `valid`, `stale` or `missing`). Any change
to the merged result invalidates the integration approval and the top-level bindings; re-review
those.
