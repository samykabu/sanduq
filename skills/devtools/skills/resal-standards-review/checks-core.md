# Check Catalog — Core (cross-cutting, every stack)

Run **all** applicable `CORE-*` checks for **every** project, regardless of stack, **in addition to** the detected stack module (`checks-python.md` / `checks-dotnet.md` / `checks-react-web.md` / `checks-react-native.md`). Enforces the shared standard `core.md` (in `./standards/`).

Each check: **ID · applicability · detection hint · default severity**. Detection patterns differ by language — where they do, the hint says "stack-specific" and the stack module lists the concrete pattern, but **the finding is recorded under the CORE id** (no double-counting with stack modules).

> **Applicability is the guardrail against false positives.** A check whose capability the project legitimately omits is **N/A — justify** (cite the stack profile), not a finding. Only `present-but-wrong` or `required-but-missing` are findings.
> **Evidence before findings (hard gate):** only author a finding for a file you enumerated (skill Step 3.5) and **opened**. Never assume a file exists from the stack's typical layout.
> **No overlap rule:** a concern is recorded **exactly once**, under the most specific matching id. Cross-cutting concerns belong here (`CORE-*`); stack modules hold only stack-specific concerns. When a stack check says "record under CORE-…" / "also CORE-…", that is a **cross-reference, not a second finding** — file it once under the named id and list the other id in the same row. Never emit two findings (one CORE, one stack) for the same issue.
> **Counting:** the severity tally counts **distinct findings**, not check IDs. A row that cites multiple IDs is one finding. Recompute the counts after any merge/split/severity change.

---

## CORE-SEC — Security (core.md §8)

| ID | Applies | Detection hint | Default |
|---|---|---|---|
| `CORE-SEC-01` | always | **No hardcoded secrets.** Grep source + config for literal credentials: `password`, `secret`, `api[_-]?key`, `token`, `connection ?string`, long base64/hex, `sk_live`, private keys. Stack-specific config files: Python `.env`/`config.py`; .NET `appsettings*.json`/`launchSettings`; React `.env`/`next.config`; RN `app.config`/`app.json`/`eas.json`. Any committed real credential → **Critical**. | Critical |
| `CORE-SEC-02` | always | **No injection / untrusted execution.** SQL/command built from external input by string-format; `eval`/`exec`; Python `ast.literal_eval`/`pickle.loads`/`yaml.load`(unsafe)/`subprocess(shell=True)`; JS `eval`/`new Function`/`dangerouslySetInnerHTML` without sanitize; .NET string-concatenated SQL/`FromSqlRaw` with interpolation. On external/user/log-derived data → **Critical**; on purely internal literals → de-escalate. | Critical |
| `CORE-SEC-03` | always | **Static scanning + dependency hygiene** in pre-commit/CI (bandit · .NET analyzers/`dotnet list package --vulnerable` · `npm audit`). Missing → finding. | Medium |
| `CORE-SEC-04` | committed config | **No real secret in a committed `.env`/example/cookiecutter file** (a populated `.env.example` with real values, not placeholders) → **Critical**. | Critical |
| `CORE-SEC-05` | prod | A signing/secret key must not rely on a random per-process default in deployed config (set explicitly via env/secret store). | Critical |

## CORE-CFG — Configuration & secrets (core.md §4)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `CORE-CFG-01` | always | Config loaded once into **one typed object** (pydantic-settings `Settings` · .NET `IOptions<T>` · FE env module). Ad-hoc `os.getenv`/`Environment.GetEnvironmentVariable`/`process.env` scattered through code → finding. | Medium |
| `CORE-CFG-02` | always | Required config has **no default** (fails fast at boot); optional is explicitly typed-optional. | Medium |
| `CORE-CFG-03` | always | A committed `*.example`/sample documents required keys; the real `.env`/secrets file is git-ignored. | Medium |
| `CORE-CFG-04` | k8s | Secrets injected at deploy (1Password via Helm / CI secrets), not baked into the image or chart values. | Medium |

## CORE-ERR — Error handling (core.md §5)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `CORE-ERR-01` | always | **No swallowing.** Empty `catch{}` / `except: pass` / catch-log-nothing / catch-and-return-generic-500-without-log → finding. | High |
| `CORE-ERR-02` | always | **A global error boundary** translates uncaught errors to a consistent shape + reports them (FastAPI handlers+Sentry · .NET exception middleware/ProblemDetails · React error boundary / RN crash reporting). Missing → finding. | High |
| `CORE-ERR-03` | always | **No downcasting** — don't catch a specific exception and rethrow as bare `Exception`/`catch (Exception)` losing type/stack. | Medium |
| `CORE-ERR-04` | API/contracts | Validation errors raised from the **contract layer**, not as framework HTTP errors thrown inside a DTO/schema/model validator. | High |
| `CORE-ERR-05` | mature service | Machine-readable error-code registry + consistent error envelope (`{code,message,correlationId,…}`) rather than bare framework default. | Medium |

