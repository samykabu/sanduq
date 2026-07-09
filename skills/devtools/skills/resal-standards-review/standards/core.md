# Resal Engineering Standards — Core (cross-cutting)

> **What this is.** The stack-agnostic spine of Resal's engineering standards. Every project — Python/FastAPI, .NET, React (web), React Native — inherits these principles. Each per-stack document (`python.md`, `dotnet.md`, `react-web.md`, `react-native.md`) is the **concrete expression** of these same principles in that ecosystem.
>
> **Audience.** Onboarding engineers and AI coding assistants. Read this first, then the file for your stack.
>
> **How to read a rule.** Rules are tagged **[STANDARD]** (applies everywhere, non-negotiable), **[GOOD-TO-HAVE]** (strongly recommended; mature services have it), **[NICE-TO-HAVE]** (polish). Deviations are flagged **⚠️**.
>
> **Golden rule:** *Match the project's real, in-use stack — never flag a capability the project legitimately doesn't use.* Generic principles, concrete per stack.

---

## Table of contents
1. [First principles](#1-first-principles)
2. [Layering & separation of concerns](#2-layering--separation-of-concerns)
3. [Naming discipline](#3-naming-discipline)
4. [Configuration & secrets](#4-configuration--secrets)
5. [Error handling philosophy](#5-error-handling-philosophy)
6. [Logging, correlation & observability](#6-logging-correlation--observability)
7. [Resilience](#7-resilience)
8. [Security baseline](#8-security-baseline)
9. [Testing discipline](#9-testing-discipline)
10. [API & contract design](#10-api--contract-design)
11. [Documentation & comments](#11-documentation--comments)
12. [Commits, PRs & Git workflow](#12-commits-prs--git-workflow)
13. [CI/CD, build & deploy](#13-cicd-build--deploy)
14. [The severity rubric](#14-the-severity-rubric)
15. [Universal anti-patterns](#15-universal-anti-patterns)

---

## 1. First principles

1. **Single responsibility, clear boundaries.** Every module/file/class has one job and a well-defined interface. If you can't say what a unit does in one sentence, it's doing too much.
2. **Layer inward.** Transport (HTTP/queue/UI) is the outermost ring; business rules don't depend on transport. You can change the delivery mechanism without rewriting the domain.
3. **Explicit over implicit.** Typed contracts, named constants, declared dependencies. No magic strings, no hidden globals.
4. **Fail fast, fail loud, recover deliberately.** Validate inputs at the edge; surface errors with context; never swallow exceptions silently.
5. **Everything observable.** A request must be traceable end-to-end (logs + correlation id + trace). If you can't debug it in prod from telemetry alone, it's not done.
6. **Secure & private by default.** No secrets in code; least privilege; validate all external input; protect PII (Resal handles user, payment, and loyalty data).
7. **Tested before trusted.** New behavior ships with tests that mirror the source layout. Coverage gates exist and ratchet upward.
8. **Consistency beats cleverness.** Follow the established pattern in the repo and stack. The fleet should read like it was written by one careful team.
9. **YAGNI.** Build for the requirement in front of you; don't add capability "just in case."

---

## 2. Layering & separation of concerns

**[STANDARD]** Every service separates these concerns, regardless of language:

| Concern | Responsibility | Must NOT |
|---|---|---|
| **Transport / entry** (controller, router, endpoint, screen) | parse input, authorize, delegate, shape output | contain business rules or data-access |
| **Domain / business logic** (service, handler, use-case) | orchestrate the actual work, enforce rules | know about HTTP/SQL/UI specifics |
| **Data access** (repository, CRUD, DAO, query) | the only place that talks to the database | contain business decisions |
| **Contracts** (DTO/schema/model/types) | validated shapes crossing a boundary | leak persistence details to the client |

Rules:
- **The entry layer is thin.** Resolve dependencies → authorize → log intent → delegate → return.
- **One place owns persistence.** Data-access code lives in a dedicated layer; business and transport layers call it, never inline raw queries.
- **Contracts are explicit and validated at the boundary.** Inbound payloads are validated before any logic runs; outbound shapes don't expose internal/storage representations.
- **Transports converge on the same domain logic.** An HTTP handler and a queue consumer that do "the same thing" call one shared function — don't duplicate logic per transport.
- ⚠️ **Leaks to avoid:** business rules in controllers; SQL/queries in transport or domain layers; consumers importing the API layer; the same logic copy-pasted across transports.

The per-stack docs name the concrete layers (FastAPI: api→domain→crud→models/schemas · .NET: API→Core←Infrastructure · React: route/screen→hook→api-client→types).

---

## 3. Naming discipline

**[STANDARD]**
- Names are descriptive and intention-revealing. Functions are verb phrases (`process_order`, `GetByIdAsync`, `useOrders`); data is a noun (`orderQuery`, not `getOrders`, for the value).
- One casing convention per language, applied consistently (see each stack doc): Python `snake_case`/`PascalCase`/`UPPER_SNAKE`; .NET `PascalCase`/`camelCase`/`_camelCase` + `Async` suffix; TS `camelCase`/`PascalCase` components/`use*` hooks.
- File names encode role where the stack uses that convention (`crud_order.py`, `OrderController.cs`, `useOrders.ts`).
- No abbreviations that aren't domain-standard; no one-letter names except trivial loop indices.
- Routes/endpoints are plural nouns (`/orders`, `/gift-cards`).
- ⚠️ No casing drift for the same concept (`base_url` vs `base_URL`), no duplicate divergent enums/constants for one idea.

---

## 4. Configuration & secrets

**[STANDARD]**
- **All runtime config comes from the environment**, loaded once into a single typed config object (pydantic-settings `Settings` · .NET `IOptions<T>` · React `NEXT_PUBLIC_*`/env). No scattered `os.getenv`/`Environment.GetEnvironmentVariable`/`process.env` reads throughout the code.
- **Required config has no default and fails fast at boot** if missing; optional config is explicitly typed-optional.
- **No hardcoded secrets — ever.** No passwords, tokens, API keys, connection strings, or signing keys in source, `appsettings.json`, committed `.env`, or `app.config`. This is the single most important rule in this document.
- A committed `*.example` documents required keys; the real values are injected at deploy time (**1Password** via Helm in the backend fleet; CI secrets; platform key stores).
- ⚠️ A random per-process default secret (e.g. `secrets.token_urlsafe(32)` as a fallback `SECRET_KEY`) is acceptable only in local dev and **must be set explicitly in prod** — otherwise tokens invalidate across restarts/replicas.
- Frontend: anything in the bundle is public. **Never put a secret in client config**; the client holds only public identifiers and the user's own token.

---

## 5. Error handling philosophy

**[STANDARD]**
- **Validate at the edge.** Reject bad input with a clear client error (4xx) before any work happens.
- **Errors carry context.** Log the what + the identifying ids; don't log-and-rethrow the same thing five times.
- **Never swallow.** No empty `catch`/`except: pass`. If you catch, you either handle meaningfully or re-raise. Catching to convert to a generic 500 with no log is a defect.
- **Re-raise typed, don't downcast.** Preserve the original exception type/stack; don't wrap everything in a bare `Exception`/`catch (Exception)`.
- **One global error boundary per process** translates uncaught errors into a consistent response shape and reports them (Sentry/OTel). Reuse the framework's built-in handler; add logging + capture around it.
- **Validation belongs in the contract layer, not the transport layer**, and validators raise validation errors — not framework HTTP exceptions (⚠️ raising an HTTP exception from inside a schema/DTO validator couples layers and bypasses the standard 422 path).

**[GOOD-TO-HAVE]** A machine-readable **error-code registry** (`<SVC>1xxx`) plus a consistent error envelope (`{code, message, correlationId, details}`), so clients and dashboards can branch on codes rather than parse prose.

---

## 6. Logging, correlation & observability

**[STANDARD]**
- **Structured logging only.** Emit structured/JSON logs in deployed environments via the stack's standard logger (structlog · Serilog · a shared FE logger). **No `print`/`Console.WriteLine`/`console.log`** as logging, and **no stdlib/default logger** where a structured one is the standard.
- **Correlation id end-to-end.** Every request gets an `X-Correlation-ID` (read from header or generated), bound to the logging context, echoed on the response, and **propagated across process hops** (HTTP headers, message headers). A consumer continues the same correlation/trace it received.
- **Bind intent.** Each handler binds a structured `action`/operation field (from an enumerated taxonomy) plus the key ids, so logs are filterable by operation.
- **Logs carry trace ids.** Where tracing is enabled, every log line includes `trace_id`/`span_id` so logs and traces correlate.
- **Distributed tracing** (OpenTelemetry) instruments inbound requests, outbound HTTP, DB, cache, and queue consume/produce. Backend services export OTLP.
- **Error tracking** (Sentry) is initialized conditionally per environment, drops 4xx noise, and samples traces below 100% outside production.
- **Sensitive-data masking** **[GOOD-TO-HAVE → adopt]**: a logging processor redacts a known set of sensitive fields (PINs, tokens, card numbers, PII) so secrets never reach the log store.

**[STANDARD]** **Health checks**: `live` (process up) and `ready` (dependencies reachable — DB, cache, broker). Readiness probes the real dependencies, not a constant.

---

## 7. Resilience

**[STANDARD where the capability is used]**
- **Idempotency.** Operations that can be retried (event handlers, create-by-natural-key, payment ops) are idempotent — guarded by a natural key + unique constraint, an idempotency key, or an upsert/`on conflict do nothing`.
- **Timeouts on every outbound call.** No unbounded network waits. External HTTP/DB/cache calls have explicit timeouts.
- **Retries with backoff** for transient failures, bounded, on operations known to be safe to retry; pair with idempotency.
- **Race-safety.** Read-modify-write uses row locking or atomic operations. **Commit-before-publish**: persist and commit state *before* emitting an event about it, so a fast consumer never reads a not-yet-committed row. (This is a real Resal incident class — covered by regression tests in OrderMs.)
- **Failure isolation.** In batch/concurrent work, isolate per-item failures (gather-with-exceptions then filter) and model partial success rather than failing the whole batch.
- **Startup gates.** Wait for critical dependencies (DB) to be reachable before serving (retry-with-backoff at boot).
- **Graceful degradation / offline** (frontend & mobile): handle loading, empty, error, and offline states explicitly.

**[GOOD-TO-HAVE]** A dead-letter / poison-message policy for events that are well-formed but repeatedly fail, beyond log-and-drop.

---

## 8. Security baseline

**[STANDARD]**
- **Authententicate and authorize at the boundary.** Each service documents its posture: in-service token verification for edge/privileged services; mesh-trust (gateway-terminated) for internal services — with **no dead auth code implying protection that isn't enforced**.
- **Least privilege** for every credential, role, DB grant, and cloud permission.
- **Validate and bound all external input** (size limits, type/range checks, allow-lists). Treat anything from the network, the user, a file, or a log line as untrusted.
- **No injection.** Parameterize/bind all queries; never build SQL/commands by string-formatting external input. Never `eval`/`exec`/`ast.literal_eval`/`pickle.loads`/`yaml.load`(unsafe)/`shell=True` on untrusted data.
- **Protect data at rest where required** (field-level encryption for sensitive identifiers, with a self-describing marker).
- **Static security scanning** runs in pre-commit/CI (bandit · analyzers · dependency audit). Dependencies are kept patched.
- **Frontend/mobile:** sanitize any HTML render (DOMPurify), store tokens securely (mobile: Keychain/SecureStore — **not** plain AsyncStorage; web: be explicit about XSS exposure of JS-readable token storage), and keep no secrets in the shipped bundle.

---

## 9. Testing discipline

**[STANDARD]**
- **Tests mirror the source tree** so each unit has an obvious test home.
- **Test behavior, not implementation.** Arrange/Act/Assert structure; data-driven tables for success and failure cases.
- **Mock at the boundary** (external HTTP, brokers, third-party SDKs) by the dependency seam, not the internals.
- **Integration tests use real dependencies where feasible** (in-memory or container DBs — e.g. Testcontainers in .NET, a test Postgres in Python) rather than mocking the database away.
- **A coverage gate exists in CI** (`--cov-fail-under` / coverlet threshold / Jest coverage). Treat **≥50% as the floor and ratchet upward**; new code ships with tests.
- **Regression tests for incident classes** (e.g. the commit-before-publish race) are permanent.

---

## 10. API & contract design

**[STANDARD]** (applies to any service exposing an API or a typed client)
- **Explicit versioning** (URL or header) so contracts can evolve without breaking consumers; add a new version only for endpoints that actually changed.
- **Declared response shape and status codes** on every endpoint (typed response model + correct status: `201` on create, `4xx`/`5xx` deliberately), plus a one-line summary/description.
- **Pagination is bounded** (offset/limit or cursor) with a capped page size.
- **A generated, accurate API doc** (OpenAPI/Swagger/Scalar) is part of the deliverable; descriptions come from code/docstrings.
- **Contracts are validated and don't leak internals** (separate request/response/persistence shapes; convert internal enums/ids to stable public values).

---

## 11. Documentation & comments

**[STANDARD]**
- **Public surface is documented** — every public function/class/endpoint has a docstring/XML-doc/JSDoc describing purpose, parameters, and return; for endpoints this doubles as the API description.
- **Comment the *why*, not the *what*.** Explain non-obvious decisions, edge cases, race conditions, and trade-offs. Don't narrate obvious code.
- **One doc style per project** (don't mix Google and reST docstrings, etc.).
- A **README** explains what the service is, how to run it, its config keys, and its stack posture (which optional capabilities it uses). Keep it in sync with reality (⚠️ README drift — referencing folders/flows that no longer exist — is a defect).
- Type hints/annotations are mandatory where the language supports them.

---

## 12. Commits, PRs & Git workflow

**[STANDARD]** (enforced by commitlint in pre-commit + CI across the fleet)
- **Conventional Commits, lowercase.** Types: `feat`, `fix`, `style`, `chore`, `refactor`, `docs`, `test`.
- Subject: `<type>: <subject>` — lowercase, imperative, **≤50 chars**, **no trailing period**.
- Body: blank line after subject, bullets, **≤100 chars/line**, explains *why*; include the ticket (e.g. `(CORC-1234)`).
- **PRs** summarize **all** changes since the branch was created and are updated as commits are added; branch from and keep current with the team's main branch (`develop` in the backend fleet).
- Before pushing: run the pre-commit suite, build, and tests locally. Never commit secrets.

---

## 13. CI/CD, build & deploy

**[STANDARD]**
- **Pre-commit + CI run the same gates**: format, lint, type-check, security scan, tests, commitlint. CI additionally builds the image and (where applicable) runs integration tests.
- **Containerized** with a slim, multi-stage Dockerfile; a prestart step runs migrations before the app serves.
- **Health endpoints** are wired for orchestration probes.
- **Deploy via Helm**; image tags promoted through environments (ArgoCD/Image-Updater in the backend fleet).
- Pin the runtime/toolchain version (`.nvmrc`, pinned Python, `<TargetFramework>`).

---

## 14. The severity rubric

The review skill rates every finding with this rubric. It is defined **once, here**; per-stack check catalogs assign a default severity per check that rolls up to it.

| Severity | Meaning | Cross-stack examples |
|---|---|---|
| 🔴 **Critical** | Security, data-integrity, or correctness defect that can cause an incident or breach | hardcoded secret/credential; SQL/command injection; `eval`/unsafe-deserialization on external input; auth missing where required; event published before the DB commit (race); missing rollback that leaks a partial write; secrets in the shipped client bundle / tokens in insecure mobile storage |
| 🟠 **High** | Significant deviation hurting reliability, observability, or maintainability of the whole unit | unstructured/stdlib logging instead of the standard; no correlation-id propagation; errors swallowed or downcast to bare `Exception`; no `/ready` dependency checks; no global error boundary; validation raised as HTTP errors from inside contracts; no tests / no coverage gate; no timeouts on outbound calls |
| 🟡 **Medium** | Convention deviation, locally contained | missing response model/status code/summary; missing API versioning; mixed docstring styles; naming/casing drift; lint config inconsistency (e.g. line-length mismatch); missing action/log taxonomy; non-idempotent retryable handler without justification |
| 🟢 **Nice-to-have** | Polish / hygiene | monolithic util files; raise the coverage floor; remove unused declared dependencies; consolidate duplicate enums/tokens; fix README/doc drift; remove stray committed files/typos; add DLQ policy |

**Escalate** toward Critical if the deviation can leak secrets/PII, corrupt or lose data, produce wrong financial/order/voucher outcomes, allow unauthorized access, or execute untrusted input. **De-escalate** toward Nice-to-have if isolated, cosmetic, or already mitigated. **Tie-break:** when a finding matches multiple checks, take the **higher** severity and cite all matching check IDs. Always record any adjustment and why.

---

## 15. Universal anti-patterns

Avoid in any stack (each per-stack doc adds its own):

- Hardcoded secrets / committed credentials.
- String-built SQL or shell from external input; `eval`/unsafe deserialization on untrusted data.
- Publishing an event before committing the corresponding DB change.
- Swallowing exceptions (`except: pass`, empty `catch`) or downcasting to a bare `Exception`.
- `print`/`console.log`/stdlib logger as production logging; logs without correlation/trace context.
- Business logic in the transport layer; raw queries outside the data layer; transports duplicating the same logic.
- Validation that throws framework HTTP errors from inside a contract/DTO.
- Config read ad-hoc from the environment all over the code instead of one typed object.
- No timeouts on outbound calls; retryable handlers that aren't idempotent.
- Tests absent or not mirroring the source; no coverage gate.
- Non-conventional commit messages; PRs that don't reflect the full change set.
- Dead auth code implying protection that isn't enforced.

---

*This is the shared core. Now read your stack file: [`python.md`](python.md) · [`dotnet.md`](dotnet.md) · [`react-web.md`](react-web.md) · [`react-native.md`](react-native.md). Index & detection map: [`README.md`](README.md).*
