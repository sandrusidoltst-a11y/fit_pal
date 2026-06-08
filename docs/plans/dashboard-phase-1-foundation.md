# Feature: Coach Dashboard — Phase 1 (Foundation)

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files (`src.models`, `src.config`, `src.database`). Never call `Base.metadata.create_all()` against production — schema changes go through Supabase migrations (`mcp__supabase__apply_migration`).

## Feature Description

Lay the data-model and backend scaffolding for the FitPal Coach Dashboard (DASHBOARD_PRD.md §9, Phase 1). Nothing is user-visible after this phase. It delivers:

1. **Three additive schema changes** — a structured `macro_targets` table (numeric daily targets per trainee, split by training vs rest day), a `coach_id` column on `user_profiles` (which coach owns each trainee), and a `photo_url` column on `personal_stats_log` (so the dashboard can render progress photos once the bot-side upload ships).
2. **Service-layer additions** for the new data domains — a `macro_targets_service`, a `coach_service` (list a coach's trainees), and a small extension to `personal_stats_service` to carry `photo_url`.
3. **Seeding Dolev as the V1 coach** — his auth user already exists and is already the `DEFAULT_COACH_ID` constant; this phase backfills every existing trainee's `coach_id` to him.
4. **A `src/dashboard/` backend skeleton** — a standalone FastAPI app, a `routes/` package with a first read-only `GET /api/dashboard/trainees` endpoint, and a `get_current_coach_id()` dependency **stub** that returns `DEFAULT_COACH_ID` today and marks exactly where Supabase-JWT coach auth plugs in later.

## User Story

As **Dolev** (the sole V1 coach),
I want the database and backend to know which trainees are mine, what their numeric macro targets are (training vs rest day), and to expose a coach-scoped trainee list over HTTP,
So that the dashboard frontend (later phases) has real, correctly-shaped data to render compliance and plan-vs-actual against — without me touching the CLI or Supabase.

## Problem Statement

The dashboard's core value (compliance at-a-glance, plan-vs-actual) requires data the current schema cannot express:

- **No numeric macro targets.** Only `user_profiles.nutrition_plan` (free narrative text) exists. Compliance math (`actual vs target ±threshold`) needs numeric daily targets, and the coaching method differentiates **training days vs rest days**, so a single number per macro is insufficient.
- **No coach ownership.** `user_profiles` has no notion of which coach owns a trainee. Even at single-coach scale, the dashboard's read path must be expressed as "this coach's trainees" so the multi-coach future is a data-only change, not a query rewrite.
- **No photo attachment point.** `personal_stats_log` tracks weight/body-fat but has nowhere to hang a progress-photo URL.
- **No backend surface.** There is no HTTP API a dashboard frontend could call. The only FastAPI app (`src/security/webapp.py`) is mounted inside the langgraph server and gated by `InternalTokenMiddleware`, which rejects everything without an `X-Internal-Token` — unsuitable for a browser/coach client.

## Solution Statement

Make three **additive, non-destructive** schema changes via a single Supabase migration, mirror them in `src/models.py`, and build thin async service functions following the existing service-layer pattern (`session`-accepting core functions; the dashboard owns its sessions via a FastAPI dependency, exactly as nodes/tools own theirs). Scope the trainee read path by `coach_id`, resolved today by a `get_current_coach_id()` dependency that returns the existing `DEFAULT_COACH_ID` constant — a deliberate single-coach stub with a documented seam for future Supabase-JWT auth. Stand up a **separate** `src/dashboard/` FastAPI app so dashboard routes are never entangled with the bot server's internal-token middleware; final hosting/Railway topology is deferred to Phase 5 per the PRD.

### Decisions made during planning (flagged for confirmation)

These re-open the PRD's proposed defaults (DASHBOARD_PRD.md §"About the Decisions", §6) per the user's direction *"building for a single coach for now, we don't need to handle coach auth for now"*:

| # | Decision | Rationale | Revisit when |
|---|---|---|---|
| **D1 — No coach auth in Phase 1** | Dashboard API does not authenticate the coach yet. A `get_current_coach_id()` dependency returns `DEFAULT_COACH_ID`. No login screen, no JWT validation, no auth middleware. | User directive: single coach, defer auth. Keeps Phase 1 to data + scaffolding. The dependency is the single seam where JWT validation lands later. | Second coach onboards, or the dashboard is exposed beyond Dolev's local/trusted use. A dedicated dashboard-auth ADR + RLS decision happens then (ADR-0001 revisit trigger #1/#2). |
| **D2 — `coach_id` column on `user_profiles`** (not a join table) | One coach per trainee. Trivial additive migration; still "multi-coach ready" (many coaches each own their trainees). A many-to-many join table is YAGNI for V1. | Matches PRD's single-coach V1; FK to `auth.users`. | A trainee genuinely needs multiple coaches. |
| **D3 — Standalone `src/dashboard/` FastAPI app** | Clean separation from the langgraph server's `InternalTokenMiddleware` (which would 401 a browser client). | PRD flags hosting as undecided; a separate app keeps Phase 1 unblocked regardless of eventual deploy topology. | Phase 5 deployment planning decides shared-origin vs split service. |
| **D4 — `macro_targets` as a row-per-(trainee, day_type)** with `day_type ∈ {training, rest}` | Captures the training/rest distinction the method requires without a wide row; extensible to future day types (e.g. refeed). One current target set per `(user_id, day_type)` enforced by a unique constraint. | PRD §4 "differentiated by training vs rest day". History/versioning of targets is deferred. | Coaches need historical target versions or more day types. |

## Feature Metadata

**Feature Type**: New Capability (foundation / data model + backend scaffold)
**Estimated Complexity**: Medium
**Primary Systems Affected**: Supabase Postgres schema, `src/models.py`, `src/services/*`, new `src/dashboard/` package
**Dependencies**: `fastapi` (already a dependency), `supabase` MCP server (for migrations). No new packages required.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

- `src/models.py` (whole file, lines 1-143) — all models. `UserProfile` (74-93) gets a `coach_id` column; `PersonalStatsLog` (96-109) gets a `photo_url` column; the new `MacroTarget` model is appended. `CoachFoodMapping` (112-142) is the closest template for a coach-scoped table and shows the established `coach_id` (Postgres-only FK to `auth.users`) convention.
- `docs/patterns/schema-management.md` (whole file) — DB conventions: UUID PKs, `user_id`/`coach_id` scoping (indexed), `DateTime(timezone=True)`, audit-timestamp `lambda` defaults, FK-to-`auth.users` lives in Postgres migrations only (NOT in SQLAlchemy), production schema via Supabase migrations not `create_all()`.
- `docs/plans/food-catalog-migration.md` (Tasks 2-4, lines 165-318) — the **exact precedent** for this work: an additive Supabase migration that adds columns + a coach-scoped table with a Postgres-only FK to `auth.users`, plus how `DEFAULT_COACH_ID` was chosen/verified (`71a8c873-c6bd-498e-a6ca-bd27d6118329`). Mirror its migration shape and RLS policy block.
- `src/config.py` (lines 25-28) — `DEFAULT_COACH_ID` already exists and maps to Dolev's prod user. Reuse it; do not invent a new constant.
- `src/services/user_profile_service.py` (whole file) — the pattern for **non-`@tool`** services the bot/back-end call directly: `async def fn(session: AsyncSession, ...)`, `select(...).where(...)`, `scalar_one_or_none()`, return plain dicts. `macro_targets_service` and `coach_service` mirror this exactly (these are dashboard/back-end services, NOT LangGraph `@tool`s).
- `src/services/personal_stats_service.py` (lines 23-60, 113-120) — `create_stat_entry` and `_serialize_stat` get a `photo_url` parameter/field. Shows the service + `@tool` dual layer (only the core function and serializer change here; the `@tool` wrappers are untouched).
- `src/database.py` (whole file) — `get_async_db_session()` returns an `AsyncSession` (use as `async with`). The dashboard's DB dependency wraps this. Note the asyncpg SSL workaround context (don't touch it).
- `src/security/webapp.py` (whole file, 6 lines) — shows how a FastAPI `app` is declared and how `InternalTokenMiddleware` is attached. The dashboard app mirrors the *structure* (a module exposing `app`) but **does NOT attach `InternalTokenMiddleware`** (that token gates the bot↔langgraph channel, not a coach browser).
- `src/security/internal_auth_middleware.py` (whole file) — read to understand *why* the dashboard needs its own app: this middleware 401s any request lacking `X-Internal-Token`. The dashboard must not inherit it.
- `tests/integration/test_user_profile_service.py` — integration test pattern for a service (real Supabase DB, `unique_user` fixture). Mirror for `macro_targets_service` and `coach_service`.
- `tests/integration/test_personal_stats_service.py` — pattern for stats-service integration tests (extend for `photo_url`).
- `tests/conftest.py` and `.claude/skills/test-engineering/references/integration-testing.md` — shared fixtures (`unique_user`, session creation) and the integration-test rules. **Read the test-engineering integration-testing reference before writing any test.**

