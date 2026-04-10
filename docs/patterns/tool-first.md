# Tool-First + Service Layer

## What It Is

Every database access in FitPal flows through async `@tool` functions, and every `@tool` function lives inside `src/services/<domain>_service.py` next to a service function that does the real work. The two layers — service function and `@tool` wrapper — are **co-located in the same file**, organized by domain (food, daily log, personal stats, user profile).

Concretely:

- A **service function** is an `async def` that accepts an explicit `session: AsyncSession` as its first parameter and returns ORM objects, primitives, or dicts. It contains the actual SQL logic. It owns no session lifecycle — the caller passes one in.
- A **`@tool` wrapper** is an `async def` decorated with `@tool` from `langchain_core.tools`. It accepts plain primitives (`str`, `float`, `dict`), creates its own session via `async with get_async_db_session()`, and delegates the work to the service function. Its return value is always JSON-serializable.
- A **node** is the third layer above. Nodes never import a DB session, never touch SQLAlchemy, and never call service functions directly. They invoke tools via `await tool.ainvoke({...})`.

The directory structure is **flat by domain**. There is no `src/tools/` directory — every tool lives next to the service it wraps:

```text
src/services/
├── daily_log_service.py     # services + log_food_entry, query_food_logs
├── food_service.py          # services + search_food, calculate_food_macros, create_food_item
├── personal_stats_service.py # services + log_personal_stat, get_latest_personal_stats, get_personal_stat_history
└── user_profile_service.py  # services only — no @tool wrappers (loaded by the bot, not by nodes)
```

This is the **only** DB access pattern in the codebase. Nothing else is allowed.

## Why This Pattern

- **Separation of concerns by responsibility, not by file location.** Nodes orchestrate the graph (state transitions, branching, message handling). Tools translate between the graph and the DB (own session lifecycle, accept primitives, return JSON-safe dicts). Services hold the actual SQL logic and are framework-free. Each layer has exactly one job, and the boundaries are sharp enough that you can change one without rippling into the others.

- **Testability via dependency injection.** Service functions accept `session` as their first argument, so integration tests pass a session bound to a transaction that gets rolled back at teardown. This means service tests run against a real Postgres database with real queries — no mocks, no in-memory fakes — but each test is hermetic because the transaction is discarded. The `@tool` wrappers are tested separately by patching `get_async_db_session` on the wrapper's module (see `tests/integration/test_food_service.py::_patch_session`).

- **LLM tool-calling ready by default.** Every `@tool`-decorated function is a binding-ready LangChain tool. We currently invoke tools imperatively from nodes (`await tool.ainvoke({...})`), but if we ever want the LLM to choose tools dynamically (e.g. via `llm.bind_tools([...])`), the surface is already correct. No refactor needed.

- **Nodes stay declarative and short.** A typical node is ~30 lines of pure orchestration: read state, await one or two tools, return a state update. Nodes never import `get_async_db_session`, never write SQL, never serialize ORM objects. This makes nodes trivially readable and trivially testable (mock the tools at the module level, no DB needed).

- **Reusability across runtime contexts.** The same `@tool` function is callable from a graph node, an integration test, an ad-hoc script, and (eventually) an LLM tool-call. The same service function is callable from a tool wrapper, a script that manages its own transaction, or a future REST endpoint. We never reimplement DB logic for "the script version" or "the test version" — there is one implementation.

- **Domain-driven file organization.** When you want to know everything about how food is stored and queried, you open exactly one file: `food_service.py`. You see the services, the tools, the helpers, the imports, and the docstring all in one place. There is no cross-file hunt between `src/tools/` and `src/services/`. The user explicitly preferred this over the alternative split (see the planning conversation that led to the `food_lookup.py` refactor: `docs/plans/refactor-food-lookup-to-service-pattern.md`).

## The Three Layers

