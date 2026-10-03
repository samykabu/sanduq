---
description: Consult relevant current product knowledge for specification and impact analysis
---

# Consult project memory

Only use this command when specifying a feature or analyzing its impact. It is
read-only and does not run archival. Do not load memory in every implementation task.

If `specs/project-memory.md` is absent, report that no features have been archived
yet and use the active feature artifacts as usual. Do not create an empty central
document or invent knowledge. Otherwise inspect its domain headings and read only
entries relevant to the feature, plus their referenced dependencies/constraints.
Compare changed behavior with current requirements, decisions, limits and open
follow-ups. Cite stable memory IDs in the new specification's impact assessment.
Use an archived source's checkpoint provenance only when its full detail is needed.
The Assure workspace scan at `.github/memory/project-memory.md` serves a different
purpose and is not the central product specification.
