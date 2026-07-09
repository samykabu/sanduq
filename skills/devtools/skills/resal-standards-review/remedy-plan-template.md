# Remedy Plan — Template

Generated **only in full mode**, **only after** the `AskUserQuestion` severity selection, and including **only the chosen tiers**. Save as `RESAL-STANDARDS-REMEDY-PLAN.md`. This is a plan — do **not** edit target code unless the user explicitly asks you to execute it.

---

```markdown
# Resal Standards — Remedy Plan

- **Service:** <name>  ·  **Generated:** <YYYY-MM-DD>
- **Companion report:** RESAL-STANDARDS-REPORT.md
- **Tiers included (user-selected):** <e.g. Critical, High>
- **Excluded tiers:** <e.g. Medium, Nice-to-have> — recorded so scope is explicit.

## Plan summary
| Tier | Items | Est. effort (S/M/L) |
|---|---|---|
| 🔴 Critical | n | … |
| 🟠 High | n | … |
| … | | |

Recommended sequencing: Critical → High → Medium → Nice-to-have. Within a tier, do quick wins (S) and shared-infra fixes (logging, CRUDBase, config) first since later items depend on them.

## Items
One block per finding, ordered by severity then dependency.

### [F-001] <short title>  ·  🔴 Critical  ·  effort: M
- **Finding / root cause:** what's wrong and why it matters (link finding ID).
- **Standard:** §<n> <area> (and check ID, e.g. CONF-03).
- **Fix steps:**
  1. concrete step
  2. concrete step
- **Files to touch:** `app/...`, `app/...`
- **Risk / sequencing:** depends on / must precede; migration or downtime notes.
- **Verification:** the exact command or test proving it's fixed
  (e.g. `grep -r "password=" app/ → none`; `pytest app/tests/... -q`; `pre-commit run --all-files`).

### [F-002] …

## Cross-cutting refactors (if several findings share one fix)
e.g. "Introduce `CRUDBase` and migrate all hand-written CRUD" resolves DB-03/DB-04 across N modules — list the affected files once.

## Out of scope (excluded tiers)
List the finding IDs deferred because their tier wasn't selected, so nothing is silently dropped. The user can re-run and select them later.

## Suggested execution order (checklist)
- [ ] F-001 …
- [ ] F-002 …
```
