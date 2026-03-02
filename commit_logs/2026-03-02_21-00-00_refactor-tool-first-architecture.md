# Refactor: Tool-First Architecture

**Commit**: `8f2ff8f`
**Branch**: `Testing_improvements`
**Date**: 2026-03-02

## Summary

Restored the node → tool → DB boundary that was broken in commit `30ad995`. All `@tool` functions are now async, and nodes have zero direct DB access.

## Changes (15 files)

### Source (5 files)
- **`src/tools/food_lookup.py`**: Converted `search_food` and `calculate_food_macros` to `async def` using `get_async_db_session()`
- **`src/services/daily_log_service.py`**: Added `log_food_entry` and `query_food_logs` `@tool` wrappers alongside existing service functions
- **`src/agents/nodes/food_search_node.py`**: Restored `await search_food.ainvoke()`, removed inline DB query
- **`src/agents/nodes/calculate_log_node.py`**: All 3 tool calls (`calculate_food_macros`, `log_food_entry`, `query_food_logs`), zero DB imports
- **`src/agents/nodes/stats_node.py`**: Uses `query_food_logs` tool, removed `daily_log_service` direct imports

### Tests (7 files)
- **`tests/conftest.py`**: Replaced DB session mocks with tool mock fixtures (`mock_search_food`, `mock_calculate_macros`, `mock_log_food_entry`, `mock_query_food_logs_for_calc`, `mock_query_food_logs_for_stats`)
- **`tests/unit/test_calculate_log_node.py`**: Mock tools instead of DB
- **`tests/unit/test_food_search_node.py`**: Mock `search_food` tool
- **`tests/unit/test_feedback_logic.py`**: Same tool mock pattern
- **`tests/unit/test_multi_item_loop.py`**: Same tool mock pattern
- **`tests/unit/test_stats_node.py`**: Mock `query_food_logs` tool
- **`tests/integration/test_food_db.py`**: Converted to async `.ainvoke()` calls

### Context (3 files)
- **`CLAUDE.md`**: Updated architecture patterns and file descriptions
- **`PRD.md`**: Updated directory structure, tech stack, added Phase 2 milestone
- **`.claude/skills/test-engineering/references/unit-testing.md`**: Updated mock patterns

## Architecture Decision

Service functions accept a `session` parameter (DI for testability). `@tool` wrappers create their own session via `async with get_async_db_session()` and delegate to service functions. This gives us:
- Clean mock boundary for unit tests (mock tools on node modules)
- DI flexibility for service-level tests
- Zero DB imports in any node

## Next Steps

- Push to remote and update PR #11
- Address remaining PR review feedback
- Continue with Phase 2 items (Off-Menu fallback, Alembic migrations)
