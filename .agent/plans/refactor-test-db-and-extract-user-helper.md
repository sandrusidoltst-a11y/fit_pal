# Feature: Refactor Test DB to Supabase, Extract get_user_id Helper, Add Estimated Reuse E2E Test

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Three targeted refactors in one pass:
1. **Swap unit test DB fixture** from in-memory SQLite to real Supabase Postgres with transaction rollback isolation — catches dialect-specific bugs (UUID handling, `ilike`, `func.date`) that SQLite silently ignores.
2. **Extract `get_user_id(config)` helper** to eliminate DRY violation across 4 tool functions — single point of change for future JWT/Auth migration.
3. **Add estimated food reuse E2E test** — verifies that a previously estimated food is found in DB on subsequent searches instead of being re-estimated by the LLM.

## User Story

As a developer
I want unit tests to run against the real Supabase Postgres and a single `get_user_id` helper
So that dialect-specific bugs are caught early and future auth changes require updating only one function.

## Problem Statement

1. Unit tests run against SQLite which has different behavior for UUIDs, `ilike`, `func.date()` and timezone handling. Bugs could pass unit tests but fail in production.
2. The `user_id` extraction pattern is copy-pasted in 4 places — fragile, DRY violation, hard to migrate to JWT.
3. No E2E test verifies the estimated food reuse path (search finds previously estimated food in DB).

## Solution Statement

1. Change `async_test_db_session` fixture to connect to real Supabase Postgres using `DATABASE_URL` from `src.config`, wrap each test in a transaction that rolls back.
2. Add `get_user_id(config)` to `src/config.py`, replace all 4 extraction sites.
3. Add `TestEstimatedFoodReuse` E2E test class with a 2-thread pattern.

## Feature Metadata

**Feature Type**: Refactor
**Estimated Complexity**: Low-Medium
**Primary Systems Affected**: `tests/conftest.py`, `src/config.py`, `src/tools/food_lookup.py`, `src/services/daily_log_service.py`, `tests/graph_api/test_graph_flows.py`
**Dependencies**: `asyncpg` (already installed), `SUPABASE_DB_URL` env var (already configured)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `tests/conftest.py` (lines 46-75) — Current SQLite fixture to replace
- `src/config.py` (lines 13-19) — `DEFAULT_DEV_USER_ID` and `DATABASE_URL` definitions
- `src/database.py` (lines 1-28) — SSL context pattern for asyncpg (must reuse in test fixture)
- `src/tools/food_lookup.py` (lines 33, 82) — Two `user_id` extraction sites to replace
- `src/services/daily_log_service.py` (lines 190, 211) — Two `user_id` extraction sites to replace
- `src/models.py` (lines 13-63) — FoodItem and DailyLog models with UUID PKs
- `tests/graph_api/test_graph_flows.py` (lines 210-233) — `TestNoMatchPath` pattern to mirror for reuse test
- `tests/graph_api/conftest.py` (lines 148-164) — `lg_client` and `thread` fixtures
- `tests/unit/test_food_lookup.py` (lines 20-26) — `_patch_session` helper (will need updating)
- `tests/unit/test_daily_log_service.py` (full file) — All service tests that use `async_test_db_session`
- `tests/unit/test_daily_log_model.py` (full file) — Model tests that use `async_test_db_session`

### New Files to Create

None — all changes are to existing files.

### Patterns to Follow

**Transaction rollback pattern for test isolation (SQLAlchemy async):**
```python
# The standard pattern: outer transaction wraps the entire test, rolls back at the end.
# The session is bound to the connection so all operations (including nested commits)
# happen within the outer transaction.
engine = create_async_engine(DATABASE_URL, **engine_kwargs)
async with engine.connect() as connection:
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    # ... seed data, yield session ...
    await transaction.rollback()
await engine.dispose()
```

**IMPORTANT — nested commit behavior:**
When the test (or the code under test) calls `await session.commit()`, SQLAlchemy issues a `RELEASE SAVEPOINT` inside the outer transaction — it does NOT actually commit to the DB. The outer `transaction.rollback()` at the end undoes everything.

However, for this to work correctly, we need to start a **nested transaction (savepoint)** after `begin()` so that `session.commit()` releases the savepoint rather than the outer transaction:
```python
await connection.begin_nested()  # creates SAVEPOINT
session = AsyncSession(bind=connection, expire_on_commit=False)
```

And we need to listen for `after_transaction_end` events to re-create savepoints after each commit, so multiple commits within a single test work correctly. **The recommended approach from SQLAlchemy docs:**

