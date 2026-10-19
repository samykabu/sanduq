# Scope analysis contract

The agent writes JSON; the runtime validates it and performs deterministic operations.
Start from the skeleton `scope.py inspect <issue> --output <snapshot> --skeleton <analysis.json>`
writes: issue, fingerprint and every image URL (`viewed: false` until actually inspected) are
copied from the snapshot. No speculative image observations.

## Effort rubric

Score each dimension 0 (none/trivial), 1 (local known work), 2 (several coordinated
changes), or 3 (broad/new/high uncertainty):

| Dimension | Consider |
| --- | --- |
| breadth | Number of independently testable behaviors and components |
| integration | External systems, cross-component contracts, unmerged prerequisites |
| data_security | Data migration, tenancy, authorization and sensitive data changes |
| verification | Test matrix, environments, rollback and release verification |
| uncertainty | Unresolved decisions, missing evidence and unfamiliar mechanisms |

Sum -> effort points: 0..1 = 1; 2..3 = 2; 4..5 = 3; 6..7 = 5;
8..10 = 8; 11..13 = 13; 14..15 = 21. A node without `score` gets it from its dimensions; a
declared score must match. Points estimate complexity, not promised days.
1/2 = small, 3/5 = medium, 8/13/21 = large. Large scores recommend decomposition;
the user chooses the actual number of new issues. Never force recursive splitting. Explain every dimension
in the rationale. Unknown details increase uncertainty; critical missing evidence
blocks publication instead of receiving an invented estimate.

Each tree node has a unique stable lowercase `key`, `title`, `scope`, `out_of_scope`,
`acceptance` string list, `covers` requirement-ID list, `evidence` string list,
`dimensions`, optional `score`, `rationale`, and optional `depends_on` leaf keys.
A leaf of any score needs `specify_prompt`; a chosen split has `children` (1..100
direct children). The approved count covers all new nodes, including nested parents.
Children must cover all parent coverage IDs. Break acceptance criteria into precise
IDs so coverage cannot hide missing behavior behind an oversized umbrella ID.
Avoid busywork splitting: each leaf must deliver an independently testable outcome.

Top-level fields: `issue`, `fingerprint`, `requirements` list, `alignment` text,
`evidence` list, `images` observation list, and `tree`. Optional `uncertainty` (or
`open_questions`) lists the questions the analysis could not settle, each a string or
`{"question": "..."}`; `render-spec` turns them into `[NEEDS CLARIFICATION: ...]` lines.

Every leaf inherits source images as reference links. Describe which regions/screens
apply in its scope; shared source images do not make every screen part of every child.

## Approval

Review, approval and publication follow `skills/scope-analyst/references/controls.md`.

## Reusing an inspect snapshot

`inspect <issue> --output <file>` saves the snapshot. `gate`, `approve`, `publish` and
`bind` accept `--snapshot <file>` and reuse it when the file is younger than
`scope.board_cache_seconds` (default 300; 0 disables) and its `fingerprint` matches one
fresh fetch of the issue; the receipt and labels still come from that fresh fetch.
Otherwise they inspect again (`gate` and `bind` read prerequisites only). Without
`--snapshot`, `gate` and `bind` use `.specify/scope/issue-<number>-snapshot.json` when it
exists. The output says which with `snapshot_reused`.

Project board reads are cached in `.specify/scope/board-cache.json`
(`{fetched_at, repo, items}`) for the same TTL. Every Scope or clarification write to the
board or an issue removes the cache, and a gate that would refuse because of a cached
status rereads the live board first.

## Rendering the specification

For an approved single-leaf analysis, `scope.py render-spec <issue> --analysis <file>
--feature specs/<feature>` prints the Spec Kit spec (`text` in the JSON output); `--apply`
writes `specs/<feature>/spec.md` with a `<!-- sanduq-scope:rendered <sha256> -->` first line.
It refuses with `SCOPE_RENDER_UNAPPROVED`, `SCOPE_RENDER_LEAF_REQUIRED` or `SCOPE_RENDER_EXISTS`
(replace an unmarked spec only with `--force`).
