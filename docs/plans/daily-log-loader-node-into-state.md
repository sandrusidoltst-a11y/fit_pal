# Feature: Move `daily_log_today` from ContextSchema to AgentState via a loader node

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

## Feature Description

Implements [ADR-0002](../adr/0002-daily-log-loader-node-into-state.md). Moves the per-user "today's food log" snapshot from `ContextSchema` (gateway-injected, request-scoped, immutable) to `AgentState`, populated by a new graph node `load_daily_context` that runs at graph entry **and again after `commit_node`**. The gateway stops fetching the daily log entirely.

This fixes a real production bug observed in LangSmith thread `73ed31fb-8391-4c97-a05f-a4b672c6fcd5` (2026-04-22): a HITL-resume turn caused `commit_node` to write new food rows, but `response_node` (running later in the same request) reported stale numbers because the gateway's pre-request snapshot in `runtime.context` could not be refreshed mid-graph. After this change, post-commit consumers always see the rows commit just wrote.

## User Story

As a **trainee**,
I want the bot's daily summary to reflect what I just confirmed in the same turn,
So that I am not given a wrong picture and forced to ask "are you sure?" on every confirmation.

As **Dolev (the developer)**,
I want fields whose source rows can be mutated mid-graph to live in `AgentState` and be refreshed by an explicit loader node,
So that future post-commit consumers get correct data without each one fetching its own copy and without subtle staleness bugs reappearing.

## Problem Statement

`runtime.context` is request-scoped and immutable from inside the graph. The gateway snapshots `daily_log_today` *before* the request begins. `commit_node` writes new `daily_logs` rows *during* the request. `response_node` runs *after* `commit_node` in the same request and reads the (now stale) snapshot. Result: undercounted summaries on every commit turn. Per-message gateway re-fetch (the 2026-04-17 mitigation) does not help because the staleness gap is *within* a single request, not between requests.

## Solution Statement

1. Remove `daily_log_today` from `ContextSchema`. Add `daily_log_today: list[dict]` to `AgentState`.
2. Create a new node `load_daily_context` that calls `get_todays_logs_serialized(session, user_id)` and writes the result to `state["daily_log_today"]`.
3. Make `load_daily_context` the graph entry point. Add a conditional edge:
   - `last_action == "LOGGED"` → `response` (came in via the post-commit refresh path)
   - otherwise → `input_parser` (fresh turn entry)
4. Replace `commit → response` with `commit → load_daily_context`. The conditional edge above then routes to `response`.
5. Update `response_node` to read `state["daily_log_today"]` instead of `runtime.context.daily_log_today`.
6. Strip `daily_log_today` plumbing from `bot/gateway.py`: remove `_load_todays_log` helper, remove the `daily_log_today` kwarg on `_call_langgraph`, remove the `body["context"]["daily_log_today"] = …` injection, remove the `get_todays_logs_serialized` import.

The cross-turn state-persistence concern (state lives across turns in the thread checkpointer) is neutralized because `load_daily_context` is the entry point and runs first on every turn — the field is always overwritten before any consumer sees it.

## Feature Metadata

**Feature Type**: Refactor (architectural — implements ADR-0002)
**Estimated Complexity**: Medium
**Primary Systems Affected**:
- `src/context.py` (remove field)
- `src/agents/state.py` (add field)
- `src/agents/nutritionist.py` (graph topology: new entry point, conditional edge, commit edge rewire)
- `src/agents/nodes/response_node.py` (read site)
- `src/agents/nodes/commit_node.py` (downstream edge changes — node body unchanged unless `daily_log_report` overlap matters)
- `bot/gateway.py` (remove fetch + injection)
- New node file: `src/agents/nodes/load_daily_context_node.py`
- Tests: `tests/conftest.py`, `tests/unit/test_response_node.py`, `tests/unit/test_gateway.py`, new `tests/unit/test_load_daily_context_node.py`

**Dependencies**: None new. `get_todays_logs_serialized` already exists in `src/services/daily_log_service.py:228`. `get_async_db_session` already used by service-layer code.