```python
from sqlalchemy import event

@event.listens_for(session.sync_session, "after_transaction_end")
def restart_savepoint(session_sync, transaction):
    if transaction.nested and not transaction._parent.nested:
        session_sync.begin_nested()
```

**SSL context for asyncpg (from `src/database.py` lines 15-20):**
```python
import ssl as _ssl
_engine_kwargs: dict = {}
if "asyncpg" in DATABASE_URL:
    _ctx = _ssl.create_default_context()
    _ctx.check_hostname = False
    _ctx.verify_mode = _ssl.CERT_NONE
    _engine_kwargs["connect_args"] = {"ssl": _ctx}
```

**User ID extraction pattern (current — to be replaced):**
```python
user_id = config["configurable"].get("user_id", DEFAULT_DEV_USER_ID) if config else DEFAULT_DEV_USER_ID
```

**E2E test 2-turn HITL pattern (from test_graph_flows.py):**
```python
await _run(lg_client, thread, input={...}, config=DEV_USER_CONFIG, test_name=tn)
await _assert_interrupted(lg_client, thread)
result = await _run(lg_client, thread, command={"resume": "yes"}, config=DEV_USER_CONFIG, test_name=tn)
```

---

## IMPLEMENTATION PLAN

### Phase 1: Extract `get_user_id` helper

Add helper to `src/config.py`, replace all 4 extraction sites. This is independent and can be validated immediately.

### Phase 2: Swap test DB fixture

Change `async_test_db_session` in `tests/conftest.py` to connect to real Supabase Postgres with transaction rollback. Update `_patch_session` in `test_food_lookup.py` if needed. Run all unit tests.

### Phase 3: Add estimated food reuse E2E test

Add `TestEstimatedFoodReuse` class in `test_graph_flows.py`. This uses a unique food name and 2 threads sharing the same `DEV_USER_CONFIG`.

---

## STEP-BY-STEP TASKS

### Task 1: ADD `get_user_id` helper to `src/config.py`

- **IMPLEMENT**: Add function after `DEFAULT_DEV_USER_ID` definition (after line 13):
  ```python
  def get_user_id(config: "RunnableConfig | None") -> str:
      """Extract user_id from LangGraph config, falling back to dev default."""
      if config:
          return config["configurable"].get("user_id", DEFAULT_DEV_USER_ID)
      return DEFAULT_DEV_USER_ID
  ```
- **IMPORTANT**: Use string annotation `"RunnableConfig | None"` to avoid importing `RunnableConfig` at module level in config.py (it would create a circular-ish dependency and is unnecessary for a utility function). Alternatively, use `from __future__ import annotations` at the top of the file.
- **VALIDATE**: `uv run python -c "from src.config import get_user_id; print(get_user_id(None))"`

### Task 2: UPDATE `src/tools/food_lookup.py` — replace extraction sites

- **REPLACE line 33** in `search_food`:
  - Old: `user_id = config["configurable"].get("user_id", DEFAULT_DEV_USER_ID)`
  - New: `user_id = get_user_id(config)`
- **REPLACE line 82** in `create_food_item`:
  - Old: `user_id = config["configurable"].get("user_id", DEFAULT_DEV_USER_ID) if config else DEFAULT_DEV_USER_ID`
  - New: `user_id = get_user_id(config)`
- **UPDATE IMPORTS**: Add `get_user_id` to the import from `src.config`. Remove `DEFAULT_DEV_USER_ID` from imports if no longer used directly.
- **VALIDATE**: `uv run pytest tests/unit/test_food_lookup.py -v`

### Task 3: UPDATE `src/services/daily_log_service.py` — replace extraction sites

- **REPLACE line 190** in `log_food_entry`:
  - Old: `user_id = config["configurable"].get("user_id", DEFAULT_DEV_USER_ID) if config else DEFAULT_DEV_USER_ID`
  - New: `user_id = get_user_id(config)`
- **REPLACE line 211** in `query_food_logs`:
  - Old: `user_id = config["configurable"].get("user_id", DEFAULT_DEV_USER_ID) if config else DEFAULT_DEV_USER_ID`
  - New: `user_id = get_user_id(config)`
- **UPDATE IMPORTS**: Add `get_user_id` to the import from `src.config`. Remove `DEFAULT_DEV_USER_ID` from imports if no longer used directly.
- **VALIDATE**: `uv run pytest tests/unit/test_daily_log_service.py -v`

### Task 4: UPDATE `tests/conftest.py` — swap SQLite fixture to Supabase Postgres

