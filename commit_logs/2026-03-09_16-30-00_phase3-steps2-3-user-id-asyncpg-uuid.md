# Phase 3 Steps 2+3: User ID Scoping, asyncpg Swap, UUID PKs

**Commit**: `93311e5` on `add_users`
**Date**: 2026-03-09

## Changes Implemented

### Database Engine Swap (aiosqlite -> asyncpg)
- `src/database.py`: Async-only engine, removed sync engine entirely
- `src/config.py`: `DATABASE_URL` from `SUPABASE_DB_URL` env var (falls back to SQLite)
- `pyproject.toml`: Added `asyncpg`, moved `aiosqlite` to dev deps, removed `alembic`
- Fix: Explicit `ssl.SSLContext` in `connect_args` to prevent asyncpg's `os.getcwd()` BlockingError

### UUID Primary Keys
- `src/models.py`: `FoodItem.id` and `DailyLog.id` changed from `Integer` to `Uuid` with `uuid4` default
- `src/agents/state.py`: All ID fields changed from `int` to `str`
- `src/schemas/selection_schema.py`: `food_id` changed from `int` to `str`
- All tools serialize IDs with `str()` on return

### User ID Scoping
- `FoodItem.user_id`: nullable UUID (shared DB foods have `None`, estimated foods have owner)
- `DailyLog.user_id`: NOT NULL UUID (every log entry belongs to a user)
- `search_food`: Estimated foods filtered by `user_id`, DB foods shared
- `daily_log_service`: All CRUD functions accept and filter by `user_id`
- Config passthrough: All nodes accept `config: RunnableConfig`, forward to tools

### Alembic Removal
- Deleted `alembic/` directory and `alembic.ini` (Supabase manages migrations)
- `ingest_simple_db.py`: Creates its own local sync engine for ETL

### Tests
- 79 unit tests passing (updated for UUID + user_id)
- 10 E2E tests passing (config passthrough verified end-to-end)
- New: `tests/unit/test_food_lookup.py` — user-scoped food isolation tests

## Key Fix: asyncpg BlockingError
asyncpg's connection setup calls `pathlib.resolve()` -> `os.getcwd()` when looking for `~/.postgresql/` SSL client certs. LangGraph's blockbuster catches this. Fixed by passing explicit `ssl.SSLContext` via `connect_args`.

## Next Steps
- Push branch and create PR for review
- Phase 3 Step 4: RLS policies on Supabase
- Phase 3 Step 5: Auth integration (Supabase Auth or external JWT)