```text
┌──────────────────────────────────────────────────────────────┐
│  Node (src/agents/nodes/*.py)                                │
│    async def food_search_node(state, runtime):               │
│        user_id = runtime.context.user_id                     │
│        results = await search_food.ainvoke({                 │
│            "query": food_name,                               │
│            "user_id": user_id,                               │
│        })                                                    │
│        return {"search_results": results}                    │
└──────────────────────────────────────────────────────────────┘
                           │
                           │  await tool.ainvoke({primitives})
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  @tool wrapper (src/services/<domain>_service.py)            │
│    @tool                                                     │
│    async def search_food(query: str, user_id: str):          │
│        async with get_async_db_session() as session:         │
│            items = await search_food_items(                  │
│                session, query, user_id,                      │
│            )                                                 │
│            return [{"id": ..., "name": ...} for i in items]  │
└──────────────────────────────────────────────────────────────┘
                           │
                           │  service_func(session, ...)
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Service function (same file as the @tool)                   │
│    async def search_food_items(                              │
│        session: AsyncSession, query: str, user_id: str,      │
│    ) -> list[FoodItem]:                                      │
│        stmt = select(FoodItem).where(...)                    │
│        return list((await session.execute(stmt)).scalars())  │
└──────────────────────────────────────────────────────────────┘
                           │
                           │  SQLAlchemy ORM
                           ▼
                    Supabase Postgres
```

Each layer has one responsibility:

| Layer | Owns | Does NOT own |
|---|---|---|
| Node | State transitions, graph orchestration | Sessions, SQL, serialization |
| `@tool` wrapper | Session lifecycle, primitive ↔ dict conversion, logging | SQL queries, business logic |
| Service function | SQL queries, query logic, ORM operations | Session lifecycle, JSON serialization, framework integration |

## Service Function Pattern

Service functions live above the `# ---` separator inside the domain service file. They take `session: AsyncSession` as the first parameter and return ORM objects, primitives, or dicts (whichever is most natural for the operation).

Real example from `src/services/daily_log_service.py`:

```python
async def create_log_entry(
    session: AsyncSession,
    user_id: str,
    food_id: Optional[str],
    amount_g: float,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    timestamp: datetime,
    meal_type: Optional[str] = None,
    original_text: Optional[str] = None,
) -> DailyLog:
    """Create and persist a new DailyLog entry."""
    log = DailyLog(
        user_id=uuid_mod.UUID(user_id),
        food_id=uuid_mod.UUID(food_id) if food_id else None,
        amount_g=amount_g,
        calories=calories,
        protein=protein,
        carbs=carbs,
        fat=fat,
        timestamp=timestamp,
        meal_type=meal_type,
        original_text=original_text,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log
```

Key conventions for service functions:

