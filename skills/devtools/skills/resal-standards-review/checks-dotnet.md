# Check Catalog — .NET (C#)

Stack-specific checks for **.NET** services (.NET 9 clean architecture + Aspire). **Run these `NET-*` checks AND all `CORE-*` checks** (`checks-core.md`). Enforces `./standards/dotnet.md` + `core.md`.

> **No double-counting:** a concern matching a CORE check is recorded under the CORE id; the ".NET detection for CORE checks" notes give C# evidence patterns. `NET-*` are .NET-specific concerns.
> Gate on the stack profile (EF Core? Aspire? Refit? HybridCache/Redis? Outbox? API-Key vs JWT?).

---

## NET-ARCH — Solution & layering

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-ARCH-01` | always | Clean-arch dependency direction: Core references nothing internal; Infrastructure→Core only; API→Core+Infra. Grep `ProjectReference` in each csproj; API referenced from Core/Infra → finding. | High |
| `NET-ARCH-02` | Aspire | Aspire defaults (`AddServiceDefaults`/`ConfigureOpenTelemetry`/`MapDefaultEndpoints`) in a **dedicated ServiceDefaults project**, not inlined into Infrastructure. | Nice-to-have |
| `NET-ARCH-03` | always | One public type per file; controllers in API (not `BaseController` in Infrastructure). | Nice-to-have |

## NET-NAME — Naming & style

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-NAME-01` | always | **File-scoped namespaces** (`namespace X;`). Grep block-scoped `namespace X\n{` → finding. | Medium |
| `NET-NAME-02` | always | Private fields `_camelCase`; **`*Async` suffix on awaitable public methods** (handlers/actions/repos). Mixed `_field`/`field`, `Handle` not `HandleAsync` → finding. | Medium |
| `NET-NAME-03` | always | Interfaces `I`-prefixed; PascalCase types/methods/consts; feature-folder layout (`Core/Feature/<F>/{Command,Handler,Response}`). | Nice-to-have |

## NET-CQRS — Business logic

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-CQRS-01` | always | Business logic in Core handlers (`ICommandHandler<,>` or MediatR), registered by DI; controllers thin. Logic in controllers → finding (also CORE-LAYER-01). | High |
| `NET-CQRS-02` | always | Commands/Responses separate from entities; mapping explicit. | Medium |
| `NET-CQRS-03` | list endpoints | List endpoints return `PagedResult<T>` from `PagedQuery<T>`. | Medium |

## NET-VAL — Validation

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-VAL-01` | has request bodies | DataAnnotations (or FluentValidation) on commands + central `InvalidModelStateResponseFactory` → RFC-7807. One validation approach, not a mix of mentioned-but-absent libs. | Medium |

## NET-API — API design

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-API-01` | exposes API | **Asp.Versioning** URL-segment (`v{version:apiVersion}/[controller]`); `[ApiController]`+`[ApiVersion]`+`[Tags]` on controllers. Missing versioning → finding (record under **CORE-API-01**). | Medium |
| `NET-API-02` | exposes API | Full `ProducesResponseType` set (typed 200 + error codes) + `[EndpointSummary]` per action. | Medium |
| `NET-API-03` | exposes API | **ProblemDetails** is the error contract; OpenAPI via Swagger/Scalar. | Medium |
| `NET-API-04` | always | Single controller base (not mixed `BaseController`/`ControllerBase`). | Nice-to-have |

## NET-CFG — Configuration & secrets (.NET detail for CORE-SEC/CORE-CFG)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-CFG-01` | always | **No secrets in `appsettings*.json`.** Grep for `KEY`/`SECRET`/`ACCESS_KEY`/`PASSWORD`/JWT key/`AKIA[0-9A-Z]{16}` with real values → **Critical** (record under **CORE-SEC-01**; rotate). | Critical |
| `NET-CFG-02` | always | **Strongly-typed `IOptions<T>`** with validation, not `IConfiguration.GetValue` reads scattered in handlers. | Medium |
| `NET-CFG-03` | Aspire | Connection via Aspire names + env overlay (`POSTGRES_*`/`REDIS_*`); User Secrets for dev. | Nice-to-have |

## NET-DB — Persistence (EF Core)

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `NET-DB-01` | EF Core | `DbContext` with `ApplyConfigurationsFromAssembly` + `IEntityTypeConfiguration<T>` per entity; `AuditableEntity` base + soft-delete query filter. | Medium |
| `NET-DB-02` | EF Core | **Read-only queries use `AsNoTracking()`.** No `AsNoTracking` anywhere → **High**. | High |
| `NET-DB-03` | EF Core | **Generic `RepositoryBase<T>`** — repos inherit it, not N× duplicated `IRepository<T>` impls (with `NotImplementedException`/sync-over-async). **Independent of NET-DB-04** — a project can have a generic base (passes 03) yet still `SaveChanges` per call (fails 04); evaluate each separately. | High |
| `NET-DB-04` | EF Core | Transactions via `CreateExecutionStrategy()` + `BeginTransactionAsync` (commit/rollback/throw); a real unit-of-work boundary — **not** `SaveChanges` inside each `AddAsync`/`UpdateAsync`. Evaluate independently of NET-DB-03. | Medium |
| `NET-DB-05` | EF Core | Migrations in Infra, applied at startup outside `Testing`; `IDesignTimeDbContextFactory` for tooling. | Nice-to-have |

> SQL injection (`FromSqlRaw`/interpolated SQL) → record under **CORE-SEC-02**.