- **IMPORTS**: Add `import ssl as _ssl`, add `from sqlalchemy import event`, add `from sqlalchemy.ext.asyncio import AsyncSession`
- **IMPORT**: Add `from src.config import DATABASE_URL`
- **REMOVE**: The `"sqlite+aiosqlite:///:memory:"` engine creation and `Base.metadata.create_all` call
- **IMPLEMENT** new `async_test_db_session` fixture:
  ```python
  @pytest_asyncio.fixture
  async def async_test_db_session():
      """Provides an async Supabase Postgres session for testing.

      Uses transaction rollback for isolation — all test data (including seed)
      is visible during the test but rolled back at the end, leaving the real
      DB untouched.
      """
      # Build engine with SSL context for asyncpg (mirrors src/database.py)
      engine_kwargs: dict = {}
      if "asyncpg" in DATABASE_URL:
          ctx = _ssl.create_default_context()
          ctx.check_hostname = False
          ctx.verify_mode = _ssl.CERT_NONE
          engine_kwargs["connect_args"] = {"ssl": ctx}

      engine = create_async_engine(DATABASE_URL, **engine_kwargs)
      async with engine.connect() as connection:
          # Outer transaction — will be rolled back at the end
          transaction = await connection.begin()
          # Nested savepoint so session.commit() releases savepoint, not outer TX
          await connection.begin_nested()

          session = AsyncSession(bind=connection, expire_on_commit=False)

          # Re-create savepoint after each commit so multiple commits work
          @event.listens_for(session.sync_session, "after_transaction_end")
          def restart_savepoint(sync_session, trans):
              if trans.nested and not trans._parent.nested:
                  sync_session.begin_nested()

          # Seed with sample food item (same as before)
          sample_food = FoodItem(
              id=uuid_mod.UUID(SEED_FOOD_ID),
              name="Test Chicken",
              calories=165.0,
              protein=31.0,
              fat=3.6,
              carbs=0.0,
              source="database",
              user_id=None,
          )
          session.add(sample_food)
          await session.flush()  # make visible within TX, don't commit outer

          yield session

          # Cleanup
          await session.close()
          await transaction.rollback()

      await engine.dispose()
  ```
