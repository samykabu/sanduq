# Format-1 candidate (legacy single document)

Read only when `prepare` returns `"memory_format": 1`, that is on a project that has not run
`migrate` yet (`specs/.archive-index.json` lacks `"memory_format": 2`). Memory is the single
document `specs/project-memory.md` and the candidate is the full reconciled document, not a delta.

Read the journal's `previous_entries` and author `candidate.json` as:

- `entries`: every entry with `id`, `domain`, `kind`, `title`, `text`, `sources`
  (`{"commit": "<checkpoint>", "path": "…", "unit": "<unit id>"}`, keeping valid previous
  provenance) and `evidence` (`{"commit": "<sha>", "path": "<code/test>"}`).
- `coverage`: one disposition per unit id, `{"action", "memory_ids", "reason"}`.
- `removed`: each previous id absent from `entries`, mapped to
  `{"reason", "source_unit", "replacement"}`.
- `migrations` and `repairs`: as in `.specify/extensions/memory/references/candidate-v2.md`.

The content rules of `.specify/extensions/memory/references/candidate-v2.md` (kinds, evidence, capability organization) apply. Large-run
packets exist only for format 2. At publication, `validate` requires the passed critique
(`review.json` with the fields `.specify/extensions/memory/references/review-and-publish.md` lists for both formats) before `finalize`.
