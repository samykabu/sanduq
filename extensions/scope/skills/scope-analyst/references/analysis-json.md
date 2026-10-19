# Analysis JSON

Follow `.specify/extensions/scope/references/analysis-contract.md` for the schema and the effort
formula. The analysis must also:

- carry the snapshot fingerprint from `inspect`;
- set each image's `viewed: true` and `observations` only after actually looking at it;
- give every node scope, exclusions, evidence, rationale, acceptance, coverage IDs and a score;
- give each Specify prompt the WHAT and WHY, the source issue identity and score, and the useful
  constraints learned from implemented prerequisites, keeping engineering evidence apart from
  stakeholder-facing requirements;
- list `requirements`, `acceptance` and `uncertainty` items completely enough that a spec can be
  rendered from them (the managed `render-spec` step);
- with a managed keep-together band, include `effort_estimate` with `value` and the exact
  declared `unit`; never equate it with the dimension score unless the project uses that unit.
