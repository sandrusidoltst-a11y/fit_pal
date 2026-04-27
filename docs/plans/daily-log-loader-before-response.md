# Feature: `daily_log_today` loader node — placed *only before* `response_node`

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

> **Relationship to the previous plan**: This plan supersedes `docs/plans/daily-log-loader-node-into-state.md` (the "entry + post-commit" design). Same goal — fix the staleness bug from LangSmith thread `73ed31fb-…` and implement ADR-0002 — but with a structurally simpler graph topology. Reasoning for the change: today `response_node` is the **only** consumer of `daily_log_today`, and any future mid-graph consumer can add its own loader edge at the time it actually exists (same wiring complexity, just paid when needed). Adopting the simpler design now applies YAGNI correctly. ADR-0002 will be amended (or superseded by ADR-0003) to reflect this once the implementation lands.

## Feature Description

Implements [ADR-0002](../adr/0002-daily-log-loader-node-into-state.md) — moves `daily_log_today` from `ContextSchema` (gateway-injected, request-scoped, immutable) to `AgentState`, populated by a new graph node `load_daily_context`.

Unlike the previous plan, the loader sits in **one place**: as the single hop between any node and `response_node`. Every existing path that ends in `response` is rewired to go *through* `load_daily_context` first. The graph entry point and the entry path are unchanged.

This still fixes the production bug observed in LangSmith thread `73ed31fb-8391-4c97-a05f-a4b672c6fcd5` (2026-04-22): a HITL-resume turn caused `commit_node` to write new food rows, but `response_node` (running later in the same request) reported stale numbers because the gateway's pre-request snapshot in `runtime.context` could not be refreshed mid-graph. After this change, `response_node` sees fresh data on every path because the loader runs immediately before it.

## User Story

As a **trainee**,
I want the bot's daily summary to reflect what I just confirmed in the same turn,
So that I am not given a wrong picture and forced to ask "are you sure?" on every confirmation.

As **Dolev (the developer)**,
I want a graph topology that is the minimum viable shape for today's consumer set,
So that I do not pay forward-compat cost for hypothetical consumers and can add edges only when real consumers arrive.

## Problem Statement

Same as previous plan: `runtime.context` is request-scoped and immutable from inside the graph; `commit_node` writes new rows mid-request; `response_node` runs later in the same request and reads the stale snapshot. Per-message gateway re-fetch does not help because the staleness gap is *within* a single request.

## Solution Statement

1. Remove `daily_log_today` from `ContextSchema`. Add `daily_log_today: list[dict]` to `AgentState`.
2. Create a new node `load_daily_context` that calls `get_todays_logs_serialized(session, user_id)` and writes the result to `state["daily_log_today"]`.
3. Place the loader as the **only** hop between any node and `response_node`. Specifically rewire:
   - `route_parser` (returns to `response` for CHITCHAT/default) → returns to `load_daily_context`
   - `route_after_selection` (returns to `response` for non-SELECTED/NO_MATCH actions) → returns to `load_daily_context`
   - `commit → response` direct edge → `commit → load_daily_context`
   - `stats_lookup → response` direct edge → `stats_lookup → load_daily_context`
   - `personal_stats → response` direct edge → `personal_stats → load_daily_context`
4. Add a single new edge: `load_daily_context → response`.
5. Update `response_node` to read `state["daily_log_today"]` instead of `runtime.context.daily_log_today`.
6. Strip `daily_log_today` plumbing from `bot/gateway.py`: remove `_load_todays_log` helper, remove the `daily_log_today` kwarg on `_call_langgraph`, remove the `body["context"]["daily_log_today"] = …` injection, remove the `get_todays_logs_serialized` import.

The cross-turn state-persistence concern (state lives across turns in the thread checkpointer) is neutralized because `load_daily_context` runs on every path that reaches `response_node`, always overwriting the field with a fresh value before the consumer reads it.

## Feature Metadata

**Feature Type**: Refactor (architectural — implements ADR-0002)
**Estimated Complexity**: Low–Medium
**Primary Systems Affected**:
- `src/context.py` (remove field)
- `src/agents/state.py` (add field)
- `src/agents/nutritionist.py` (graph topology: 2 routing-fn returns + 3 direct edges + 1 new edge)
- `src/agents/nodes/response_node.py` (read site)
- `bot/gateway.py` (remove fetch + injection)
- New node file: `src/agents/nodes/load_daily_context_node.py`
- Tests: `tests/conftest.py`, `tests/unit/test_response_node.py`, `tests/unit/test_gateway.py`, `tests/unit/test_feedback_integration.py`, new `tests/unit/test_load_daily_context_node.py`

