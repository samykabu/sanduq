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
`evidence` list, `images` observation list, and `tree`.

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
