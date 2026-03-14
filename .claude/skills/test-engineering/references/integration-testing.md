# Integration Testing — FitPal Patterns

Tests in `tests/integration/` verify service functions, ORM models, and tool user-scoping against the **real Supabase Postgres** database. They sit between unit tests (fully mocked) and graph-api tests (full server E2E).

**What this tier catches that unit tests don't:**
- SQL query bugs (wrong WHERE clause, broken JOINs, missing filters)
- ORM constraint violations (NOT NULL, FK, unique)
- User-scoping failures (user A sees user B's data)
- Transaction/commit behavior differences between SQLite and Postgres

---

## 1. File Header Standard

Every integration test file MUST open with a module-level docstring declaring scope.

```python
"""
Integration tests for <Service/Model/Tool Name> (`<source_file>.py`).

Scope:
    Tests against real Supabase Postgres via async_test_db_session fixture.
    Verifies <brief description of what is being tested>.

LLM Usage:
    NONE — pure database operations.
"""
```

---

## 2. The `async_test_db_session` Fixture

All integration tests use this fixture from `tests/conftest.py`. It provides a real async Supabase Postgres session with transaction-rollback isolation.

**How it works:**
1. Opens a connection to the real Supabase DB (`DATABASE_URL`)
2. Begins an outer transaction (will be rolled back at teardown)
3. Creates a nested savepoint so `session.commit()` releases the savepoint, not the outer TX
4. Re-creates a new savepoint after each commit (supports multiple commits per test)
5. Seeds a shared `FoodItem(id=SEED_FOOD_ID, name="Test Chicken")` visible within the test
6. On teardown: rolls back the outer transaction — **no permanent data changes**

**Usage:** Just declare it as a parameter — pytest injects it automatically.

```python
async def test_create_log_entry(async_test_db_session):
    log = await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        food_id=SEED_FOOD_ID,
        amount_g=100.0,
        calories=165.0,
        protein=31.0,
        carbs=0.0,
        fat=3.6,
        timestamp=datetime.now(timezone.utc),
    )
    assert log.id is not None
```

---

## 3. Two Patterns

### 3.1 Service Function Tests (zero mocks)

Service functions accept `session` as a parameter (DI). Inject the test session directly, call the function, assert the result. No mocks needed.

```python
from src.services.daily_log_service import create_log_entry, get_logs_by_date

async def test_get_logs_by_date(async_test_db_session):
    """
    arrange: Create a log entry for today.
    act:     Query logs for today.
    assert:  Returns the created entry.
    """
    now = datetime.now(timezone.utc)
    await create_log_entry(
        async_test_db_session, user_id=TEST_USER_A,
        food_id=SEED_FOOD_ID, amount_g=100.0, calories=165.0,
        protein=31.0, carbs=0.0, fat=3.6, timestamp=now,
    )

    logs = await get_logs_by_date(async_test_db_session, TEST_USER_A, now.date())
    assert len(logs) == 1
```

### 3.2 Tool Tests (session patch)

Tools create their own DB session internally via `get_async_db_session()`. To redirect them to the test session, patch the session factory on the tool's module using the `_patch_session` helper.

```python
from contextlib import asynccontextmanager
from unittest.mock import patch

def _patch_session(session):
    """Create a context manager patch that yields the test session."""
    @asynccontextmanager
    async def _fake_session():
        yield session

    return patch("src.tools.food_lookup.get_async_db_session", _fake_session)


async def test_search_food(async_test_db_session):
    """
    arrange: Seeded FoodItem exists (from conftest).
    act:     Call search_food tool with patched session.
    assert:  Returns the seeded food.
    """
    with _patch_session(async_test_db_session):
        results = await search_food.ainvoke({"query": "Chicken"}, config=TEST_CONFIG_A)

    assert any(r["name"] == "Test Chicken" for r in results)
```

**Key difference from service tests:** Tools own their session, so we must patch. Service functions accept `session` as a param, so we inject directly.

---

## 4. ORM Model Tests

Test model creation, constraints, nullable fields, and relationships by creating instances and committing them through the test session.

```python
from src.models import DailyLog

async def test_daily_log_creation(async_test_db_session):
    """
    arrange: Build a DailyLog with all required fields.
    act:     Add and commit to DB.
    assert:  ID is generated, all fields persisted correctly.
    """
    log = DailyLog(
        food_id=uuid_mod.UUID(SEED_FOOD_ID),
        user_id=uuid_mod.UUID(TEST_USER_A),
        amount_g=100.0,
        calories=165.0, protein=31.0, carbs=0.0, fat=3.6,
        timestamp=datetime.now(timezone.utc),
    )
    async_test_db_session.add(log)
    await async_test_db_session.commit()

    assert log.id is not None
```

For relationship tests, use `await session.refresh(obj, ["relationship_name"])` to load lazy relationships.

---

## 5. User Data Isolation Tests

A key integration concern: verify that `user_id` scoping works correctly at the SQL layer.

```python
class TestUserDataIsolation:
    """Verify user data isolation at the service/tool layer."""

    async def test_user_a_cannot_see_user_b_logs(self, async_test_db_session):
        """
        arrange: User A and User B each log food on the same date.
        act:     Query logs for User A only.
        assert:  Only User A's logs returned.
        """
        now = datetime.now(timezone.utc)
        await create_log_entry(async_test_db_session, user_id=TEST_USER_A, ...)
        await create_log_entry(async_test_db_session, user_id=TEST_USER_B, ...)

        logs_a = await get_logs_by_date(async_test_db_session, TEST_USER_A, now.date())
        assert len(logs_a) == 1
```

---

## 6. Shared Test Constants

Import from `tests/conftest.py` — never redefine:

| Constant | Value | Purpose |
|---|---|---|
| `TEST_USER_A` | `"aaaaaaaa-aaaa-..."` | First test user UUID |
| `TEST_USER_B` | `"bbbbbbbb-bbbb-..."` | Second test user UUID |
| `TEST_CONFIG_A` | `{"configurable": {"user_id": TEST_USER_A}}` | RunnableConfig for user A |
| `TEST_CONFIG_B` | `{"configurable": {"user_id": TEST_USER_B}}` | RunnableConfig for user B |
| `SEED_FOOD_ID` | `"11111111-1111-..."` | Pre-seeded FoodItem UUID |