- **GOTCHA**: Use `await session.flush()` (not `commit()`) for the seed data to keep it inside the savepoint cleanly. If tests call `commit()`, the savepoint listener handles re-creation.
- **GOTCHA**: The SSL context setup MUST match `src/database.py` exactly — without it, asyncpg calls `os.getcwd()` and tests fail with BlockingError (not an issue here since tests don't run under blockbuster, but consistency is good practice).
- **GOTCHA**: `Base.metadata.create_all` is removed — tables already exist in Supabase.
- **VALIDATE**: `uv run pytest tests/unit/test_daily_log_model.py -v`

### Task 5: VERIFY `tests/unit/test_food_lookup.py` — `_patch_session` compatibility

- **CHECK**: The `_patch_session` helper patches `src.tools.food_lookup.get_async_db_session` to yield the test session. This should still work because the test session is now a real Postgres session (just wrapped in a rollback transaction). **No changes expected**, but verify by running:
- **VALIDATE**: `uv run pytest tests/unit/test_food_lookup.py -v`

### Task 6: ADD `TestEstimatedFoodReuse` E2E test to `tests/graph_api/test_graph_flows.py`

- **LOCATION**: After `TestNoMatchPath` class (after line 233)
- **IMPLEMENT**:
  ```python
  class TestEstimatedFoodReuse:
      """Estimated food logged once should be found in DB on subsequent searches, not re-estimated."""

      async def test_estimated_food_reused_on_second_log(self, lg_client, thread):
          """
          arrange: Thread 1 logs a unique unknown food → LLM estimates → user confirms.
          act:     Thread 2 logs the same food name again (same user).
          assert:  Thread 2 completes without error (food found in DB, not re-estimated).
                   Both threads produce non-empty final messages.
          """
          tn = "test_estimated_food_reused_on_second_log"
          unique_food = "xyzreuse77777qwerty"

          # --- Thread 1: first-time estimation + confirm ---
          await _run(
              lg_client, thread,
              input={"messages": [{"role": "human", "content": f"I ate 200g of {unique_food}"}]},
              config=DEV_USER_CONFIG,
              test_name=tn,
          )
          await _assert_interrupted(lg_client, thread)

          result1 = await _run(
              lg_client, thread,
              command={"resume": "yes"},
              config=DEV_USER_CONFIG,
              test_name=tn,
          )
          msgs1 = result1.get("messages", [])
          assert len(msgs1) >= 2
          assert msgs1[-1]["content"].strip() != ""

          # --- Thread 2: same food, should reuse estimated entry ---
          thread2 = (await lg_client.threads.create())["thread_id"]
          try:
              await _run(
                  lg_client, thread2,
                  input={"messages": [{"role": "human", "content": f"I ate 150g of {unique_food}"}]},
                  config=DEV_USER_CONFIG,
                  test_name=tn,
              )
              await _assert_interrupted(lg_client, thread2)

              result2 = await _run(
                  lg_client, thread2,
                  command={"resume": "yes"},
                  config=DEV_USER_CONFIG,
                  test_name=tn,
              )
              msgs2 = result2.get("messages", [])
              assert len(msgs2) >= 2
              assert msgs2[-1]["content"].strip() != ""
          finally:
              await lg_client.threads.delete(thread2)
  ```
- **PATTERN**: Mirrors `TestNoMatchPath` for Turn 1, adds a second thread for reuse verification.
- **GOTCHA**: The second thread must be created manually (not via the `thread` fixture) since the fixture only provides one thread. Clean up via `finally` block.
- **GOTCHA**: Use a unique food name (`xyzreuse77777qwerty`) that won't match any real DB food — ensures first search triggers estimation, not DB match.
- **VALIDATE**: `uv run pytest tests/graph_api/test_graph_flows.py::TestEstimatedFoodReuse -v -s`

---

## TESTING STRATEGY

### Unit Tests (Phase 1 + 2)

All 79 existing unit tests must pass against real Supabase Postgres:
- `test_food_lookup.py` — 4 tests: shared food access, estimated isolation, create sets user_id
- `test_daily_log_service.py` — 10 tests: CRUD + user isolation
- `test_daily_log_model.py` — 5 tests: model creation, timestamps, relationships

The `get_user_id` helper is tested implicitly through all existing tests that pass config objects.

### E2E Tests (Phase 3)

New `TestEstimatedFoodReuse` — 1 test verifying the 2-thread reuse path.

### Edge Cases

- `get_user_id(None)` returns `DEFAULT_DEV_USER_ID`
- `get_user_id({"configurable": {}})` returns `DEFAULT_DEV_USER_ID` (no user_id key)
- Transaction rollback: seed data must not persist in Supabase after test run
- Multiple `session.commit()` calls within a single test must work (savepoint re-creation)

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
```bash
uv run ruff check .
```

### Level 2: Unit Tests (now against real Postgres)
```bash
uv run pytest tests/unit/ -v
```

### Level 3: E2E Tests
```bash
uv run pytest tests/graph_api/ -v -s
```

### Level 4: Verify no data pollution
After running unit tests, verify no test data persists in Supabase:
```bash
uv run python -c "
import asyncio
from src.database import get_async_db_session
from src.models import FoodItem
from sqlalchemy import select
async def check():
    async with get_async_db_session() as s:
        r = await s.execute(select(FoodItem).where(FoodItem.name == 'Test Chicken'))
        assert r.scalars().first() is None, 'FAIL: seed data leaked to Supabase!'
        print('OK: No test data pollution detected.')
asyncio.run(check())
"
```

---

## ACCEPTANCE CRITERIA

- [ ] `get_user_id(config)` helper exists in `src/config.py` and is used in all 4 extraction sites
- [ ] No remaining `config["configurable"].get("user_id"` patterns in `src/tools/` or `src/services/`
- [ ] `async_test_db_session` connects to real Supabase Postgres
- [ ] All unit tests pass against Postgres (79 tests)
- [ ] No test data persists in Supabase after test run (transaction rollback works)
- [ ] `TestEstimatedFoodReuse` E2E test passes
- [ ] All 11 E2E tests pass (10 existing + 1 new)
- [ ] Ruff linting passes with zero errors

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + E2E)
- [ ] No linting or type checking errors
- [ ] Acceptance criteria all met

---

## NOTES

- **Why not a new test tier?** The user explicitly decided against a separate `tests/integration/` tier. The conftest fixture swap is simpler and tests the same code paths against real Postgres.
- **Transaction rollback pattern**: This is the standard SQLAlchemy pattern for test isolation. The outer transaction wraps everything; `session.commit()` releases a savepoint (not the outer TX). The `after_transaction_end` event listener re-creates savepoints so multiple commits work.
- **SSL context duplication**: The SSL context setup in conftest mirrors `src/database.py`. If we refactor later, we could extract a shared `create_engine_with_ssl()` helper, but that's not in scope for this plan.
- **`get_user_id` future-proofing**: When we add JWT auth (Phase 3 Step 5), we update ONE function — `get_user_id` — to decode the JWT and extract the user ID. All tools automatically pick up the change.
- **E2E estimated reuse test**: The unique food name ensures no collision with real DB foods. The test verifies the full cycle: estimate → persist → reuse on search.