**Resolves**:
- ADR-0002 (this is its implementation)
- The thread `73ed31fb-…` undercounting bug (audit done 2026-04-25)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `docs/adr/0002-daily-log-loader-node-into-state.md` (full file) — the decision this plan implements. Read first; everything else depends on understanding the rules in the *Consequences → What we are committing to* section, especially the "loader after mutation" generalization.
- `docs/patterns/runtime-context.md` (lines 13-30, the new "What Belongs in Context vs State" section) — the rule that scoped this change. Confirms `user_id` and `user_profile` stay in context; `daily_log_today` moves out.
- `src/context.py` (full file, 51 lines) — `ContextSchema` dataclass. Line 44 holds the `daily_log_today` field to be removed. Do **not** touch `user_id` or `user_profile`.
- `src/agents/state.py` (lines 137-167) — `AgentState` TypedDict. Add `daily_log_today: List[dict]` here. Mirror the `daily_log_report: List[QueriedLog]` field shape (line 158) — same type intent (list of serialized log dicts), so consider if reusing `List[QueriedLog]` is appropriate. Note: `_serialize_log` (in `daily_log_service.py:170-225`) emits a superset of `QueriedLog` (adds `category`, `tag`, `serving_amount_g`); use `List[dict]` for breadth or extend `QueriedLog` if you want strict typing. Recommended: `List[dict]` for parity with how `ContextSchema.daily_log_today` was typed.
- `src/agents/nutritionist.py` (full file, 95 lines) — graph wiring. Currently `set_entry_point("input_parser")` (line 54) and `add_edge("commit", "response")` (line 89). Both change.
- `src/agents/nodes/response_node.py` (lines 199-255 specifically; full file for surrounding helpers) — current consumer of `context.daily_log_today` at line 225. Change to `state.get("daily_log_today")`. The `_format_daily_log` helper (line 40) and signature stay the same.
- `src/agents/nodes/commit_node.py` (full file, 109 lines) — note line 89 in the graph (`commit → response`) becomes `commit → load_daily_context`. The body of `commit_node` itself does not need to change; it already updates `daily_log_report` (different field, used by stats flow) — leave that alone. Be aware: `commit_node` returns `last_action: "LOGGED"` (line 107), which is what the new conditional edge from `load_daily_context` will route on.
- `src/agents/nodes/stats_node.py` (full file, 37 lines) — separate flow that writes `daily_log_report`. Read to confirm there is no overlap with `daily_log_today`. Stats uses `query_food_logs` tool with arbitrary date ranges; the new loader uses `get_todays_logs_serialized` with today-only. Different fields, different lifecycles, do not merge.
- `src/services/daily_log_service.py` (lines 170-225 for `_serialize_log`; lines 228-243 for `get_todays_logs_serialized`) — the fetcher already exists. The new loader node calls it. The serializer emits Israel-local timestamps (Bug 2 fix from 2026-04-17) and includes coach-method metadata when mappings are present — both behaviors are preserved.
- `src/database.py` — defines `get_async_db_session` async context manager. Pattern: `async with get_async_db_session() as session:` followed by an awaited service call. Used everywhere a node needs a DB session.
- `bot/gateway.py` (lines 31, 90-117, 220-233, 294-344) — the gateway pieces to delete:
  - Line 31: `from src.services.daily_log_service import get_todays_logs_serialized` import (remove if unused after the rest)
  - Lines 90-117: `_call_langgraph` signature with `daily_log_today: list[dict] | None = None` kwarg (remove); body lines `if daily_log_today is not None: body["context"]["daily_log_today"] = daily_log_today` (remove)
  - Lines 226-233: `_load_todays_log(user_id)` helper (remove)
  - Line 324: `todays_log = await _load_todays_log(user_id)` (remove)
  - Lines 335 and 343: `daily_log_today=todays_log` kwarg in both `_call_langgraph` call sites (remove)
- `tests/conftest.py` (lines 27-58) — `_make_mock_runtime` and `basic_state` fixture. The mock runtime constructs `ContextSchema(user_id=..., user_profile=...)` — that call will still work after `daily_log_today` is removed from the dataclass (it had a `field(default_factory=list)`). The `basic_state` fixture (line 44-58) already does NOT include `daily_log_today`; add it (`"daily_log_today": []`) so unit tests of nodes that read state get a sane default.
- `tests/unit/test_response_node.py` (specifically lines 585-700) — tests that pass `daily_log_today=logs` and `daily_log_today=[]` to `ContextSchema` (lines 647 and 679). These need to move from the `ContextSchema(...)` call to `state["daily_log_today"] = logs`. Look at how `_make_state()` is constructed in this file (search for `def _make_state`) and update accordingly.
- `tests/unit/test_gateway.py` (lines 50, 82, 128-290) — every test mocks `_load_todays_log` and asserts `daily_log_today=[]` is passed to `_call_langgraph`. Both must be removed: drop the `@patch("bot.gateway._load_todays_log", …)` decorators, drop the `daily_log_today=[]` assertions on the mock-call kwargs, drop the corresponding parameter from each test method signature.

### New Files to Create

- `src/agents/nodes/load_daily_context_node.py` — new graph node implementing the loader. ~25 lines. Async, accepts `state: AgentState` and `runtime: Runtime[ContextSchema]`, calls `get_todays_logs_serialized(session, runtime.context.user_id)` inside an `async with get_async_db_session() as session:` block, returns `{"daily_log_today": logs}`.
- `tests/unit/test_load_daily_context_node.py` — unit tests for the new node. Mock `get_todays_logs_serialized` (or the whole DB session — see existing patterns in `tests/unit/test_commit_node.py` if it exists). Cover: empty result, non-empty result, runtime context with valid user_id.