## NET-ERR — Error handling (.NET detail for CORE-ERR)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-ERR-01` | always | **Global exception middleware** maps typed domain exceptions → ProblemDetails; registered first; checks `Response.HasStarted`. Missing → finding (record under **CORE-ERR-02**). | High |
| `NET-ERR-02` | always | Domain rules throw **domain exceptions** (`Core/Exceptions/`), not framework `InvalidOperationException`/`KeyNotFoundException`. | Medium |
| `NET-ERR-03` | prod | 500 ProblemDetails does **not** leak `ex.Message` outside dev. | Medium |

## NET-OBS — Logging & observability (.NET detail for CORE-LOG)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-OBS-01` | always | OpenTelemetry traces+metrics+logs via OTLP (AspNetCore/HttpClient/Npgsql/EFCore/Redis/Runtime); health endpoints filtered from traces. | Medium |
| `NET-OBS-02` | always | **Serilog structured templates only** — `LogInformation("...{X}", x)`, never string interpolation in the message. Grep `Log\w+\($"` → finding. | Medium |
| `NET-OBS-03` | always | Scope middleware binds correlation id (`TraceIdentifier`) + client IP (record correlation under **CORE-LOG-02**). | High |

## NET-RES — Resilience

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `NET-RES-01` | outbound HTTP | `AddStandardResilienceHandler` on all HttpClients + Refit clients (retry + total-timeout). Missing → finding (record timeout under **CORE-RES-01**). | High |
| `NET-RES-02` | outbound HTTP | **Refit** typed clients; interfaces in **Core**, registered in Infra, with a logging handler. | Medium |
| `NET-RES-03` | cross-service side effects | **Outbox pattern** + background dispatcher with backoff for at-least-once delivery. | Medium |
| `NET-RES-04` | mutating endpoints | Idempotency on a business key. (record under **CORE-RES-02**) | High |

## NET-CACHE — Caching

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `NET-CACHE-01` | uses cache | **HybridCache** preferred over raw `IDistributedCache`/`IConnectionMultiplexer`; key-prefix + TTL convention. | Nice-to-have |

## NET-SEC — Auth & security

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-SEC-01` | has auth | Policy-based authz with **policy constants** (no magic strings); identity via `ClaimsPrincipal` extensions; auth in `Authentication/`. | Medium |
| `NET-SEC-02` | parses JWT | JWT validated with signature (not `ReadJwtToken` for trust). Reading JWT without validation for authz → **Critical**. | Critical |
| `NET-SEC-03` | always | `Nullable=enable` in all projects **and** analyzers + `TreatWarningsAsErrors` so nullable warnings fail the build. Nullable on but warnings-as-errors off → finding. | Medium |

## NET-ASYNC — Async/concurrency

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-ASYNC-01` | always | **`CancellationToken` propagated** through handler contract + controller actions + repo methods. Handler `Handle` without `CancellationToken` → finding. | Medium |

## NET-TEST — Testing (.NET detail for CORE-TEST)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-TEST-01` | always | xUnit + FluentAssertions + NSubstitute; `Method_State_Expected`; AAA. Missing tests → finding (record under **CORE-TEST-01**). | High |
| `NET-TEST-02` | hits DB | **Testcontainers** Postgres integration; `public partial class Program {}` for `WebApplicationFactory`. | Medium |
| `NET-TEST-03` | always | Don't duplicate the exception→ProblemDetails mapping in test helpers (drifts from middleware); have real over-HTTP endpoint tests. | Nice-to-have |

## NET-TOOL — Tooling

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-TOOL-01` | always | **`.editorconfig`** present (enforces file-scoped namespaces, naming, formatting). Missing → finding. | Medium |
| `NET-TOOL-02` | multi-project | **`Directory.Packages.props`** (Central Package Management) — versions not duplicated/drifting across csproj. Missing/version drift → finding. | Medium |
| `NET-TOOL-03` | always | **`Directory.Build.props`** (shared Nullable/LangVersion/AnalysisLevel/TreatWarningsAsErrors) + **`global.json`** (pinned SDK); `dotnet format` + analyzers in CI. | Nice-to-have |

## NET-OPS — Build & deploy (.NET detail for CORE-OPS)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `NET-OPS-01` | always | Multi-stage **Alpine** Docker, **non-root `$APP_UID`**, port 8080. | Nice-to-have |
| `NET-OPS-02` | Aspire | AppHost wires Postgres/Redis/API via `.WithReference`/`.WaitFor`. | Nice-to-have |
| `NET-OPS-03` | services | `/health` + `/alive` probes (record dependency-readiness under **CORE-OPS-01**). | High |

---

## .NET anti-patterns (also flag)
secrets in `appsettings.json` (NET-CFG-01/CORE-SEC-01, Critical) · no `.editorconfig`/CPM/`Directory.Build.props`/`global.json` (NET-TOOL) · no analyzers/`TreatWarningsAsErrors` (NET-SEC-03) · **`AsNoTracking` never used** (NET-DB-02) + no `RepositoryBase<T>` (NET-DB-03) · `SaveChanges` per call (NET-DB-04) · **no `CancellationToken`** (NET-ASYNC-01) · block-scoped namespaces / `_field` drift / missing `*Async` (NET-NAME) · `IConfiguration` over `IOptions<T>` (NET-CFG-02) · 500 leaks `ex.Message` (NET-ERR-03) · JWT read without signature validation (NET-SEC-02, Critical) · test helper duplicates middleware (NET-TEST-03) · ServiceDefaults inlined in Infra / `BaseController` misplaced (NET-ARCH-02/03).
