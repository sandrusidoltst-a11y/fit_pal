# Feature: Async Database Migration

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to import paths — the async SQLAlchemy classes live in `sqlalchemy.ext.asyncio`, NOT in the standard `sqlalchemy.orm`. The checkpointer import path also changed between versions, verify with the installed package.

## Feature Description

Refactor all synchronous SQLAlchemy database operations and the LangGraph checkpointer to use async I/O (`AsyncSession`, `async_sessionmaker`, `AsyncSqliteSaver`). This eliminates sync blocking inside LangGraph's async event loop and establishes the architectural foundation that makes a future switch to PostgreSQL/Supabase a near-trivial connection-string change.

SQLite remains the database — only the driver changes from the built-in `sqlite3` (sync-only) to `aiosqlite` (async-compatible). **No schema changes. No data migration. No new features.**

## User Story

As the FitPal developer
I want all database I/O to run asynchronously
So that the application is non-blocking inside LangGraph's async event loop and ready for production-scale deployment without a future rewrite.

## Problem Statement

All current database calls (`session.execute()`, `session.commit()`, `session.refresh()`) are synchronous. When executed inside LangGraph's async event loop (`langgraph dev`), they silently block the entire event loop, preventing concurrency and creating a hidden bottleneck that would require a full rewrite when moving to a web server in Phase 3.

## Solution Statement

1. Add `aiosqlite` as a runtime dependency and `anyio` + `pytest-asyncio` as dev dependencies.
2. Replace `create_engine` / `sessionmaker` / `Session` with `create_async_engine` / `async_sessionmaker` / `AsyncSession` in `src/database.py`.
3. Convert all service functions in `src/services/daily_log_service.py` to `async def` with `await` on I/O calls.
4. Convert the two DB-touching nodes (`calculate_log_node`, `stats_lookup_node`) to `async def` with `async with` session context managers.
5. Swap `SqliteSaver` → `AsyncSqliteSaver` in `src/agents/nutritionist.py` and make `define_graph()` async.
6. Update `conftest.py` to provide an async in-memory session fixture, and convert all affected test functions to `async def` with `@pytest.mark.anyio`.

## Feature Metadata

**Feature Type**: Refactor  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: `src/database.py`, `src/services/daily_log_service.py`, `src/agents/nodes/calculate_log_node.py`, `src/agents/nodes/stats_node.py`, `src/agents/nutritionist.py`, `tests/conftest.py`, five test files  
**Dependencies**: `aiosqlite` (runtime), `anyio`, `pytest-asyncio` (dev)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `src/database.py` (lines 1–13) — Full file. The sync `create_engine` + `SessionLocal` + `get_db_session()` to be replaced.
- `src/services/daily_log_service.py` (lines 1–135) — Full file. All four functions become `async def`. `session.commit()`, `session.refresh()`, and `session.execute()` all need `await`.
- `src/agents/nodes/calculate_log_node.py` (lines 1–98) — Full file. `calculate_log_node` becomes `async def`. `get_db_session()` → `get_async_db_session()`. Context manager changes to `async with`.
- `src/agents/nodes/stats_node.py` (lines 1–45) — Full file. `stats_lookup_node` becomes `async def`. Same session swap.
- `src/agents/nutritionist.py` (lines 1–88) — Full file. `define_graph()` becomes `async def`. `SqliteSaver` → `AsyncSqliteSaver`. `sqlite3.connect()` removed.
- `tests/conftest.py` (lines 1–58) — Full file. `test_db_session` fixture must become async and use `AsyncSession` / `aiosqlite`.
- `tests/unit/test_daily_log_service.py` (lines 1–201) — Full file. All 5 test functions → `async def` + `@pytest.mark.anyio`. `test_db_session` → `async_test_db_session`.
- `tests/unit/test_calculate_log_node.py` (lines 1–145) — Full file. Mock pattern changes from `__enter__` to `__aenter__`. All 3 tests → `async def` + `@pytest.mark.anyio`.
- `tests/unit/test_stats_node.py` (lines 1–78) — Full file. Same async mock pattern. Both tests → `async def` + `@pytest.mark.anyio`.
- `tests/unit/test_feedback_integration.py` (lines 1–89) — Full file. Patches `SqliteSaver` → `AsyncSqliteSaver`. Integration test becomes `async def` + `@pytest.mark.anyio`. `define_graph` must be awaited.
- `tests/unit/test_multi_item_loop.py` (lines 1–81) — Full file. Calls `calculate_log_node` directly — all calls must `await` the node. All 5 tests → `async def` + `@pytest.mark.anyio`.

