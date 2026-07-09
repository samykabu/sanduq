# Resal Python / FastAPI Standards

> **Inherits [`core.md`](core.md).** This file is the Python-specific expression of the core principles. Read core first. Tags: **[STANDARD]** / **[GOOD-TO-HAVE]** / **[NICE-TO-HAVE]** / **⚠️**.
>
> **Baseline exemplar:** **OrderMs** — the richest reference service. Patterns confirmed across InventoryMs, Restock, VoucherMS, resal-admin-backend. All services are scaffolded from the same Resal **cookiecutter "micro service template"** (`pyproject.toml` → `description = "Resal micro service template"`).
>
> **Golden rule (from core):** match the service's *real* stack — several services legitimately omit Redis, Kafka, in-service JWT, or Unleash. See the [capability matrix](#capability-matrix).

## Stack [STANDARD]

Python `3.11.9` (pinned) · FastAPI · Pydantic **v2** + pydantic-settings · SQLAlchemy 2.0 **async** + asyncpg · Alembic · faust-streaming (consume) + aiokafka (produce/health) · redis(asyncio) · structlog · OpenTelemetry · sentry-sdk · tenacity · UnleashClient · httpx[http2] · python-jose + passlib[bcrypt] · Poetry · pytest + pytest-asyncio + pytest-cov · black/isort/flake8/mypy/bandit/docformatter + pre-commit.

## 1. Project structure [STANDARD]

Source package is **`app/`** (not `src/`):

```
app/
  main.py                 # FastAPI app: middleware, exception handlers, health, router mounting
  api/
    deps.py               # DI: get_session, auth, feature-flag gate
    api_v1/{api.py, endpoints/<domain>.py}
    api_v2/{api.py, endpoints/<domain>.py}   # only for evolved endpoints
  core/{config.py, constants.py, security.py}
  crud/{base.py, crud_<domain>.py, __init__.py}
  models/<domain>.py      # SQLAlchemy ORM
  schemas/<domain>.py     # Pydantic (+ utils.py)
  db/{session.py, base_class.py, base.py}
  <domain>/  or  src/     # business logic / event-driven core (producer.py, <svc>_processor.py, events/)
  context_store/context.py
  logs/{log_conf.py, log_actions.py}
  redis_store/            # if used
  alembic/{env.py, versions/}
  tests/                  # mirrors app/ exactly
```

**Per-domain fan-out [STANDARD]:** a new entity = `models/<d>.py` + `schemas/<d>.py` + `crud/crud_<d>.py` + `api/api_v1/endpoints/<d>.py` + `tests/.../test_<d>.py` + a `<Domain>Actions` log enum. Business logic dir name varies (`orders/`, `operations/`, `src/controllers/`) — pick one per service; default `app/<domain-plural>/` for logic + `app/src/` for events.

## 2. Naming [STANDARD]

`snake_case` funcs/vars · `PascalCase` classes · `UPPER_SNAKE` constants/enum members · lowercase module singletons (`order = CRUDOrder(Order)`, `settings`, `redis_client`, `logger`). CRUD classes are **`CRUD<Domain>`**; modules `crud_<domain>.py`. Routes are plural kebab nouns. ⚠️ camelCase helpers (`setRequestInitialContext`) are a template artifact — new code is snake_case.

**Dual Int/Str enum [STANDARD]:** store an `IntEnum` in the DB, expose a `str, Enum` on the API, bridge with validators:
```python
class Source(IntEnum): ADMIN = 1; STORE = 3
class SourceStr(str, Enum):
    ADMIN = "ADMIN"; STORE = "STORE"
    @classmethod
    def _missing_(cls, v): return next((s for s in cls if s.value == v.upper()), None)
```

## 3. Layering [STANDARD]

`endpoint (thin) → domain logic → crud (only SQL) → models + schemas`. Endpoints: `bind_contextvars(action=…)` → log → delegate → return. Cross-layer imports via aggregators (`from app import crud, schemas, src`).

```python
@router.get("/", response_model=List[schemas.Category])
async def get_categories(session: AsyncSession = Depends(deps.get_session)) -> List[schemas.Category]:
    bind_contextvars(action=CategoryActions.RETRIEVE_BULK)
    logger.info("Getting all existing categories")
    return await crud.category.get_multi(session=session)
```

## 4. Configuration [STANDARD]

One `pydantic-settings` singleton in `core/config.py`; required vars typed without default; DB URI assembled by a `field_validator`; `model_config = SettingsConfigDict(case_sensitive=True)`. Header names are config constants. Secrets via 1Password in Helm; `.env.example` committed, `.env` not.

```python
@field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
@classmethod
def assemble_db_connection(cls, v, info):
    return v if isinstance(v, str) else "postgresql+asyncpg://{}:{}@{}/{}".format(
        info.data["POSTGRES_USER"], info.data["POSTGRES_PASSWORD"],
        info.data["POSTGRES_SERVER"], info.data["POSTGRES_DB"])
```

