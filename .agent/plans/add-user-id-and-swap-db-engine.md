# Feature: Combined Phase 3 Steps 2+3 — Add user_id + Swap DB Engine

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Migrate FitPal from local SQLite to Supabase Postgres and make the schema multi-user ready by adding `user_id` columns to both tables. This combines Phase 3 Steps 2 and 3 from the deployment plan to avoid touching every file twice.

Three simultaneous changes:
1. **Swap DB engine**: SQLite (`aiosqlite`) → Supabase Postgres (`asyncpg`)
2. **Add user_id columns**: `daily_logs.user_id` (NOT NULL) + `food_items.user_id` (nullable)
3. **Change PKs**: Integer → UUID (models must match existing Supabase schema)

## User Story

As a FitPal developer
I want user-scoped data and a production-ready database
So that the app is ready for multi-user deployment without a second rewrite

## Problem Statement

Currently all data lives in a single-user local SQLite database with integer PKs. The Supabase Postgres tables (created in Step 1) use UUID PKs and have no user_id columns. The app needs to talk to Postgres, use UUIDs, and scope all data by user_id.

## Solution Statement

Update SQLAlchemy models to use `Uuid` type for PKs and add `user_id` columns. Switch the async engine from `aiosqlite` to `asyncpg`. Add `user_id` filtering to all queries. Pass `user_id` through LangGraph's `config["configurable"]` — nodes accept `config: RunnableConfig` and forward it to tools via `ainvoke(params, config=config)`. Tools extract `user_id` from config internally. Remove Alembic (no longer needed). Apply Supabase migration for the new columns.

## Feature Metadata

**Feature Type**: Enhancement + Refactor
**Estimated Complexity**: High
**Primary Systems Affected**: models, database, config, tools, services, nodes (commit, stats, food_search, confirmation, calculate_macros), all tests
**Dependencies**: `asyncpg` (new), `sqlalchemy.Uuid` type (already available in SQLAlchemy 2.0+)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `src/models.py` — Current models with Integer PKs, no user_id. Will be fully rewritten.
- `src/database.py` — Current dual-engine (async aiosqlite + sync sqlite). Will be simplified to async-only Postgres.
- `src/config.py` — DATABASE_URL is hardcoded SQLite path. Will read from env var. Add DEFAULT_DEV_USER_ID.
- `src/tools/food_lookup.py` — 3 tools (search_food, calculate_food_macros, create_food_item) + 1 helper (compute_food_macros). All need config passthrough + user_id.
- `src/services/daily_log_service.py` — 4 service functions + 2 @tool wrappers + 1 serializer. All need user_id param.
- `src/agents/nodes/commit_node.py` — Calls create_food_item, log_food_entry, query_food_logs. Needs config passthrough.
- `src/agents/nodes/stats_node.py` — Calls query_food_logs. Needs config passthrough.
- `src/agents/nodes/food_search_node.py` — Calls search_food. Needs config passthrough.
- `src/agents/nodes/confirmation_node.py` — Calls calculate_food_macros in _apply_edits. Needs config passthrough.
- `src/agents/nodes/calculate_macros_node.py` — Calls calculate_food_macros. Needs config passthrough.
- `src/agents/state.py` — TypedDicts with `int` types for id/food_id. Change to `str`.
- `src/schemas/selection_schema.py` — `food_id: Optional[int]`. Change to `Optional[str]`.
- `src/agents/nutritionist.py` — Imports AsyncSqliteSaver (unused but imported). Remove.
- `src/scripts/ingest_simple_db.py` — ETL script. Update SQLite path for UUID models.
- `tests/conftest.py` — async_test_db_session seeds FoodItem(id=1). Change to UUID. Add user_id.
- `tests/unit/test_daily_log_service.py` — All service tests. Add user_id, UUID types.
- `tests/unit/test_daily_log_model.py` — Model creation tests. Add user_id, UUID types.
- `tests/unit/test_commit_node.py` — Mock return values use int IDs. Change to UUID strings.
- `tests/unit/test_stats_node.py` — Mock return values use int IDs. Add config forwarding.
- `tests/unit/test_food_search_node.py` — Mock return values use int IDs. Add config forwarding.
- `tests/unit/test_calculate_macros_node.py` — Mock return values. Add config forwarding.
- `tests/unit/test_confirmation_node.py` — Mock return values. Add config forwarding.
- `tests/unit/test_agent_selection.py` — Uses int food_id in state. Change to UUID string.
- `tests/unit/test_response_node.py` — Minimal changes (no DB calls).
- `tests/unit/test_feedback_logic.py` — Uses int food_id. Change to UUID string.
- `tests/unit/test_feedback_integration.py` — Full flow mock. Update IDs.
- `tests/unit/test_multi_item_loop.py` — Uses int food_id. Change to UUID string.
- `tests/unit/test_state_consistency.py` — No changes needed (tests Literal types, not values).
- `tests/unit/test_input_parser.py` — No changes needed (no DB/ID involvement).
- `tests/graph_api/test_graph_flows.py` — Add config with user_id to all _run calls. Add isolation tests.
- `tests/graph_api/conftest.py` — No changes needed (server management only).
- `pyproject.toml` — Add asyncpg, move aiosqlite to dev, remove alembic.
- `langgraph.json` — No changes needed.
- `alembic/` — Delete entire directory.
- `alembic.ini` — Delete.

### New Files to Create

- `tests/unit/test_food_lookup.py` — Unit tests for food_lookup tools (user_id scoping, search isolation)

### Relevant Documentation

