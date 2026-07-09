# Check Catalog — Python / FastAPI

Stack-specific checks for **Python/FastAPI** services (Resal cookiecutter template). **Run these `PY-*` checks AND all `CORE-*` checks** (`checks-core.md`). Enforces `./standards/python.md` + `core.md`.

> **No double-counting:** if a finding matches a CORE check, record it under the CORE id. The "Python detection for CORE checks" section below just gives you the Python grep patterns so CORE findings have good evidence. The `PY-*` checks are concerns unique to FastAPI/the cookiecutter that CORE doesn't cover.

Each check: **ID · applicability · detection · default severity**. Gate on the stack profile (no false positives for unused capabilities: e.g. VoucherMS/Restock have no Redis; Restock/admin-backend have no Kafka).

---

## PY-STRUCT — Structure

| ID | Applies | Detection | Default |
|---|---|---|---|
| `PY-STRUCT-01` | always | Source package is **`app/`** (not `src/`). `Glob app/main.py` missing → finding. | High |
| `PY-STRUCT-02` | DB service | Per-domain fan-out: domain has `models/<d>.py` + `schemas/<d>.py` + `crud/crud_<d>.py` + endpoint. Orphan model w/o schema/crud → finding. | Medium |
| `PY-STRUCT-03` | event-driven | Consumers/domain don't import the API layer. Grep `from app.api` in `app/src`/domain → finding. | Medium |
| `PY-STRUCT-04` | always | No stray committed dirs/typos: `app;C/`, `bak/`, `*.py.py`, `__int__.py`. | Nice-to-have |

## PY-SCHEMA — Pydantic v2

| ID | Applies | Detection | Default |
|---|---|---|---|
| `PY-SCHEMA-01` | always | v2 idioms: `field_validator`/`model_validator` + `@classmethod`, `ConfigDict`. Grep v1 `@validator(`/`class Config:` → finding. | Medium |
| `PY-SCHEMA-02` | DB service | Schema family Base/Create/(CreateDB)/Update/Response; response `from_attributes=True`. | Medium |
| `PY-SCHEMA-03` | updates | Partial updates use `model_dump(exclude_none=True)`. | Medium |
| `PY-SCHEMA-04` | enums cross DB/API | Dual Int/Str enum + request/response bridge mixins where DB stores int, API shows str. | Nice-to-have |
| `PY-SCHEMA-05` | user-facing content | Bilingual ar/en fields via localized base classes + `json_schema_extra` examples. | Nice-to-have |

> Validators must raise `ValueError`/`PydanticCustomError`, **not** `HTTPException` — record under **CORE-ERR-04** (Python detection: grep `raise HTTPException` within `app/schemas/`).

## PY-DB — Persistence (SQLAlchemy 2.0 async)

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `PY-DB-01` | DB service | Async engine + `sessionmaker(expire_on_commit=False, class_=AsyncSession)` in `db/session.py`. | High |
| `PY-DB-02` | DB service | `get_session` owns the transaction (`async with session.begin()`). | High |
| `PY-DB-03` | DB service | Generic `CRUDBase[Model,Create,Update]` exists and is subclassed; hand-written per-domain CRUD without a base → finding. | High |
| `PY-DB-04` | DB service | CRUD methods: `try/except (SQLAlchemyError, DBAPIError)` → `rollback()` → `logger.error` → `raise`. Missing rollback → **Critical**; bare `Exception` wrap → High (also CORE-ERR-03). | High |
| `PY-DB-05` | concurrent writes | Read-modify-write uses `with_for_update(nowait=False)` row locks. | High |
| `PY-DB-06` | M2M writes | Idempotent writes via `on_conflict_do_nothing`/`insert().from_select`. | Medium |
| `PY-DB-07` | DB service | Alembic: `target_metadata = Base.metadata`; `db/base.py` imports every model; `compare_type=True`; new model missing from `db/base.py` → finding. | Medium |

> SQL injection → record under **CORE-SEC-02** (Python detection: `text(f"…")`, `.format(`/`%` built SQL, f-strings inside `execute(`. A `text("… = :x")` with `{"x": v}` bound param is **safe** — N/A, not a finding).

## PY-LOG — Logging (structlog) — Python detection for CORE-LOG

| ID | Applies | Detection | Default |
|---|---|---|---|
| `PY-LOG-01` | always | structlog config (`log_conf.py`): JSON renderer in deployed envs; injects OTel `trace_id`/`span_id`; captures third-party loggers. Missing/partial → finding. | High |
| `PY-LOG-02` | always | Handlers bind an action: `bind_contextvars(action=<Domain>Actions.X)`; actions are StrEnums in `log_actions.py`. Missing taxonomy → finding. | Medium |

> **CORE-LOG-01** Python detection: must use `logger = log_conf.Logger(__name__)`; grep `logging.getLogger(` → High, `print(` in `app/` → Medium.
> **CORE-LOG-02** Python detection: correlation id via `context_store/context.py` contextvars, set per request (middleware) + per consumed message, echoed on response.
> **CORE-LOG-05** Python detection: `mask_sensitive_log_fields` processor over `SENSITIVE_FIELDS`.

