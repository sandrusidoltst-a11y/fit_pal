# Fully Async

## What It Is

All nodes, tools, services, and DB access in the runtime path use `async`/`await`. The async engine (`asyncpg`) is the primary DB path. A sync engine (`psycopg2`) exists only for the ETL ingest script (`src/scripts/ingest_simple_db.py`), which runs standalone outside the async runtime.

## Why This Pattern

- **LangGraph runs in an ASGI server** — any blocking call inside an async node triggers `BlockingError` from the `blockbuster` library that LangGraph uses to detect event loop stalls
- **Throughput** — async DB calls let the server handle multiple concurrent graph runs without thread-pool contention
- **Consistency** — one async path everywhere means no accidental mixing of sync/async that causes subtle deadlocks

## Async DB Engine

`src/database.py` sets up the async engine and session factory:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

async_engine = create_async_engine(DATABASE_URL, ...)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

def get_async_db_session():
    return AsyncSessionLocal()
```

Key details:
- `expire_on_commit=False` prevents `MissingGreenlet` errors when accessing ORM attributes after commit
- `DATABASE_URL` uses the `postgresql+asyncpg://` scheme (converted from `SUPABASE_DB_URL` in `src/config.py`)

### SSL Context Workaround

`database.py` creates a custom SSL context and passes it via `connect_args={"ssl": _ctx}`. This prevents asyncpg from calling `pathlib.resolve()` → `os.getcwd()` when searching for `~/.postgresql/` client certificates. That sync filesystem call triggers `BlockingError` inside the ASGI server.

## Tool and Service Patterns

Tools and services are all `async def` and use `get_async_db_session()`:

```python
@tool
async def search_food(query: str, user_id: str) -> list[dict]:
    async with get_async_db_session() as session:
        stmt = select(FoodItem).where(...)
        results = (await session.execute(stmt)).all()
        ...
```

Service functions accept an explicit `AsyncSession` parameter (for DI/testability). Tool wrappers create their own session and delegate:

```python
# Service function — accepts session
async def create_log_entry(session: AsyncSession, ...) -> DailyLog:
    ...

# Tool wrapper — owns session, delegates to service
@tool
async def log_food_entry(...) -> dict:
    async with get_async_db_session() as session:
        log = await create_log_entry(session=session, ...)
```

## Node Pattern

Nodes are `async def` and call tools via `await tool.ainvoke(...)`:

```python
async def food_search_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    results = await search_food.ainvoke({"query": food_name, "user_id": user_id})
    return {"search_results": results}
```

## Known Gotchas (Fixed)

### 1. `os.getcwd()` in async nodes

Five nodes were calling `os.path.join(os.getcwd(), "prompts/...")` to load prompt files. `os.getcwd()` is a sync syscall that triggers `BlockingError`.

**Fix**: Replace with `BASE_DIR` from `src.config` — computed once at import time, not at runtime.

### 2. Sync `tool.invoke()` in async nodes

Two nodes called `.invoke()` (sync) on tools instead of `.ainvoke()` (async), blocking the event loop.

**Fix**: Always use `await tool.ainvoke(...)` from async nodes. Never call `.invoke()`.

## Rules

- Every node, tool, and service function in the runtime path must be `async def`
- Always use `await tool.ainvoke(...)` in nodes — never `.invoke()`
- Always use `get_async_db_session()` for DB access — never the sync engine
- Never call blocking functions (`os.getcwd()`, `open()`, `time.sleep()`) inside nodes or tools — use `BASE_DIR`, `aiofiles`, `asyncio.sleep()` instead
- The sync engine in `database.py` and `ingest_simple_db.py` is ETL-only — never import it in `src/agents/` or `src/tools/`