### New Files to Create

- `src/services/macro_targets_service.py` — async CRUD for `macro_targets` (set/upsert per day_type, get both day types for a trainee).
- `src/services/coach_service.py` — `list_trainees_for_coach(session, coach_id)` returning the coach's trainee profiles.
- `src/dashboard/__init__.py` — package marker.
- `src/dashboard/app.py` — standalone `FastAPI()` app; includes the trainees router; **no `InternalTokenMiddleware`**.
- `src/dashboard/dependencies.py` — `get_current_coach_id()` (returns `DEFAULT_COACH_ID`; documented auth seam) and `get_db_session()` (yields an `AsyncSession`).
- `src/dashboard/routes/__init__.py` — package marker.
- `src/dashboard/routes/trainees.py` — `APIRouter` with `GET /api/dashboard/trainees` (coach-scoped list).
- `tests/unit/test_dashboard_skeleton.py` — app imports, route registered, `get_current_coach_id` returns `DEFAULT_COACH_ID`, endpoint returns coach's trainees with a mocked service.
- `tests/integration/test_macro_targets_service.py` — real-DB CRUD round-trip + unique-constraint behavior.
- `tests/integration/test_coach_service.py` — real-DB trainee listing scoped by `coach_id`.

### Files to Update

- `src/models.py` — add `coach_id` to `UserProfile`, `photo_url` to `PersonalStatsLog`, append `MacroTarget` model.
- `src/services/personal_stats_service.py` — add `photo_url` param to `create_stat_entry` and field to `_serialize_stat`.
- `tests/integration/test_personal_stats_service.py` — assert `photo_url` round-trips.

