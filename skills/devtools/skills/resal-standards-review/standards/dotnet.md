# Resal .NET (C#) Standards

> **Inherits [`core.md`](core.md).** Read core first. Tags: **[STANDARD]** / **[GOOD-TO-HAVE]** / **[NICE-TO-HAVE]** / **⚠️**.
>
> **Baseline exemplar:** **ResalPay** (`Resal.PointPaymentGateway`, .NET 9 / C# 13). Clean-architecture split + Aspire confirmed across `OrderUpdatesMS_Net` and `NotifyHub-MS` (tagged **[shared]**).
>
> **Note:** ResalPay ships `.github/instructions/csharp.instructions.md` with aspirational rules the code only partially follows. This standard states the rule **and** flags where the code diverges so it's auditable.

## Stack [STANDARD]

.NET 9 / C# 13 · **clean architecture** (API → {Core, Infrastructure}, Infrastructure → Core) + **.NET Aspire** AppHost · ASP.NET Core MVC controllers + **Asp.Versioning** · **EF Core + Npgsql** + migrations · custom **CQRS** (`ICommandHandler<TCommand,TResult>`, no MediatR) + **repository pattern** · **Serilog → OpenTelemetry** (OTLP) · `Microsoft.Extensions.Http.Resilience` + **Refit** · **HybridCache** over Redis · API-Key + JWT auth, policy-based · **ProblemDetails** errors · **Outbox** · xUnit + FluentAssertions + NSubstitute + **Testcontainers** · nullable enabled · multi-stage Alpine Docker + Helm + ECR.

## 1. Solution & layering [STANDARD]

Four runtime projects + tests. **Dependency direction is the rule:** `Core` references nothing internal (the center); `Infrastructure` → Core only; `API` → Core + Infrastructure; `AppHost` orchestrates. **Never reference API from Core/Infrastructure.**

- **Core** — entities, enums, **feature handlers (CQRS)**, interfaces, DTOs (Command/Response), options, outbox contracts.
- **Infrastructure** — `DbContext`, repositories, Refit clients, AWS, background services, DI/observability aggregator.
- **API** — controllers, middleware, authentication, `Program.cs`.
- **AppHost** — Aspire (Postgres, Redis, API wiring).

**[GOOD-TO-HAVE]** Put the Aspire `AddServiceDefaults`/`ConfigureOpenTelemetry`/`MapDefaultEndpoints` in a **dedicated `ServiceDefaults` project** (as `OrderUpdatesMS_Net` does). ⚠️ ResalPay inlines these into `Infrastructure/Setup.cs` and misplaces `BaseController` in Infrastructure — avoid both.

## 2. Naming & files [STANDARD]

Namespaces mirror folders (`Resal.<Svc>.<Layer>.<Folder>`); **one public type per file**; **file-scoped namespaces** (`namespace X;`). PascalCase types/methods/members/consts; camelCase locals/params; `I`-prefixed interfaces; **private fields `_camelCase`**; **`*Async` suffix on every awaitable public method**. **Feature-folder** organization: `Core/Feature/<Feature>/{XxxCommand, XxxCommandHandler, XxxResponse}.cs`.
⚠️ Baseline diverges: ~140 files still block-scoped namespaces; mixed `_field`/`field`; `Handle` (not `HandleAsync`); enforce via `.editorconfig` (§16).

## 3. Layering & CQRS [STANDARD]

Business logic lives in **Core feature handlers** implementing `ICommandHandler<TCommand,TResult>`, registered by **assembly scanning** in DI. Commands/Responses are separate from entities. **Mapping is manual** (no AutoMapper). List endpoints return **`PagedResult<T>`** from a `PagedQuery<T>`.

```csharp
public interface ICommandHandler<TCommand, TResult>
    where TCommand : ICommand where TResult : IResponse
{ Task<TResult> Handle(TCommand command); }   // add CancellationToken — see §14
```

⚠️ Controllers inject the **concrete** handler via `[FromServices]` (not substitutable) and handlers read `IConfiguration` directly — prefer typed options (§7).

## 4. Validation [STANDARD]

**DataAnnotations on commands** + custom attributes (`Core/Validators/Attributes/`), surfaced through a **central `InvalidModelStateResponseFactory`** that returns RFC-7807 `ValidationProblemDetails` with an `errorsList` extension. Bind explicitly (`[FromBody]`/`[FromQuery]`/`[FromRoute]`).
⚠️ The instructions mention FluentValidation but none exists — pick one (DataAnnotations is what's real).

## 5. API design [STANDARD]

Controller-based MVC; **URL-segment versioning** (`Asp.Versioning`, `v{version:apiVersion}/[controller]`). Every controller: `[ApiController]` + `[ApiVersion]` + `[Tags("area")]`. Every action: full `ProducesResponseType` set (typed 200 + 400/401/403/404/500) + `[EndpointSummary]`/`[EndpointDescription]`, returning `Results.Ok(...)`. **ProblemDetails** is the universal error contract. **OpenAPI** via multi-doc Swagger + **Scalar** + ReDoc. ⚠️ Pick one controller base (baseline mixes `BaseController`/`ControllerBase`).

## 6. Configuration & secrets [STANDARD]

Aspire connection names (`"resalpay-db"`, `"redis-cache"`); env-var overlay merge (`POSTGRES_*`/`REDIS_*`); **User Secrets** for dev. **Strongly-typed options** bound via `IOptions<T>` with validation — ⚠️ baseline reads `IConfiguration` directly; fix.
⚠️ **CRITICAL: NO secrets in `appsettings*.json`.** ResalPay commits live AWS keys, the JWT signing key, and API keys — these must be **rotated** and moved to env/user-secrets/1Password/Aspire parameters. This is the top fleet-level .NET defect.

## 7. Persistence (EF Core) [STANDARD]

`DbContext` with `ApplyConfigurationsFromAssembly` + a global **soft-delete query filter**; one `IEntityTypeConfiguration<T>` per entity; `AuditableEntity` base (`Id` GUID app-generated, `CreatedAt`/`LastUpdateAt`/`IsDeleted`/`DeletedAt`). **Repository pattern** via `IRepository<T>` (`GetQueryableWithIncludes`, `GetPagedAsync(PagedQuery<T>)`, `RunInTransaction`). **Transactions** via `CreateExecutionStrategy()` + `BeginTransactionAsync` (commit/rollback/throw). Migrations applied at startup (outside `Testing`).

⚠️ **High-impact gaps to fix:** **`AsNoTracking()` is never used** — read-only queries **must** use it; **no `RepositoryBase<T>`** — 17 repos duplicate `IRepository<T>` (with `NotImplementedException` + sync-over-async drift) → add a generic base; `AddAsync`/`UpdateAsync` call `SaveChanges` internally, defeating unit-of-work.

## 8. Error handling [STANDARD]

A single **global exception middleware** (`sealed`, registered first) maps **typed domain exceptions** (`Core/Exceptions/`) → status + **ProblemDetails** (`application/problem+json`); check `Response.HasStarted` before writing. Business rules throw domain exceptions, not framework ones.
⚠️ Don't leak `ex.Message` into 500 ProblemDetails in non-dev; avoid reflection-based result exceptions; don't throw `InvalidOperationException`/`KeyNotFoundException` for domain conditions.

## 9. Logging & observability [STANDARD, shared]

**OpenTelemetry** traces + metrics + logs via OTLP, with AspNetCore/HttpClient/Npgsql/EFCore/Redis/Runtime instrumentation, health endpoints filtered out of traces, resource attributes set. **Serilog** via the OTel logging provider. **Structured templates only** (`LogInformation("...{MerchantId}", id)`) — never string interpolation in log messages. A scope middleware begins a logging scope with **correlation id** (`TraceIdentifier`) + project + resolved client IP. Health: `/health` (all) + `/alive` (live). Export via `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_EXPORTER_OTLP_PROTOCOL`.

## 10. Resilience [STANDARD, shared]

`AddStandardResilienceHandler` (retry + total-timeout) on **all** HttpClients and per **Refit** client; Refit client **interfaces live in Core**, registered in Infrastructure, with a `RefitLoggingHandler`. **Idempotency** on a business key (e.g. Authorize on `ResalOrderId`). **Outbox pattern** (`OutboxMessage` w/ `RowVersion` + `(Status,NextAttemptAt)` index) + background dispatcher with exponential backoff for at-least-once cross-service side effects.

## 11. Caching [STANDARD where used]

**`HybridCache`** (L1 in-memory + Redis L2) preferred over raw `IDistributedCache`/`IConnectionMultiplexer`; backed by the Aspire-registered Redis. **[GOOD-TO-HAVE]** define a key-prefix + TTL convention (⚠️ currently ad hoc).

## 12. Auth & security [STANDARD]

Auth schemes in `Authentication/`; **policy-based authorization with policy constants** (never magic strings); read identity via `ClaimsPrincipal` extension methods. API-Key (`X-API-Key`, Internal + DB-backed Merchant keys → role claims) is the live scheme. **Nullable reference types enabled** in every project; non-root container; HTTPS redirection; forwarded headers.
⚠️ **Treat warnings as errors + enable analyzers** (absent today, so nullable warnings don't fail the build). ⚠️ Don't read JWT without signature validation. ⚠️ Secrets out of `appsettings` (§6).

## 13. Async / concurrency [STANDARD]

`async`/`await` end-to-end; `await using` for transactions/disposables. **Propagate `CancellationToken`** through `ICommandHandler.Handle`, controller actions, and repository methods — ⚠️ baseline omits it from the handler contract; add it. Document the explicit decision: no `ConfigureAwait(false)` in ASP.NET Core app code (no sync context).

## 14. Testing [STANDARD, shared]

xUnit + **FluentAssertions** + **NSubstitute** (Moq present) + Bogus + MockQueryable + **Testcontainers.PostgreSql** + coverlet + `Microsoft.AspNetCore.Mvc.Testing`. Naming `Method_State_Expected`; AAA (no comment labels). Hand-written fakes in `Tests/Fakes/` preferred over mocks for repositories. Expose `public partial class Program {}` for `WebApplicationFactory`. Collect coverage with coverlet (enforce a floor).
⚠️ Don't re-implement the exception→ProblemDetails mapping in test helpers (it drifts from the middleware); add real over-HTTP endpoint tests.

## 15. Tooling [STANDARD]

`net9.0`, `Nullable=enable`, `ImplicitUsings=enable`, `GenerateDocumentationFile=true` in all projects. **Required shared files (⚠️ all missing in ResalPay — add them):** `.editorconfig` (enforce file-scoped namespaces, naming, formatting), **`Directory.Packages.props`** (Central Package Management — versions already drift), **`Directory.Build.props`** (shared `Nullable`/`LangVersion`/`AnalysisLevel`/`TreatWarningsAsErrors`), **`global.json`** (pin SDK). Run **analyzers** + `dotnet format` in CI. Conventional commits; branch from `develop`.

## 16. Build & deploy [STANDARD, shared]

Multi-stage **Alpine** Docker (sdk → aspnet runtime), csproj-first restore, `UseAppHost=false`, **non-root `$APP_UID`**, port 8080. **Aspire AppHost** for local orchestration (Postgres + Redis + API via `.WithReference`/`.WaitFor`). `/health` + `/alive` probes. Per-env Helm + env config; build/push to **ECR** per environment branch.

## Capability matrix

| Capability | ResalPay | OrderUpdatesMS_Net | NotifyHub-MS |
|---|:--:|:--:|:--:|
| Clean arch (API/Core/Infra/AppHost) | ✅ | ✅ | ✅ |
| Dedicated ServiceDefaults project | ⚠️ in Infra | ✅ | ✅ |
| EF Core + repository + Outbox | ✅ | partial | partial |
| OTel + Serilog + health | ✅ | ✅ | ✅ |
| Resilience + Refit | ✅ | — | — |
| HybridCache/Redis | ✅ | — | — |
| `.editorconfig`/CPM/`Directory.Build.props`/`global.json` | ❌ | check | check |

## .NET anti-patterns (+ core §15)

⚠️ **secrets committed in `appsettings.json`** (Critical — rotate) · no `.editorconfig`/CPM/`Directory.Build.props`/`global.json` · no analyzers / not `TreatWarningsAsErrors` · **`AsNoTracking` never used** + no `RepositoryBase<T>` (duplicated impls, `NotImplementedException`, sync-over-async) · `SaveChanges` inside `AddAsync`/`UpdateAsync` (no UoW) · **no `CancellationToken`** in handler/controller contract · block vs file-scoped namespace split · inconsistent `_field` naming + missing `*Async` suffix · `IConfiguration` read instead of typed `IOptions<T>` · 500 leaks `ex.Message`; JWT read without signature validation · test helper duplicates middleware mapping; few over-HTTP tests · ServiceDefaults inlined in Infrastructure; `BaseController` misplaced.

## Checklists

**New service:** Aspire solution (API/Core/Infrastructure/**ServiceDefaults**/AppHost) · `.editorconfig` + `Directory.Build.props` + `Directory.Packages.props` + `global.json` · nullable + analyzers + `TreatWarningsAsErrors` · CQRS `ICommandHandler` (+ `CancellationToken`) + assembly-scan DI · EF Core + `IEntityTypeConfiguration` + `AuditableEntity` + soft-delete filter + `RepositoryBase<T>` + `AsNoTracking` reads · typed `IOptions<T>` + secrets out of appsettings · Asp.Versioning + `ProducesResponseType` + ProblemDetails + Scalar · global exception middleware · OTel+Serilog + `/health`+`/alive` · resilience handler + Refit (interfaces in Core) + Outbox · HybridCache · API-Key/JWT policy constants · xUnit+FluentAssertions+NSubstitute+Testcontainers + `public partial class Program` + coverage floor · multi-stage Alpine non-root Docker + Helm + ECR.

**New feature:** `Core/Feature/<Feature>/` with `Command`+`Handler : ICommandHandler<,>`+`Response` · DataAnnotations + custom attributes · repository method (`AsNoTracking` if read) · controller action (versioned route, `ProducesResponseType`, `[Tags]`, `Results.Ok`) · domain exceptions → middleware · `Method_State_Expected` tests (+ Testcontainers if it hits the DB).
