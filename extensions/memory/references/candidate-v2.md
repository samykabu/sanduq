# Delta candidate (memory format 2)

Read at the author step of `run.md`. Write only changes to `candidate.json` in the run directory,
never a full document. `prepare` wrote the skeleton; keep `schema_version`, `base_memory_root` and
`checkpoint` as they are. `A preflight --run <id>` checks every mechanical rule (allowed keys, id
reuse, hashes, links, coverage completeness, budgets, text markers, stray files) and its error names
the rule that failed; this file explains what the fields mean and how to decide their content.

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

- **Entries.** `id` (`PM-<slug>`), `domain`, `kind` (`behavior`, `decision`, `limit`, `follow-up`,
  `dependency`, `lesson`), `title` (one line, the claim), `text`, `relations`, `selectors` (kinds
  `route`, `path`, `error_code`, `config_key`) and optional `summary`, `constrains`, `supersedes`.
  Links: `relations` means see also; `constrains` lists live entries whose behavior this entry
  limits (a rule anyone changing them must respect); `supersedes` lists entries, live or retired,
  that describe an older state this entry replaces. Omit a list rather than leave it empty. An
  update carries the complete new entry, not a patch.
- **Anchoring.** An updated id is anchored when it appears in a `provenance` record with `units`
  from this run or in a coverage group's `memory_ids`; an evidence-only record does not anchor. A
  reviewed correction that no unit of this run supports (stale wording, a claim the code
  contradicts) instead carries `"reason": "<why>"` on the update; the integration review lists
  every update with its reason. A reason never rewrites an entry wholesale.
- **expected_hash.** For every update and removal, copy the `expected_hash` that
  `A memory show --id PM-x` or `A memory query --format json` prints for that entry. A mismatch at
  preflight means memory moved since you read it: read the entry again.
- **Provenance (compact).** One record per entry you add, update or cite from coverage. `units`
  maps a path to unit items; a unit id splits at its last `:`, so `specs/x/spec.md:L42` is
  `{"specs/x/spec.md": ["L42"]}` and `specs/x/a.png:binary` is `{"specs/x/a.png": ["binary"]}`. The
  commit is the checkpoint, implied by the ledger header. `evidence` lists code or test paths
  (outside `specs/`) present at the checkpoint. Every behavior in the result, including untouched
  ones, needs such a path; when validate reports one missing, add fresh evidence or update or
  remove the entry. An evidence-only record `{"entry", "units": {}, "evidence": [...]}` re-anchors
  a behavior whose old evidence files were renamed or deleted. Specifications do not establish
  shipped behavior; external uncertainty belongs in limits and follow-ups. Prior provenance stays
  in earlier ledgers; do not repeat it.
- **Tombstones.** Supersede one obsolete `add` record of an entry: `A memory provenance --id PM-x`
  emits per-record objects `{"ledger", "record_hash", "record"}`; put that `record_hash` in the
  tombstone's `record`. Use only to drop provenance that is wrong; ledgers are append-only.
- **Removals.** A removal deletes the entry file and appends a `retire` record; the id joins the
  registry's `retired_memory_ids` and is never reused. Give the reason, the inventoried
  `source_unit` that justifies it and a `replacement` that is live in the result (or `null`).
  Prefer pointing `PM-` references at the replacement; references to retired ids stay valid, but a
  `constrains` link to a removed id must move to the replacement or go.
- **Taxonomy.** `op: add` creates a governed domain (kebab-case `id`, `label`, optional
  `definition`); `op: update` relabels or redefines one. Prefer existing domains; a new domain is
  reviewed like any other change.
- **Coverage, grouped by path.** Every inventoried unit belongs to exactly one group. `omitted`
  groups carry a `reason` (optional `reason_code`); `retained`, `merged` and `superseded` groups
  carry the `memory_ids` whose provenance (existing ledgers plus this candidate) cites those units
  at the checkpoint. Check that an omitted unit really is structure or boilerplate.
- **Budgets and text.** Policy `memory_budgets` bounds entry text, `INDEX.md` and each catalog page
  (tokens = chars/4). Split an oversized entry into related entries rather than trimming facts.
  Catalogs and INDEX are regenerated by validate; never write them. Entry text is plain prose with
  level-3 headings at most.
- **Migrations and repairs** (both formats). `migrations` lists machine-required artifacts only,
  each `{"source": "specs/<feature>/<file>", "destination": "tests/Fixtures/spec-memory/<feature>/<file>"}`
  with exact committed bytes preserved; do not copy other assets or keep an on-disk feature archive.
  `repairs` holds one item per preflight reference path, each `{"path": "...", "replacements":
  [{"before": "exact text", "after": "replacement", "count": 1}]}`. Point runtime consumers at the
  permanent fixture path without weakening assertions; point passive documentation citations at
  immutable `git:<checkpoint>:specs/<feature>/<file>` references or valid memory ids; repair active
  pointers. Handle every reference path; do not edit vendor extension files. The helper checks
  again after deletion for remaining consumers.

Organize by product capability, not archive date or feature. Merge duplicate facts by updating the
existing entry; replace obsolete rules; remove resolved follow-ups. Keep only rationale that still
explains a constraint. Do not append feature summaries or a changelog. Account for gotchas,
implementation captures, decisions and meaningful unbuilt work as well as formal requirements. Do
not convert inputs to omissions to pass checks.