- [LangGraph Nodes — config: RunnableConfig](https://docs.langchain.com/oss/python/langgraph/graph-api)
  - Section: Node function signatures — `(state, config: RunnableConfig)`
  - Why: Pattern for how nodes receive and forward config
- [LangGraph get_config()](https://docs.langchain.com/langsmith/configurable-headers)
  - Section: `from langgraph.config import get_config`
  - Why: Alternative way for tools to access config (we use explicit passthrough instead)
- [SQLAlchemy Uuid type](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.Uuid)
  - Why: Cross-dialect UUID type — native uuid on Postgres, CHAR(32) on SQLite

### Patterns to Follow

**Config Passthrough (NEW pattern for this feature)**:
```python
# Node — accepts config, forwards to tool
async def some_node(state: AgentState, config: RunnableConfig) -> dict:
    result = await some_tool.ainvoke({"param": value}, config=config)
    return {... }

# Tool — extracts user_id from config
from src.config import DEFAULT_DEV_USER_ID

@tool
async def some_tool(param: str, config: RunnableConfig) -> dict:
    user_id = config["configurable"].get("user_id", DEFAULT_DEV_USER_ID)
    # use user_id in queries...
```

**Service Layer (existing pattern — add user_id param)**:
```python
# Service function — accepts session + user_id (DI/testability)
async def get_logs_by_date(session, user_id: str, target_date: date) -> list:
    stmt = select(DailyLog).where(DailyLog.user_id == user_id).where(...)

# @tool wrapper — creates own session, extracts user_id from config
@tool
async def query_food_logs(target_date: str, ..., config: RunnableConfig) -> list:
    user_id = config["configurable"].get("user_id", DEFAULT_DEV_USER_ID)
    async with get_async_db_session() as session:
        logs = await get_logs_by_date(session, user_id, ...)
```

**UUID Model (NEW pattern)**:
```python
import uuid as uuid_mod
from sqlalchemy import Uuid

class FoodItem(Base):
    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    user_id: Mapped[Optional[uuid_mod.UUID]] = mapped_column(Uuid, nullable=True, index=True)
```

**Tool Return Serialization (updated pattern)**:
```python
# Always str() UUIDs when returning dicts from tools
return {"id": str(food.id), "name": food.name, "source": food.source}
```

**Mock Pattern for Config (NEW for tests)**:
```python
from langchain_core.runnables import RunnableConfig

TEST_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TEST_CONFIG: RunnableConfig = {"configurable": {"user_id": TEST_USER_ID}}

# Node tests — pass config as second arg
result = await some_node(state, TEST_CONFIG)

# Verify config forwarded to tool mock
mock_tool.ainvoke.assert_called_once_with({"param": ...}, config=TEST_CONFIG)
```

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (Config, Models, DB Engine, Dependencies)

Set up the base infrastructure: new dependencies, updated config, models with UUID + user_id, database engine pointing to Supabase Postgres. Remove Alembic.

### Phase 2: Supabase Migration

Apply the SQL migration to add user_id columns and indexes to the remote Supabase tables.

### Phase 3: Tools & Services

Update all tools and service functions to accept/extract user_id and filter queries accordingly.

### Phase 4: Nodes

Update all nodes that call tools to accept `config: RunnableConfig` and forward it.

### Phase 5: State, Schemas & Graph

Update TypedDicts and Pydantic schemas for UUID string types. Clean up graph definition.

### Phase 6: ETL Script

Update the ETL script's SQLite path for UUID-based models.

### Phase 7: Tests — Unit

Update all existing unit tests for UUID + user_id. Add new isolation tests.

### Phase 8: Tests — Graph API (E2E)

Update existing E2E tests to pass user_id in config. Add new data isolation tests.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

---

### Task 1: UPDATE `pyproject.toml` — Dependencies

- **IMPLEMENT**: Add `asyncpg` to runtime dependencies. Move `aiosqlite` from runtime to dev group (still needed for unit test in-memory SQLite). Remove `alembic` from dev group. Remove `langgraph-checkpoint-sqlite` from runtime deps (server manages its own checkpointer).
- **PATTERN**: Existing dependency layout in pyproject.toml
- **CHANGES**:
  ```
  # Add to [project] dependencies:
  "asyncpg>=0.30.0",

  # Remove from [project] dependencies:
  "aiosqlite>=0.19.0",        → move to [dependency-groups] dev
  "langgraph-checkpoint-sqlite>=3.0.3",  → remove entirely

  # Add to [dependency-groups] dev:
  "aiosqlite>=0.19.0",

  # Remove from [dependency-groups] dev:
  "alembic>=1.18.4",
  ```
- **VALIDATE**: `uv sync` (installs asyncpg, keeps aiosqlite in dev)

---

### Task 2: UPDATE `src/config.py` — Database URL + Dev User ID

- **IMPLEMENT**:
  - Add `DEFAULT_DEV_USER_ID = "00000000-0000-0000-0000-000000000001"` constant
  - Change `DATABASE_URL` to read from env var `SUPABASE_DB_URL`, converting to asyncpg dialect
  - Keep SQLite fallback for when env var is not set (backward compat)
  - Keep `DB_PATH` for ETL script reference
- **PATTERN**: Existing config.py structure
- **CHANGES**:
  ```python
  # Add after DB_PATH line:
  DEFAULT_DEV_USER_ID = "00000000-0000-0000-0000-000000000001"

  # Replace DATABASE_URL line with:
  _supabase_url = os.getenv("SUPABASE_DB_URL")
  if _supabase_url:
      DATABASE_URL = _supabase_url.replace("postgresql://", "postgresql+asyncpg://", 1)
  else:
      DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
  ```
- **GOTCHA**: The `.replace()` must use count=1 to avoid double-replacing if URL already has `+asyncpg`
- **VALIDATE**: `uv run python -c "from src.config import DATABASE_URL, DEFAULT_DEV_USER_ID; print(DATABASE_URL[:30]); print(DEFAULT_DEV_USER_ID)"`

---

### Task 3: UPDATE `src/database.py` — Async-Only Engine

- **IMPLEMENT**:
  - Remove the entire sync engine section (engine, SessionLocal, get_db_session, SYNC_DATABASE_URL)
  - Keep only the async engine (create_async_engine, AsyncSessionLocal, get_async_db_session)
  - Remove `check_same_thread` (SQLite-specific, not needed for Postgres)
- **PATTERN**: Existing database.py — keep the async section, delete sync section
- **FULL NEW CONTENTS**:
  ```python
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

  from src.config import DATABASE_URL

  # --- Async infrastructure (service layer + graph nodes) ---
  # expire_on_commit=False is REQUIRED: prevents MissingGreenlet errors when
  # accessing ORM attributes after commit() in async context.
  async_engine = create_async_engine(DATABASE_URL)
  AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


  def get_async_db_session() -> AsyncSession:
      """Returns a new async database session (use as async context manager)."""
      return AsyncSessionLocal()
  ```
- **GOTCHA**: The sync imports (create_engine, Session, sessionmaker) must be removed too. ETL script creates its own engine.
- **VALIDATE**: `uv run python -c "from src.database import get_async_db_session; print('OK')"`

---

### Task 4: UPDATE `src/models.py` — UUID PKs + user_id Columns

- **IMPLEMENT**:
  - Import `uuid as uuid_mod` and `from sqlalchemy import Uuid`
  - Change `FoodItem.id` from `Mapped[int]` / `Integer` to `Mapped[uuid_mod.UUID]` / `Uuid` with `default=uuid_mod.uuid4`
  - Add `FoodItem.user_id`: `Mapped[Optional[uuid_mod.UUID]]` / `Uuid`, nullable=True, index=True
  - Change `DailyLog.id` from `Mapped[int]` / `Integer` to `Mapped[uuid_mod.UUID]` / `Uuid` with `default=uuid_mod.uuid4`
  - Change `DailyLog.food_id` from `Mapped[Optional[int]]` / `Integer` to `Mapped[Optional[uuid_mod.UUID]]` / `Uuid`
  - Add `DailyLog.user_id`: `Mapped[uuid_mod.UUID]` / `Uuid`, nullable=False, index=True (no default — always provided)
  - Update the ForeignKey reference: `ForeignKey("food_items.id")` stays the same (FK target column name doesn't change)
- **IMPORTS**:
  ```python
  import uuid as uuid_mod
  from sqlalchemy import Uuid, String, Float, DateTime, ForeignKey
  # Remove Integer import
  ```
- **GOTCHA**: `Uuid` type on SQLite stores as CHAR(32) — Python `uuid.UUID` objects are used in both dialects. Use `default=uuid_mod.uuid4` (no parentheses — pass the function, not the result). On Supabase, `gen_random_uuid()` server default generates the UUID if none is provided, but our Python default ensures it works on SQLite tests too.
- **GOTCHA**: Remove `Integer` from imports — no longer used.
- **VALIDATE**: `uv run python -c "from src.models import FoodItem, DailyLog; print('OK')"`

---

### Task 5: REMOVE Alembic — Delete Directory and Config

- **IMPLEMENT**:
  - Delete `alembic/` directory entirely (env.py, script.py.mako, versions/)
  - Delete `alembic.ini`
- **GOTCHA**: Make sure to `git rm` (or just delete) — these files are tracked.
- **VALIDATE**: Verify directory is gone: `ls alembic/ 2>/dev/null && echo "STILL EXISTS" || echo "REMOVED OK"`

---

### Task 6: APPLY Supabase Migration — Add user_id Columns

- **IMPLEMENT**: Apply migration via `mcp__supabase__apply_migration` to add user_id columns to both tables on the remote Supabase project.
- **SQL**:
  ```sql
  -- Add user_id to daily_logs (NOT NULL, no existing rows so safe)
  ALTER TABLE daily_logs
    ADD COLUMN user_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';

  -- Add user_id to food_items (nullable — NULL for shared database foods)
  ALTER TABLE food_items
    ADD COLUMN user_id uuid;

  -- Indexes for query performance
  CREATE INDEX idx_daily_logs_user_id ON daily_logs(user_id);
  CREATE INDEX idx_food_items_user_id ON food_items(user_id);
  ```
- **GOTCHA**: daily_logs has 0 rows in Supabase so the NOT NULL + DEFAULT is safe. food_items has 335 rows — they stay with user_id=NULL (shared database foods).
- **VALIDATE**: `mcp__supabase__list_tables` with verbose=true — verify user_id columns appear on both tables.

---

### Task 7: UPDATE `src/tools/food_lookup.py` — Config + user_id + UUID Types

- **IMPLEMENT**:
  - Add `RunnableConfig` import from `langchain_core.runnables`
  - Add `from src.config import DEFAULT_DEV_USER_ID` import
  - Add `import uuid as uuid_mod` import
  - **`search_food`**: Add `config: RunnableConfig` parameter. Extract `user_id`. For estimated foods query, add `.where(FoodItem.user_id == uuid_mod.UUID(user_id))`. Database foods query stays unchanged (shared, no user filter). Serialize IDs with `str()`.
  - **`calculate_food_macros`**: Change `food_id` param type from `int` to `str`. Parse to UUID: `await session.get(FoodItem, uuid_mod.UUID(food_id))`. Serialize `food.id` in return dict.
  - **`create_food_item`**: Add `config: RunnableConfig` parameter. Extract `user_id`. Set `user_id=uuid_mod.UUID(user_id)` on the FoodItem. Serialize `food_item.id` in return dict.
  - **`compute_food_macros`**: No change (pure calculation, no DB).
- **PATTERN**: Existing tool structure — `async with get_async_db_session() as session`
- **KEY CHANGES**:
  ```python
  @tool
  async def search_food(query: str, config: RunnableConfig) -> list[dict]:
      user_id = config["configurable"].get("user_id", DEFAULT_DEV_USER_ID)
      async with get_async_db_session() as session:
          # First: search shared database foods (no user filter)
          stmt = (
              select(FoodItem.id, FoodItem.name)
              .where(FoodItem.name.ilike(f"%{query}%"), FoodItem.source == "database")
              .limit(10)
          )
          results = (await session.execute(stmt)).all()
          if results:
              return [{"id": str(r.id), "name": r.name, "source": "database"} for r in results]

          # Fallback: search THIS USER's estimated foods
          stmt = (
              select(FoodItem.id, FoodItem.name)
              .where(FoodItem.name.ilike(f"%{query}%"), FoodItem.source == "estimated")
              .where(FoodItem.user_id == uuid_mod.UUID(user_id))
              .limit(10)
          )
          results = (await session.execute(stmt)).all()
          return [{"id": str(r.id), "name": r.name, "source": "estimated"} for r in results]
  ```
- **GOTCHA**: `config: RunnableConfig` must be the LAST parameter in the `@tool` function (LangChain injects it). Don't include it in the tool's docstring schema.
- **VALIDATE**: `uv run python -c "from src.tools.food_lookup import search_food, calculate_food_macros, create_food_item; print('OK')"`

---

### Task 8: UPDATE `src/services/daily_log_service.py` — user_id in All Functions + UUID Types

- **IMPLEMENT**:
  - Add `import uuid as uuid_mod` and `from langchain_core.runnables import RunnableConfig`
  - Add `from src.config import DEFAULT_DEV_USER_ID`
  - **`create_log_entry`**: Add `user_id: str` parameter. Set `DailyLog(user_id=uuid_mod.UUID(user_id), ...)`. Change `food_id` param type from `Optional[int]` to `Optional[str]`. Convert: `food_id=uuid_mod.UUID(food_id) if food_id else None`.
  - **`get_daily_totals`**: Add `user_id: str` parameter. Add `.where(DailyLog.user_id == uuid_mod.UUID(user_id))`.
  - **`get_logs_by_date`**: Add `user_id: str` parameter. Add `.where(DailyLog.user_id == uuid_mod.UUID(user_id))`.
  - **`get_logs_by_date_range`**: Add `user_id: str` parameter. Add `.where(DailyLog.user_id == uuid_mod.UUID(user_id))`.
  - **`_serialize_log`**: Change `"id"` and `"food_id"` to `str()`: `"id": str(log.id)`, `"food_id": str(log.food_id) if log.food_id else None`.
  - **`log_food_entry` @tool**: Add `config: RunnableConfig` parameter. Extract `user_id`. Pass to `create_log_entry`. Change `food_id` param type from `Optional[int]` to `Optional[str]`.
  - **`query_food_logs` @tool**: Add `config: RunnableConfig` parameter. Extract `user_id`. Pass to service functions.
- **GOTCHA**: Service functions accept `user_id: str` (not UUID object) — they do the conversion internally. This keeps the interface simple for tests.
- **VALIDATE**: `uv run python -c "from src.services.daily_log_service import create_log_entry, log_food_entry; print('OK')"`

---

### Task 9: UPDATE `src/agents/state.py` — UUID String Types

- **IMPLEMENT**:
  - In `SearchResult`: change `id: int` → `id: str`
  - In `QueriedLog`: change `id: int` → `id: str`, `food_id: int` → `food_id: Optional[str]`
  - In `MacroResult`: change `food_id: Optional[int]` → `food_id: Optional[str]`
  - In `AgentState`: change `selected_food_id: Optional[int]` → `selected_food_id: Optional[str]`
- **GOTCHA**: Do NOT change `PendingFoodItem` — it has no ID fields. Do NOT change `ProcessingResult` — it inherits from `PendingFoodItem` and has no ID.
- **VALIDATE**: `uv run python -c "from src.agents.state import AgentState, MacroResult, SearchResult; print('OK')"`

---

### Task 10: UPDATE `src/schemas/selection_schema.py` — UUID food_id

- **IMPLEMENT**: Change `food_id: Optional[int]` → `food_id: Optional[str]` in `FoodSelectionResult`.
- **VALIDATE**: `uv run python -c "from src.schemas.selection_schema import FoodSelectionResult; print('OK')"`

---

### Task 11: UPDATE `src/agents/nodes/food_search_node.py` — Config Passthrough

- **IMPLEMENT**:
  - Add `from langchain_core.runnables import RunnableConfig` import
  - Add `config: RunnableConfig` as second parameter to `food_search_node`
  - Pass config to tool: `await search_food.ainvoke({"query": food_name}, config=config)`
- **PATTERN**: Existing node signature `async def food_search_node(state: AgentState) -> dict` → `async def food_search_node(state: AgentState, config: RunnableConfig) -> dict`
- **VALIDATE**: `uv run python -c "from src.agents.nodes.food_search_node import food_search_node; print('OK')"`

---

### Task 12: UPDATE `src/agents/nodes/calculate_macros_node.py` — Config Passthrough

- **IMPLEMENT**:
  - Add `from langchain_core.runnables import RunnableConfig` import
  - Add `config: RunnableConfig` as second parameter to `calculate_macros_node`
  - Pass config to tool: `await calculate_food_macros.ainvoke({...}, config=config)`
- **GOTCHA**: The `_estimate_macros` helper does NOT need config — it's pure LLM, no DB.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.calculate_macros_node import calculate_macros_node; print('OK')"`

---

### Task 13: UPDATE `src/agents/nodes/confirmation_node.py` — Config Passthrough

- **IMPLEMENT**:
  - Add `from langchain_core.runnables import RunnableConfig` import
  - Add `config: RunnableConfig` as second parameter to `confirmation_node`
  - Pass config to `_apply_edits`: `batch = await _apply_edits(batch, decision.edits or [], config)`
  - Update `_apply_edits` signature: add `config: RunnableConfig` parameter
  - In `_apply_edits`, pass config to tool: `await calculate_food_macros.ainvoke({...}, config=config)`
  - Change `item["food_id"]` type check: `is not None` stays the same (works for both int and str)
- **GOTCHA**: `confirmation_node` returns `Command` — the signature is `async def confirmation_node(state: AgentState, config: RunnableConfig) -> Command[...]`. LangGraph supports this.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.confirmation_node import confirmation_node; print('OK')"`

---

### Task 14: UPDATE `src/agents/nodes/commit_node.py` — Config Passthrough

- **IMPLEMENT**:
  - Add `from langchain_core.runnables import RunnableConfig` import
  - Add `config: RunnableConfig` as second parameter to `commit_node`
  - Pass config to ALL tool calls:
    - `await create_food_item.ainvoke({...}, config=config)`
    - `await log_food_entry.ainvoke({...}, config=config)`
    - `await query_food_logs.ainvoke({...}, config=config)`
- **GOTCHA**: The `food_id` variable in commit_node comes from `item.get("food_id")` (state MacroResult) or from `created["id"]` (create_food_item return). Both are now strings.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.commit_node import commit_node; print('OK')"`

---

### Task 15: UPDATE `src/agents/nodes/stats_node.py` — Config Passthrough

- **IMPLEMENT**:
  - Add `from langchain_core.runnables import RunnableConfig` import
  - Add `config: RunnableConfig` as second parameter to `stats_lookup_node`
  - Pass config to tool: `await query_food_logs.ainvoke({...}, config=config)`
- **VALIDATE**: `uv run python -c "from src.agents.nodes.stats_node import stats_lookup_node; print('OK')"`

---

### Task 16: UPDATE `src/agents/nutritionist.py` — Remove SQLite Checkpointer Import

- **IMPLEMENT**:
  - Remove: `from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver`
  - The server injects its own checkpointer via `kwargs.get("checkpointer")` — no change to that logic.
- **VALIDATE**: `uv run python -c "from src.agents.nutritionist import define_graph; print('OK')"`

---

### Task 17: UPDATE `src/scripts/ingest_simple_db.py` — UUID-Compatible SQLite Path

- **IMPLEMENT**:
  - Update `ingest_sqlite()` to work with UUID-based models:
    - Add `import uuid as uuid_mod` at top
    - FoodItem creation needs explicit `id=uuid_mod.uuid4()` since SQLite has no `gen_random_uuid()`
    - Actually: the model already has `default=uuid_mod.uuid4` from Task 4, so `FoodItem(**item)` will auto-generate UUIDs. No explicit id needed.
  - Update `ingest_sqlite()` engine to use the sync SQLite URL directly (can't import from database.py anymore since it's async-only):
    ```python
    def ingest_sqlite(items: list[dict]):
        from sqlalchemy import create_engine
        from src.config import DB_PATH
        from src.models import FoodItem

        engine = create_engine(f"sqlite:///{DB_PATH}")
        # ... rest same
    ```
  - Remove `from src.database import get_db_session` import in `ingest_sqlite`
  - The Postgres path (`ingest_postgres`) stays as raw SQL — no ORM changes needed there.
- **GOTCHA**: The `ingest_sqlite` function currently imports `get_db_session` which will no longer exist. It must create its own sync engine.
- **VALIDATE**: `uv run python src/scripts/ingest_simple_db.py --target sqlite` (verify no import errors)

---

### Task 18: UPDATE `tests/conftest.py` — UUID Fixtures + user_id + Config

- **IMPLEMENT**:
  - Add `import uuid as uuid_mod` and `from langchain_core.runnables import RunnableConfig`
  - Add constants:
    ```python
    TEST_USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    TEST_USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    TEST_CONFIG_A: RunnableConfig = {"configurable": {"user_id": TEST_USER_A}}
    TEST_CONFIG_B: RunnableConfig = {"configurable": {"user_id": TEST_USER_B}}
    ```
  - Update `basic_state`: change `"selected_food_id": None` — no type change needed (already None)
  - Update `async_test_db_session`: change seed FoodItem to use UUID id and add user_id=None (shared database food):
    ```python
    sample_food = FoodItem(
        id=uuid_mod.UUID("11111111-1111-1111-1111-111111111111"),
        name="Test Chicken",
        calories=165.0, protein=31.0, fat=3.6, carbs=0.0,
        source="database",
        user_id=None,  # shared database food
    )
    ```
  - Update mock fixture return values: tool mocks should remain generic (tests set specific return values). No changes to mock fixtures themselves.
- **VALIDATE**: `uv run pytest tests/unit/test_state_consistency.py -v` (quick sanity check)

---

### Task 19: UPDATE `tests/unit/test_daily_log_service.py` — user_id in All Tests

- **IMPLEMENT**:
  - Import `TEST_USER_A, TEST_USER_B` from conftest (or define locally)
  - Add `import uuid as uuid_mod`
  - Update ALL `create_log_entry` calls to include `user_id=TEST_USER_A`
  - Update ALL `get_logs_by_date` calls to include `user_id=TEST_USER_A`
  - Update ALL `get_daily_totals` calls to include `user_id=TEST_USER_A`
  - Update ALL `get_logs_by_date_range` calls to include `user_id=TEST_USER_A`
  - Change `food_id=1` to `food_id="11111111-1111-1111-1111-111111111111"` (matches seed)
  - Add NEW isolation tests (see Testing Strategy section)
- **GOTCHA**: `food_id` param is now a string. The seed FoodItem has id `11111111-1111-1111-1111-111111111111`.
- **VALIDATE**: `uv run pytest tests/unit/test_daily_log_service.py -v`

---

### Task 20: UPDATE `tests/unit/test_daily_log_model.py` — UUID + user_id

- **IMPLEMENT**:
  - Add `import uuid as uuid_mod`
  - Update all DailyLog creation to include `user_id=uuid_mod.UUID(TEST_USER_A)`
  - Update all FoodItem creation to use UUID id
  - Change `food_id=1` references to `food_id=uuid_mod.UUID("11111111-1111-1111-1111-111111111111")`
  - Update assertions that check `log.id` type — now UUID, not int
- **VALIDATE**: `uv run pytest tests/unit/test_daily_log_model.py -v`

---

### Task 21: UPDATE `tests/unit/test_commit_node.py` — UUID IDs + Config Forwarding

- **IMPLEMENT**:
  - Import `TEST_CONFIG_A, TEST_USER_A` from conftest
  - Update ALL `commit_node(state)` calls to `commit_node(state, TEST_CONFIG_A)`
  - Update mock return values:
    - `mock_log_food_entry.ainvoke.return_value = {"id": "log-uuid-1", "status": "logged"}`
    - `mock_create_food_item.ainvoke.return_value = {"id": "food-uuid-99", "name": "pizza"}`
  - Update state values: `"food_id": "food-uuid-1"` instead of `"food_id": 1`
  - Add assertions verifying `config=TEST_CONFIG_A` is passed to tool ainvoke calls
- **VALIDATE**: `uv run pytest tests/unit/test_commit_node.py -v`

---

### Task 22: UPDATE `tests/unit/test_stats_node.py` — Config Forwarding

- **IMPLEMENT**:
  - Import `TEST_CONFIG_A` from conftest
  - Update ALL `stats_lookup_node(state)` calls to `stats_lookup_node(state, TEST_CONFIG_A)`
  - Update mock return values to use UUID string IDs
  - Add assertion that `config=TEST_CONFIG_A` is passed to tool ainvoke
- **VALIDATE**: `uv run pytest tests/unit/test_stats_node.py -v`

---

### Task 23: UPDATE `tests/unit/test_food_search_node.py` — Config Forwarding

- **IMPLEMENT**:
  - Import `TEST_CONFIG_A` from conftest
  - Update ALL `food_search_node(state)` calls to `food_search_node(state, TEST_CONFIG_A)`
  - Update mock return values: `{"id": "food-uuid-1", "name": "Chicken", "source": "database"}`
  - Add assertion that `config=TEST_CONFIG_A` is passed to tool ainvoke
- **VALIDATE**: `uv run pytest tests/unit/test_food_search_node.py -v`

---

### Task 24: UPDATE `tests/unit/test_calculate_macros_node.py` — Config Forwarding

- **IMPLEMENT**:
  - Import `TEST_CONFIG_A` from conftest
  - Update ALL `calculate_macros_node(state)` calls to `calculate_macros_node(state, TEST_CONFIG_A)`
  - Update `selected_food_id` in state from int to UUID string: `"selected_food_id": "food-uuid-1"`
  - Update mock return values to use UUID strings
  - Update assertions for food_id type
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_macros_node.py -v`

---

### Task 25: UPDATE `tests/unit/test_confirmation_node.py` — Config Forwarding

- **IMPLEMENT**:
  - Import `TEST_CONFIG_A` from conftest
  - Update ALL `confirmation_node(state)` calls to `confirmation_node(state, TEST_CONFIG_A)`
  - Update `food_id` values in test batch items from int to UUID strings
  - Update `_apply_edits` mock calls if needed (config forwarding)
  - For the edit test that calls `calculate_food_macros`: verify config is forwarded
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v`

---

### Task 26: UPDATE `tests/unit/test_agent_selection.py` — UUID food_id

- **IMPLEMENT**:
  - Update search_results in state: `{"id": "food-uuid-165", "name": ...}` instead of `{"id": 165, ...}`
  - Update assertions: `assert result["selected_food_id"] == "food-uuid-165"` etc.
  - Update mock LLM FoodSelectionResult: `food_id="food-uuid-165"` instead of `food_id=165`
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py -v`

---

### Task 27: UPDATE Remaining Unit Tests — UUID IDs

- **IMPLEMENT**: For each file, update int IDs to UUID strings:
  - `test_feedback_logic.py`: Update food_id in MacroResult dicts, search_results
  - `test_feedback_integration.py`: Update all food_id references in the full flow mock
  - `test_multi_item_loop.py`: Update food_id in MacroResult dicts
  - `test_response_node.py`: Minimal — update any food_id in state if present (check if used)
  - `test_input_parser.py`: No changes needed (no IDs involved)
  - `test_state_consistency.py`: No changes needed (tests Literal types)
- **VALIDATE**: `uv run pytest tests/unit/ -v`

---

### Task 28: CREATE `tests/unit/test_food_lookup.py` — New Isolation Tests

- **IMPLEMENT**: New test file for food_lookup tool functions with user_id scoping. Uses `async_test_db_session` fixture (in-memory SQLite with real DB).
- **PATTERN**: Follow AAA docstring pattern from test_daily_log_service.py
- **TESTS**:
  ```python
  class TestSearchFoodSharedAccess:
      async def test_shared_db_food_visible_to_all_users(self, async_test_db_session):
          """
          arrange: Seed a source="database" food with user_id=None.
          act:     search_food with user_a config, then user_b config.
          assert:  Both users find the same shared food.
          """

  class TestSearchFoodEstimatedIsolation:
      async def test_estimated_food_scoped_to_owner(self, async_test_db_session):
          """
          arrange: Create source="estimated" food with user_id=user_a.
          act:     search_food with user_b config.
          assert:  User B does NOT find user A's estimated food.
          """

      async def test_estimated_food_visible_to_owner(self, async_test_db_session):
          """
          arrange: Create source="estimated" food with user_id=user_a.
          act:     search_food with user_a config.
          assert:  User A finds their own estimated food.
          """

  class TestCreateFoodItemSetsUserId:
      async def test_created_item_has_user_id(self, async_test_db_session):
          """
          arrange: user_a config.
          act:     create_food_item with user_a config.
          assert:  Created FoodItem.user_id matches user_a.
          """
  ```
- **GOTCHA**: These tests need to call the actual tool functions against the in-memory DB. You'll need to mock `get_async_db_session` to return the test session, OR restructure to call the underlying query logic directly. Recommended: patch `src.tools.food_lookup.get_async_db_session` to return a context manager yielding the test session.
- **VALIDATE**: `uv run pytest tests/unit/test_food_lookup.py -v`

---

### Task 29: ADD Isolation Tests to `tests/unit/test_daily_log_service.py`

- **IMPLEMENT**: Add new test class with data isolation tests:
  ```python
  class TestUserDataIsolation:
      async def test_get_logs_by_date_filters_by_user(self, async_test_db_session):
          """
          arrange: User A logs chicken, User B logs rice, same date.
          act:     query logs for User A.
          assert:  Only chicken returned, not rice.
          """

      async def test_get_daily_totals_filters_by_user(self, async_test_db_session):
          """
          arrange: User A logs 200 cal, User B logs 500 cal, same date.
          act:     get_daily_totals for User A.
          assert:  Total is 200, not 700.
          """

      async def test_get_logs_by_date_range_filters_by_user(self, async_test_db_session):
          """
          arrange: User A and B both log on 3 consecutive days.
          act:     get_logs_by_date_range for User A.
          assert:  Only User A's logs returned.
          """

      async def test_create_log_entry_stores_user_id(self, async_test_db_session):
          """
          arrange: Create log with user_id=user_a.
          act:     Query the row directly.
          assert:  row.user_id matches user_a.
          """
  ```
- **VALIDATE**: `uv run pytest tests/unit/test_daily_log_service.py -v`

---

### Task 30: UPDATE `tests/graph_api/test_graph_flows.py` — Pass user_id Config

- **IMPLEMENT**:
  - Add `DEV_USER_CONFIG = {"configurable": {"user_id": "00000000-0000-0000-0000-000000000001"}}` constant
  - Update `_run` helper to accept optional `config` kwarg and merge it:
    ```python
    async def _run(lg_client, thread, *, input=None, command=None, config=None, test_name="unknown"):
        kwargs = {"raise_error": False}
        if input is not None:
            kwargs["input"] = input
        if command is not None:
            kwargs["command"] = command
        if config is not None:
            kwargs["config"] = config
        # ... rest same
    ```
  - Update ALL `_run` calls to pass `config=DEV_USER_CONFIG`
  - Add NEW `TestUserDataIsolation` class with E2E isolation tests:
    ```python
    class TestUserDataIsolation:
        """Verify user A's data is invisible to user B through the full graph."""

        USER_A_CONFIG = {"configurable": {"user_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}}
        USER_B_CONFIG = {"configurable": {"user_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"}}

        async def test_user_a_log_not_visible_to_user_b(self, lg_client, thread):
            """
            arrange: User A logs 200g chicken (confirm via HITL).
            act:     User B asks "what did I eat today?" on a new thread.
            assert:  User B's response indicates no food logged.
            """
    ```
- **GOTCHA**: Each user needs a separate thread. The `thread` fixture creates one thread — for isolation tests, create additional threads manually.
- **GOTCHA**: E2E isolation tests require the server to be connected to Supabase (env var set). If SUPABASE_DB_URL is not set, the server falls back to SQLite and isolation tests may not reflect production behavior. Consider skipping these tests if not connected to Postgres.
- **VALIDATE**: `uv run pytest tests/graph_api/ -v -s`

---

## TESTING STRATEGY

### Unit Tests — Service Layer (Highest Priority)

Tests data isolation at the query level using in-memory SQLite.

**New tests**: 4 isolation tests in `TestUserDataIsolation` class
**Updated tests**: All existing tests get `user_id` parameter + UUID IDs

### Unit Tests — Tool Layer

Tests user_id scoping in `search_food` and `create_food_item`.

**New file**: `test_food_lookup.py` with 4 tests
**Approach**: Patch `get_async_db_session` to use test session

### Unit Tests — Node Layer

Tests config passthrough from nodes to tools.

**Updated tests**: All node test files get `config` parameter
**Key assertion**: `mock_tool.ainvoke.assert_called_with(..., config=TEST_CONFIG_A)`

### Graph-API Tests — E2E Isolation

Tests data isolation through the full graph via HTTP.

**New class**: `TestUserDataIsolation` with 1-2 E2E tests
**Pattern**: Two users, two threads, different configs, verify isolation

### Edge Cases

- Shared food (source="database", user_id=NULL) visible to all users
- Estimated food (source="estimated", user_id=X) only visible to user X
- User B cannot see user A's daily logs
- User B's stats don't include user A's entries
- Missing user_id in config falls back to DEFAULT_DEV_USER_ID
- food_id=None (estimated items pre-commit) handled correctly as UUID

---

## VALIDATION COMMANDS

### Level 1: Import Checks (after each file change)

```bash
uv run python -c "from src.models import FoodItem, DailyLog; print('models OK')"
uv run python -c "from src.database import get_async_db_session; print('database OK')"
uv run python -c "from src.config import DATABASE_URL, DEFAULT_DEV_USER_ID; print('config OK')"
uv run python -c "from src.tools.food_lookup import search_food; print('tools OK')"
uv run python -c "from src.services.daily_log_service import log_food_entry; print('services OK')"
uv run python -c "from src.agents.nutritionist import define_graph; print('graph OK')"
```

### Level 2: Unit Tests

```bash
# Run all unit tests
uv run pytest tests/unit/ -v

# Run specific test files during development
uv run pytest tests/unit/test_daily_log_service.py -v
uv run pytest tests/unit/test_food_lookup.py -v
uv run pytest tests/unit/test_commit_node.py -v

# Last-failed retry loop
uv run pytest --lf -v
```

### Level 3: Graph-API Tests (E2E)

```bash
# Full E2E suite (auto-starts server)
uv run pytest tests/graph_api/ -v -s
```

### Level 4: Supabase Verification

```bash
# Via MCP: verify user_id columns exist
# mcp__supabase__list_tables(project_id, schemas=["public"], verbose=true)

# Via MCP: verify data after E2E test
# mcp__supabase__execute_sql("SELECT COUNT(*) FROM daily_logs WHERE user_id IS NOT NULL")
```

---

## ACCEPTANCE CRITERIA

- [ ] `asyncpg` is a runtime dependency; `aiosqlite` is dev-only
- [ ] `alembic/` directory and `alembic.ini` are deleted
- [ ] `src/models.py` uses `Uuid` type for all PKs and FKs
- [ ] `FoodItem.user_id` (nullable) and `DailyLog.user_id` (NOT NULL) columns exist in models
- [ ] Supabase tables have `user_id` columns with indexes
- [ ] `DATABASE_URL` reads from `SUPABASE_DB_URL` env var with SQLite fallback
- [ ] `DEFAULT_DEV_USER_ID` constant exists in config
- [ ] All tools extract `user_id` from `config["configurable"]`
- [ ] All nodes accept `config: RunnableConfig` and forward to tools
- [ ] `search_food` filters estimated foods by user_id (shared DB foods unfiltered)
- [ ] `create_food_item` sets user_id on new items
- [ ] All daily_log queries filter by user_id
- [ ] `log_food_entry` sets user_id on new entries
- [ ] All unit tests pass with UUID IDs and user_id params
- [ ] New isolation tests verify User A's data is invisible to User B
- [ ] Graph-API E2E tests pass with user_id in config
- [ ] ETL script works for both targets (sqlite, supabase)

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order (1-30)
- [ ] Each task validation passed immediately
- [ ] `uv run pytest tests/unit/ -v` — all pass
- [ ] `uv run pytest tests/graph_api/ -v -s` — all pass
- [ ] No import errors across the codebase
- [ ] Supabase tables verified via MCP
- [ ] Code reviewed for quality and maintainability

---

## EXECUTION RULES

### Stop-and-Ask Policy

**CRITICAL**: During execution, if you encounter ANY of the following situations, STOP immediately and ask the developer before proceeding. Do NOT assume or guess.

1. **Ambiguous behavior**: If a query, function, or tool could work two different ways and the plan doesn't specify which — STOP and ask.
2. **Missing context**: If you need to make a design choice not covered by this plan (e.g., error message wording, column ordering, default values not specified) — STOP and ask.
3. **Unexpected codebase state**: If a file doesn't match what the plan describes (e.g., extra functions, renamed variables, different imports) — STOP and explain what you found.
4. **Test failures with unclear cause**: If a test fails and the fix isn't obvious from the plan — STOP and share the error. Don't try multiple speculative fixes.
5. **Dependency issues**: If `asyncpg` won't install, or a version conflict arises — STOP and present options (e.g., asyncpg vs psycopg).
6. **Security decisions**: If you need to decide between stricter vs. more permissive behavior (e.g., should missing user_id raise an error or fallback?) — STOP and ask.
7. **Schema mismatches**: If the Supabase table schema doesn't match what this plan expects — STOP and show the difference.
8. **New files or patterns**: If you think a new helper, utility, or abstraction is needed that the plan doesn't mention — STOP and propose it first.

**Rule of thumb**: If you're about to type "I'll assume..." — don't. Ask instead.

---

## REQUIRED TOOLS & RESOURCES

### MCP Servers

| MCP Server | Tools Needed | When |
|---|---|---|
| `supabase` | `apply_migration` | Task 6: Add user_id columns to Supabase tables |
| `supabase` | `list_tables` (verbose) | Task 6: Verify migration applied correctly |
| `supabase` | `execute_sql` | Debugging: inspect data, verify indexes, drop DEFAULT |
| `docs-langchain` | `SearchDocsByLangChain` | If unsure about RunnableConfig, tool signatures, or SDK patterns |

### Skills

| Skill | When to Use |
|---|---|
| `test-engineering` | Before writing ANY test (Tasks 18-30). Provides mock boundaries, AAA docstring format, fixture patterns |
| `langchain-architecture` | If unsure about LangGraph node signatures, state management, or config passthrough patterns |
| `validation` | After all tasks complete — run comprehensive validation before committing |
| `commit` | When the developer asks to commit the changes |

### Key Commands

| Command | Purpose |
|---|---|
| `uv sync` | After dependency changes (Task 1) |
| `uv run pytest tests/unit/ -v` | After each test file update |
| `uv run pytest tests/graph_api/ -v -s` | After all implementation complete (requires running server) |
| `uv run python -c "from src.<module> import <name>; print('OK')"` | Quick import sanity check after each source file change |

---

## NOTES

### Key Design Decisions

1. **`sqlalchemy.Uuid` type** (not String): Required for asyncpg compatibility. Supabase tables have native `uuid` columns — `String` would cause type mismatch errors. `Uuid` maps correctly on both Postgres and SQLite.

2. **Config passthrough** (not InjectedToolArg): Nodes accept `config: RunnableConfig`, forward to `tool.ainvoke(params, config=config)`. Tools extract `user_id` from `config["configurable"]`. Chosen because our tools are called by nodes (not by LLM), so InjectedToolArg's "hidden from LLM schema" benefit doesn't apply.

3. **Remove Alembic entirely**: Tests use `Base.metadata.create_all()` (no Alembic). Production uses Supabase MCP migrations. No scenario where Alembic is needed. Easy to recreate if ever needed.

4. **Unit tests stay on in-memory SQLite**: Fast, deterministic, no external dependencies. Models with `Uuid` type work on both dialects. Graph-API tests validate the real Postgres path.

5. **DEFAULT_DEV_USER_ID fallback**: Pre-auth, user_id comes from config with a hardcoded fallback. After Step 4 (auth), it comes from JWT automatically. Graph code won't change — only the source of user_id changes.

6. **Service functions accept `user_id: str`** (not UUID object): Keeps the interface simple. Functions convert to `uuid.UUID()` internally for SQLAlchemy queries. This means tests pass plain strings.

### Risk: Breaking asyncpg on Windows

asyncpg has had historical issues on Windows. If `uv add asyncpg` fails or the package doesn't install, try `uv add asyncpg --no-binary asyncpg` or check if a newer version fixes it. Fallback: use `psycopg[binary]` with `postgresql+psycopg://` dialect instead.

### Risk: Supabase Connection Pooling

The `SUPABASE_DB_URL` uses the session pooler (port 5432). For asyncpg, this is fine. If connection limits become an issue, switch to the transaction pooler (port 6543) — but this requires `prepared_statement_cache_size=0` on the engine: `create_async_engine(url, connect_args={"prepared_statement_cache_size": 0})`.