## PY-KAFKA — Event-driven (Faust + aiokafka)

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `PY-KAFKA-01` | event-driven | Consume via faust `@app.agent` in `app/src/<svc>_processor.py`; produce/health via aiokafka. | Medium |
| `PY-KAFKA-02` | event-driven | Envelope `{"body_args": {...}}`; two-stage key validation (`PROTOCOL_KEYS` + `EVENT_SCHEMA_KEYS`), drop-and-log invalid. | Medium |
| `PY-KAFKA-03` | producer | `produce_to_topic` injects correlation-id + W3C trace headers (`propagate.inject`). | High |
| `PY-KAFKA-04` | consumer | Per-message try/except so one bad message can't kill the agent; `SpanKind.CONSUMER` from headers. | High |

> Commit-before-publish → record under **CORE-RES-03** (Python detection: DB commit precedes `produce_to_topic`; if publish can fire before the outer txn commits → Critical; if cross-layer/unprovable → High + recommend regression test `PY-TEST-03`).

## PY-REDIS — Caching

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `PY-REDIS-01` | uses Redis | `redis.asyncio.Redis` singleton in `redis_store/base.py`, `decode_responses=True`. | Medium |
| `PY-REDIS-02` | uses Redis | Keys `PREFIX:id` + `PREFIX_ids` set; atomic via `pipeline(transaction=True)`; `model_dump_json`/`model_validate_json`. | Nice-to-have |
| `PY-REDIS-03` | needs a cache | No file-based cache (`tokens.txt`). Grep token/cache file read/write → finding. | High |

## PY-AUTH — Auth & security (Python detail for CORE-SEC/§13)

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `PY-AUTH-01` | edge/privileged | In-service JWT decode (`python-jose`, `jwt.decode`) + user resolution. Required-but-missing → Critical. | Critical |
| `PY-AUTH-02` | mesh-trust | Posture documented (README); no dead JWT code implying unenforced protection. | Medium |
| `PY-AUTH-03` | admin API | RBAC dependency (`GetCurrentUser(api_name=…|services=[…])`) on protected routes; permission model in DB. Unprotected admin mutation → Critical. | Critical |
| `PY-AUTH-04` | stores sensitive fields | Field encryption (Fernet/AES-SIV) with `encrypted::` prefix. | Medium |

> `bandit` in pre-commit → record under **CORE-SEC-03**.

## PY-FLAG — Feature flags

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `PY-FLAG-01` | runtime toggles | Unleash with env fallback, **or** settings-bool + `check_feature_flag` decorator. Scattered hardcoded toggles → finding. | Nice-to-have |

## PY-RES — Resilience (Python detail for CORE-RES)

| ID | Applies when | Detection | Default |
|---|---|---|---|
| `PY-RES-01` | DB service | tenacity startup DB-readiness gate (`backend_pre_start.py`, `@retry`). Declared-but-unused tenacity → Medium. | Medium |
| `PY-RES-02` | external vendors | Idempotency keys (`uuid4`) to vendors; retry-with-backoff; timeout→status mapping. | Medium |
| `PY-RES-03` | batch/concurrent | `asyncio.gather(..., return_exceptions=True)` + filtering; partial-success modeling. | Medium |
| `PY-RES-04` | blocking SDKs | `run_in_threadpool(...)` around sync SDK calls. Finding only if a blocking call is NOT wrapped. | Medium |

## PY-TEST — Testing (Python detail for CORE-TEST)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `PY-TEST-01` | always | `pytest` + `pytest-asyncio`; `app/tests/` mirrors source; async tests `@pytest.mark.asyncio`. | High |
| `PY-TEST-02` | always | `conftest.py`: NullPool engine, `dependency_overrides[get_session]`, `LifespanManager` + `AsyncClient(ASGITransport)`. | Medium |
| `PY-TEST-03` | event-driven + DB | Commit-before-publish regression test (publish sees the committed row). | High |

> Coverage gate → record under **CORE-TEST-02** (Python detection: `--cov-fail-under=N` in `tests-start.sh`; floor < 50 → finding).

## PY-TOOL — Tooling

| ID | Applies | Detection | Default |
|---|---|---|---|
| `PY-TOOL-01` | always | pre-commit: black, flake8, isort, bandit, docformatter, commitlint, mypy, unit-tests. Missing hooks → finding. | Medium |
| `PY-TOOL-02` | always | **Line length 127** consistent. `[tool.isort] line_length = 88` vs black/flake8 127 → finding. | Medium |
| `PY-TOOL-03` | always | mypy schema-strict: global `ignore_errors=True` but `[mypy-app.schemas.*]` strict; pydantic+sqlalchemy plugins. | Nice-to-have |

## PY-OPS — Build & deploy (Python detail for CORE-OPS)

| ID | Applies | Detection | Default |
|---|---|---|---|
| `PY-OPS-01` | always | `/health/live` + `/health/ready`; `/ready` checks DB `SELECT 1`, Redis ping, Kafka brokers as applicable. | High |
| `PY-OPS-02` | event-driven | Faust worker `/health/ready` includes stuck-worker detection. | Medium |
| `PY-OPS-03` | always | Dockerfile `python:3.11.9-slim` + Poetry `virtualenvs.create false`; `prestart.sh` → `backend_pre_start.py` → `alembic upgrade head` → app/worker. | Nice-to-have |

---

## Python anti-patterns (also flag)
`HTTPException` in validators (CORE-ERR-04) · stdlib logging (CORE-LOG-01) · hand-written CRUD without `CRUDBase` (PY-DB-03) · DB errors in bare `Exception` (PY-DB-04/CORE-ERR-03) · split transaction control · `tenacity` declared-but-unused · isort 88 vs 127 · `ast.literal_eval` on parsed log lines (CORE-SEC-02) · coverage floor < 50 (CORE-TEST-02).
