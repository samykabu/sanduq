---
description: Consult relevant current product knowledge for specification and impact analysis
---

# Consult project memory

Only use this command when specifying a feature or analyzing its impact. It is
read-only and does not run archival. Do not load memory in every implementation task.

If `specs/memory/INDEX.md` does not exist, check `specs/project-memory.md`. If that is also
absent, report that no features have been archived yet and use the active feature artifacts
as usual. Do not create memory or invent knowledge.

Project memory (format 2) is one small file per entry under `specs/memory/entries/`.
Provenance is kept out of the reading path. Retrieve within a budget:

1. **Query by what the feature touches.** Run, from the repository root:
   `python .specify/extensions/memory/scripts/archive.py memory query --route "<METHOD /path>" --path <code file or directory> --error-code <code> --text "<key terms>" --budget 8000`
   Repeat `--route`, `--path` and `--error-code` as needed. The output is whole entries,
   ranked, with the reason each one matched. `inferred` means the match came from entry
   text or archived code evidence, not from a reviewed selector.
2. **Continue when told to.** If the output says more matches remain, rerun with the given
   `--cursor`. Also open the related entries it lists when they constrain the change:
   `memory show --id PM-…`.
3. **Browse for capability context.** `specs/memory/INDEX.md` (under 3k tokens) lists every
   domain. `memory catalog --domain <id>` lists a domain's entries as `id · kind · title`.
   Cross-cutting rules (tenancy, error envelopes, external providers) often touch many domains.
4. **Assess.** Compare the planned change with current behavior, decisions, limits and open
   follow-ups. Cite stable memory ids in the specification's impact assessment.

An empty result is not proof that nothing is affected. Widen the query (`--text`, catalogs)
and inspect the code. Use provenance only when an archived source's full detail is needed:
`memory provenance --id PM-…`, then `git show <commit>:<path>`.

Never load `memory export` into context; it renders the whole memory as one document.
The Assure workspace scan at `.github/memory/project-memory.md` serves a different purpose
and is not the product memory.
