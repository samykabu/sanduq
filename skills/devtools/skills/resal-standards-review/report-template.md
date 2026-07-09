# Compliance & Gaps Report — Template

Fill this in and save to the target repo as `RESAL-STANDARDS-REPORT.md`. Produced in **both** modes. For a **multi-stack** target, repeat sections 1 + 3 + 4 per detected stack under a "## Stack: <name>" heading, and keep one combined executive summary (§2).

---

```markdown
# Resal Standards — Compliance & Gaps Report

- **Project:** <name>  ·  **Path:** <repo path>
- **Detected stack(s):** python | dotnet | react-web | react-native | multi  ·  **Evidence:** <marker file(s)>
- **Reviewed:** <YYYY-MM-DD>  ·  **Reviewer:** Resal Standards Review skill
- **Standards:** ./standards/ (core.md + <stack>.md)  | bundled checks
- **Mode:** Full | Report-only
- **Commit/branch:** <git rev>

## 1. Stack profile (Step-3 detection)
What this project actually uses — every "N/A" below is justified by this. (Rows are stack-appropriate; examples for backend services shown.)

| Capability | Present? | Evidence |
|---|---|---|
| Persistence / DB + migrations | yes/no | manifest + file |
| Messaging / queue (Kafka/…) | yes/no | imports |
| Cache (Redis) | yes/no | dep |
| Structured logging | yes/no / regression | logger config |
| Tracing / error tracking (OTel/Sentry) | yes/no | bootstrap |
| Auth posture | in-service / mesh / gateway / n-a | deps + middleware |
| Feature flags | which / none | config |
| Async / event-driven | yes/no | agents/handlers |
| (FE) data layer / state / forms / i18n-RTL | … | package.json |

## 2. Executive summary
2–4 sentences: overall posture, biggest risks, headline counts.

| Severity | Count |
|---|---|
| 🔴 Critical | n |
| 🟠 High | n |
| 🟡 Medium | n |
| 🟢 Nice-to-have | n |
| **Total** | n |

> Recompute these counts after any severity adjustment.

## 3. Section scorecard
Pass / Partial / Fail / N/A per area (any Critical/High = Fail; only Medium/Nice = Partial; capability unused = N/A with profile evidence). Use the core areas (security, config, errors, logging/observability, API, resilience, testing, docs, commits, CI/build) plus the stack module's areas.

| Area | Status | Notes |
|---|---|---|
| Security (CORE-SEC) | ✅/🟡/❌/N-A | |
| Config & secrets (CORE-CFG) | | |
| Error handling (CORE-ERR) | | |
| Logging & observability (CORE-LOG) | | |
| API & contracts (CORE-API) | | |
| Resilience (CORE-RES) | | |
| Testing (CORE-TEST) | | |
| Docs (CORE-DOC) | | |
| Commits/CI/build (CORE-GIT/OPS) | | |
| Layering & naming (CORE-LAYER) | | |
| <stack-specific areas> | | |

## 4. Findings
Sorted by severity. Every finding cites evidence (file:line) and the check id.

### 🔴 Critical
| ID | Check | Finding | Evidence (file:line) | Expected | Sev adj. |
|---|---|---|---|---|---|

### 🟠 High
| ID | Check | Finding | Evidence | Expected | Sev adj. |
|---|---|---|---|---|---|

### 🟡 Medium
| ID | Check | Finding | Evidence | Expected | Sev adj. |
|---|---|---|---|---|---|

### 🟢 Nice-to-have
| ID | Check | Finding | Evidence | Expected | Sev adj. |
|---|---|---|---|---|---|

## 5. What's compliant (strengths)
Brief list of areas that follow the standard well — avoids an all-negative report.

## 6. N/A checks (justified)
Checks skipped because the capability isn't used, with the profile evidence.
```

*(Report-only mode ends at the report — do not append the severity question or a remedy plan. Full mode continues to the severity selection and a separate remedy-plan file.)*