## CORE-LOG — Logging & observability (core.md §6)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `CORE-LOG-01` | always | **Structured logging via the stack's standard logger.** `print`/`Console.WriteLine`/`console.log` as logging, or the stdlib/default logger where a structured one is standard → finding (stack-specific: see module). | High |
| `CORE-LOG-02` | services | **Correlation id end-to-end**: read/generate `X-Correlation-ID`, bind to log context, echo on response, propagate across hops (HTTP/message headers). Missing → finding. | High |
| `CORE-LOG-03` | services | Logs carry trace ids and an `action`/operation field; distributed tracing (OTel) instruments inbound/outbound/DB/cache/queue where tracing is enabled. | Medium |
| `CORE-LOG-04` | error tracking enabled | Sentry conditional per-env init, drops 4xx noise, samples <100% outside prod. | Medium |
| `CORE-LOG-05` | handles PII/secrets | Sensitive-field masking before logs reach the store. | High |

## CORE-API — API & contract design (core.md §10)

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `CORE-API-01` | exposes an API | **Explicit versioning** (URL/header); new version only for changed endpoints. Missing versioning on a public API → finding. | Medium |
| `CORE-API-02` | exposes an API | Each endpoint declares a **typed response + correct status code** (201 on create, etc.) and a one-line summary/description. | Medium |
| `CORE-API-03` | list endpoints | **Bounded pagination** (offset/limit or cursor) with a capped page size. | Medium |
| `CORE-API-04` | exposes an API | A generated, accurate API doc (OpenAPI/Swagger/Scalar) exists; descriptions sourced from code. | Nice-to-have |
| `CORE-API-05` | exposes an API | Request/response/persistence shapes are separate; internals/enum ids not leaked raw to clients. | Medium |

## CORE-RES — Resilience (core.md §7)

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `CORE-RES-01` | makes outbound calls | **Timeouts on every outbound call** (HTTP/DB/cache). Unbounded waits → finding. | High |
| `CORE-RES-02` | retryable ops | **Idempotency** for retryable operations (natural key + unique constraint / idempotency key / upsert). | High |
| `CORE-RES-03` | writes then emits events | **Commit-before-publish:** persist+commit before emitting an event about the change. Publish that can precede commit → **Critical** (race); if unprovable statically → High + recommend a regression test. | Critical |
| `CORE-RES-04` | retries | Retries are bounded, with backoff, on safe operations; paired with idempotency. | Medium |
| `CORE-RES-05` | batch/concurrent | Per-item failure isolation + partial-success modeling (not all-or-nothing). | Medium |
| `CORE-RES-06` | event consumers | DLQ / poison-message policy beyond log-and-drop for repeatedly-failing valid messages. | Nice-to-have |

## CORE-TEST — Testing discipline (core.md §9)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `CORE-TEST-01` | always | Tests exist and **mirror the source tree**. No test suite → **High**. | High |
| `CORE-TEST-02` | always | A coverage **threshold is enforced** in CI (the build fails below it), floor **≥50%**. Distinguish *collected* from *enforced*: merely producing a coverage report with no failing threshold still counts as **no gate** → finding. Floor present but < 50 → finding; no threshold enforced → High. | Medium |
| `CORE-TEST-03` | always | Behavior-focused tests: AAA, data-driven success/failure tables, mock at the boundary, real/containerized deps for integration. | Nice-to-have |
| `CORE-TEST-04` | had an incident class | Regression tests for known incident classes (e.g. commit-before-publish) are present and permanent. | Medium |

## CORE-DOC — Documentation (core.md §11)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `CORE-DOC-01` | always | Public functions/classes/endpoints documented (docstring/XML-doc/JSDoc); one doc style per project. | Medium |
| `CORE-DOC-02` | always | README explains purpose, run steps, config keys, and stack posture; **no README drift** (references things that no longer exist). | Nice-to-have |

## CORE-GIT — Commits & PRs (core.md §12)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `CORE-GIT-01` | always | **Conventional Commits** enforced (commitlint config present); lowercase `<type>: <subject>` ≤50 chars, no trailing period. | Medium |

## CORE-OPS — CI/CD, build & deploy (core.md §13)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `CORE-OPS-01` | services | **Health checks**: `live` + `ready`; `ready` probes real dependencies (DB/cache/broker), not a constant. Missing dep checks → High. | High |
| `CORE-OPS-02` | always | Pre-commit + CI run the same gates (format, lint, type-check, security, tests, commitlint); CI builds the image. | Medium |
| `CORE-OPS-03` | always | Containerized (slim, multi-stage); migrations run before serving; runtime/toolchain version pinned. | Nice-to-have |
| `CORE-OPS-04` | always | Deploy via Helm; image tags promoted through environments. | Nice-to-have |

## CORE-LAYER — Layering & naming (core.md §2–§3)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `CORE-LAYER-01` | always | Transport layer is thin (no business rules / data-access in controllers/endpoints/screens). | High |
| `CORE-LAYER-02` | DB project | Data access isolated to one layer; no raw queries in transport/domain. | High |
| `CORE-LAYER-03` | always | Same logic not duplicated across transports (HTTP + queue + UI converge on one function). | Medium |
| `CORE-NAME-01` | always | Consistent casing per the language; intention-revealing names; no casing drift for one concept; no duplicate divergent enums/constants. | Medium |

---

## Scoring & severity
Use the rubric in `core.md` §14 (`./standards/core.md`). **Tie-break:** a finding matching multiple checks takes the **higher** severity; cite all matching ids. Escalate toward Critical for secret/PII leak, data loss/corruption, wrong financial outcome, unauthorized access, untrusted execution; de-escalate for isolated/cosmetic/already-mitigated. Record every adjustment + reason.

Section score: **Fail** = any Critical/High · **Partial** = only Medium/Nice · **Pass** = none above Nice · **N/A** = capability unused (cite profile).
