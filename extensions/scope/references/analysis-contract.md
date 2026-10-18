# Scope analysis contract

The agent writes JSON; the runtime validates it and performs deterministic operations.
Start from `examples/analysis.json` in this extension. Use the exact current issue
number and fingerprint returned by inspect. No speculative image observations.

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
8..10 = 8; 11..13 = 13; 14..15 = 21. Points estimate complexity, not promised days.
1/2 = small, 3/5 = medium, 8/13/21 = large. Large scores recommend decomposition;
the user chooses the actual number of new issues. Never force recursive splitting. Explain every dimension
in the rationale. Unknown details increase uncertainty; critical missing evidence
blocks publication instead of receiving an invented estimate.

Each tree node has a unique stable lowercase `key`, `title`, `scope`, `out_of_scope`,
`acceptance` string list, `covers` requirement-ID list, `evidence` string list,
`dimensions`, computed `score`, `rationale`, and optional `depends_on` leaf keys.
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

## Review and publication approval

`publish` without `--apply` returns findings and makes no GitHub writes. Present the
complexity findings, ask for the preferred sub-issue count (zero keeps the issue),
then present the exact count-matched proposal for explicit approval. Choosing a count
alone is not approval of a breakdown the user has not seen.

`approve` records the actual user's approval statement locally. The receipt binds
repository, issue, full analysis SHA-256, source fingerprint, current prerequisites and
exact new-issue count. `publish --apply` requires that receipt before its first write.
Do not put a fabricated approval flag in analysis JSON. Changing any bound input
requires fresh user approval. Version 2 published scope receipts preserve approval
provenance. Legacy small/medium receipts remain valid; approved large leaves retain
honest scores and can pass the normal Specify gate once prerequisites and plan pass.

## Reusing an inspect snapshot

`inspect <issue> --output <file>` saves the snapshot. `gate`, `approve`, `publish` and
`bind` accept `--snapshot <file>` and reuse it when the file is younger than
`scope.board_cache_seconds` (default 300; 0 disables) and its `fingerprint` matches one
fresh fetch of the issue; the receipt and labels still come from that fresh fetch.
Otherwise they run a full inspect. The output says which with `snapshot_reused`.

Project board reads are cached in `.specify/scope/board-cache.json`
(`{fetched_at, repo, items}`) for the same TTL. Every Scope or clarification write to the
board or an issue removes the cache, and a gate that would refuse because of a cached
status rereads the live board first.

## In-session first round

When `clarification.in_session_first_round` is true, round 1 can be answered in the session with
`clarification.py publish <issue> --analysis <file> --answers <answers.json> --apply`, where
`answers.json` lists `{key, option (1-based) | answer (text), answered_by, answered_at}` for every
question, as in `examples/answers.json`.

## Rendering the specification

For an approved single-leaf analysis, `scope.py render-spec <issue> --analysis <file>
--feature specs/<feature>` prints the spec (`text` in the JSON output) and writes nothing;
`--apply` writes `specs/<feature>/spec.md`. The first line is
`<!-- sanduq-scope:rendered <sha256 of the analysis file bytes> -->`, followed by the Spec
Kit sections: Overview (`alignment`, `tree.scope`), User Scenarios (`tree.specify_prompt`),
Functional Requirements (`FR-001`... from `requirements`, in order), Success Criteria
(`SC-001`... from `tree.acceptance`), Out of Scope (`tree.out_of_scope`) and Open
Questions. The issue's published scope receipt must approve exactly this analysis
(`SCOPE_RENDER_UNAPPROVED`), the tree must have no children (`SCOPE_RENDER_LEAF_REQUIRED`),
and an existing `spec.md` without the marker is replaced only with `--force`
(`SCOPE_RENDER_EXISTS`).