**Dependencies**: None new. `get_todays_logs_serialized` already exists in `src/services/daily_log_service.py:228`. `get_async_db_session` already used by service-layer code.

**Resolves**:
- ADR-0002 (this is its implementation, with the simpler topology)
- The thread `73ed31fb-…` undercounting bug (audit done 2026-04-25)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `docs/adr/0002-daily-log-loader-node-into-state.md` (full file) — the decision this plan implements. The "Decision" section currently describes the entry-loader topology; that wording will be amended after this plan ships. The Context, Alternatives, and Consequences sections still hold.
- `docs/plans/daily-log-loader-node-into-state.md` (full file) — the previous plan. Read for historical context only. The pattern files, helper choices, and validation strategy carry over; the **graph topology is different** in this plan.
- `docs/patterns/runtime-context.md` (lines 13-30) — the carve-out that justifies moving `daily_log_today` out of `ContextSchema`. Confirms `user_id` and `user_profile` stay in context.
- `src/context.py` (full file, 51 lines) — `ContextSchema` dataclass. Line 44 holds the `daily_log_today` field to be removed. Do **not** touch `user_id` or `user_profile`.
- `src/agents/state.py` (lines 137-167) — `AgentState` TypedDict. Add `daily_log_today: List[dict]` here. Mirror `daily_log_report: List[QueriedLog]` field shape (line 158); use `List[dict]` not `List[QueriedLog]` because `_serialize_log` emits a superset (extra `category`, `tag`, `serving_amount_g` fields when coach mapping is present).
- `src/agents/nutritionist.py` (full file, 95 lines) — graph wiring. The two routing functions (`route_parser`, `route_after_selection`) and three direct edges (`commit → response`, `stats_lookup → response`, `personal_stats → response`) all change. Entry point and the `response → END` edge are unchanged.
- `src/agents/nodes/response_node.py` (lines 199-255 specifically; full file for surrounding helpers) — current consumer of `context.daily_log_today` at line 225. Change to `state.get("daily_log_today", [])`. The `_format_daily_log` helper (line 40) and the response_node signature stay the same.
- `src/agents/nodes/commit_node.py` (full file, 109 lines) — body unchanged. The graph edge out of commit changes from `→ response` to `→ load_daily_context`. `commit_node` still updates the unrelated `daily_log_report` field (used by stats flow); leave that alone.
- `src/agents/nodes/stats_node.py` (full file, 37 lines) — body unchanged. Edge changes only.
- `src/agents/nodes/personal_stats_node.py` (full file) — body unchanged. Edge changes only.
- `src/services/daily_log_service.py` (lines 170-225 for `_serialize_log`; lines 228-243 for `get_todays_logs_serialized`) — the fetcher already exists. The new loader node calls it. Behavior unchanged.
- `src/database.py` — defines `get_async_db_session` async context manager. Pattern: `async with get_async_db_session() as session:` followed by an awaited service call.
- `bot/gateway.py` (lines 31, 90-117, 220-233, 294-344) — the gateway pieces to delete (same as previous plan):
  - Line 31: `from src.services.daily_log_service import get_todays_logs_serialized` import
  - Lines 90-117: `_call_langgraph` signature `daily_log_today: list[dict] | None = None` kwarg + body `if daily_log_today is not None: body["context"]["daily_log_today"] = daily_log_today`
  - Lines 226-233: `_load_todays_log(user_id)` helper
  - Line 324: `todays_log = await _load_todays_log(user_id)`
  - Lines 335 and 343: `daily_log_today=todays_log` kwarg in both `_call_langgraph` call sites
- `tests/conftest.py` (lines 27-58) — `_make_mock_runtime` and `basic_state` fixture. After `daily_log_today` is removed from `ContextSchema`, the runtime mock still works (it never passed `daily_log_today=`). Add `"daily_log_today": []` to `basic_state`.
- `tests/unit/test_response_node.py` (lines 585-700) — two tests pass `daily_log_today=` to `ContextSchema(...)` (lines 647 and 679). Move both to `state["daily_log_today"]` via the `_make_state(...)` helper.
- `tests/unit/test_gateway.py` (lines 50, 82, 128-290) — every test mocks `_load_todays_log` and asserts `daily_log_today=[]` on `_call_langgraph`. Both removed (decorator + parameter + assertion).
- `tests/unit/test_feedback_integration.py` (full file) — patches every node imported in `nutritionist.py` to keep the test graph offline. Will need a new `mock_loader` patch entry for `load_daily_context` so it doesn't hit the real DB.

