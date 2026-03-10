# Refactor: Test DB to Supabase Postgres, Extract get_user_id, Estimated Reuse E2E

**Date**: 2026-03-10
**Branch**: add_users
**Commit**: 9dcdbe0

## Changes Implemented

### 1. Extract `get_user_id(config)` helper (`src/config.py`)
- Added `get_user_id(config: RunnableConfig | None) -> str` to centralize user ID extraction
- Replaced 4 duplicated `config["configurable"].get("user_id", DEFAULT_DEV_USER_ID)` patterns:
  - `src/tools/food_lookup.py` — `search_food` and `create_food_item`
  - `src/services/daily_log_service.py` — `log_food_entry` and `query_food_logs`
- Single point of change for future JWT/Auth migration

### 2. Swap unit test DB fixture to Supabase Postgres (`tests/conftest.py`)
- Replaced in-memory SQLite with real Supabase Postgres via `DATABASE_URL`
- Transaction rollback isolation: outer TX wraps each test, rolls back at end
- Savepoint re-creation via `after_transaction_end` event listener for multiple commits
- SSL context mirrors `src/database.py` for asyncpg compatibility
- Catches dialect-specific bugs (UUID handling, `ilike`, `func.date`) that SQLite silently ignores

### 3. Add `TestEstimatedFoodReuse` E2E test (`tests/graph_api/test_graph_flows.py`)
- 2-thread pattern: Thread 1 logs unknown food (estimated), Thread 2 logs same food (should reuse)
- Verifies estimated food persistence and DB-first search behavior
- Uses unique food name `xyzreuse77777qwerty` to avoid collisions

### 4. Relax shared food search assertion (`tests/unit/test_food_lookup.py`)
- Changed `results[0]["name"] == "Test Chicken"` to `any(r["name"] == "Test Chicken" ...)`
- Real Supabase DB has existing chicken entries that may sort before seeded test data

## Files Modified
- `src/config.py` — added `get_user_id` helper
- `src/tools/food_lookup.py` — replaced 2 extraction sites
- `src/services/daily_log_service.py` — replaced 2 extraction sites
- `tests/conftest.py` — swapped SQLite to Postgres with rollback
- `tests/graph_api/test_graph_flows.py` — added `TestEstimatedFoodReuse`
- `tests/unit/test_food_lookup.py` — relaxed assertion
- `.agent/plans/refactor-test-db-and-extract-user-helper.md` — plan file

## Validation
- Ruff lint: all checks passed
- Unit tests: 78/79 passed (1 transient connection error, passed on retry)
- Data pollution check: confirmed no test data leaked to Supabase

## Next Steps
- Run E2E tests (`uv run pytest tests/graph_api/ -v -s`) to validate new `TestEstimatedFoodReuse`
- Consider dedicated test Supabase project when upgrading to Pro plan