### Migrations to Apply (via `mcp__supabase__apply_migration`)

- One migration `dashboard_phase1_foundation` — adds `user_profiles.coach_id` (+ index, + Postgres FK to `auth.users`, backfill to `DEFAULT_COACH_ID`), `personal_stats_log.photo_url`, creates `macro_targets` (+ indexes, + Postgres FK, + unique `(user_id, day_type)`, + RLS policies).

### Relevant Documentation — READ BEFORE IMPLEMENTING

- [FastAPI — Bigger Applications / APIRouter](https://fastapi.tiangolo.com/tutorial/bigger-applications/) — router-per-resource + `app.include_router(...)`. Why: structure the `routes/` package.
- [FastAPI — Dependencies / yield](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/) — `Depends` with `async def ... yield` for the DB-session dependency. Why: `get_db_session` lifecycle.
- [Supabase — RLS policies](https://supabase.com/docs/guides/database/postgres/row-level-security) — `service_role` full-access + `authenticated` read policies. Why: match the RLS block used in `food-catalog-migration.md` for the new table (defense-in-depth; enforcement remains app-layer per ADR-0001).

### Patterns to Follow

**Model template** (`docs/patterns/schema-management.md` §"The Model Template", and `CoachFoodMapping` in `src/models.py:112-142`):
- UUID PK: `mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)` (function, no parens).
- Scoping column indexed: `mapped_column(Uuid, nullable=False, index=True)`.
- `DateTime(timezone=True)` everywhere; audit defaults use `lambda:` (mandatory — bare `datetime.now()` freezes at import).
- FK between our tables → in the model. FK to `auth.users` → **migration only**, never in SQLAlchemy (`create_all()` would raise `NoReferencedTableError`).

**Service function** (`src/services/user_profile_service.py`):
```python
async def get_user_profile(session: AsyncSession, user_id: str) -> Optional[dict]:
    stmt = select(UserProfile).where(UserProfile.user_id == uuid_mod.UUID(user_id))
    result = await session.execute(stmt)
    profile = result.scalar_one_or_none()
    ...
```
Core functions accept an explicit `session` (DI/testability); return JSON-safe dicts, not ORM objects. These dashboard services are **plain async functions, not `@tool`s** (mirror `user_profile_service`, which is "not exposed as LangGraph tools").

**Migration** (`docs/plans/food-catalog-migration.md` Task 2): additive `ALTER TABLE ... ADD COLUMN` (nullable first), new table with `gen_random_uuid()` PK default, Postgres FK to `auth.users(id) ON DELETE CASCADE`, `ENABLE ROW LEVEL SECURITY` + `service_role`/`authenticated` policies.

**Logging**: `logger = structlog.get_logger(__name__)`; `logger.info("...", key=value)` on writes (mirror existing services).

---

## IMPLEMENTATION PLAN

### Phase 1: Schema (migration + models)

Apply one additive Supabase migration, then mirror the changes in `src/models.py`. Models and DB must agree, but the migration is the source of truth (never `create_all()`).

### Phase 2: Services

Add `macro_targets_service`, `coach_service`, and extend `personal_stats_service` with `photo_url`. All follow the `session`-accepting, dict-returning pattern.

### Phase 3: Dashboard skeleton

Standalone FastAPI app + `routes/` package + dependency stubs. One working read endpoint proving the wiring end-to-end (route → dependency → service → DB).

### Phase 4: Testing & validation

Unit tests for the skeleton (mocked service), integration tests for the new services (real DB), extend stats integration test. Run the unit gate; run integration against Supabase.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Task 1 — VERIFY `DEFAULT_COACH_ID` exists in `auth.users`

- **IMPLEMENT**: Confirm Dolev's coach UUID is present before backfilling FKs against it.
- **PATTERN**: Same verification as `food-catalog-migration.md` Task 1.
- **VALIDATE** (`mcp__supabase__execute_sql`):
  ```sql
  SELECT id, email FROM auth.users WHERE id = '71a8c873-c6bd-498e-a6ca-bd27d6118329';
  ```
  Expect exactly 1 row (`275939731@telegram.fitpal.bot`). If absent, STOP and re-confirm the coach UUID with Dolev before proceeding.

### Task 2 — INSPECT existing constraint/column names (pre-migration safety)

- **IMPLEMENT**: Confirm `user_profiles` and `personal_stats_log` don't already have the target columns, and capture exact table names.
- **VALIDATE**:
  ```sql
  SELECT column_name FROM information_schema.columns
  WHERE table_name IN ('user_profiles','personal_stats_log')
    AND column_name IN ('coach_id','photo_url');
  -- Expect 0 rows (columns not yet present)
  SELECT to_regclass('public.macro_targets'); -- Expect NULL (table absent)
  ```

### Task 3 — APPLY Supabase migration `dashboard_phase1_foundation`

- **IMPLEMENT**: `mcp__supabase__apply_migration` with name `dashboard_phase1_foundation` and the SQL below.
- **PATTERN**: Mirrors `food-catalog-migration.md` Task 2 — additive, nullable-first, Postgres-only `auth.users` FKs, RLS enabled with `service_role`/`authenticated` policies.
- **GOTCHA**:
  - Add `coach_id` nullable, backfill, then (optionally) leave nullable — do NOT set NOT NULL in the same statement before backfill or existing rows fail. (Backfill makes every current row non-null; keep the column nullable in SQLAlchemy to match, since new trainees may briefly exist before assignment.)
  - `macro_targets.user_id` is the **trainee**, not the coach. Do not add a `coach_id` to `macro_targets` — coach ownership is derived via `user_profiles`.
  - `day_type` CHECK must be `('training','rest')`.
  - Unique `(user_id, day_type)` enforces one current target set per day type.
- **VALIDATE** (after apply):
  ```sql
  SELECT column_name FROM information_schema.columns
  WHERE table_name='user_profiles' AND column_name='coach_id';            -- 1 row
  SELECT column_name FROM information_schema.columns
  WHERE table_name='personal_stats_log' AND column_name='photo_url';      -- 1 row
  SELECT to_regclass('public.macro_targets');                              -- non-null
  SELECT COUNT(*) FROM user_profiles WHERE coach_id IS NULL;               -- 0 (all backfilled)
  ```

**SQL body:**
```sql
-- 1. Coach ownership on user_profiles (nullable, then backfill to the single V1 coach)
ALTER TABLE user_profiles ADD COLUMN coach_id UUID;
UPDATE user_profiles SET coach_id = '71a8c873-c6bd-498e-a6ca-bd27d6118329' WHERE coach_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_user_profiles_coach_id ON user_profiles (coach_id);
ALTER TABLE user_profiles
  ADD CONSTRAINT fk_user_profiles_coach_id
  FOREIGN KEY (coach_id) REFERENCES auth.users(id) ON DELETE SET NULL;

-- 2. Progress-photo URL on personal_stats_log (bot upload flow ships later)
ALTER TABLE personal_stats_log ADD COLUMN photo_url TEXT;

-- 3. Structured macro targets (per trainee, per day_type)
CREATE TABLE macro_targets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,                               -- the trainee
  day_type TEXT NOT NULL CHECK (day_type IN ('training','rest')),
  calories DOUBLE PRECISION NOT NULL,
  protein_g DOUBLE PRECISION NOT NULL,
  carbs_g DOUBLE PRECISION NOT NULL,
  fat_g DOUBLE PRECISION NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ,
  UNIQUE (user_id, day_type)
);
CREATE INDEX idx_macro_targets_user_id ON macro_targets (user_id);
ALTER TABLE macro_targets
  ADD CONSTRAINT fk_macro_targets_user_id
  FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- RLS (defense-in-depth; app-layer remains primary enforcement per ADR-0001)
ALTER TABLE macro_targets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access" ON macro_targets
  AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated users can read" ON macro_targets
  AS PERMISSIVE FOR SELECT TO authenticated USING (true);
```

### Task 4 — UPDATE `src/models.py`

- **IMPLEMENT**:
  - Add to `UserProfile`: `coach_id: Mapped[Optional[uuid_mod.UUID]] = mapped_column(Uuid, nullable=True, index=True)` (FK to `auth.users` lives in Postgres only — do NOT add `ForeignKey(...)`).
  - Add to `PersonalStatsLog`: `photo_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)`.
  - Append new `MacroTarget` model (template below).
- **PATTERN**: `CoachFoodMapping` (`src/models.py:112-142`) for the coach-scoped/`auth.users`-FK convention; `docs/patterns/schema-management.md` for the model template.
- **IMPORTS**: All needed symbols (`Uuid, String, Float, DateTime, Text, UniqueConstraint`, `Mapped, mapped_column`, `uuid_mod`, `datetime, timezone`, `Optional`) are already imported in `src/models.py`. No new imports.
- **GOTCHA**: `MacroTarget.user_id` is the trainee (not coach). Audit defaults use `lambda:`. Use `Float` in SQLAlchemy (maps to `DOUBLE PRECISION`).
- **VALIDATE**:
  ```bash
  uv run python -c "from src.models import UserProfile, PersonalStatsLog, MacroTarget; \
print('coach_id' in UserProfile.__table__.columns.keys()); \
print('photo_url' in PersonalStatsLog.__table__.columns.keys()); \
print(MacroTarget.__table__.columns.keys())"
  ```

**New `MacroTarget` model (append after `CoachFoodMapping`):**
```python
class MacroTarget(Base):
    """Structured numeric macro targets per trainee, split by training vs rest day.

    One row per (user_id, day_type). `user_id` is the trainee (FK to auth.users in
    Postgres only). Compliance math (dashboard) compares a day's logged macros
    against the matching day_type row.
    """

    __tablename__ = "macro_targets"

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False, index=True)
    day_type: Mapped[str] = mapped_column(String, nullable=False)  # CHECK ('training','rest') in Postgres
    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (UniqueConstraint("user_id", "day_type", name="uq_macro_targets_user_day_type"),)
```

### Task 5 — CREATE `src/services/macro_targets_service.py`

- **IMPLEMENT**:
  - `set_macro_targets(session, user_id, day_type, calories, protein_g, carbs_g, fat_g) -> dict` — upsert by `(user_id, day_type)`: select existing; update if present, else insert. Commit, return serialized dict.
  - `get_macro_targets(session, user_id) -> dict` — return `{"training": {...} | None, "rest": {...} | None}`.
  - `_serialize_target(row) -> dict` helper.
- **PATTERN**: `src/services/user_profile_service.py` (select / `scalar_one_or_none` / commit / return dict). Not a `@tool`.
- **IMPORTS**: `import uuid as uuid_mod`, `from typing import Optional`, `import structlog`, `from sqlalchemy import select`, `from sqlalchemy.ext.asyncio import AsyncSession`, `from src.models import MacroTarget`.
- **GOTCHA**: Validate `day_type in {"training","rest"}` and raise `ValueError` otherwise (matches the DB CHECK; fail fast in Python). Convert `user_id` string → `uuid_mod.UUID` in the `WHERE`/constructor, as the other services do.
- **VALIDATE**: `uv run ruff check src/services/macro_targets_service.py` and `uv run python -c "from src.services.macro_targets_service import set_macro_targets, get_macro_targets; print('ok')"`

### Task 6 — CREATE `src/services/coach_service.py`

- **IMPLEMENT**: `list_trainees_for_coach(session, coach_id) -> list[dict]` — `select(UserProfile).where(UserProfile.coach_id == uuid_mod.UUID(coach_id))`, return a list of profile dicts (`user_id`, `name`, `height_cm`, `age`, `gender`, `nutrition_plan`). Reuse/mirror the dict shape in `user_profile_service.get_user_profile` but include `user_id` (as `str`).
- **PATTERN**: `src/services/user_profile_service.py`.
- **IMPORTS**: same imports as Task 5 plus `from src.models import UserProfile`.
- **GOTCHA**: Accept `coach_id` as `str`; convert to `uuid_mod.UUID`. Return `[]` when none.
- **VALIDATE**: `uv run ruff check src/services/coach_service.py` and import smoke check.

### Task 7 — UPDATE `src/services/personal_stats_service.py` for `photo_url`

- **IMPLEMENT**: Add `photo_url: Optional[str] = None` param to `create_stat_entry`, pass to the `PersonalStatsLog(...)` constructor; add `"photo_url": entry.photo_url` to `_serialize_stat`.
- **PATTERN**: existing function body (lines 23-60, 113-120).
- **GOTCHA**: Do NOT change the `@tool` wrappers (`log_personal_stat`, etc.) — bot-side photo upload is out of scope. Only the core function + serializer change.
- **VALIDATE**: `uv run ruff check src/services/personal_stats_service.py`; `uv run pytest tests/unit -k personal_stats -q` (if any unit coverage exists, else covered by Task 11).

### Task 8 — CREATE `src/dashboard/` package skeleton (`__init__.py`, `dependencies.py`)

- **IMPLEMENT**:
  - `src/dashboard/__init__.py` — empty package marker.
  - `src/dashboard/dependencies.py`:
    - `def get_current_coach_id() -> str:` → returns `str(DEFAULT_COACH_ID)`. Docstring states this is the single-coach Phase-1 stub and the exact seam where Supabase-JWT validation will replace it (decision D1).
    - `async def get_db_session():` → `async with get_async_db_session() as session: yield session` (FastAPI yield-dependency).
- **PATTERN**: `src/database.py` (`get_async_db_session`); FastAPI yield-dependency docs.
- **IMPORTS**: `from src.config import DEFAULT_COACH_ID`, `from src.database import get_async_db_session`.
- **GOTCHA**: `get_current_coach_id` returns a **str** (services convert to UUID). Keep it a plain function (sync) — no request parsing yet; that's the future auth seam.
- **VALIDATE**: `uv run python -c "from src.dashboard.dependencies import get_current_coach_id; print(get_current_coach_id())"` → prints the coach UUID.

### Task 9 — CREATE `src/dashboard/routes/` (trainees endpoint)

- **IMPLEMENT**:
  - `src/dashboard/routes/__init__.py` — empty.
  - `src/dashboard/routes/trainees.py`:
    ```python
    from fastapi import APIRouter, Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.dashboard.dependencies import get_current_coach_id, get_db_session
    from src.services.coach_service import list_trainees_for_coach

    router = APIRouter(prefix="/api/dashboard", tags=["trainees"])

    @router.get("/trainees")
    async def list_trainees(
        coach_id: str = Depends(get_current_coach_id),
        session: AsyncSession = Depends(get_db_session),
    ) -> list[dict]:
        return await list_trainees_for_coach(session, coach_id)
    ```
- **PATTERN**: FastAPI APIRouter docs.
- **VALIDATE**: `uv run python -c "from src.dashboard.routes.trainees import router; print([r.path for r in router.routes])"` → includes `/api/dashboard/trainees`.

### Task 10 — CREATE `src/dashboard/app.py`

- **IMPLEMENT**:
  ```python
  from fastapi import FastAPI

  from src.dashboard.routes.trainees import router as trainees_router

  app = FastAPI(title="FitPal Coach Dashboard API")
  app.include_router(trainees_router)

  @app.get("/health")
  async def health() -> dict:
      return {"status": "ok"}
  ```
- **PATTERN**: `src/security/webapp.py` (declares `app`) — but **do NOT** add `InternalTokenMiddleware` (that gates the bot↔langgraph channel; a coach browser has no such token). No auth middleware in Phase 1 (decision D1).
- **GOTCHA**: This app is not yet wired to any deployment (Phase 5). It must merely import and serve locally (`uv run uvicorn src.dashboard.app:app`).
- **VALIDATE**: `uv run python -c "from src.dashboard.app import app; print([r.path for r in app.routes if hasattr(r,'path')])"` → includes `/health` and `/api/dashboard/trainees`.

### Task 11 — CREATE unit tests `tests/unit/test_dashboard_skeleton.py`

- **IMPLEMENT** (AAA docstrings per test-engineering skill):
  - `get_current_coach_id()` returns `str(DEFAULT_COACH_ID)`.
  - The app exposes `/health` and `/api/dashboard/trainees` (inspect `app.routes`).
  - `GET /api/dashboard/trainees` returns the service result with `list_trainees_for_coach` **mocked** and `get_db_session` dependency-overridden — assert the mocked coach_id is passed through. Use `fastapi.testclient.TestClient` with `app.dependency_overrides`.
- **PATTERN**: `.claude/skills/test-engineering/references/unit-testing.md` (mock boundary: mock the service + DB dependency, never hit a real DB in unit tier). `tests/unit/test_gateway.py` for FastAPI/async mocking style.
- **IMPORTS**: `from fastapi.testclient import TestClient`, `from unittest.mock import AsyncMock, patch`, `from src.dashboard.app import app`, `from src.dashboard.dependencies import get_db_session`, `from src.config import DEFAULT_COACH_ID`.
- **GOTCHA**: Override `get_db_session` via `app.dependency_overrides[get_db_session] = lambda: None` (the service is mocked, so the session is unused). Patch `src.dashboard.routes.trainees.list_trainees_for_coach` with an `AsyncMock`. Clear `app.dependency_overrides` in teardown.
- **VALIDATE**: `uv run pytest tests/unit/test_dashboard_skeleton.py -v`

### Task 12 — CREATE integration tests for the new services

- **IMPLEMENT**:
  - `tests/integration/test_macro_targets_service.py`: set training + rest targets for a `unique_user`; `get_macro_targets` returns both; re-`set` same `(user, day_type)` updates (not duplicates) — assert single row / values changed.
  - `tests/integration/test_coach_service.py`: create N profiles with `coach_id=DEFAULT_COACH_ID` and one with a different coach_id; `list_trainees_for_coach(DEFAULT_COACH_ID)` returns only the matching ones.
  - Extend `tests/integration/test_personal_stats_service.py`: create an entry with `photo_url` and assert it round-trips through `_serialize_stat`/`get_latest_stats`.
- **PATTERN**: `tests/integration/test_user_profile_service.py` + `tests/integration/test_personal_stats_service.py`; **read `.claude/skills/test-engineering/references/integration-testing.md` first** for the `unique_user` fixture, session handling, and cleanup conventions.
- **GOTCHA**: Integration tier hits real Supabase (`SUPABASE_DB_URL`). Use the established per-test user fixture so rows are isolated and FK-to-`auth.users` is satisfied (the fixture creates a real auth user). `coach_id` must reference a real `auth.users` row — `DEFAULT_COACH_ID` qualifies.
- **VALIDATE**: `uv run pytest tests/integration/test_macro_targets_service.py tests/integration/test_coach_service.py tests/integration/test_personal_stats_service.py -v`

### Task 13 — Full validation sweep + commit

- **IMPLEMENT**: Run the validation commands below; fix any failures; commit on `claude/practical-meitner-5IOrs` with a descriptive message; write a `commit_logs/` entry mirroring the existing format.
- **VALIDATE**: see VALIDATION COMMANDS.

---

## TESTING STRATEGY

### Unit Tests (`tests/unit/`, mocked — pre-commit gate)
- Dashboard skeleton: dependency stub value, route registration, endpoint passes `coach_id` to a **mocked** `list_trainees_for_coach`. No DB, no network.

### Integration Tests (`tests/integration/`, real Supabase DB)
- `macro_targets_service`: insert + upsert + get-both-day-types.
- `coach_service`: coach-scoped filtering (only the coach's trainees returned).
- `personal_stats_service`: `photo_url` round-trip.

### Edge Cases
- `set_macro_targets` with invalid `day_type` → `ValueError` (Python guard mirrors DB CHECK).
- Re-setting the same `(user_id, day_type)` updates in place (unique constraint not violated).
- `list_trainees_for_coach` with a coach that owns no trainees → `[]`.
- `get_macro_targets` for a trainee with only one day_type set → the other key is `None`.
- A `user_profiles` row whose `coach_id` is NULL is excluded from a coach's trainee list.

---

## VALIDATION COMMANDS

Execute in order. Zero regressions required.

### Level 1: Syntax & Style
```bash
uv run ruff check src/ tests/
uv run python -c "from src.models import UserProfile, PersonalStatsLog, MacroTarget; print('models ok')"
uv run python -c "from src.dashboard.app import app; print('app ok')"
```

### Level 2: Unit Tests (mandatory gate)
```bash
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests (requires SUPABASE_DB_URL)
```bash
uv run pytest tests/integration/test_macro_targets_service.py \
              tests/integration/test_coach_service.py \
              tests/integration/test_personal_stats_service.py -v
```

### Level 4: Manual / DB Validation
```bash
# App boots locally and serves the route
uv run uvicorn src.dashboard.app:app --port 8100 &
sleep 2 && curl -s localhost:8100/health && curl -s localhost:8100/api/dashboard/trainees; kill %1
```
```sql
-- via mcp__supabase__execute_sql
SELECT COUNT(*) FROM user_profiles WHERE coach_id IS NULL;                 -- 0
SELECT conname FROM pg_constraint WHERE conname='fk_macro_targets_user_id';-- 1 row
SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='uq_macro_targets_user_day_type';
```

---

## ACCEPTANCE CRITERIA

- [ ] Migration `dashboard_phase1_foundation` applied; `user_profiles.coach_id` (backfilled, indexed, FK), `personal_stats_log.photo_url`, and `macro_targets` (FK + unique `(user_id, day_type)` + RLS) all present.
- [ ] `src/models.py` declares `coach_id`, `photo_url`, and `MacroTarget`; imports cleanly.
- [ ] `macro_targets_service` and `coach_service` exist and follow the `session`-accepting, dict-returning service pattern.
- [ ] `personal_stats_service.create_stat_entry` / `_serialize_stat` carry `photo_url`; `@tool` wrappers unchanged.
- [ ] `src/dashboard/` app serves `/health` and `GET /api/dashboard/trainees`; **no** `InternalTokenMiddleware`; `get_current_coach_id()` returns `DEFAULT_COACH_ID` with a documented auth seam.
- [ ] Unit gate green; new integration tests green against Supabase.
- [ ] No changes to bot/agent runtime behavior (nodes, tools, graph, gateway untouched).
- [ ] `commit_logs/` entry added; work committed to `claude/practical-meitner-5IOrs`.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order; each task's VALIDATE passed.
- [ ] Migration applied via `mcp__supabase__apply_migration` and DB-verified.
- [ ] `uv run ruff check src/ tests/` clean.
- [ ] `uv run pytest tests/unit/ -v` green.
- [ ] New integration tests green.
- [ ] App boots and serves locally.
- [ ] Decisions D1–D4 reviewed with Dolev (single-coach, no-auth scaffold confirmed acceptable for Phase 1).

---

## NOTES

### Why no auth in Phase 1 (D1)
Per the user's directive (single coach, defer auth). `get_current_coach_id()` is the one place future Supabase-JWT validation lands — it changes from "return the constant" to "decode the Bearer token, look up the coach, return their id." Nothing downstream (services, routes) changes when that happens, because everything already flows `coach_id` as a string. **Do not deploy this app publicly until auth lands** — it currently trusts any caller as the single coach. Local/trusted use only for now.

### Why a separate FastAPI app (D3)
`src/security/webapp.py`'s `InternalTokenMiddleware` 401s any request without `X-Internal-Token`, which is correct for the bot↔langgraph channel and wrong for a browser coach client. A separate `src/dashboard/app.py` avoids carving fragile exceptions into that middleware. Deployment topology (shared origin vs split Railway service) is a Phase 5 decision and is intentionally not made here.

### Why `macro_targets.user_id` is the trainee, not a `coach_id`
Targets belong to a trainee; the owning coach is derivable via `user_profiles.coach_id`. Adding a redundant `coach_id` to `macro_targets` would risk drift. Coach-scoped target queries join through `user_profiles`.

### ADR follow-up
A dashboard-auth/RLS ADR should be written when D1 is revisited (ADR-0001 names this exact inflection — "second backend service"). Not in scope for Phase 1.

### Confidence: 8/10 for one-pass success
Risks: (1) the `unique_user`/auth-user integration fixture must satisfy the new `auth.users` FKs — verify the fixture creates a real auth user before writing `macro_targets`/`coach_id` rows; (2) exact RLS policy syntax must match the project's existing policies (copy from `food-catalog-migration.md`); (3) `app.dependency_overrides` cleanup in the unit test must be in a fixture teardown to avoid cross-test leakage.
