# Migrate to Runtime[ContextSchema] + User Profile Injection

**Date**: 2026-04-02
**Branch**: Menu-and-Personal-Details
**Commit**: 5a4d551

## Changes Implemented

### New: `src/context.py`
- `ContextSchema` dataclass with `user_id` (str, UUID-validated) and `user_profile` (dict)
- `__post_init__` validates UUID, falls back to `DEFAULT_DEV_USER_ID`
- `UserProfile` TypedDict for documentation
- Defaults enable LangGraph Studio to work without bot context

### Graph: `src/agents/nutritionist.py`
- Added `context_schema=ContextSchema` to StateGraph constructor

### Nodes (7 files)
- All config-accepting nodes migrated from `config: RunnableConfig` to `runtime: Runtime[ContextSchema]`
- Nodes read `runtime.context.user_id` and pass it as a plain string to tools
- `response_node` injects user profile into SystemMessage content

### Tools (3 files)
- All `config: RunnableConfig` parameters replaced with `user_id: str`
- No framework dependency — tools are pure functions accepting plain parameters
- `RunnableConfig` import removed from all tools and services

### Bot: `bot/gateway.py`
- Sends `context: {"user_id": ..., "user_profile": ...}` instead of `config.configurable`

### Config: `src/config.py`
- Removed `get_user_id()`, `get_user_profile()`, `DEFAULT_DEV_USER_ID`, `DEFAULT_DEV_PROFILE`
- All moved to `src/context.py`

### Tests
- Unit tests use mock `Runtime` (TEST_RUNTIME_A/B) instead of TEST_CONFIG_A/B
- Integration tests pass `user_id` as string parameter directly
- E2E tests use `context=` instead of `config=` in SDK calls
- New tests for `ContextSchema` defaults and UUID validation

## Key Design Decision: Tools Accept Plain Strings
ToolRuntime auto-injection doesn't work with direct `.ainvoke()` calls (only within graph context). Instead of a hack bridge, tools accept `user_id: str` directly. This makes them simpler, more testable, and framework-independent.

## Validation Results
- `ruff check .` — all passed
- `pytest tests/unit/` — 95 passed
- `pytest tests/integration/` — 26 passed
- `pytest tests/graph_api/` — 13 passed

## Next Steps
- Test user profile injection via local dev bot ("what's my name?")
- Merge branch to main for production deploy
- Consider merging dev + e2e test users into one
