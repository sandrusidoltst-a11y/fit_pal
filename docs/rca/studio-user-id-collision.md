# RCA: Studio user_id Collision Causes ValueError in search_food

## Problem Description

When logging food via LangGraph Studio (`langgraph dev`), the graph crashes with:
```
ValueError: badly formed hexadecimal UUID string
```
at `src/tools/food_lookup.py:53` inside `search_food`.

## Reproduction Steps

1. Run `langgraph dev` (no auth, dev mode)
2. Open Studio, send "hi i ate a banana"
3. `input_parser` succeeds → `LOG_FOOD`
4. `food_search` calls `search_food(query="Banana")`
5. No DB match → falls back to estimated food search → calls `uuid_mod.UUID(user_id)`
6. **Crash**: `user_id` is a non-UUID string injected by Studio

## Root Cause Analysis

LangGraph Studio automatically injects a `user_id` into `config["configurable"]` for its built-in Store (cross-thread memory namespacing). This is a Studio-generated string identifier, **not a UUID**.

Our `get_user_id()` in `src/config.py` has this priority chain:
1. `config["configurable"]["langgraph_auth_user"]["identity"]` → production (auth handler)
2. `config["configurable"]["user_id"]` → dev/manual
3. `DEFAULT_DEV_USER_ID` → fallback

In Studio (no auth), step 1 is skipped. Step 2 finds Studio's non-UUID `user_id` and returns it. Step 3 (the valid UUID fallback) is never reached.

Downstream, `search_food` passes this value to `uuid_mod.UUID()` which raises `ValueError`.

### Why tests didn't catch it

All test configs explicitly pass valid UUIDs:
- Unit/integration: `TEST_CONFIG_A` / `TEST_CONFIG_B` (valid UUIDs in `tests/conftest.py`)
- Graph-API E2E: `DEV_USER_CONFIG` with `"00000000-0000-0000-0000-000000000001"`

No test exercises the "configurable contains a non-UUID user_id" path.

### Trace evidence

- Thread: `7a872aee-2a33-4c8a-9be1-5c35364a2aab`
- Run: `019d057b-db58-7ee1-bdb5-3f06be9c340d`
- Saved: `traces/7a872aee-thread-trace.txt`

## Broader Codebase Scan

All `uuid_mod.UUID(user_id)` calls that would be affected:
- `src/tools/food_lookup.py:53` — `search_food` estimated food fallback
- `src/tools/food_lookup.py:69` — `calculate_food_macros` (uses `food_id`, not `user_id` — unaffected)
- `src/tools/food_lookup.py:98` — `create_food_item` uses `uuid_mod.UUID(user_id)`
- `src/services/daily_log_service.py` — service functions receive `user_id` from nodes which get it from `get_user_id()`

All downstream consumers trust `get_user_id()` to return a valid UUID. Fixing it at the source fixes all paths.

## Proposed Fix

Add UUID validation in `get_user_id()`. If `configurable["user_id"]` is not a valid UUID, log a warning and fall back to `DEFAULT_DEV_USER_ID`.

```python
def get_user_id(config: RunnableConfig | None) -> str:
    if config:
        auth_user = config["configurable"].get("langgraph_auth_user")
        if auth_user:
            return auth_user["identity"]
        user_id = config["configurable"].get("user_id", DEFAULT_DEV_USER_ID)
        try:
            uuid.UUID(user_id)
            return user_id
        except ValueError:
            logger.warning("Non-UUID user_id in config, falling back to default",
                           received=user_id, fallback=DEFAULT_DEV_USER_ID)
            return DEFAULT_DEV_USER_ID
    logger.warning("No config provided, falling back to default", user_id=DEFAULT_DEV_USER_ID)
    return DEFAULT_DEV_USER_ID
```

Add a unit test for the non-UUID fallback path.

## Validation Commands

```bash
# Unit tests (includes new test)
uv run pytest tests/unit/test_auth_handler.py -v

# Full unit suite
uv run pytest tests/unit/ -v

# Manual: run langgraph dev, send "i ate a banana" in Studio
```