### New Files to Create

None. This is a pure refactor — no new files.

### Relevant Documentation — SHOULD READ BEFORE IMPLEMENTING

- [SQLAlchemy Async ORM Synopsis](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#synopsis-orm)
  - Section: "Synopsis - ORM" 
  - Why: Shows the exact `create_async_engine`, `async_sessionmaker`, `async with session.begin()` pattern. **Critical**: note that `expire_on_commit=False` is required on `async_sessionmaker` to access attributes after `commit()`.
- [SQLAlchemy Async Session — Preventing Implicit IO](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#preventing-implicit-io-when-using-asyncsession)
  - Why: Explains the `expire_on_commit=False` requirement in detail — attributes accessed after commit would trigger lazy-load I/O, which is not allowed in async context.
- [pytest-asyncio docs](https://pytest-asyncio.readthedocs.io/en/latest/reference/modes/auto.html)
  - Section: `asyncio_mode = "auto"`
  - Why: Setting `asyncio_mode = "auto"` in `pyproject.toml` removes the need to decorate every test with `@pytest.mark.asyncio`, keeping tests clean.
- [LangGraph AsyncSqliteSaver source](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/aio.py)
  - Why: Confirms the import path `from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver` and the `from_conn_string` class method signature.

---

## Patterns to Follow

### Async Engine + Session Factory (new pattern for `src/database.py`)
```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_async_db_session() -> AsyncSession:
    """Returns a new async database session."""
    return AsyncSessionLocal()
```

**GOTCHA**: `expire_on_commit=False` is **mandatory**. Without it, accessing any ORM attribute after `await session.commit()` will trigger a synchronous lazy-load, raising `MissingGreenlet` error.

### Async Service Function Pattern (for `src/services/daily_log_service.py`)
```python
# Before
def create_log_entry(session: Session, ...) -> DailyLog:
    session.add(log)
    session.commit()
    session.refresh(log)
    return log

# After
async def create_log_entry(session: AsyncSession, ...) -> DailyLog:
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log
```

### Async Node Pattern (for `calculate_log_node` and `stats_lookup_node`)
```python
# Before
def calculate_log_node(state: AgentState) -> dict:
    with get_db_session() as session:
        ...

# After
async def calculate_log_node(state: AgentState) -> dict:
    async with get_async_db_session() as session:
        ...
```

**GOTCHA**: The function `get_async_db_session()` must be used as a context manager via `async with`. This requires the factory to return an `AsyncSession` that supports `async with`. Since `async_sessionmaker` returns a proper context manager, this works cleanly.

### AsyncSqliteSaver Pattern (for `src/agents/nutritionist.py`)
```python
# Before
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
conn = sqlite3.connect("data/checkpoints.sqlite", check_same_thread=False)
memory = SqliteSaver(conn)

# After
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
memory = AsyncSqliteSaver.from_conn_string("data/checkpoints.sqlite")
```
`define_graph()` becomes `async def define_graph()`.

### Async Test Fixture Pattern (for `tests/conftest.py`)
```python
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

@pytest_asyncio.fixture
async def async_test_db_session() -> AsyncSession:
    """Async in-memory SQLite session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    AsyncTestSession = async_sessionmaker(engine, expire_on_commit=False)
    async with AsyncTestSession() as session:
        # Seed sample food item
        sample_food = FoodItem(id=1, name="Test Chicken", calories=165.0, protein=31.0, fat=3.6, carbs=0.0)
        session.add(sample_food)
        await session.commit()
        yield session
    await engine.dispose()
```

**GOTCHA**: Use `@pytest_asyncio.fixture` (not `@pytest.fixture`) for async fixtures. This is required by `pytest-asyncio` when `asyncio_mode` is not `"auto"`. To avoid this complexity, set `asyncio_mode = "auto"` in `pyproject.toml`.

### Async Node Mock Pattern (for `test_calculate_log_node.py` and `test_stats_node.py`)
```python
# Before (sync context manager mock)
@pytest.fixture
def mock_db_session():
    with patch("src.agents.nodes.calculate_log_node.get_db_session") as mock:
        session = MagicMock()
        mock.return_value.__enter__.return_value = session
        yield session

# After (async context manager mock)
@pytest.fixture
def mock_db_session():
    with patch("src.agents.nodes.calculate_log_node.get_async_db_session") as mock:
        session = AsyncMock()
        mock.return_value.__aenter__.return_value = session
        mock.return_value.__aexit__.return_value = False
        yield session
```

**GOTCHA**: Must use `AsyncMock` (from `unittest.mock`) not `MagicMock` for async context managers. `AsyncMock` automatically implements `__aenter__` and `__aexit__`.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — Dependencies & Config

Add runtime and dev dependencies, update `DATABASE_URL` prefix, configure pytest for async.

### Phase 2: Core Infrastructure — database.py

Replace the sync engine factory with the async version. This is the single source of truth — all other changes flow from this.

### Phase 3: Service Layer — daily_log_service.py

Convert all four service functions to `async def`. The SQL queries themselves (`select`, `func.sum`) are unchanged — only the execution and commit calls get `await`.

### Phase 4: Graph Nodes — calculate_log_node.py & stats_node.py

Convert both DB-touching nodes to `async def` and update the session usage pattern.

### Phase 5: Checkpointer — nutritionist.py

Swap the LangGraph checkpointer to its async variant and make `define_graph` async.

### Phase 6: Tests — conftest.py + 5 test files

Update the shared fixture, then convert each test file in dependency order (service tests first, then node tests, then integration).

---

## STEP-BY-STEP TASKS

### TASK 1 — UPDATE `pyproject.toml`
- **ADD** runtime dependency: `aiosqlite>=0.19.0`
- **ADD** dev dependencies: `anyio>=4.0.0`, `pytest-asyncio>=0.23.0`
- **ADD** pytest configuration section to enable auto asyncio mode:
  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  ```
- **IMPORTS**: None
- **GOTCHA**: `asyncio_mode = "auto"` means ALL `async def` test functions are automatically treated as async tests — no decorator needed per test. If you skip this, you need `@pytest.mark.asyncio` on every single async test function.
- **VALIDATE**: `uv sync` (installs new deps), then `uv run pytest --collect-only` (ensures no collection errors)

### TASK 2 — UPDATE `src/config.py`
- **UPDATE** `DATABASE_URL` to use the `aiosqlite` driver prefix:
  ```python
  # Before
  DATABASE_URL = f"sqlite:///{DB_PATH}"
  # After
  DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
  ```
- **PATTERN**: `src/config.py` lines 10–12
- **IMPORTS**: No new imports needed
- **GOTCHA**: This single character change is what bridges SQLAlchemy's async engine to the `aiosqlite` driver. Without it, `create_async_engine` will fail with a driver error.
- **VALIDATE**: `uv run python -c "from src.config import DATABASE_URL; print(DATABASE_URL)"` — must print a URL starting with `sqlite+aiosqlite:///`

### TASK 3 — REFACTOR `src/database.py`
- **REPLACE** entire file content with async version:
  ```python
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
  from src.config import DATABASE_URL

  # expire_on_commit=False is REQUIRED: prevents MissingGreenlet errors when
  # accessing ORM attributes after commit() in async context.
  engine = create_async_engine(DATABASE_URL)
  AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

  def get_async_db_session() -> AsyncSession:
      """Returns a new async database session (use as async context manager)."""
      return AsyncSessionLocal()
  ```
- **REMOVE**: `create_engine`, `sessionmaker`, `Session`, `get_db_session`
- **IMPORTS**: `from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine`
- **GOTCHA**: `get_async_db_session()` is a plain (sync) factory that returns an `AsyncSession`. The `async with` keyword in the calling code handles the async context management. Do NOT make `get_async_db_session` itself an `async def` — that would require `await` to call it, which is inconsistent with the context manager pattern.
- **VALIDATE**: `uv run python -c "from src.database import get_async_db_session; print('OK')"` — must print `OK` with no errors

### TASK 4 — REFACTOR `src/services/daily_log_service.py`
- **UPDATE** import: `from sqlalchemy.orm import Session` → `from sqlalchemy.ext.asyncio import AsyncSession`
- **CONVERT** all four functions to `async def`:
  - `create_log_entry(session: AsyncSession, ...)`: add `await` before `session.commit()` and `session.refresh(log)`
  - `get_daily_totals(session: AsyncSession, ...)`: add `await` before `session.execute(stmt)`; result access `.one()` stays sync (it operates on the already-resolved `Result` object)
  - `get_logs_by_date(session: AsyncSession, ...)`: add `await` before `session.execute(stmt)`; `.scalars().all()` stays sync
  - `get_logs_by_date_range(session: AsyncSession, ...)`: same pattern as `get_logs_by_date`
- **PATTERN**: `src/services/daily_log_service.py` lines 17–135 (all functions)
- **GOTCHA**: Only the `session.execute()`, `session.commit()`, and `session.refresh()` calls get `await`. Chained calls on the `Result` object (`.one()`, `.scalars()`, `.all()`) are synchronous and must NOT get `await`.
- **VALIDATE**: `uv run python -c "import asyncio; from src.services.daily_log_service import create_log_entry; import inspect; assert asyncio.iscoroutinefunction(create_log_entry); print('OK')"` — must print `OK`

### TASK 5 — REFACTOR `src/agents/nodes/calculate_log_node.py`
- **UPDATE** import: `from src.database import get_db_session` → `from src.database import get_async_db_session`
- **CONVERT** `calculate_log_node` to `async def calculate_log_node(state: AgentState) -> dict:`
- **UPDATE** session block:
  ```python
  # Before
  with get_db_session() as session:
      daily_log_service.create_log_entry(...)
      logs = daily_log_service.get_logs_by_date(...)
  
  # After
  async with get_async_db_session() as session:
      await daily_log_service.create_log_entry(...)
      logs = await daily_log_service.get_logs_by_date(...)
  ```
- **PATTERN**: `src/agents/nodes/calculate_log_node.py` lines 46–75
- **GOTCHA**: Every call to a service function that is now `async` must have `await`. Missing a single `await` returns a coroutine object instead of the actual result — this will not raise an immediate error but will silently produce wrong behavior (e.g., `updated_report` would be a coroutine, not a list).
- **VALIDATE**: `uv run python -c "import asyncio; from src.agents.nodes.calculate_log_node import calculate_log_node; assert asyncio.iscoroutinefunction(calculate_log_node); print('OK')"`

### TASK 6 — REFACTOR `src/agents/nodes/stats_node.py`
- **UPDATE** import: `from src.database import get_db_session` → `from src.database import get_async_db_session`
- **CONVERT** `stats_lookup_node` to `async def stats_lookup_node(state: AgentState) -> Dict:`
- **UPDATE** session block:
  ```python
  # Before
  with get_db_session() as session:
      logs = daily_log_service.get_logs_by_date(...)

  # After
  async with get_async_db_session() as session:
      logs = await daily_log_service.get_logs_by_date(...)
  ```
- **PATTERN**: `src/agents/nodes/stats_node.py` lines 18–25
- **GOTCHA**: Same as Task 5 — all service calls need `await`.
- **VALIDATE**: `uv run python -c "import asyncio; from src.agents.nodes.stats_node import stats_lookup_node; assert asyncio.iscoroutinefunction(stats_lookup_node); print('OK')"`

### TASK 7 — REFACTOR `src/agents/nutritionist.py`
- **REMOVE** import: `import sqlite3` and `from langgraph.checkpoint.sqlite import SqliteSaver`
- **ADD** import: `from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver`
- **CONVERT** `define_graph()` to `async def define_graph():`
- **REPLACE** checkpointer setup (last 4 lines of the function):
  ```python
  # Before
  conn = sqlite3.connect("data/checkpoints.sqlite", check_same_thread=False)
  memory = SqliteSaver(conn)
  return workflow.compile(checkpointer=memory)

  # After
  memory = AsyncSqliteSaver.from_conn_string("data/checkpoints.sqlite")
  return workflow.compile(checkpointer=memory)
  ```
- **PATTERN**: `src/agents/nutritionist.py` lines 84–87
- **GOTCHA**: Verify the import path for `AsyncSqliteSaver` matches the installed version of `langgraph-checkpoint-sqlite`. Run `uv run python -c "from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver; print('OK')"` before writing any code.
- **VALIDATE**: `uv run python -c "import asyncio; from src.agents.nutritionist import define_graph; assert asyncio.iscoroutinefunction(define_graph); print('OK')"`

### TASK 8 — REFACTOR `tests/conftest.py`
- **UPDATE** imports:
  - Remove: `from sqlalchemy import create_engine`, `from sqlalchemy.orm import sessionmaker`
  - Add: `import pytest_asyncio`, `from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine`
- **RENAME** fixture `test_db_session` → `async_test_db_session`
- **CONVERT** fixture to async using `@pytest_asyncio.fixture`:
  ```python
  @pytest_asyncio.fixture
  async def async_test_db_session():
      """Provides an async in-memory SQLite session for testing."""
      engine = create_async_engine("sqlite+aiosqlite:///:memory:")
      async with engine.begin() as conn:
          await conn.run_sync(Base.metadata.create_all)

      AsyncTestSession = async_sessionmaker(engine, expire_on_commit=False)
      async with AsyncTestSession() as session:
          sample_food = FoodItem(
              id=1, name="Test Chicken",
              calories=165.0, protein=31.0, fat=3.6, carbs=0.0,
          )
          session.add(sample_food)
          await session.commit()
          yield session

      await engine.dispose()
  ```
- **UPDATE** `basic_state` fixture: remove `"daily_totals"` key (does not exist in current `AgentState`) and add missing `"daily_log_report": []`, `"start_date": None`, `"end_date": None`, `"processing_results": []` keys to match `AgentState` TypedDict exactly.
- **PATTERN**: `tests/conftest.py` lines 32–57 (old `test_db_session`)
- **GOTCHA**: The fixture must use `@pytest_asyncio.fixture` not `@pytest.fixture`. With `asyncio_mode = "auto"` this distinction matters specifically for async generator fixtures. Also, `Base.metadata.create_all` is synchronous and must be called via `await conn.run_sync(Base.metadata.create_all)` — do NOT put `await` directly on `Base.metadata.create_all`.
- **VALIDATE**: `uv run pytest tests/conftest.py --collect-only` — no collection errors

### TASK 9 — REFACTOR `tests/unit/test_daily_log_service.py`
- **UPDATE** fixture parameter name: `test_db_session` → `async_test_db_session` in all 5 test function signatures
- **CONVERT** all 5 test functions to `async def`
- **ADD** `await` to all direct service function calls (e.g., `await create_log_entry(...)`, `await get_daily_totals(...)`, `await get_logs_by_date(...)`, `await get_logs_by_date_range(...)`)
- **PATTERN**: `tests/unit/test_daily_log_service.py` lines 15–201
- **GOTCHA**: With `asyncio_mode = "auto"`, no `@pytest.mark.asyncio` decorator is needed. Just `async def` is sufficient.
- **VALIDATE**: `uv run pytest tests/unit/test_daily_log_service.py -v` — all 5 tests pass

### TASK 10 — REFACTOR `tests/unit/test_calculate_log_node.py`
- **UPDATE** import: add `from unittest.mock import AsyncMock`
- **UPDATE** mock fixtures to use async context manager pattern:
  ```python
  @pytest.fixture
  def mock_db_session():
      with patch("src.agents.nodes.calculate_log_node.get_async_db_session") as mock:
          session = AsyncMock()
          mock.return_value.__aenter__ = AsyncMock(return_value=session)
          mock.return_value.__aexit__ = AsyncMock(return_value=False)
          yield session
  ```
- **CONVERT** all 3 test functions to `async def`
- **ADD** `await` to `calculate_log_node(state)` call in all 3 tests
- **PATTERN**: `tests/unit/test_calculate_log_node.py` lines 8–22 (fixtures), 24–92 (tests)
- **GOTCHA**: The mock for `mock_daily_log_service` stays as a regular `MagicMock` (it mocks the module, not the session). However, if `daily_log_service.create_log_entry` is now `async`, its mock must return a coroutine. With `patch`, this is automatic when you set the `AsyncMock` return value. Specifically: `mock_daily_log_service.get_logs_by_date.return_value = [log_mock]` must remain — the patched module's method automatically becomes an `AsyncMock` when the calling code `await`s it (Python 3.8+ behavior under `patch`). Verify this works; if not, explicitly set `mock_daily_log_service.get_logs_by_date = AsyncMock(return_value=[log_mock])`.
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_log_node.py -v` — all 3 tests pass

### TASK 11 — REFACTOR `tests/unit/test_stats_node.py`
- **UPDATE** import: add `from unittest.mock import AsyncMock`
- **UPDATE** `mock_db_session` fixture: patch `get_async_db_session`, use `AsyncMock` for `__aenter__`/`__aexit__`
- **CONVERT** both test functions to `async def`
- **ADD** `await` to `stats_lookup_node(state)` calls
- **PATTERN**: `tests/unit/test_stats_node.py` lines 8–18 (fixtures), 20–77 (tests)
- **VALIDATE**: `uv run pytest tests/unit/test_stats_node.py -v` — both tests pass

### TASK 12 — REFACTOR `tests/unit/test_multi_item_loop.py`
- **CONVERT** all 5 test functions to `async def`
- **UPDATE** all calls: `calculate_log_node(basic_state)` → `await calculate_log_node(basic_state)`
- **PATTERN**: `tests/unit/test_multi_item_loop.py` lines 5–80
- **GOTCHA**: These tests use `basic_state` fixture from `conftest.py`. After Task 8, verify `basic_state` has all required `AgentState` keys (particularly `daily_log_report`, `processing_results`, `start_date`, `end_date`). The current `basic_state` has a stale `daily_totals` key that doesn't exist in `AgentState` — fix this in Task 8.
- **VALIDATE**: `uv run pytest tests/unit/test_multi_item_loop.py -v` — all 5 tests pass

### TASK 13 — REFACTOR `tests/unit/test_feedback_integration.py`
- **UPDATE** patch target: `"src.agents.nutritionist.SqliteSaver"` → `"src.agents.nutritionist.AsyncSqliteSaver"`
- **REMOVE** the `sqlite3.connect` patch (no longer needed — `AsyncSqliteSaver.from_conn_string` manages the connection internally)
- **CONVERT** `test_integration_full_flow` to `async def`
- **UPDATE** graph invocation: `define_graph()` → `await define_graph()` (since `define_graph` is now async)
- **UPDATE** the `app.invoke(...)` call: LangGraph's async graph uses `await app.ainvoke(...)` not `app.invoke(...)`:
  ```python
  final_state = await app.ainvoke(
      {"messages": [("user", "I ate an apple")]},
      config={"configurable": {"thread_id": "1"}}
  )
  ```
- **PATTERN**: `tests/unit/test_feedback_integration.py` lines 10–88
- **GOTCHA**: `app.invoke()` is the sync API. After the checkpointer is async, the graph must be called with `await app.ainvoke()`. Calling `app.invoke()` on an async checkpointer will hang or raise an event loop error.
- **VALIDATE**: `uv run pytest tests/unit/test_feedback_integration.py -v` — test passes

---

## TESTING STRATEGY

### Unit Tests

**Scope**: Each refactored component tested in isolation using async mocks to simulate DB behavior without actual DB connections.

- `test_daily_log_service.py`: Tests the service functions through a real async in-memory SQLite DB (no mocks). Tests verify actual SQL behavior.
- `test_calculate_log_node.py`: Mocks both the DB session and the service module. Tests routing logic and state update correctness.
- `test_stats_node.py`: Mocks DB session and service. Tests single-day and date-range routing.
- `test_multi_item_loop.py`: Mocks the full DB stack implicitly (no selection or session calls hit real DB in these cases). Tests the item-removal loop logic.

### Integration Tests

- `test_feedback_integration.py`: Tests the full LangGraph graph execution with all node functions mocked except `response_node` (which uses a real but mocked LLM). Verifies that the async graph compiles, routes correctly, and the checkpointer does not block.

### Edge Cases

- `test_daily_log_service.py::test_get_daily_totals_empty`: Verify `await session.execute()` on empty table returns zeros (not `None`).
- `test_calculate_log_node.py::test_calculate_log_node_macro_error`: Verify `daily_log_report` is preserved unchanged when macro calculator returns an error dict.
- `test_calculate_log_node.py::test_calculate_log_node_no_selection_or_processed`: Verify no DB calls are made when `selected_food_id` is `None`.
- `test_multi_item_loop.py::test_calculate_log_empty_pending`: Verify `return {}` for empty pending items (no session opened).

---

## VALIDATION COMMANDS

Execute every command in order to ensure zero regressions.

### Level 1: Syntax Check
```bash
uv run python -c "from src.database import get_async_db_session; print('database.py OK')"
uv run python -c "from src.services.daily_log_service import create_log_entry, get_daily_totals, get_logs_by_date, get_logs_by_date_range; print('daily_log_service.py OK')"
uv run python -c "from src.agents.nodes.calculate_log_node import calculate_log_node; print('calculate_log_node.py OK')"
uv run python -c "from src.agents.nodes.stats_node import stats_lookup_node; print('stats_node.py OK')"
uv run python -c "from src.agents.nutritionist import define_graph; print('nutritionist.py OK')"
```

### Level 2: Async Coroutine Verification
```bash
uv run python -c "import asyncio; from src.services.daily_log_service import create_log_entry, get_daily_totals, get_logs_by_date, get_logs_by_date_range; assert all(asyncio.iscoroutinefunction(f) for f in [create_log_entry, get_daily_totals, get_logs_by_date, get_logs_by_date_range]); print('All service functions are async OK')"
uv run python -c "import asyncio; from src.agents.nodes.calculate_log_node import calculate_log_node; from src.agents.nodes.stats_node import stats_lookup_node; assert asyncio.iscoroutinefunction(calculate_log_node) and asyncio.iscoroutinefunction(stats_lookup_node); print('Both nodes are async OK')"
uv run python -c "import asyncio; from src.agents.nutritionist import define_graph; assert asyncio.iscoroutinefunction(define_graph); print('define_graph is async OK')"
```

### Level 3: DB-Layer Unit Tests (service functions with real async in-memory DB)
```bash
uv run pytest tests/unit/test_daily_log_service.py -v
```

### Level 4: Node Unit Tests (mocked DB)
```bash
uv run pytest tests/unit/test_calculate_log_node.py tests/unit/test_stats_node.py tests/unit/test_multi_item_loop.py -v
```

### Level 5: Full Unit Suite
```bash
uv run pytest tests/unit/ -v
```

### Level 6: Integration Test
```bash
uv run pytest tests/unit/test_feedback_integration.py -v
```

### Level 7: Full Test Suite (Zero Regressions)
```bash
uv run pytest -v
```

### Level 8: Linting
```bash
uv run ruff check src/ tests/
```

---

## ACCEPTANCE CRITERIA

- [ ] `aiosqlite`, `anyio`, and `pytest-asyncio` are installed and in `pyproject.toml`
- [ ] `DATABASE_URL` in `src/config.py` uses `sqlite+aiosqlite:///` prefix
- [ ] `src/database.py` exports `get_async_db_session()` (sync factory, returns `AsyncSession`)
- [ ] All four functions in `src/services/daily_log_service.py` are `async def`
- [ ] `calculate_log_node` and `stats_lookup_node` are both `async def`
- [ ] `define_graph()` in `src/agents/nutritionist.py` is `async def` and uses `AsyncSqliteSaver`
- [ ] `tests/conftest.py` provides `async_test_db_session` fixture (async, in-memory, aiosqlite)
- [ ] `basic_state` fixture reflects the actual `AgentState` TypedDict (no stale `daily_totals` key)
- [ ] All 5 test files with async functions converted; no sync `def test_*` functions calling async nodes/services
- [ ] `uv run pytest -v` passes with 100% of tests (zero failures, zero errors)
- [ ] `uv run ruff check src/ tests/` reports zero violations
- [ ] No synchronous `sqlite3.connect()` or `create_engine()` calls remain in production code
- [ ] No regression in non-async tests (`test_input_parser.py`, `test_response_node.py`, `test_agent_selection.py`, `test_food_search_node.py`, `test_state_consistency.py`)

---

## COMPLETION CHECKLIST

- [ ] Task 1: `pyproject.toml` updated with deps + pytest config
- [ ] Task 2: `src/config.py` DATABASE_URL prefix updated
- [ ] Task 3: `src/database.py` fully replaced with async version
- [ ] Task 4: `src/services/daily_log_service.py` all 4 functions async
- [ ] Task 5: `src/agents/nodes/calculate_log_node.py` async
- [ ] Task 6: `src/agents/nodes/stats_node.py` async
- [ ] Task 7: `src/agents/nutritionist.py` async + AsyncSqliteSaver
- [ ] Task 8: `tests/conftest.py` async fixture + fixed basic_state
- [ ] Task 9: `tests/unit/test_daily_log_service.py` async
- [ ] Task 10: `tests/unit/test_calculate_log_node.py` async mocks
- [ ] Task 11: `tests/unit/test_stats_node.py` async mocks
- [ ] Task 12: `tests/unit/test_multi_item_loop.py` async
- [ ] Task 13: `tests/unit/test_feedback_integration.py` async + ainvoke
- [ ] Level 1–8 validation commands all pass
- [ ] All acceptance criteria checked off

---

## NOTES

### Why `expire_on_commit=False` Is Non-Negotiable
In SQLAlchemy's async mode, after `await session.commit()`, SQLAlchemy would normally "expire" all ORM objects (mark their attributes as stale, to be lazily reloaded on next access). This lazy reload would trigger implicit I/O — which is forbidden in async context, resulting in a `MissingGreenlet` runtime error. Setting `expire_on_commit=False` disables this expiry, so attributes accessed after commit return the in-memory values from before the commit. Since `create_log_entry` calls `await session.refresh(log)` explicitly after commit, data freshness is still guaranteed.

### Why `test_multi_item_loop.py` Has No DB Calls
Looking at the test fixture (`basic_state`), `selected_food_id` is set to `1` but there is no mock for `get_db_session`. This works because in `calculate_log_node`, the `calculate_food_macros.invoke()` call is also not mocked — it relies on `calculate_food_macros` being a LangChain tool that returns consistent results, or the test relies on reaching the `selected_food_id is None` path. After refactoring, if these tests start failing due to an open DB connection attempt, add `mock_db_session` and `mock_daily_log_service` fixtures to the affected test functions.

### Future Phase 3 Migration Path
After this refactor, switching to PostgreSQL in Phase 3 requires exactly:
1. `uv add asyncpg`
2. Change `.env`: `DATABASE_URL=postgresql+asyncpg://user:pass@host/db`
3. Swap `AsyncSqliteSaver` → `AsyncPostgresSaver` in `nutritionist.py`

Zero application logic changes required.

### DB-Touching File Inventory (Complete)
Only these files touch the database. All others are untouched by this refactor:
- `src/database.py` ✓ (infrastructure)
- `src/services/daily_log_service.py` ✓ (service layer)
- `src/agents/nodes/calculate_log_node.py` ✓ (consumer)
- `src/agents/nodes/stats_node.py` ✓ (consumer)
- `src/agents/nutritionist.py` ✓ (checkpointer only)
- `src/scripts/ingest_simple_db.py` — Uses sync SQLAlchemy for a one-time ETL script. Intentionally left synchronous — it's a standalone CLI tool, not part of the agent graph.