- **`session: AsyncSession` is always the first positional parameter.** This makes the calling pattern uniform and grep-friendly.
- **Return type is the most natural Python type for the operation.** Inserts return the freshly committed ORM object (after `refresh` to populate auto-generated fields like `id`). Reads return ORM objects, lists of ORM objects, or scalars. Aggregations return dicts of primitives.
- **`uuid.UUID(user_id)` conversion happens here, not in the tool wrapper.** Service functions accept `user_id: str` (because that's what the bot/runtime/tests pass), and convert to `UUID` exactly when handing off to SQLAlchemy. Doing the conversion at the service-layer boundary keeps tool wrappers free of UUID details.
- **No logging required at the service layer.** The wrapper logs. Adding logging here would create double-logging on every successful call. Exception: if a service function does something complex (a multi-step query, a fallback path), a single `logger.debug` is fine. The two-tier search in `food_service.py::search_food_items` is intentionally silent — its tool wrapper handles the logging.
- **No exception handling unless there's something useful to do.** Let SQLAlchemy errors propagate. The tool wrapper or the node will surface them.
- **Commit the session.** Service functions that mutate (insert, update, delete) call `await session.commit()` and `await session.refresh()` themselves. This is the pattern across `daily_log_service.py`, `food_service.py`, and `personal_stats_service.py`. The exception is when a caller passes a session that's part of a larger transaction — that caller would manage its own commit. We don't currently do that, but the pattern leaves the door open.

## Tool Wrapper Pattern

Tool wrappers live below the `# ---` separator inside the same service file. They are decorated with `@tool` from `langchain_core.tools`, accept plain primitives, own their own session, delegate to service functions, and return JSON-serializable values.

Real example from `src/services/daily_log_service.py`:

```python
@tool
async def log_food_entry(
    food_id: Optional[str],
    amount_g: float,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    timestamp: str,
    original_text: str = "",
    user_id: str = "",
) -> dict:
    """Log a food entry to the daily log. Timestamp should be ISO format string."""
    parsed_ts = datetime.fromisoformat(timestamp)
    async with get_async_db_session() as session:
        log = await create_log_entry(
            session=session,
            user_id=user_id,
            food_id=food_id,
            amount_g=amount_g,
            calories=calories,
            protein=protein,
            carbs=carbs,
            fat=fat,
            timestamp=parsed_ts,
            original_text=original_text or None,
        )
        logger.info("Daily log created", log_id=str(log.id), user_id=user_id, calories=calories)
        return {"id": str(log.id), "status": "logged"}
```

Key conventions for tool wrappers:

- **Parameters are plain primitives only.** `str`, `float`, `int`, `bool`, `Optional[str]`, `list[str]`. No ORM objects, no Pydantic models, no `RunnableConfig`, no `ToolRuntime`. The reason: `@tool` introspects the function signature to build the LLM tool schema, and the LLM can only produce JSON-primitive arguments. Even when we don't bind tools to an LLM, keeping the signature primitive-only means the tool is callable from any context (test, script, REPL).
- **Datetime/date inputs are ISO strings, parsed inside the wrapper.** `timestamp: str` → `datetime.fromisoformat(timestamp)`. Same reason as above: the LLM can produce ISO strings but not `datetime` objects, so we accept strings and parse at the boundary.
- **`user_id: str = ""` is a default, not required.** The default empty string exists because `@tool` schemas distinguish required vs optional parameters by presence of a default. We want `user_id` to be technically optional in the tool schema (so the LLM doesn't think it has to invent one) but always populated in practice by the calling node. The node passes `user_id=runtime.context.user_id` from `runtime.context`. See `runtime-context.md` for how user_id flows through the graph.
- **Session lifecycle is owned here, not in the service function.** `async with get_async_db_session() as session:` opens, commits, and closes the session for the duration of the tool call. The service function inside the `with` block sees a live session passed by the caller (the wrapper).
- **Logging happens here, not in the service function.** `logger.info("Daily log created", log_id=..., user_id=..., calories=...)` — structured key-value logs via `structlog`. Log on success at the wrapper boundary so we get exactly one log line per high-level operation. Log on failure (or unusual paths like the not-found case in `calculate_food_macros`) with `logger.warning` or `logger.error`.
- **Return value is always a JSON-serializable dict, list of dicts, or scalar.** Never return an ORM object or a SQLAlchemy `Row`. The reason is twofold: (1) once the `with` block exits, the session closes and any unpopulated ORM attributes raise `MissingGreenlet` on access; (2) LangGraph state must be JSON-serializable for checkpointing and HTTP transport. See "Serialization Boundary" below.

## Node Pattern

Nodes live in `src/agents/nodes/*.py`. They are `async def` and call tools via `await tool.ainvoke({...})`. They never import `get_async_db_session`, never import SQLAlchemy, and never import service functions directly.

Real example from `src/agents/nodes/food_search_node.py`:

```python
import structlog
from langgraph.runtime import Runtime

from src.agents.state import AgentState
from src.context import ContextSchema
from src.services.food_service import search_food

logger = structlog.get_logger(__name__)


async def food_search_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    """
    Search for food items based on pending_food_items.

    Calls search_food tool for the first pending item and
    populates search_results in state.
    """
    pending_items = state.get("pending_food_items", [])

    if not pending_items:
        logger.warning("food_search_node called with empty pending_food_items")
        return {"search_results": []}

    first_item = pending_items[0]
    food_name = first_item.get("food_name", "")

    user_id = runtime.context.user_id
    results = await search_food.ainvoke({"query": food_name, "user_id": user_id})

    return {"search_results": results}
```

Key conventions for nodes:

- **Always `await tool.ainvoke({...})` — never `tool.invoke(...)`.** The sync `.invoke()` blocks the event loop and triggers `BlockingError` from the `blockbuster` library that LangGraph uses to detect event loop stalls. This was the root cause of an entire class of production bugs in early FitPal — see `docs/rca/blocking-error-sync-tools-in-async-nodes.md`. The async patterns doc covers this in depth: see [async-patterns.md](async-patterns.md).
- **Pass `user_id` as a plain string, sourced from `runtime.context.user_id`.** Tools accept `user_id: str` because they are framework-free — they have no knowledge of `RunnableConfig`, `Runtime`, or `ContextSchema`. This is intentional. See [runtime-context.md](runtime-context.md) for the full rationale and how the context flows from the bot through the graph to the node.
- **Tool inputs go in a single dict argument to `ainvoke`.** `await search_food.ainvoke({"query": ..., "user_id": ...})`. Not `search_food.ainvoke(query=..., user_id=...)` and not `search_food(query, user_id)`. The dict form is what LangChain's `BaseTool.ainvoke` expects when the tool was created with `@tool` — it gets validated against the tool's input schema before the function body runs.
- **The node returns a state update dict, not the tool's return value.** Even if the node only calls one tool, it wraps the result in a state-shaped dict (`{"search_results": results}`) so LangGraph knows which state field to merge into.
- **Nodes that don't need DB access don't import any tools.** `input_parser_node.py` and `agent_selection_node.py` are pure LLM-call nodes — no tools, no service imports, no `runtime` parameter. The tool-first rule says "if you touch the DB, go through a tool"; it doesn't say "every node must call a tool".

## Serialization Boundary

The boundary between "ORM objects" and "JSON-safe dicts" lives **inside the `@tool` wrapper**, never inside the node. This is non-negotiable for two reasons:

1. **Session lifetime.** Once `async with get_async_db_session() as session:` exits, the session closes. Accessing any unpopulated lazy attribute on an ORM object after that point raises `MissingGreenlet` (the SQLAlchemy async-mode equivalent of "lazy load outside session"). If a node received an ORM object from a tool, the node would have to either (a) only access pre-populated attributes (fragile), or (b) reopen a session and re-attach the object (wasteful). Neither is acceptable. The fix is to flatten ORM objects to dicts inside the wrapper, while the session is still alive.

2. **LangGraph state must be JSON-serializable.** LangGraph checkpoints state to Postgres after every node. The checkpointer uses `json.dumps()` (with some custom encoders for known types like datetime), but ORM objects with circular references and lazy-loaded relationships cannot be serialized cleanly. If a node returned an ORM object as part of a state update, the checkpointer would either crash or produce unreadable state. The fix is the same: serialize at the wrapper boundary.

The standard pattern is a small `_serialize_*` helper next to the tool wrappers. From `src/services/daily_log_service.py`:

```python
def _serialize_log(log: DailyLog) -> dict:
    """Convert a DailyLog ORM object to a JSON-serializable dict."""
    return {
        "id": str(log.id),
        "food_id": str(log.food_id) if log.food_id else None,
        "amount_g": log.amount_g,
        "calories": log.calories,
        "protein": log.protein,
        "carbs": log.carbs,
        "fat": log.fat,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "meal_type": log.meal_type,
        "original_text": log.original_text,
    }
```

Used by the `@tool query_food_logs` wrapper:

```python
@tool
async def query_food_logs(target_date: str, end_date: str = "", user_id: str = "") -> list[dict]:
    """Query food log entries by date or date range."""
    parsed_date = date.fromisoformat(target_date)
    async with get_async_db_session() as session:
        if end_date:
            parsed_end = date.fromisoformat(end_date)
            logs = await get_logs_by_date_range(session, user_id, parsed_date, parsed_end)
        else:
            logs = await get_logs_by_date(session, user_id, parsed_date)
        return [_serialize_log(log) for log in logs]
```

Conventions for serializers:

- **Underscore-prefixed (`_serialize_log`)**: signals "private to this module".
- **Live next to the tool wrappers**, not next to the service functions (because the service returns ORM objects; the wrapper does the conversion).
- **One serializer per ORM class**, even if multiple tools use the same model. DRY at the dict-shape level.
- **UUID columns become `str(value)`.** JSON has no UUID type; serialize via `str()`.
- **Datetime columns become ISO 8601 strings via `.isoformat()`.** Same reason.
- **Optional FK columns**: `str(log.food_id) if log.food_id else None`.

When a service function returns dicts directly (because the operation is naturally a projection — e.g. an aggregation, or a query that selects only a few columns), no serializer is needed. Example: `personal_stats_service.py::get_latest_stats` and `get_stat_history` return dicts directly because they're already shaped for the response. The rule is simple: **if an ORM object ever escapes the `with` block, it must be serialized first**.

## When a Service Doesn't Need a `@tool` Wrapper

Not every service function needs a `@tool` wrapper. The rule is precise:

> **A service function gets a `@tool` wrapper only when a graph node needs to call it.**

Today, three of four service files have wrappers:

| Service file | Has `@tool` wrappers? | Why |
|---|---|---|
| `daily_log_service.py` | Yes — `log_food_entry`, `query_food_logs` | Called by `commit_node` and `stats_lookup_node` |
| `food_service.py` | Yes — `search_food`, `calculate_food_macros`, `create_food_item` | Called by `food_search_node`, `calculate_macros_node`, `confirmation_node`, `commit_node` |
| `personal_stats_service.py` | Yes — `log_personal_stat`, `get_latest_personal_stats`, `get_personal_stat_history` | Called by `personal_stats_node` and `response_node` |
| `user_profile_service.py` | **No** | Loaded by the bot (`bot/gateway.py`) at session creation, not by any graph node |

`user_profile_service.py` is the canonical example of a service-only file. The bot loads the user profile when it creates the in-memory session, caches it, and then attaches the profile to every API call as part of the `Runtime[ContextSchema]` context. The graph itself never queries the user profile from the DB — it just reads `runtime.context.user_profile` (which is a plain dict by the time the node sees it). See [runtime-context.md](runtime-context.md) for the full flow.

The reason this matters: **don't add a `@tool` wrapper preemptively just because the service exists**. Adding a wrapper that nothing calls is dead code. If a future node needs to call `get_user_profile`, the wrapper can be added at that time as a one-line change. Until then, the service stands alone, and the LLM tool surface stays minimal.

A second case: **internal helper services**. If a service function is only ever called by other service functions (e.g. a helper that fetches a row by ID, called from three other services in the same file), it doesn't get a `@tool` wrapper either — it's plumbing inside the service layer, not part of the public surface. The tool wrappers are the DB layer's *public API*; service functions are its *implementation*.

## Cross-References

This pattern doesn't exist in isolation. Three other patterns are tightly coupled to it and should be read together:

- **[async-patterns.md](async-patterns.md)** — explains why every node, tool, and service must be `async def`, why `await tool.ainvoke(...)` is mandatory (and `tool.invoke(...)` will crash the server with `BlockingError`), and how the async DB engine (`asyncpg`) is wired up. Read this before adding any code in `src/services/`, `src/agents/nodes/`, or anything that touches the DB.

- **[runtime-context.md](runtime-context.md)** — explains how `user_id` flows from the Telegram bot through `Runtime[ContextSchema]` into nodes, and why tools accept `user_id: str` instead of `RunnableConfig` or `ToolRuntime`. The "tools are framework-free" philosophy in this doc is grounded there.

- **[state-schemas.md](state-schemas.md)** — explains the `InputState` / `AgentState` / `OutputState` split. Service functions return ORM objects, tools return dicts, and those dicts get merged into `AgentState` fields like `search_results: List[SearchResult]`. The shape of the dicts that tools return must match the `TypedDict`s in `src/agents/state.py`.

## Rules

Hard rules that this pattern enforces. Violating any of these is a bug.

1. **Nodes never import `get_async_db_session` or any SQLAlchemy symbol.** Grep `src/agents/nodes/` for `from src.database` or `from sqlalchemy` — the result must be empty. If a node needs DB access, the answer is "wrap the access in a tool", not "import the session".

2. **Nodes never import service functions directly.** Only `@tool`-decorated functions. The reason: importing a service function would skip the session-management layer, which means the node would have to manage the session itself, which violates rule 1. Grep `src/agents/nodes/` for any `from src.services.*_service import <name_without_@tool>` — result must be empty.

3. **Nodes always call tools via `await tool.ainvoke({...})`.** Never `tool.invoke(...)` (sync, blocks event loop), never `await tool(...)` (bypasses input validation), never `await tool.arun(...)` (deprecated). The dict-form `ainvoke` is the only correct call.

4. **Service functions accept `session: AsyncSession` as the first parameter.** No defaults, no `Optional`. The session is mandatory; the caller (tool wrapper or test) is responsible for providing it.

5. **`@tool` wrappers own their session via `async with get_async_db_session()`.** Never pass a session into a tool wrapper. Never store a session as module state. The `async with` block defines the transaction lifetime.

6. **`@tool` wrappers accept only JSON-primitive parameters.** `str`, `float`, `int`, `bool`, `Optional[...]`, `list[...]`, `dict`. No ORM objects, no Pydantic models (unless wrapped in `dict`-able shape), no `RunnableConfig`, no `ToolRuntime`, no `Session`.

7. **Tools return JSON-serializable values.** Dicts, lists of dicts, primitives. Never an ORM object. Use `_serialize_<model>` helpers for the conversion, defined next to the tool wrappers.

8. **Pure helpers that don't need a session stay at module level.** Example: `compute_food_macros` in `food_service.py` is a pure function (no I/O, no DB). It lives at module level — not nested inside the tool — so it can be unit-tested directly and so other code can import it if needed.

9. **One file per domain in `src/services/`.** All services and tools for a domain live in `<domain>_service.py`. Do not split services and tools across files. Do not create a `src/tools/` directory — it does not exist.

10. **Add a `@tool` wrapper only when a node needs it.** Don't preemptively wrap every service function. `user_profile_service.py` has zero wrappers because no node calls it; that's correct.

11. **Tool names are part of the public LLM tool-calling contract.** Even if no LLM currently binds them, do not rename `@tool` functions casually. Renaming a tool is a breaking change for any future code (or LLM) that depends on the name. Service function names are internal and can be renamed freely.

12. **Patch the wrapper's module, not the service module, in tests.** When a test needs to redirect a tool to a test session, it patches `src.services.<domain>_service.get_async_db_session` — the import on the wrapper's own module. Patching `src.database.get_async_db_session` will not work because the wrapper has already pulled the symbol into its own namespace at import time. See `tests/integration/test_food_service.py::_patch_session` for the canonical example, and the test-engineering skill reference at `.claude/skills/test-engineering/references/integration-testing.md` (section "3.2 Tool Tests") for the full pattern.