### Relevant Documentation — YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LangGraph: Conditional edges](https://langchain-ai.github.io/langgraph/concepts/low_level/#conditional-edges) — pattern for `add_conditional_edges` with a routing function. We use this to dispatch from `load_daily_context` to either `input_parser` (fresh turn) or `response` (post-commit refresh).
  - Why: the loader has two downstream destinations. Plain `add_edge` won't work.
- [LangGraph: State channels and reducers](https://langchain-ai.github.io/langgraph/concepts/low_level/#state) — confirms that returning `{"field_name": value}` from a node merges into state without needing a custom reducer. `daily_log_today` is a plain `List[dict]` — last-write-wins is correct semantics here (each loader run overwrites).
  - Why: ensures we don't accidentally accumulate logs across turns.
- [LangGraph: `set_entry_point` vs entry-edge](https://langchain-ai.github.io/langgraph/concepts/low_level/#start-node) — `set_entry_point("load_daily_context")` vs `add_edge(START, "load_daily_context")`. Either works; pick whichever matches the codebase convention (current code uses `set_entry_point`, line 54 in `nutritionist.py`).
  - Why: stay consistent with how the graph is currently wired.
- (Use the `docs-langchain` MCP server when verifying any of the above signatures against the installed LangGraph version. The codebase is on LangGraph v1.x — `pyproject.toml` will have the exact pin.)

### Patterns to Follow

**Node signature pattern** (from `src/agents/nodes/food_search_node.py:11`):
```python
async def food_search_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    user_id = runtime.context.user_id
    # ... use the user_id with services/tools ...
    return {"some_state_field": result}
```
The new loader follows this exact shape.

**Async DB session pattern** (used inside `@tool` wrappers in `src/services/daily_log_service.py:260-274`):
```python
async with get_async_db_session() as session:
    logs = await get_todays_logs_serialized(session, user_id)
```
The new loader uses the same idiom — but as a node, not a `@tool`. (Tools are framework-free; nodes already have framework context.)

**Logging** (from `src/agents/nodes/commit_node.py:11, 26`):
```python
import structlog
logger = structlog.get_logger(__name__)
# ...
logger.info("Loading daily context", user_id=user_id, count=len(logs))
```
Use structlog with module-level logger and structured kwargs. Do not use `f-strings` for log messages.

**Naming conventions**:
- Module: `load_daily_context_node.py` (mirrors `food_search_node.py`, `commit_node.py`, `stats_node.py`).
- Function: `load_daily_context` (mirrors the node-id used in graph wiring; matches the file's primary export).
- Graph node id: `"load_daily_context"`.

**Conditional edge function pattern** (from `src/agents/nutritionist.py:21-29`):
```python
def route_parser(state: AgentState):
    action = state.get("last_action")
    if action in ["LOG_FOOD", "QUERY_FOOD_INFO"]:
        return "food_search"
    # ...
    return "response"
```
The new `route_after_load_daily_context` follows the same shape — read `state["last_action"]`, return a string key matching the conditional-edge map.

**State field addition pattern** (from `src/agents/state.py:166`):
TypedDict field, plain Python type, no reducer annotation needed for last-write-wins:
```python
daily_log_today: List[dict]
```

**Test pattern for nodes that hit the DB via an `async with` block**:
Look at how `tests/unit/test_commit_node.py` (if it exists) mocks `log_food_entry` and `create_food_item` via `tests/conftest.py:150-170`. For the new loader, you'll either:
- Mock `get_todays_logs_serialized` directly via `@patch("src.agents.nodes.load_daily_context_node.get_todays_logs_serialized")`, OR
- Mock `get_async_db_session` to yield a `MagicMock` session and assert the call shape.
The first is simpler — the loader is thin enough that you primarily care about the result reaching state.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — Schema and Service Wiring

State schema is updated first so subsequent code can reference the new field with type-checking confidence. No graph behavior changes yet.

**Tasks:**
- Add `daily_log_today: List[dict]` to `AgentState` (`src/agents/state.py`).
- Update `basic_state` fixture in `tests/conftest.py` to include `"daily_log_today": []`.

### Phase 2: Core Implementation — New Loader Node

The loader is the central new piece. Build and unit-test it in isolation before wiring into the graph.

**Tasks:**
- Create `src/agents/nodes/load_daily_context_node.py` with the loader function.
- Create `tests/unit/test_load_daily_context_node.py` with unit tests.

### Phase 3: Integration — Graph Topology Changes

Rewire the graph so the loader runs at entry and after commit. Switch `response_node` to read from state. Remove gateway plumbing.

**Tasks:**
- Update `src/agents/nutritionist.py`: register the node, change entry point, add conditional edge, replace `commit → response` edge.
- Update `src/agents/nodes/response_node.py`: read `state["daily_log_today"]` instead of `runtime.context.daily_log_today`.
- Remove `daily_log_today` from `ContextSchema` (`src/context.py`).
- Strip gateway plumbing in `bot/gateway.py`.

### Phase 4: Test Migration

Existing tests assume the old contract. Update them to the new model.

**Tasks:**
- Update `tests/unit/test_response_node.py`: move `daily_log_today` from `ContextSchema(...)` calls to `state["daily_log_today"]`.
- Update `tests/unit/test_gateway.py`: remove all `_load_todays_log` mocks and `daily_log_today=[]` assertions.
- Run unit, integration, and graph-API suites; fix any remaining fallout.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### 1. UPDATE `src/agents/state.py`

- **IMPLEMENT**: Add `daily_log_today: List[dict]` to the `AgentState` TypedDict (after `pending_confirmations`, line 166). Update the docstring's `Attributes:` block to describe the new field: *"daily_log_today: Today's serialized food logs (Israel-local timestamps), populated by load_daily_context node at entry and after commit."*
- **PATTERN**: Mirror the `daily_log_report: List[QueriedLog]` field at line 158 — same shape (`List[...]`), no reducer annotation. Use plain `List[dict]` rather than `List[QueriedLog]` because `_serialize_log` emits a superset (extra `category`, `tag`, `serving_amount_g` fields when coach mapping is present).
- **IMPORTS**: `List` is already imported at line 2.
- **GOTCHA**: Do not add `Annotated[..., add_messages]` or any reducer — last-write-wins is correct (each loader run overwrites the previous turn's value).
- **VALIDATE**: `uv run python -c "from src.agents.state import AgentState; assert 'daily_log_today' in AgentState.__annotations__"`

### 2. UPDATE `tests/conftest.py`

- **IMPLEMENT**: In the `basic_state` fixture (line 44-58), add `"daily_log_today": []` to the returned dict.
- **PATTERN**: Mirror the existing `"daily_log_report": []` line.
- **IMPORTS**: None.
- **GOTCHA**: This fixture is reused across many unit tests. Adding a key with default `[]` is safe (matches the empty-state convention).
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -k "test_response" --collect-only` — should still collect tests without errors.

### 3. CREATE `src/agents/nodes/load_daily_context_node.py`

- **IMPLEMENT**: New file. Single async function `load_daily_context(state, runtime)` that opens a DB session, calls `get_todays_logs_serialized`, and returns `{"daily_log_today": logs}`. Module-level `structlog` logger.

  ```python
  import structlog
  from langgraph.runtime import Runtime

  from src.agents.state import AgentState
  from src.context import ContextSchema
  from src.database import get_async_db_session
  from src.services.daily_log_service import get_todays_logs_serialized

  logger = structlog.get_logger(__name__)


  async def load_daily_context(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
      """Fetch today's food log into state.

      Runs at graph entry (every turn) and after commit_node (refresh after DB writes).
      The entry-edge run guarantees cross-turn state persistence is harmless because
      every turn's first execution overwrites the field.

      See docs/adr/0002-daily-log-loader-node-into-state.md.
      """
      user_id = runtime.context.user_id
      async with get_async_db_session() as session:
          logs = await get_todays_logs_serialized(session, user_id)
      logger.info("Loaded daily context", user_id=user_id, log_count=len(logs))
      return {"daily_log_today": logs}
  ```
- **PATTERN**: Node signature mirrors `src/agents/nodes/food_search_node.py:11` (state + runtime, async, dict return). DB session pattern mirrors `src/services/daily_log_service.py:260` (`async with get_async_db_session() as session:`).
- **IMPORTS**: `structlog`, `Runtime`, `AgentState`, `ContextSchema`, `get_async_db_session`, `get_todays_logs_serialized`.
- **GOTCHA**: Do **not** import the `query_food_logs` tool — that tool is for the stats flow (arbitrary date ranges) and uses a different `func.date()` comparison that has the known UTC-vs-Israel boundary bug. `get_todays_logs_serialized` is the correct function and already encapsulates the "today in Israel" computation.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.load_daily_context_node import load_daily_context; import inspect; assert inspect.iscoroutinefunction(load_daily_context)"`

### 4. CREATE `tests/unit/test_load_daily_context_node.py`

- **IMPLEMENT**: Unit tests covering:
  1. Returns `{"daily_log_today": <list>}` with the data from `get_todays_logs_serialized`.
  2. Returns `{"daily_log_today": []}` when the service returns an empty list.
  3. Reads `user_id` from `runtime.context.user_id` and passes it to the service.

  Mock `get_todays_logs_serialized` directly:
  ```python
  from unittest.mock import AsyncMock, patch
  import pytest

  from src.agents.nodes.load_daily_context_node import load_daily_context
  from tests.conftest import TEST_RUNTIME_A, TEST_USER_A


  class TestLoadDailyContext:
      @pytest.mark.asyncio
      @patch("src.agents.nodes.load_daily_context_node.get_todays_logs_serialized", new_callable=AsyncMock)
      @patch("src.agents.nodes.load_daily_context_node.get_async_db_session")
      async def test_returns_logs_from_service(self, mock_session, mock_get_logs, basic_state):
          mock_get_logs.return_value = [{"id": "abc", "amount_g": 100, "calories": 200,
                                         "protein": 20, "carbs": 0, "fat": 5,
                                         "timestamp": "2026-04-22T22:00:00+03:00",
                                         "meal_type": None, "original_text": "test", "food_id": None}]
          mock_session.return_value.__aenter__.return_value = AsyncMock()
          result = await load_daily_context(basic_state, TEST_RUNTIME_A)
          assert "daily_log_today" in result
          assert len(result["daily_log_today"]) == 1
          mock_get_logs.assert_awaited_once()
          assert mock_get_logs.call_args.args[1] == TEST_USER_A
      # ... (similar for empty + user_id pass-through)
  ```
- **PATTERN**: Mock-decorator and `AsyncMock` patterns mirror `tests/conftest.py:150-170` and existing node tests in `tests/unit/`.
- **IMPORTS**: `AsyncMock`, `patch`, `pytest`, the new node, `TEST_RUNTIME_A`, `TEST_USER_A` from `tests.conftest`.
- **GOTCHA**: `get_async_db_session` is an async context manager — mock both `__aenter__` and `__aexit__`. Easier to mock `get_todays_logs_serialized` and let the session mock be a no-op.
- **VALIDATE**: `uv run pytest tests/unit/test_load_daily_context_node.py -v`

### 5. UPDATE `src/agents/nutritionist.py` — register node, rewire edges

- **IMPLEMENT**:
  1. Add import: `from src.agents.nodes.load_daily_context_node import load_daily_context`.
  2. Inside `define_graph`, add a new routing function:
     ```python
     def route_after_load_daily_context(state: AgentState):
         """Loader runs at entry (fresh turn) and after commit (refresh).
         Distinguish via last_action: LOGGED means we just came from commit."""
         if state.get("last_action") == "LOGGED":
             return "response"
         return "input_parser"
     ```
  3. Register the node: `workflow.add_node("load_daily_context", load_daily_context)`.
  4. Replace `workflow.set_entry_point("input_parser")` with `workflow.set_entry_point("load_daily_context")`.
  5. Add the conditional edge:
     ```python
     workflow.add_conditional_edges(
         "load_daily_context",
         route_after_load_daily_context,
         {"input_parser": "input_parser", "response": "response"},
     )
     ```
  6. Replace `workflow.add_edge("commit", "response")` with `workflow.add_edge("commit", "load_daily_context")`.
- **PATTERN**: Conditional edge mirrors existing `route_parser` (line 21-29) and its registration (line 56-65).
- **IMPORTS**: As above; ensure import order matches the existing alphabetical block at lines 3-13.
- **GOTCHA**:
  - Do **not** delete the `commit → response` edge before adding the new `commit → load_daily_context` edge — the file is small enough that a single edit is fine, but if you split the work, sequence matters for graph compilation.
  - The conditional-edge function must return a string that exists as a key in the dict map. A typo silently routes to `END`.
  - Other inbound paths to `response` (`stats_lookup → response`, `personal_stats → response`, `agent_selection → response`, `input_parser → response`) are unchanged — they bypass the loader because they don't mutate `daily_logs`.
- **VALIDATE**: `uv run python -c "import asyncio; from src.agents.nutritionist import define_graph; g = asyncio.run(define_graph()); print(sorted(g.nodes))" ` — should include `load_daily_context`.

### 6. UPDATE `src/agents/nodes/response_node.py` — read from state

- **IMPLEMENT**: At line 225, change:
  ```python
  daily_log = context.daily_log_today if context.daily_log_today is not None else []
  ```
  to:
  ```python
  daily_log = state.get("daily_log_today", [])
  ```
- **PATTERN**: `state.get(...)` with a default mirrors how other state fields are read in the same node (e.g. `state.get("messages", [])` at line 248).
- **IMPORTS**: None added; the `context` reference for `user_profile` (lines 210-211) stays.
- **GOTCHA**: Leave the `context.user_profile` access alone (lines 210-211, 217). Only `daily_log_today` moves out of context.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v` (some tests will still fail until Task 9 — that is expected at this point).

### 7. UPDATE `src/context.py` — remove field

- **IMPLEMENT**: Delete line 44 (`daily_log_today: list[dict] = field(default_factory=list)`) from the `ContextSchema` dataclass. Leave `user_id` and `user_profile` intact.
- **PATTERN**: Match the dataclass shape from before the 2026-04-17 daily-log injection landed — i.e., back to the PR #21 (nutrition_plan) era of `ContextSchema`.
- **IMPORTS**: If removing `field` leaves it unused, keep it — `user_profile` (line 43) still uses `field(default_factory=...)`.
- **GOTCHA**: Any leftover code anywhere referencing `runtime.context.daily_log_today` or `ContextSchema(daily_log_today=...)` will now break with `AttributeError` / `TypeError`. Tasks 6 and 9 cover the production and test sites; if any third caller exists (search before the next task), fix it here.
- **VALIDATE**: `uv run python -c "from src.context import ContextSchema; assert not hasattr(ContextSchema(), 'daily_log_today')"` AND `grep -rn 'daily_log_today' src bot tests | grep -v 'state\|AgentState\|test_load_daily_context'` — should show no `context.daily_log_today` references.

### 8. UPDATE `bot/gateway.py` — strip gateway plumbing

- **IMPLEMENT**: Remove the following:
  1. Line 31: import `from src.services.daily_log_service import get_todays_logs_serialized`.
  2. Lines 226-233: the entire `_load_todays_log` async helper.
  3. From the `_call_langgraph` signature (lines 90-117): the `daily_log_today: list[dict] | None = None` keyword arg, and the body lines `if daily_log_today is not None: body["context"]["daily_log_today"] = daily_log_today`.
  4. Line 324: `todays_log = await _load_todays_log(user_id)`.
  5. Lines 335 and 343: the `daily_log_today=todays_log` kwarg from both `_call_langgraph` calls (resume branch and new-input branch).
- **PATTERN**: Result should mirror the gateway shape *before* the 2026-04-17 daily-log injection landed — i.e., context body holds `user_id` and `user_profile` only.
- **IMPORTS**: Remove the `get_todays_logs_serialized` import. Do not remove `get_user_profile` or other unrelated imports.
- **GOTCHA**: `_load_todays_log` is referenced by tests that mock it (Task 10 covers their removal). If you remove the helper before updating the tests, those tests will fail with an `AttributeError` from the `@patch` decorator — sequence-wise, it's fine because Task 10 immediately follows.
- **VALIDATE**: `uv run python -c "from bot import gateway; assert not hasattr(gateway, '_load_todays_log')"` AND `grep -n daily_log_today bot/gateway.py` — should return no results.

### 9. UPDATE `tests/unit/test_response_node.py`

- **IMPLEMENT**:
  - For each test that currently passes `daily_log_today=...` to `_make_runtime` / `_make_mock_runtime` / `ContextSchema(...)` (lines 647 and 679 specifically, plus any others surfaced by `grep`):
    - Remove the `daily_log_today=` kwarg from the runtime/context construction.
    - Inject the same value into the state passed to the node: `state["daily_log_today"] = logs` (or `state["daily_log_today"] = []` for the empty case).
  - If a helper like `_make_state` exists in this file, consider adding a `daily_log_today` parameter to it (default `[]`) for cleanliness.
- **PATTERN**: Mirror existing state-construction in the same file — most tests construct state inline before calling the node. Adding one key is straightforward.
- **IMPORTS**: None.
- **GOTCHA**: After Task 7, passing `daily_log_today=` to `ContextSchema(...)` raises `TypeError: ContextSchema.__init__() got an unexpected keyword argument 'daily_log_today'`. The tests must be updated, not the dataclass restored.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v` — all tests pass.

### 10. UPDATE `tests/unit/test_gateway.py`

- **IMPLEMENT**:
  - Remove every `@patch("bot.gateway._load_todays_log", new_callable=AsyncMock, return_value=[])` decorator (occurrences at lines 128, 163, 198, 225, 252, 279).
  - Remove the corresponding parameter (`mock_load_todays_log`) from each affected test method's signature.
  - Remove every `daily_log_today=[]` line from `assert_called_*` / kwargs assertions on the `_call_langgraph` mock (lines 157, 191, plus any others).
  - Update the `body` payload assertion at line 50 area if applicable: `body["context"]` should now only contain `user_id` and (sometimes) `user_profile`.
- **PATTERN**: Inverse of how the daily-log injection landed in the 2026-04-17 commit (`commit_logs/2026-04-17_11-54-54_feat-daily-log-injection-and-israel-tz.md`).
- **IMPORTS**: None.
- **GOTCHA**: Decorator order and parameter order are coupled — if you remove a decorator, you must remove its corresponding mock parameter from the method signature, in the right position. (Decorators apply bottom-up; the bottom-most decorator's mock is the first parameter after `self`.)
- **VALIDATE**: `uv run pytest tests/unit/test_gateway.py -v` — all tests pass.

### 11. RUN full unit suite

- **IMPLEMENT**: `uv run pytest tests/unit/ -v`
- **PATTERN**: Pre-commit gate per CLAUDE.md.
- **IMPORTS**: N/A.
- **GOTCHA**: If unrelated tests fail (e.g., `test_commit_node.py`), inspect — it might be that they relied on an indirect behavior of the old wiring.
- **VALIDATE**: All unit tests pass with no regressions vs. baseline.

### 12. RUN integration suite

- **IMPLEMENT**: `uv run pytest tests/integration/ -v`
- **PATTERN**: Per CLAUDE.md, real Supabase DB. `tests/integration/test_daily_log_service.py` covers `get_todays_logs_serialized` and `_serialize_log` — should still pass without changes (we did not touch those).
- **IMPORTS**: N/A.
- **GOTCHA**: Integration tests need `SUPABASE_DB_URL` set; failures unrelated to this change should be surfaced and skipped if pre-existing.
- **VALIDATE**: All integration tests pass.

### 13. RUN graph-API suite (mandatory — graph topology changed)

- **IMPLEMENT**: `uv run pytest tests/graph_api/ -v -s`
- **PATTERN**: Required per CLAUDE.md whenever graph edges/nodes change. Will spin up a real LangGraph server.
- **IMPORTS**: N/A.
- **GOTCHA**: The HITL confirmation E2E test (`tests/graph_api/test_*` covering interrupt/resume) is the canary for the bug we fixed — if it now asserts a correct daily summary, beautiful. If it still passes against an old assertion, consider whether to add a new assertion verifying that the daily summary post-commit reflects the just-committed items.
- **VALIDATE**: All graph-API tests pass.

### 14. MANUAL smoke (recommended)

- **IMPLEMENT**: Run the bot locally with `POLLING_MODE=true` and reproduce the original bug:
  1. Send a multi-item food list in Hebrew or English.
  2. Confirm via "yes".
  3. Immediately ask "where am I today?" (or in Hebrew: "איפה אני עומד היום?").
  4. Verify the summary reflects the just-confirmed items (no undercounting).
- **PATTERN**: Mirrors the failure scenario from LangSmith thread `73ed31fb-…`.
- **IMPORTS**: N/A.
- **GOTCHA**: Bot needs `BOT_TOKEN`, `SUPABASE_DB_URL`, `LANGGRAPH_URL`, `OPENAI_API_KEY`, `BOT_PASSWORD_SEED` in `.env`. `langgraph dev` needs to be running on port 2024.
- **VALIDATE**: Visual confirmation in Telegram. Optionally compare with a fresh LangSmith trace of the corrected behavior.

---

## TESTING STRATEGY

### Unit Tests

- New file `tests/unit/test_load_daily_context_node.py` covers the loader in isolation (mocked DB).
- `tests/unit/test_response_node.py` updated so `daily_log_today` is injected via state, not context. Existing assertions on `_format_daily_log` rendering are unchanged (the formatter is untouched).
- `tests/unit/test_gateway.py` updated so it no longer asserts a behavior the gateway no longer has.

### Integration Tests

- `tests/integration/test_daily_log_service.py` (existing) — `get_todays_logs_serialized` + `_serialize_log` unchanged; no edits needed.
- No new integration test required — the new node is a thin wrapper around an already-tested service function.

### Graph-API Tests

- Mandatory full run after this change because graph topology changed (new node, new entry point, new conditional edge, rewired commit edge).
- If there is an existing HITL confirmation E2E test, either confirm it still passes or add an assertion verifying the post-commit response reflects the just-committed items. The latter would prevent regression of the original bug.

### Edge Cases

- **Empty log day** — `get_todays_logs_serialized` returns `[]`; loader writes `[]` to state; `_format_daily_log` renders the "Nothing logged yet today." line. Already covered by an existing test in `test_response_node.py`.
- **User with no profile but valid user_id** — loader does not depend on profile; it only needs `user_id`. No change to behavior.
- **Studio fallback (no bot)** — `ContextSchema` defaults to `DEFAULT_DEV_USER_ID`. Loader queries on that user. Whatever is in the DB for that user will appear. Studio behavior unchanged otherwise.
- **HITL resume turn that does NOT reach commit** (e.g. user replies "no, cancel")** — confirmation_node returns `Command(...)` routing somewhere other than commit. Loader does not re-run; response sees the entry-time snapshot. That's correct: nothing was written, so the snapshot is still fresh.
- **HITL resume turn that DOES reach commit** — commit writes rows; loader runs again; response sees fresh data. This is the bug fix.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check src/agents/nodes/load_daily_context_node.py src/agents/state.py src/agents/nutritionist.py src/agents/nodes/response_node.py src/context.py bot/gateway.py tests/conftest.py tests/unit/test_response_node.py tests/unit/test_gateway.py tests/unit/test_load_daily_context_node.py
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

### Level 4: Graph-API Tests (mandatory — graph changed)

```bash
uv run pytest tests/graph_api/ -v -s
```

### Level 5: Manual Smoke (Telegram)

Reproduce the LangSmith thread `73ed31fb-…` scenario locally with `POLLING_MODE=true`. Verify the post-commit summary matches the DB state.

---

## ACCEPTANCE CRITERIA

- [ ] `daily_log_today` field removed from `ContextSchema` (`src/context.py`).
- [ ] `daily_log_today: List[dict]` field added to `AgentState` (`src/agents/state.py`).
- [ ] `src/agents/nodes/load_daily_context_node.py` exists with the loader function.
- [ ] Graph entry point is `load_daily_context`; conditional edge routes to `input_parser` (fresh) or `response` (post-commit).
- [ ] `commit → load_daily_context` edge present; `commit → response` edge removed.
- [ ] `response_node` reads `state["daily_log_today"]`, not `runtime.context.daily_log_today`.
- [ ] `bot/gateway.py` no longer fetches the daily log or sends it in the HTTP context body.
- [ ] All unit, integration, and graph-API tests pass.
- [ ] Manual smoke confirms post-commit summary reflects just-committed items.
- [ ] No leftover references to `runtime.context.daily_log_today` anywhere in `src/`, `bot/`, or `tests/` (other than this plan and the ADR).

---

## COMPLETION CHECKLIST

- [ ] All 14 tasks completed in order
- [ ] Each task validation passed immediately
- [ ] `uv run ruff check` clean on all modified files
- [ ] Full unit suite passes: `uv run pytest tests/unit/ -v`
- [ ] Full integration suite passes: `uv run pytest tests/integration/ -v`
- [ ] Full graph-API suite passes: `uv run pytest tests/graph_api/ -v -s`
- [ ] Manual smoke test with the Telegram bot reproduces correct post-commit summary
- [ ] No regressions in existing functionality (Hebrew input parsing, HITL flow, stats lookup, personal stats logging)
- [ ] CLAUDE.md updated by `sync-context` to reflect that `daily_log_today` lives in state, not context (post-implementation, separate task)

---

## NOTES

### Design decisions captured in ADR-0002

- `daily_log_today` is graph-internal mutable data, not ambient request context. State is its home.
- The loader is the single source of truth for fetching today's log into the graph. Nodes do not self-fetch this field.
- The "loader after mutation" rule generalizes: any future node that mutates data the loader reads must add a refresh edge into the loader before any consumer node runs in the same request.

### Why a single loader with a conditional edge, not two separate nodes

A second-node approach (`load_daily_context_entry`, `load_daily_context_refresh`) would duplicate code with no behavioral difference. A single node + conditional edge is more honest: the action is identical, only the downstream destination differs.

### What is *not* changing

- `user_id` and `user_profile` continue to flow through `ContextSchema`. They are stable per request and should stay there.
- `daily_log_report` (different state field, used by `stats_lookup_node` and `commit_node`) is untouched. It carries arbitrary date-range query results, not "today's snapshot."
- `_serialize_log`, `get_todays_logs_serialized`, and `_format_daily_log` are unchanged. The bug was about *when* the data is fetched and *where* it lives, not how it's shaped or rendered.
- The bot's `user_profile` cache and onboarding flow are unaffected.

### Out of scope / follow-ups

- **CLAUDE.md update** — the `Runtime Context + User Profile` row in the Architecture Patterns table mentions `daily_log_today` as living in `ContextSchema`. After this lands, run `sync-context` (or update manually) so CLAUDE.md matches reality.
- **Bug 1 (UTC date boundary)** — `get_todays_logs_serialized` still inherits the `func.date(timestamp) == target_date` issue from `get_logs_by_date`. Logs made 00:00–03:00 Israel local fall on the previous UTC date. This is pre-existing and tracked separately in `brain/TASKS.md` (Maintenance tier).
- **Future consumers** — coaching node, end-of-day summary, plan-aware estimation in `calculate_macros_node`. Each will read `state["daily_log_today"]` for free.
- **Pre-commit hook for missing refresh edges** — the ADR's revisit trigger names "3+ DB-mutating nodes" as the point to consider auto-refresh. Until then, manual edge wiring is the rule. A lightweight defense would be a graph-validation test asserting that every node in a hard-coded list of "mutators" routes through `load_daily_context` before reaching `response` — out of scope for this plan but worth filing as a follow-up.

### Confidence

**8/10** for one-pass implementation success. The risk areas are:
- (a) test-decorator parameter ordering in `test_gateway.py` (mechanical but error-prone if hurried),
- (b) the conditional edge logic in `nutritionist.py` (verify the routing function returns string keys that exist in the dict map, and verify that `route_after_load_daily_context` correctly detects the post-commit path via `last_action == "LOGGED"`),
- (c) the graph-API suite must actually run — if the executor skips it because the local Postgres or langgraph dev server isn't available, the topology change goes un-validated.
