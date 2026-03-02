# RCA: BlockingError — Sync Tool Calls Inside Async LangGraph Nodes

## Summary

The LangGraph dev server threw `BlockingError: An internal error occurred` when running graph-api tests through the food-logging path, causing `test_log_common_food_completes` and `test_multi_item_input_completes` to fail.

## Root Cause

Two graph nodes called sync `@tool.invoke()` methods that used the sync SQLAlchemy engine (`get_db_session()`), blocking the async event loop. The LangGraph agent server explicitly forbids synchronous blocking operations inside async node functions.

**Affected call sites:**

| Node | File:Line | Blocking Call |
|---|---|---|
| `calculate_log_node` | `src/agents/nodes/calculate_log_node.py:33` | `calculate_food_macros.invoke(...)` |
| `food_search_node` | `src/agents/nodes/food_search_node.py:22` | `search_food.invoke(...)` |

Both tools (`calculate_food_macros`, `search_food`) use `get_db_session()` which returns a sync SQLAlchemy session backed by `sqlite3` — a blocking I/O call that deadlocks the async event loop.

## Fix

### Strategy: Replace sync tool calls with async DB queries + pure helpers

1. **Extracted `compute_food_macros()`** — a pure function (no DB, no I/O) in `src/tools/food_lookup.py` that performs the macro ratio math. The existing `@tool calculate_food_macros` was updated to call this helper internally (DRY).

2. **`food_search_node.py`** — converted from sync to async. Replaced `search_food.invoke()` with a direct async DB query via `get_async_db_session()`.

3. **`calculate_log_node.py`** — replaced `calculate_food_macros.invoke()` with `await session.get(FoodItem, id)` + `compute_food_macros()`. Consolidated into a single `get_async_db_session()` context for both the lookup and the subsequent log write.

### Files Modified

- `src/tools/food_lookup.py` — extracted `compute_food_macros()` helper
- `src/agents/nodes/food_search_node.py` — converted to async
- `src/agents/nodes/calculate_log_node.py` — replaced sync tool with async DB + helper
- `tests/conftest.py` — removed `mock_calculate_macros`, added `mock_food_search_db_session`
- `tests/unit/test_calculate_log_node.py` — mock `session.get()` instead of `.invoke()`
- `tests/unit/test_feedback_logic.py` — same
- `tests/unit/test_multi_item_loop.py` — same
- `tests/unit/test_food_search_node.py` — converted to async, mock DB
- `tests/graph_api/conftest.py` — fixed duplicate imports + f-string lint

## Prevention

- **Rule**: Graph nodes must never call `@tool.invoke()` directly. Use async DB queries + pure helper functions instead.
- **Rule**: All nodes in the LangGraph graph must be `async def` and use only `get_async_db_session()` for database access.
- The sync `@tool` functions (`search_food`, `calculate_food_macros`) remain available for LangChain tool-calling patterns but must not be called from within graph nodes.

## Date

2026-03-02