## 5. Schemas & validation (Pydantic v2) [STANDARD]

Family per domain: `<D>Base / <D>CreateRequest / <D>CreateDB / <D>Update / <D>`(response, `from_attributes=True`). `field_validator`/`model_validator` + `@classmethod`. `model_dump(exclude_none=True)` for partial updates. Discriminated unions for polymorphic payloads. Localized ar/en fields via shared base classes in `schemas/utils.py`.
⚠️ **Never raise `HTTPException` inside a validator** — raise `ValueError`/`PydanticCustomError`.

## 6. API design [STANDARD]

`APIRouter` per module → aggregated in `api_v1/api.py` → mounted under `settings.API_V*_STR`. URL versioning (`api_v1`/`api_v2`), v2 only for evolved endpoints. Keyword-only signatures, `Depends(deps.get_session)`. Declare a response (`response_model=` or return annotation); set `status_code` for non-200 success; docstring-as-OpenAPI. Offset/limit pagination capped (`Field(100, le=100)`). Docs at `/docs` + `/redocs`; gate in prod.

## 7. Persistence [STANDARD]

Async engine + `sessionmaker(expire_on_commit=False, class_=AsyncSession)`; `get_session` owns the transaction (`async with session.begin()`). Declarative `Base` auto-derives `__tablename__`. **Generic `CRUDBase[Model, Create, Update]`** subclassed per domain + lowercase singleton re-exported in `crud/__init__.py`. SQLAlchemy 2.0 imperative style + `.returning(literal_column("*"))`. **Every CRUD method:** `try/except (SQLAlchemyError, DBAPIError)` → `rollback()` → `logger.error` → `raise` (re-raise; ⚠️ don't wrap in bare `Exception`). `with_for_update(nowait=False)` for read-modify-write. Idempotent M2M via `on_conflict_do_nothing`.

```python
class CRUDOrder(CRUDBase[Order, schemas.OrderCreateDB, Order]):
    async def get_pending_by_source(self, session, *, order_id, source):
        try:
            q = await session.execute(select(Order).where(Order.order_id == order_id)
                .where(Order.status == schemas.OrderState.PENDING).with_for_update(nowait=False))
            return q.scalar()
        except (SQLAlchemyError, DBAPIError) as error:
            await session.rollback(); logger.error("CRUD ERROR: get pending", error=error); raise
order = CRUDOrder(Order)
```

**Alembic:** `target_metadata = Base.metadata`; `db/base.py` imports every model; `compare_type=True`; new models must be added to `db/base.py`. ⚠️ **SQL injection:** bind params (`text("... = :x")`, `{"x": v}`); never f-string SQL. JSONB filters use bound params.

## 8. Error handling [STANDARD]

`HTTPException` + `fastapi.status` constants. Global handlers in `main.py` re-use FastAPI built-ins + Sentry capture for `StarletteHTTPException` and `RequestValidationError`. **[GOOD-TO-HAVE]** error-code registry (`<SVC>1xxx`) + `MessageProcessingError(error_code=…)` + explicit envelope. ⚠️ no `except Exception: pass`.

## 9. Logging & observability [STANDARD]

`from app.logs import log_conf; logger = log_conf.Logger(__name__)` — **never `logging.getLogger` or `print`**. structlog: JSON in deployed envs, console local, OTel `trace_id`/`span_id` injected per line, third-party loggers captured. `bind_contextvars(action=<Domain>Actions.X, …)` at each handler; actions are StrEnums in `log_actions.py`. Correlation id via `context_store/context.py` contextvars — set per request (middleware) and per consumed message, echoed on response, propagated to Kafka headers. Sentry: conditional init, `before_send` drops 4xx, env `traces_sampler`. OTel instruments FastAPI + httpx + manual consumer spans. **[GOOD-TO-HAVE → adopt]** `mask_sensitive_log_fields` processor over `SENSITIVE_FIELDS`.

## 10. Event-driven (Kafka/Faust) [STANDARD where used]

Consume via faust `@app.agent` in `app/src/<svc>_processor.py`; produce/health via aiokafka. Envelope `{"body_args": {...}}`; two-stage key validation (`PROTOCOL_KEYS` + `EVENT_SCHEMA_KEYS`), drop-and-log invalid. `produce_to_topic` injects correlation + W3C trace headers (`propagate.inject`). Per-message try/except so one bad message can't kill the agent; `SpanKind.CONSUMER`. **Commit-before-publish** (race fix; regression-tested). ⚠️ no DLQ fleet-wide → [GOOD-TO-HAVE] gap.

## 11. Caching / Redis [STANDARD where used]

`redis.asyncio.Redis` singleton in `redis_store/base.py`, `decode_responses=True`. Keys `PREFIX:id` + `PREFIX_ids` set; atomic via `pipeline(transaction=True)`; `model_dump_json`/`model_validate_json`. ⚠️ no file-based cache (`tokens.txt`).

## 12. Auth & security [STANDARD]

Posture per service: edge/privileged (OrderMs, admin-backend) decode JWT in-service (`python-jose`, HS256); internal mesh services trust the gateway via `Proxy-Client-Source` (no dead JWT code). RBAC reference = admin-backend `GetCurrentUser(api_name=…|services=[…])` + 5-table permission model. Field encryption: Fernet/AES-SIV with `encrypted::` prefix. `bandit` in pre-commit.

## 13. Resilience [STANDARD]

tenacity startup DB-readiness gate (`backend_pre_start.py`). Idempotency: lookup-before-create + unique composite index. `with_for_update` locks. Commit-before-publish. `asyncio.gather(..., return_exceptions=True)` + filter for batch isolation. Registry dispatch (`HANDLERS = {…}; if h := HANDLERS.get(k)`) over if/elif chains.

## 14. Testing [STANDARD]

`pytest` + `pytest-asyncio`; `tests/` mirrors `app/`; `@pytest.mark.asyncio`. `conftest.py`: NullPool engine, `dependency_overrides[get_session]`, `LifespanManager` + `AsyncClient(ASGITransport)`. AAA blocks; parametrized success/failure tables; factories in `tests/utils/utils.py`; mock by module path. Coverage gate in `tests-start.sh` (`--cov-fail-under=N`; ⚠️ floors of 20-28 are too low — target ≥50). Commit-before-publish regression test for event-driven + DB services.

## 15. Tooling [STANDARD]

pre-commit: black, flake8, isort, bandit, docformatter, commitlint, mypy, unit-tests. **Line length 127** (black/flake8/isort) — ⚠️ fix `[tool.isort] line_length = 88` drift. mypy schema-strict: global `ignore_errors=True` but `[mypy-app.schemas.*]` strict + pydantic/sqlalchemy plugins.

## 16. Build & deploy [STANDARD]

Dockerfile `python:3.11.9-slim` + Poetry `virtualenvs.create false`; `prestart.sh` → `backend_pre_start.py` → `alembic upgrade head` → app/worker. Two runtimes for event-driven services (uvicorn + faust worker). `/health/live` + `/health/ready` (DB `SELECT 1`, Redis ping, Kafka brokers; faust stuck-worker detection). Helm + ECR + ArgoCD.

## Capability matrix

| Capability | OrderMs | InventoryMs | VoucherMS | Restock | admin-backend |
|---|:--:|:--:|:--:|:--:|:--:|
| Async SQLAlchemy + Postgres | ✅ | ✅ | ✅ | ❌ | ✅ |
| `CRUDBase` generic | ✅ | ✅ | ✅ | — | ⚠️ hand-written |
| Kafka (Faust+aiokafka) | ✅ | ✅ | ✅ | ✅ | ❌ |
| Redis | ✅ | ✅ | ❌ | ❌ | ❌ |
| structlog + OTel + Sentry | ✅ | ✅ | ✅ | ✅ | ⚠️ stdlib logging |
| In-service JWT | ✅ | ❌ mesh | ❌ mesh | ❌ | ✅ + RBAC |
| Feature flags | Unleash+env | settings+decorator | ❌ | settings | settings |

## Python anti-patterns (+ core §15)

⚠️ `HTTPException` in Pydantic validators · stdlib logging instead of structlog · hand-written CRUD without `CRUDBase` · DB errors wrapped in bare `Exception` · split transaction control (endpoint commits + CRUD rolls back) · `tenacity` declared but unused · isort 88 vs 127 · missing `response_model`/`status_code` · `ast.literal_eval` on parsed log lines · coverage floor < 50 · README drift.

## Checklists

**New service:** scaffold from cookiecutter · decide & document auth/Redis/Kafka/flags · `app/` layout + `deps.py`/`crud/base.py`/`db/*`/`logs/*`/`context_store` · settings singleton + `.env.example` + 1Password keys · structlog + conditional Sentry/OTel · Alembic + `db/base.py` + tenacity gate · `/health/*` · pre-commit (127, schema-strict mypy) · `tests/` mirror + NullPool conftest + cov ≥50 · CI + Dockerfile + Helm.

**New endpoint:** model (+migration, add to `db/base.py`) · schemas (Base/Create/CreateDB/Update/Response; dual enums) · `CRUD<D>(CRUDBase)` + singleton; try/except+rollback+re-raise; row locks · thin router (`response_model`, `status_code`, docstring, `bind_contextvars`) · Kafka envelope + key validation if event-driven · tests (AAA, parametrized, mock by module path; commit-before-publish if it produces).