### New Files to Create

- `src/agents/nodes/load_daily_context_node.py` — new graph node implementing the loader. ~25 lines. Async, accepts `state: AgentState` and `runtime: Runtime[ContextSchema]`, calls `get_todays_logs_serialized(session, runtime.context.user_id)` inside an `async with get_async_db_session() as session:` block, returns `{"daily_log_today": logs}`. Includes the `runtime.context is None` defensive fallback (mirrors `response_node:210`) so unit tests / Studio invocations without context do not raise `AttributeError`.
- `tests/unit/test_load_daily_context_node.py` — unit tests for the new node. Mock `get_todays_logs_serialized` and the async session context manager. Cover: returns service result, returns empty list when service returns empty, passes `user_id` from `runtime.context` to the service.

### Relevant Documentation — YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LangGraph: State channels and reducers](https://langchain-ai.github.io/langgraph/concepts/low_level/#state) — confirms returning `{"field_name": value}` from a node merges into state without needing a custom reducer. Last-write-wins is correct semantics for `daily_log_today` (each loader run overwrites).
- [LangGraph: Conditional edges](https://langchain-ai.github.io/langgraph/concepts/low_level/#conditional-edges) — pattern for `add_conditional_edges` with a routing function. We are *modifying the return values* of two existing routing functions, not adding new conditional edges. The conditional-edge dict maps must be updated to include `load_daily_context` as a destination.
- (Use the `docs-langchain` MCP server when verifying any signature against the installed LangGraph version. The codebase is on LangGraph v1.x — `pyproject.toml` will have the exact pin.)

### Patterns to Follow

**Node signature pattern** (from `src/agents/nodes/food_search_node.py:11`):
```python
async def food_search_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    user_id = runtime.context.user_id
    return {"some_state_field": result}
```

**Async DB session pattern** (used inside `@tool` wrappers in `src/services/daily_log_service.py:260-274`):
```python
async with get_async_db_session() as session:
    logs = await get_todays_logs_serialized(session, user_id)
```

**Defensive context guard** (mirrors `src/agents/nodes/response_node.py:210`):
```python
context = runtime.context if runtime.context is not None else ContextSchema()
user_id = context.user_id
```
Required for invocations that don't supply context (e.g. `test_feedback_integration.py` invoking the graph without a `context` body).

**Logging** (from `src/agents/nodes/commit_node.py:11, 26`):
```python
import structlog
logger = structlog.get_logger(__name__)
logger.info("Loaded daily context", user_id=user_id, log_count=len(logs))
```

**Naming conventions**:
- Module: `load_daily_context_node.py` (mirrors `food_search_node.py`, `commit_node.py`, `stats_node.py`).
- Function: `load_daily_context`.
- Graph node id: `"load_daily_context"`.

**State field addition pattern** (from `src/agents/state.py:166`):
```python
daily_log_today: List[dict]
```

**Routing-function pattern** (from `src/agents/nutritionist.py:21-29`): change the string the function returns; ensure the conditional-edge map dict (line 56-65, 69-76) has the new destination key.

**Test pattern for nodes that hit the DB via `async with`**: mock `get_todays_logs_serialized` directly with `@patch("src.agents.nodes.load_daily_context_node.get_todays_logs_serialized", new_callable=AsyncMock)` and provide a fake async-context-manager for `get_async_db_session`. Pattern:
```python
from contextlib import asynccontextmanager
@asynccontextmanager
async def _fake_session_cm():
    yield MagicMock()

@patch("src.agents.nodes.load_daily_context_node.get_async_db_session", return_value=_fake_session_cm())
```

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — Schema and Service Wiring

State schema is updated first so subsequent code can reference the new field.

**Tasks:**
- Add `daily_log_today: List[dict]` to `AgentState` (`src/agents/state.py`).
- Update `basic_state` fixture in `tests/conftest.py` to include `"daily_log_today": []`.

### Phase 2: Core Implementation — New Loader Node

Build and unit-test the loader in isolation before wiring into the graph.

**Tasks:**
- Create `src/agents/nodes/load_daily_context_node.py`.
- Create `tests/unit/test_load_daily_context_node.py`.

### Phase 3: Integration — Graph Topology Changes

Rewire the graph so the loader runs immediately before `response`. Switch `response_node` to read from state. Remove gateway plumbing.

**Tasks:**
- Update `src/agents/nutritionist.py`: register the node, change routing function returns, rewire three direct edges, add the single `load_daily_context → response` edge.
- Update `src/agents/nodes/response_node.py`: read `state["daily_log_today"]` instead of `runtime.context.daily_log_today`.
- Remove `daily_log_today` from `ContextSchema` (`src/context.py`).
- Strip gateway plumbing in `bot/gateway.py`.

### Phase 4: Test Migration

**Tasks:**
- Update `tests/unit/test_response_node.py`: move `daily_log_today` from `ContextSchema(...)` calls to `state["daily_log_today"]`.
- Update `tests/unit/test_gateway.py`: remove all `_load_todays_log` mocks and `daily_log_today=[]` assertions.
- Update `tests/unit/test_feedback_integration.py`: add `mock_loader` patch so the loader does not hit the real DB inside the in-memory graph run.
- Run unit, integration, and graph-API suites; fix any remaining fallout.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### 1. UPDATE `src/agents/state.py`

- **IMPLEMENT**: Add `daily_log_today: List[dict]` to the `AgentState` TypedDict (after `pending_confirmations`, line 166). Update the docstring's `Attributes:` block: *"daily_log_today: Today's serialized food logs (Israel-local timestamps), populated by load_daily_context node immediately before response_node runs."*
- **PATTERN**: Mirror the `daily_log_report: List[QueriedLog]` field at line 158. Use `List[dict]`, not `List[QueriedLog]`, because `_serialize_log` emits a superset.
- **IMPORTS**: `List` already imported at line 2.
- **GOTCHA**: Do not add a reducer annotation — last-write-wins is correct (the loader overwrites every time it runs).
- **VALIDATE**: `uv run python -c "from src.agents.state import AgentState; assert 'daily_log_today' in AgentState.__annotations__"`

### 2. UPDATE `tests/conftest.py`

- **IMPLEMENT**: In the `basic_state` fixture (line 44-58), add `"daily_log_today": []` to the returned dict.
- **PATTERN**: Mirror the existing `"daily_log_report": []` line.
- **IMPORTS**: None.
- **GOTCHA**: This fixture is reused across many unit tests. Adding a key with default `[]` is safe.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py --collect-only -q | head -20`

### 3. CREATE `src/agents/nodes/load_daily_context_node.py`

- **IMPLEMENT**:
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

      Runs immediately before response_node on every path. Always-fresh by
      construction — no consumer reads daily_log_today without the loader
      having just written it.

      See docs/adr/0002-daily-log-loader-node-into-state.md.
      """
      # Defensive fallback for graph invocations without context (Studio default,
      # some unit/integration tests). Mirrors response_node's same guard.
      context = runtime.context if runtime.context is not None else ContextSchema()
      user_id = context.user_id
      async with get_async_db_session() as session:
          logs = await get_todays_logs_serialized(session, user_id)
      logger.info("Loaded daily context", user_id=user_id, log_count=len(logs))
      return {"daily_log_today": logs}
  ```
- **PATTERN**: Node signature mirrors `src/agents/nodes/food_search_node.py:11`. DB session pattern mirrors `src/services/daily_log_service.py:260`. Defensive guard mirrors `src/agents/nodes/response_node.py:210`.
- **IMPORTS**: `structlog`, `Runtime`, `AgentState`, `ContextSchema`, `get_async_db_session`, `get_todays_logs_serialized`.
- **GOTCHA**: Do **not** import the `query_food_logs` tool — that tool uses a `func.date()` comparison with a known UTC-vs-Israel boundary bug. `get_todays_logs_serialized` already encapsulates "today in Israel."
- **VALIDATE**: `uv run python -c "from src.agents.nodes.load_daily_context_node import load_daily_context; import inspect; assert inspect.iscoroutinefunction(load_daily_context)"`

### 4. CREATE `tests/unit/test_load_daily_context_node.py`

- **IMPLEMENT**: Three tests covering: returns logs from service; returns empty list when service returns empty; passes `user_id` from runtime context to the service. Use the patch + asynccontextmanager pattern from the *Patterns to Follow* section. Reference: previous plan (`docs/plans/daily-log-loader-node-into-state.md`) Task 4 has a working code skeleton.
- **PATTERN**: Mock-decorator + `AsyncMock` patterns from `tests/conftest.py:150-170` and existing node tests.
- **IMPORTS**: `AsyncMock`, `patch`, `MagicMock`, `pytest`, `asynccontextmanager`, the new node, `TEST_RUNTIME_A`, `TEST_USER_A` from `tests.conftest`.
- **GOTCHA**: `get_async_db_session` is an async context manager. Use a real `@asynccontextmanager` helper that yields a `MagicMock` — mocking `__aenter__` / `__aexit__` directly tends to be brittle.
- **VALIDATE**: `uv run pytest tests/unit/test_load_daily_context_node.py -v`

### 5. UPDATE `src/agents/nutritionist.py` — register node and rewire edges

- **IMPLEMENT**:
  1. Add import: `from src.agents.nodes.load_daily_context_node import load_daily_context` (alphabetical position).
  2. Inside `define_graph`, change `route_parser` (lines 21-29): replace the final `return "response"` (line 29) with `return "load_daily_context"`. Keep the other branches unchanged.
  3. Change `route_after_selection` (lines 31-36): replace `return "response"` (line 36) with `return "load_daily_context"`.
  4. Register the node: `workflow.add_node("load_daily_context", load_daily_context)` (alongside existing add_node calls).
  5. Update both conditional-edge maps so `load_daily_context` is a valid destination key:
     ```python
     workflow.add_conditional_edges(
         "input_parser",
         route_parser,
         {
             "food_search": "food_search",
             "stats_lookup": "stats_lookup",
             "personal_stats": "personal_stats",
             "load_daily_context": "load_daily_context",
         },
     )
     ```
     ```python
     workflow.add_conditional_edges(
         "agent_selection",
         route_after_selection,
         {
             "calculate_macros": "calculate_macros",
             "load_daily_context": "load_daily_context",
         },
     )
     ```
     Removing the `"response"` keys is correct — those routing functions no longer return `"response"`.
  6. Rewire three direct edges:
     - `workflow.add_edge("commit", "response")` → `workflow.add_edge("commit", "load_daily_context")`
     - `workflow.add_edge("personal_stats", "response")` → `workflow.add_edge("personal_stats", "load_daily_context")`
     - `workflow.add_edge("stats_lookup", "response")` → `workflow.add_edge("stats_lookup", "load_daily_context")`
  7. Add the single new edge: `workflow.add_edge("load_daily_context", "response")`.
- **PATTERN**: Direct-edge calls mirror existing `add_edge` pattern (lines 89-93). Conditional-edge maps mirror lines 56-85.
- **IMPORTS**: As above.
- **GOTCHA**:
  - Entry point stays `input_parser` — do **not** change `set_entry_point`.
  - The `response → END` edge is unchanged.
  - A typo in a routing-function return value silently routes to `END`. Cross-check that every key returned by `route_parser` and `route_after_selection` exists in its conditional-edge map.
  - `confirmation_node` returns `Command(...)` for dynamic routing (commit or response). The Command-based routes are also affected if any of them go to `"response"`. Inspect `src/agents/nodes/confirmation_node.py` and check every `goto=` value: any `goto="response"` becomes `goto="load_daily_context"`. (If none exist, no change required.)
- **VALIDATE**:
  - `uv run python -c "import asyncio; from src.agents.nutritionist import define_graph; g = asyncio.run(define_graph()); assert 'load_daily_context' in g.nodes"`
  - Inspect graph topology: `uv run python -c "import asyncio; from src.agents.nutritionist import define_graph; g = asyncio.run(define_graph()); print(g.get_graph().draw_mermaid())"` — confirm every former `* → response` is now `* → load_daily_context → response`.

### 6. INSPECT and rewire `src/agents/nodes/confirmation_node.py` if needed

- **IMPLEMENT**: Search for `goto="response"` and `goto='response'` in `src/agents/nodes/confirmation_node.py`. If found, change to `goto="load_daily_context"`. If not found, no edit required.
- **PATTERN**: Command-based routing already used in this node (per CLAUDE.md "HITL Batch Confirmation").
- **IMPORTS**: None.
- **GOTCHA**: A "REJECTED" path or a "no items to commit" path may route directly to `response` via `Command`. Those need rerouting too — otherwise the response after a rejection sees stale data. Verify by reading the file.
- **VALIDATE**: `grep -n 'goto=' src/agents/nodes/confirmation_node.py` — every `goto=` should target either `commit` or `load_daily_context` (never `response`).

### 7. UPDATE `src/agents/nodes/response_node.py` — read from state

- **IMPLEMENT**: At line 225, change:
  ```python
  daily_log = context.daily_log_today if context.daily_log_today is not None else []
  ```
  to:
  ```python
  # Sourced from state, populated by load_daily_context (runs immediately before this node).
  # See docs/adr/0002-daily-log-loader-node-into-state.md.
  daily_log = state.get("daily_log_today", [])
  ```
- **PATTERN**: `state.get(...)` mirrors how other state fields are read in the same node.
- **IMPORTS**: None added.
- **GOTCHA**: Leave `context.user_profile` (lines 210-211, 217) alone — only `daily_log_today` moves out of context.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v` (some tests fail until Task 9 — expected at this stage).

### 8. UPDATE `src/context.py` — remove field

- **IMPLEMENT**: Delete line 44 (`daily_log_today: list[dict] = field(default_factory=list)`).
- **PATTERN**: Match the pre-2026-04-17 dataclass shape (PR #21 era).
- **IMPORTS**: Keep `field` import — `user_profile` still uses it.
- **GOTCHA**: Any leftover `runtime.context.daily_log_today` or `ContextSchema(daily_log_today=...)` reference will now break at runtime. Tasks 7 and 9 cover the production and test sites.
- **VALIDATE**:
  - `uv run python -c "from src.context import ContextSchema; assert not hasattr(ContextSchema(), 'daily_log_today')"`
  - `grep -rn 'daily_log_today' src bot --include='*.py' | grep -v 'state\|AgentState\|load_daily_context_node\|response_node'` → should return no matches.

### 9. UPDATE `bot/gateway.py` — strip plumbing

- **IMPLEMENT**:
  1. Remove import: `from src.services.daily_log_service import get_todays_logs_serialized` (line 31).
  2. Remove the `_load_todays_log` async helper (lines 226-233).
  3. From `_call_langgraph` signature: remove `daily_log_today: list[dict] | None = None` kwarg.
  4. From `_call_langgraph` body: remove the `if daily_log_today is not None: body["context"]["daily_log_today"] = daily_log_today` block.
  5. In `_handle_authenticated_message`: remove `todays_log = await _load_todays_log(user_id)` (line 324).
  6. In both `_call_langgraph` call sites (lines 335 and 343 in the resume + new-input branches): remove `daily_log_today=todays_log` kwarg.
- **PATTERN**: Result mirrors the gateway shape *before* the 2026-04-17 daily-log injection landed.
- **IMPORTS**: Remove `get_todays_logs_serialized` import.
- **GOTCHA**: Tests in `test_gateway.py` reference `_load_todays_log` via `@patch`; Task 11 removes those.
- **VALIDATE**:
  - `uv run python -c "from bot import gateway; assert not hasattr(gateway, '_load_todays_log')"`
  - `grep -n 'daily_log_today\|todays_log\|get_todays_logs_serialized' bot/gateway.py` → no matches.

### 10. UPDATE `tests/unit/test_response_node.py`

- **IMPLEMENT**:
  - In `_make_state` (line 20-34), add `"daily_log_today": []` to the defaults so existing tests don't accidentally rely on missing-key fallback.
  - In `test_daily_log_section_shown_when_log_present` (around line 643): remove `daily_log_today=logs` from the `ContextSchema(...)` call. Pass via state: `state = _make_state(last_action="CHITCHAT", daily_log_today=logs)`.
  - In `test_daily_log_empty_section_shown_when_log_empty` (around line 676): remove `daily_log_today=[]` from `ContextSchema(...)`. Pass via state: `state = _make_state(last_action="CHITCHAT", daily_log_today=[])`. Update the docstring: replace *"context.daily_log_today is empty"* with *"state.daily_log_today is empty"*.
- **PATTERN**: Existing inline state construction in the same file.
- **IMPORTS**: None.
- **GOTCHA**: After Task 8, passing `daily_log_today=` to `ContextSchema(...)` raises `TypeError: ContextSchema.__init__() got an unexpected keyword argument`. Must update the tests, not restore the dataclass.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

### 11. UPDATE `tests/unit/test_gateway.py`

- **IMPLEMENT**:
  - Remove every `@patch("bot.gateway._load_todays_log", new_callable=AsyncMock, return_value=[])` decorator (occurrences at lines 128, 163, 198, 225, 252, 279).
  - Remove the corresponding `mock_load_todays_log` parameter from each affected method signature.
  - Remove every `daily_log_today=[]` line from `assert_called_once_with` / kwargs assertions on the `_call_langgraph` mock (lines 157, 191, plus any others).
- **PATTERN**: Inverse of how the daily-log injection landed in `commit_logs/2026-04-17_11-54-54_feat-daily-log-injection-and-israel-tz.md`.
- **IMPORTS**: None.
- **GOTCHA**: Decorator order and parameter order are coupled — the bottom-most decorator's mock is the first parameter after `self`. Removing a decorator without removing its parameter (or vice versa) shifts every other parameter by one position.
- **VALIDATE**: `uv run pytest tests/unit/test_gateway.py -v`

### 12. UPDATE `tests/unit/test_feedback_integration.py`

- **IMPLEMENT**: In the `with patch(...)` block (around line 33-40), add `patch("src.agents.nutritionist.load_daily_context") as mock_loader,`. Inside the block, set `mock_loader.return_value = {"daily_log_today": []}`.
- **PATTERN**: Mirrors the other `patch("src.agents.nutritionist.<node>")` calls in the same block.
- **IMPORTS**: None.
- **GOTCHA**: Without this mock, the in-memory graph compiled in this test will hit the real DB through the loader → fail with connection errors / unrelated test noise.
- **VALIDATE**: `uv run pytest tests/unit/test_feedback_integration.py -v`

### 13. RUN full unit suite

- **IMPLEMENT**: `uv run pytest tests/unit/ -v`
- **PATTERN**: Pre-commit gate per CLAUDE.md.
- **IMPORTS**: N/A.
- **GOTCHA**: If unrelated tests fail, inspect — a topology change can ripple in surprising places.
- **VALIDATE**: All unit tests pass.

### 14. RUN integration suite

- **IMPLEMENT**: `uv run pytest tests/integration/ -v`
- **PATTERN**: Real Supabase DB.
- **IMPORTS**: N/A.
- **GOTCHA**: Needs `SUPABASE_DB_URL` set.
- **VALIDATE**: All integration tests pass.

### 15. RUN graph-API suite (mandatory — graph topology changed)

- **IMPLEMENT**: `uv run pytest tests/graph_api/ -v -s`
- **PATTERN**: Required per CLAUDE.md whenever graph edges/nodes change.
- **IMPORTS**: N/A.
- **GOTCHA**: HITL confirmation E2E test is the canary — if it asserts the post-commit summary reflects the just-committed items, beautiful. If not, consider adding such an assertion.
- **VALIDATE**: All graph-API tests pass.

### 16. MANUAL smoke (recommended)

- **IMPLEMENT**: Run the bot locally with `POLLING_MODE=true` and reproduce the bug:
  1. Send a multi-item food list.
  2. Confirm with "yes".
  3. Immediately ask "where am I today?".
  4. Verify the summary reflects the just-confirmed items.
- **VALIDATE**: Visual confirmation in Telegram.

### 17. AMEND ADR-0002 (or write ADR-0003 superseding it)

- **IMPLEMENT**:
  - Decide between (a) editing ADR-0002's "Decision" section to describe the simpler topology *if the ADR has not yet been widely cited*, or (b) writing **ADR-0003** that supersedes ADR-0002 with the simpler design and updating ADR-0002's index status to *"Superseded by ADR-0003"*.
  - Per the ADR skill's rules, **detail files are immutable after acceptance**. So default to (b): write ADR-0003.
- **PATTERN**: Use the `/adr` skill; reference ADR-0002 in the new ADR's Context section; update ADR-0002's index row in `docs/adr/DECISIONS.md` to *"Superseded by ADR-0003"*.
- **VALIDATE**: `docs/adr/0003-*.md` exists; `docs/adr/DECISIONS.md` shows ADR-0002 as superseded.

---

## TESTING STRATEGY

### Unit Tests

- New file `tests/unit/test_load_daily_context_node.py` covers the loader in isolation (mocked DB).
- `tests/unit/test_response_node.py` updated so `daily_log_today` is injected via state, not context.
- `tests/unit/test_gateway.py` updated so it no longer asserts a behavior the gateway no longer has.
- `tests/unit/test_feedback_integration.py` updated to mock the new loader (otherwise the in-memory graph hits the real DB).

### Integration Tests

- `tests/integration/test_daily_log_service.py` (existing) — `get_todays_logs_serialized` + `_serialize_log` unchanged; no edits needed.
- No new integration test required — the new node is a thin wrapper around an already-tested service function.

### Graph-API Tests

- Mandatory full run because graph topology changed (new node, 5 edge changes, 1 new edge).
- HITL confirmation E2E test is the regression guard for the original bug. If it doesn't already assert correctness of the post-commit summary, consider adding such an assertion.

### Edge Cases

- **Empty log day** — loader writes `[]`; `_format_daily_log` renders the "Nothing logged yet today." line.
- **Studio fallback (no bot)** — `ContextSchema` defaults to `DEFAULT_DEV_USER_ID`; loader queries on that user.
- **HITL resume turn that does NOT reach commit** (user replies "no, cancel") — confirmation_node returns `Command(goto="load_daily_context")` (after Task 6); loader runs; response sees fresh data. No staleness possible because the loader always runs.
- **HITL resume turn that DOES reach commit** — commit writes rows; commit → load_daily_context → response; consumer sees fresh data. The bug is fixed.
- **CHITCHAT path** — input_parser → load_daily_context → response. One extra DB query per CHITCHAT turn (cost: ~5ms, indexed). This is the price for a uniform topology rule.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check src/agents/nodes/load_daily_context_node.py src/agents/state.py src/agents/nutritionist.py src/agents/nodes/response_node.py src/agents/nodes/confirmation_node.py src/context.py bot/gateway.py tests/conftest.py tests/unit/test_response_node.py tests/unit/test_gateway.py tests/unit/test_load_daily_context_node.py tests/unit/test_feedback_integration.py
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
- [ ] Graph entry point unchanged (`input_parser`).
- [ ] Every former `* → response` edge or routing return now goes through `load_daily_context` first. Cross-check via `g.get_graph().draw_mermaid()`.
- [ ] Single new edge `load_daily_context → response` present.
- [ ] `response_node` reads `state["daily_log_today"]`, not `runtime.context.daily_log_today`.
- [ ] `bot/gateway.py` no longer fetches the daily log or sends it in the HTTP context body.
- [ ] All unit, integration, and graph-API tests pass.
- [ ] Manual smoke confirms post-commit summary reflects just-committed items.
- [ ] No leftover references to `runtime.context.daily_log_today` anywhere in `src/`, `bot/`, or `tests/` (other than this plan and the ADR).
- [ ] ADR-0002 amended or superseded by ADR-0003 to reflect the simpler topology.

---

## COMPLETION CHECKLIST

- [ ] All 17 tasks completed in order
- [ ] Each task validation passed immediately
- [ ] `uv run ruff check` clean on all modified files
- [ ] Full unit suite passes: `uv run pytest tests/unit/`
- [ ] Full integration suite passes: `uv run pytest tests/integration/`
- [ ] Full graph-API suite passes: `uv run pytest tests/graph_api/`
- [ ] Manual smoke test reproduces correct post-commit summary
- [ ] No regressions in existing functionality
- [ ] ADR-0003 created (or ADR-0002 amended) and DECISIONS.md updated
- [ ] CLAUDE.md update queued for `sync-context` (post-implementation)

---

## NOTES

### Why this design (vs the entry + post-commit one)

- **Today**: only `response_node` consumes `daily_log_today`. Placing the loader at entry pre-pays a forward-compat cost for hypothetical mid-graph consumers.
- **Tomorrow**: when a real mid-graph consumer arrives, adding a loader edge for *that consumer* costs the same single-edge change either way.
- **Net**: this design is strictly simpler now and costs the same to extend later.

### What is *not* changing

- `user_id` and `user_profile` continue to flow through `ContextSchema`. Stable per request, no need to move.
- `daily_log_report` (different state field for stats flow) is untouched.
- `_serialize_log`, `get_todays_logs_serialized`, `_format_daily_log` unchanged.
- The bot's `user_profile` cache and onboarding flow are unaffected.
- Graph entry point stays `input_parser`.

### Known follow-ups

- **CLAUDE.md**: the runtime-context row currently states `daily_log_today` lives in `ContextSchema`. After this lands, run `sync-context` (or update manually).
- **Bug 1 (UTC date boundary)**: pre-existing in `get_todays_logs_serialized` via `get_logs_by_date`. Logs made 00:00–03:00 Israel local fall on the previous UTC date. Tracked in `brain/TASKS.md`.
- **ADR-0002 status**: needs to be amended or superseded as part of this plan (Task 17). The ADR's *Context*, *Alternatives*, *Consequences*, and *Revisit trigger* sections still hold; only the *Decision* topology specifics change.

### Confidence

**8.5/10** for one-pass implementation. Lower-risk than the previous plan because:
- No conditional edge from the loader to debug.
- Entry point unchanged.
- Routing-function changes are minimal (two `return "response"` → `return "load_daily_context"`).

The remaining risk areas are:
- (a) `confirmation_node` `goto=` rewiring (Task 6) — easy to miss if not searched explicitly.
- (b) Conditional-edge dict-map updates (Task 5 step 5) — typos silently route to `END`.
- (c) `test_feedback_integration.py` patch addition (Task 12) — without it the integration test hits the real DB.
