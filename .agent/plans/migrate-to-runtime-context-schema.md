# Feature: Migrate to Runtime[ContextSchema] + Inject User Profile

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Migrate from `config["configurable"]` to LangGraph's typed `Runtime[ContextSchema]` for passing user context (user_id, user_profile) through the graph. Also inject user profile into `response_node`'s SystemMessage so the LLM knows the user's name, age, gender, and height.

## User Story

As a FitPal user
I want the agent to know my name and profile details
So that responses are personalized ("Hey Dolev, here's your summary")

## Problem Statement

1. User profile is injected into `config["configurable"]["user_profile"]` by the bot but no node reads it — the LLM has no knowledge of who the user is.
2. `config["configurable"]` is an untyped dict — no validation, no autocomplete, easy to misspell keys.
3. LangGraph v1 provides `Runtime[ContextSchema]` as the proper typed mechanism for this, but we're using the legacy pattern.

## Solution Statement

1. Define a `ContextSchema` dataclass with `user_id` and `user_profile` fields
2. Register it on `StateGraph` via `context_schema=ContextSchema`
3. Migrate all nodes from `config: RunnableConfig` to `runtime: Runtime[ContextSchema]`
4. Migrate all `@tool` functions from `config: RunnableConfig` to `runtime: ToolRuntime[ContextSchema]`
5. Update bot to pass `context` as a separate top-level HTTP field
6. Inject user profile into `response_node`'s SystemMessage content
7. Simplify `get_user_id()` / `get_user_profile()` in config.py

## Feature Metadata

**Feature Type**: Refactor + Enhancement
**Estimated Complexity**: High
**Primary Systems Affected**: All nodes, all tools, bot gateway, config.py, tests
**Dependencies**: `langgraph>=1.0.7` (already installed), `langchain>=1.2.8` (already installed)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

**Graph definition:**
- `src/agents/nutritionist.py` (lines 15-94) — StateGraph construction, must add `context_schema`

**Nodes that use config (6 nodes — must migrate to runtime):**
- `src/agents/nodes/food_search_node.py` (line 10) — `async def food_search_node(state, config: RunnableConfig)`
- `src/agents/nodes/calculate_macros_node.py` (line 15) — `async def calculate_macros_node(state, config: RunnableConfig)`
- `src/agents/nodes/confirmation_node.py` (lines 48-50) — `async def confirmation_node(state, config: RunnableConfig)`
- `src/agents/nodes/commit_node.py` (line 13) — `async def commit_node(state, config: RunnableConfig)`
- `src/agents/nodes/personal_stats_node.py` (line 21) — `async def personal_stats_node(state, config: RunnableConfig)`
- `src/agents/nodes/stats_node.py` (line 10) — `async def stats_lookup_node(state, config: RunnableConfig)`

**Nodes that don't use config (3 nodes):**
- `src/agents/nodes/input_node.py` (line 13) — `input_parser_node(state)` — no config, no change
- `src/agents/nodes/selection_node.py` (line 13) — `agent_selection_node(state)` — no config, no change
- `src/agents/nodes/response_node.py` (line 67) — `response_node(state)` — no config currently, but WILL ADD `runtime` to inject profile

**Tools (must migrate config → ToolRuntime):**
- `src/tools/food_lookup.py` (lines 29, 63, 79-86) — `search_food(query, config)`, `calculate_food_macros(food_id, amount_g)` (no config!), `create_food_item(..., config=None)`
- `src/services/daily_log_service.py` (lines 181-215) — `log_food_entry(..., config=None)`, `query_food_logs(..., config=None)`
- `src/services/personal_stats_service.py` (lines 131-186) — `log_personal_stat(...)`, `get_latest_personal_stats(...)`, `get_personal_stat_history(...)`

**Config helpers:**
- `src/config.py` (lines 22-72) — `DEFAULT_DEV_USER_ID`, `DEFAULT_DEV_PROFILE`, `get_user_id(config)`, `get_user_profile(config)`

**Bot:**
- `bot/gateway.py` (lines 90-108) — `_call_langgraph()` builds request body with `config.configurable`

**Tests:**
- `tests/conftest.py` (lines 23-26) — `TEST_CONFIG_A`, `TEST_CONFIG_B`
- `tests/unit/test_auth_handler.py` — Tests `get_user_id()` priority chain
- All unit tests that mock tool `.ainvoke()` calls with `config=` kwarg

**Response prompt:**
- `prompts/response_generator.md` — System prompt for response_node

### New Files to Create

- `src/context.py` — `ContextSchema` dataclass + `UserProfile` TypedDict

### Relevant Documentation — READ BEFORE IMPLEMENTING

- [LangGraph Runtime Context](https://docs.langchain.com/oss/python/langgraph/graph-api#add-runtime-configuration)
  - How to define `context_schema`, register on graph, access in nodes via `Runtime`
- [LangGraph Context Overview](https://docs.langchain.com/oss/python/concepts/context#static-runtime-context)
  - Static runtime context concept, workflow node pattern
- [LangChain ToolRuntime](https://docs.langchain.com/oss/python/langchain/tools#access-context)
  - `ToolRuntime` in tools, reserved parameter names
- [LangChain Tools — Reserved Names](https://docs.langchain.com/oss/python/langchain/tools#reserved-argument-names)
  - `config` and `runtime` are reserved — cannot be used as regular tool args

### Patterns to Follow

**Node pattern (current → new):**
```python
# BEFORE
from langchain_core.runnables import RunnableConfig
from src.config import get_user_id

async def my_node(state: AgentState, config: RunnableConfig):
    user_id = get_user_id(config)
    result = await some_tool.ainvoke({"arg": val}, config=config)

# AFTER
from langgraph.runtime import Runtime
from src.context import ContextSchema

async def my_node(state: AgentState, runtime: Runtime[ContextSchema]):
    # Tools auto-receive runtime context — no need to pass config manually
    result = await some_tool.ainvoke({"arg": val})
```

**Tool pattern (current → new):**
```python
# BEFORE
from langchain_core.runnables import RunnableConfig
from src.config import get_user_id

@tool
async def search_food(query: str, config: RunnableConfig) -> list[dict]:
    user_id = get_user_id(config)
    ...

# AFTER
from langchain.tools import ToolRuntime
from src.context import ContextSchema

@tool
async def search_food(query: str, runtime: ToolRuntime[ContextSchema]) -> list[dict]:
    user_id = runtime.context.user_id
    ...
```

**Bot HTTP pattern (current → new):**
```python
# BEFORE
body = {
    "assistant_id": ASSISTANT_ID,
    "config": {"configurable": {"user_id": user_id, "user_profile": profile}},
}

# AFTER
body = {
    "assistant_id": ASSISTANT_ID,
    "context": {"user_id": user_id, "user_profile": profile},
}
```

---

## CRITICAL GOTCHAS

### 1. Cannot mix `config["configurable"]` and `context`
The LangGraph server returns 400 if both are present. The bot must use `context` for user data and NOT set `config.configurable`. `thread_id` is managed by the server (passed via URL path `/threads/{thread_id}/runs/wait`), not in config.

### 2. `runtime` is a reserved parameter name
In `@tool` functions, `runtime` is automatically injected and hidden from the LLM schema. Never use `runtime` as a regular tool argument name.

### 3. `config` is also reserved in tools
After migration, tools should NOT have `config: RunnableConfig` as a parameter. Access config via `runtime.config` if needed.

### 4. Tools auto-receive context
When a node calls `tool.ainvoke(args)`, the tool's `runtime` parameter is automatically populated from the graph's runtime context. **Nodes do NOT need to pass config to tools anymore.** This simplifies all `ainvoke` calls.

### 5. LangGraph Studio fallback
LangGraph Studio may not pass `context`. The `ContextSchema` should have sensible defaults so Studio still works:
```python
@dataclass
class ContextSchema:
    user_id: str = "fbeeb45f-d728-4c7c-9e6d-7b9b41685da7"  # DEFAULT_DEV_USER_ID
    user_profile: dict = field(default_factory=lambda: DEFAULT_DEV_PROFILE)
```

### 6. Verify ainvoke behavior without config
Currently nodes pass `config=config` to every `tool.ainvoke()` call. After migration, this should be removed (just `tool.ainvoke(args)`). The runtime context propagates automatically. **MUST VERIFY** this works by running tests after migration.

### 7. RemoteGraph checkpointing concern (Issue #6342)
There was a reported bug where `context` without `configurable` broke checkpointing in RemoteGraph. Our setup uses raw HTTP + thread_id in URL path (not configurable), so this likely doesn't apply. **MUST VERIFY** via E2E tests.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — Define ContextSchema

Create the schema and register it on the graph. This is non-breaking — existing code still works since nodes can accept both `config` and `runtime`.

### Phase 2: Migrate Nodes

Update all 6 config-accepting nodes + response_node to use `runtime: Runtime[ContextSchema]`. Remove `config=config` from `ainvoke` calls.

### Phase 3: Migrate Tools

Update all `@tool` functions to use `runtime: ToolRuntime[ContextSchema]` instead of `config: RunnableConfig`.

### Phase 4: Inject Profile into Response

Add user profile to `response_node`'s SystemMessage content.

### Phase 5: Update Bot Gateway

Change the HTTP request body to use `context` instead of `config.configurable`.

### Phase 6: Simplify Config Helpers

Remove or simplify `get_user_id(config)` and `get_user_profile(config)` — they're no longer needed.

### Phase 7: Update Tests

Migrate test fixtures, mocks, and assertions to the new pattern.

### Phase 8: Validation

Run all test tiers to confirm nothing breaks.

---

## STEP-BY-STEP TASKS

### Task 1: CREATE `src/context.py` — Define ContextSchema

Create a new file `src/context.py` with the context schema:

```python
from dataclasses import dataclass, field
from typing import TypedDict

# Fallbacks for LangGraph Studio (no bot to inject context)
DEFAULT_DEV_USER_ID = "fbeeb45f-d728-4c7c-9e6d-7b9b41685da7"
DEFAULT_DEV_PROFILE = {
    "name": "Dev User",
    "height_cm": 175.0,
    "age": 25,
    "gender": "male",
}


class UserProfile(TypedDict, total=False):
    """User profile data collected during onboarding."""
    name: str
    height_cm: float
    age: int
    gender: str


@dataclass
class ContextSchema:
    """Static context passed to every graph run.

    Injected by the bot gateway at invocation time.
    Available in nodes via runtime.context and in tools via runtime.context.
    """
    user_id: str = DEFAULT_DEV_USER_ID
    user_profile: dict = field(default_factory=lambda: DEFAULT_DEV_PROFILE.copy())
```

- **GOTCHA**: Move `DEFAULT_DEV_USER_ID` and `DEFAULT_DEV_PROFILE` from `src/config.py` to `src/context.py`. Update imports in any file that references them.
- **VALIDATE**: `uv run ruff check src/context.py`

### Task 2: UPDATE `src/agents/nutritionist.py` — Register context_schema

Add `context_schema=ContextSchema` to the `StateGraph` constructor:

```python
from src.context import ContextSchema

workflow = StateGraph(
    state_schema=AgentState,
    input_schema=InputState,
    output_schema=OutputState,
    context_schema=ContextSchema,
)
```

- **VALIDATE**: `uv run ruff check src/agents/nutritionist.py`

### Task 3: UPDATE all 6 config-accepting nodes — Migrate to Runtime

For each of the 6 nodes that accept `config: RunnableConfig`:

**Pattern for each node:**
1. Replace `from langchain_core.runnables import RunnableConfig` with `from langgraph.runtime import Runtime` and `from src.context import ContextSchema`
2. Change function signature from `config: RunnableConfig` to `runtime: Runtime[ContextSchema]`
3. Remove all `config=config` kwargs from `tool.ainvoke()` calls
4. Remove `get_user_id(config)` calls if they exist in the node (they shouldn't — user_id is used in tools, not nodes directly)

**Files to update:**
- `src/agents/nodes/food_search_node.py` — 1 ainvoke call
- `src/agents/nodes/calculate_macros_node.py` — 1 ainvoke call + LLM call (LLM call has no config, leave as-is)
- `src/agents/nodes/confirmation_node.py` — ainvoke calls in `_apply_edits` helper. Note: `_apply_edits` receives `config` param — change to receive nothing (tools get runtime automatically)
- `src/agents/nodes/commit_node.py` — 3+ ainvoke calls
- `src/agents/nodes/personal_stats_node.py` — 1 ainvoke call
- `src/agents/nodes/stats_node.py` — 1-2 ainvoke calls

- **GOTCHA**: `confirmation_node.py` has a helper function `_apply_edits(batch, edits, config)` that passes `config` to `calculate_food_macros.ainvoke()`. Remove the `config` param from `_apply_edits` and remove `config=config` from the ainvoke call inside it.
- **VALIDATE**: `uv run ruff check src/agents/nodes/`

### Task 4: UPDATE `src/agents/nodes/response_node.py` — Add Runtime + Profile Injection

This node currently takes only `state`. Add `runtime` parameter and inject profile into SystemMessage:

1. Add `from langgraph.runtime import Runtime` and `from src.context import ContextSchema`
2. Change signature to `async def response_node(state: AgentState, runtime: Runtime[ContextSchema])`
3. Read profile: `profile = runtime.context.user_profile`
4. Build profile context string and add to SystemMessage content between system prompt and context JSON

```python
# Build user profile section
profile = runtime.context.user_profile
profile_section = (
    f"\nUser Profile:\n"
    f"- Name: {profile.get('name', 'Unknown')}\n"
    f"- Age: {profile.get('age', 'Unknown')}\n"
    f"- Gender: {profile.get('gender', 'Unknown')}\n"
    f"- Height: {profile.get('height_cm', 'Unknown')}cm\n"
)

system_message = SystemMessage(
    content=f"{system_prompt}\n{profile_section}\n---\nContext JSON:\n```json\n{json_context}\n```"
)
```

- **GOTCHA**: The function is currently sync (`def`). If Runtime injection requires async, make it `async def`. Check if other sync nodes without config need changes.
- **VALIDATE**: `uv run ruff check src/agents/nodes/response_node.py`

### Task 5: UPDATE all @tool functions — Migrate to ToolRuntime

For each `@tool` function that uses `config: RunnableConfig`:

**Pattern:**
1. Replace `from langchain_core.runnables import RunnableConfig` with `from langchain.tools import ToolRuntime` and `from src.context import ContextSchema`
2. Replace `config: RunnableConfig` (or `config: RunnableConfig = None`) with `runtime: ToolRuntime[ContextSchema]`
3. Replace `get_user_id(config)` with `runtime.context.user_id`
4. Remove `from src.config import get_user_id` imports

**Files and tools to update:**

`src/tools/food_lookup.py`:
- `search_food(query, config)` → `search_food(query, runtime: ToolRuntime[ContextSchema])`
- `create_food_item(..., config=None)` → `create_food_item(..., runtime: ToolRuntime[ContextSchema])`
- `calculate_food_macros(food_id, amount_g)` — NO CONFIG, leave unchanged

`src/services/daily_log_service.py`:
- `log_food_entry(..., config=None)` → `log_food_entry(..., runtime: ToolRuntime[ContextSchema])`
- `query_food_logs(..., config=None)` → `query_food_logs(..., runtime: ToolRuntime[ContextSchema])`

`src/services/personal_stats_service.py`:
- `log_personal_stat(..., config=None)` → `log_personal_stat(..., runtime: ToolRuntime[ContextSchema])`
- `get_latest_personal_stats(config=None)` → `get_latest_personal_stats(runtime: ToolRuntime[ContextSchema])`
- `get_personal_stat_history(..., config=None)` → `get_personal_stat_history(..., runtime: ToolRuntime[ContextSchema])`

- **GOTCHA**: `config` was optional (default None) in most tools. `runtime` is auto-injected — no default needed. Remove the `= None` default.
- **GOTCHA**: `runtime` is a reserved name — it's hidden from the LLM tool schema. The LLM never sees this parameter.
- **VALIDATE**: `uv run ruff check src/tools/ src/services/`

### Task 6: UPDATE `bot/gateway.py` — Pass context instead of config.configurable

In `_call_langgraph()` (lines 90-108):

```python
# BEFORE
body = {
    "assistant_id": ASSISTANT_ID,
    "config": {"configurable": {"user_id": user_id}},
}
if user_profile:
    body["config"]["configurable"]["user_profile"] = user_profile

# AFTER
body = {
    "assistant_id": ASSISTANT_ID,
    "context": {"user_id": user_id},
}
if user_profile:
    body["context"]["user_profile"] = user_profile
```

- **GOTCHA**: Do NOT include `config.configurable` anymore — server returns 400 if both `configurable` and `context` are present. `thread_id` is in the URL path (`/threads/{thread_id}/runs/wait`), not in config.
- **GOTCHA**: Keep the `config` key in the body but only if needed for non-configurable settings. If not needed, remove it entirely.
- **VALIDATE**: `uv run ruff check bot/gateway.py`

### Task 7: UPDATE `src/config.py` — Simplify or remove config helpers

- Remove `get_user_id()` and `get_user_profile()` — no longer used anywhere
- Move `DEFAULT_DEV_USER_ID` and `DEFAULT_DEV_PROFILE` to `src/context.py` (done in Task 1)
- Update any remaining imports of these from `src/config`
- Keep `get_llm_for_node()`, `get_openai_api_key()`, `get_langchain_api_key()`, `BASE_DIR`, `DATABASE_URL`, `GLOBAL_PROVIDER`, `GLOBAL_MODEL` — these are unrelated to user context

- **GOTCHA**: `DEFAULT_DEV_USER_ID` is imported in `tests/unit/test_auth_handler.py`. These tests test the old `get_user_id()` function — they should be removed or rewritten.
- **VALIDATE**: `uv run ruff check src/config.py`

### Task 8: UPDATE `tests/conftest.py` — Migrate test fixtures

Replace `TEST_CONFIG_A/B` with context-based equivalents:

```python
# BEFORE
TEST_CONFIG_A: RunnableConfig = {"configurable": {"user_id": TEST_USER_A}}

# AFTER
from src.context import ContextSchema
TEST_CONTEXT_A = ContextSchema(user_id=TEST_USER_A)
TEST_CONTEXT_B = ContextSchema(user_id=TEST_USER_B)
# Keep TEST_CONFIG_A for any tests that still need RunnableConfig
TEST_CONFIG_A: RunnableConfig = {"configurable": {"user_id": TEST_USER_A}}
```

- **GOTCHA**: Integration tests patch `get_async_db_session` and call service functions directly with `session` param — they don't go through tools. These tests pass `user_id` directly, not via config/context. They may not need changes.
- **GOTCHA**: Unit tests mock `tool.ainvoke()` calls. The mock assertions may check for `config=` kwargs that are now removed. Update mock assertions.
- **VALIDATE**: `uv run ruff check tests/`

### Task 9: UPDATE unit tests — Fix mock assertions

Unit tests that mock `tool.ainvoke()` often assert it was called with `config=config`. After migration, `ainvoke` calls no longer pass `config`. Update these assertions.

Search for `config=` in all test files and update accordingly.

- **VALIDATE**: `uv run pytest tests/unit/ -v`

### Task 10: UPDATE `tests/unit/test_auth_handler.py` — Remove or rewrite

This file tests `get_user_id()` which is being removed. Options:
- Remove the entire file if `get_user_id` is deleted
- Or rewrite to test `ContextSchema` defaults and fallback behavior

- **VALIDATE**: `uv run pytest tests/unit/ -v`

### Task 11: UPDATE `tests/graph_api/test_graph_flows.py` — Migrate DEV_USER_CONFIG

```python
# BEFORE
DEV_USER_CONFIG = {"configurable": {"user_id": "72c10336-..."}}
# Used as: config=DEV_USER_CONFIG

# AFTER  
DEV_USER_CONTEXT = {"user_id": "72c10336-..."}
# Used as: context=DEV_USER_CONTEXT (if using langgraph-sdk)
# Or in _run() helper, pass context instead of config
```

- **GOTCHA**: The `_run()` helper calls `lg_client.runs.wait()`. Check if the langgraph-sdk's `runs.wait()` method accepts a `context` parameter. If not, we may need to use raw HTTP like the bot does.
- **VALIDATE**: `uv run pytest tests/graph_api/ -v -s` (after all other changes)

### Task 12: RUN full validation suite

```bash
uv run ruff check .
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -v
uv run pytest tests/graph_api/ -v -s
```

---

## TESTING STRATEGY

### Unit Tests

- Update all mock assertions that check for `config=config` in `ainvoke` calls
- Remove/rewrite `test_auth_handler.py` (tests removed `get_user_id`)
- Add test for `ContextSchema` defaults (verify Studio fallback works)
- Test `response_node` profile injection (mock runtime with profile, verify SystemMessage contains profile)

### Integration Tests

- Likely no changes — integration tests use service functions directly with `session` param, not through tools
- Verify by running `uv run pytest tests/integration/ -v`

### E2E Tests

- Update `DEV_USER_CONFIG` to `DEV_USER_CONTEXT`
- Verify all flows work with the new context pattern
- **Critical**: Verify checkpointing still works (thread state persists across turns)

### Edge Cases

- LangGraph Studio invocation with no context (should use defaults)
- Bot invocation with profile (should reach response_node)
- Bot invocation without profile (new user, no onboarding yet)
- HITL interrupt/resume with context

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
```bash
uv run ruff check .
```

### Level 2: Unit Tests
```bash
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests
```bash
uv run pytest tests/integration/ -v
```

### Level 4: E2E Tests
```bash
uv run pytest tests/graph_api/ -v -s
```

### Level 5: Manual Validation
- Start `langgraph dev` + bot in polling mode
- Send passphrase to dev bot
- Complete onboarding
- Send "what's my name?" — agent should know
- Log food, verify HITL still works
- Query stats, verify response is personalized

---

## ACCEPTANCE CRITERIA

- [ ] `ContextSchema` defined with typed `user_id` and `user_profile` fields
- [ ] All 6 config-accepting nodes migrated to `runtime: Runtime[ContextSchema]`
- [ ] `response_node` reads profile from `runtime.context.user_profile` and includes in SystemMessage
- [ ] All 7 `@tool` functions migrated to `runtime: ToolRuntime[ContextSchema]`
- [ ] Bot passes `context` field (not `config.configurable`) in HTTP body
- [ ] `get_user_id()` and `get_user_profile()` removed from config.py
- [ ] All `config=config` kwargs removed from `tool.ainvoke()` calls in nodes
- [ ] LangGraph Studio works with default context (no bot)
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] All E2E tests pass (checkpointing, HITL, food logging, stats)
- [ ] Agent responds with user's name when asked

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order (Tasks 1-12)
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration + E2E)
- [ ] No linting errors
- [ ] Manual Telegram bot testing confirms personalized responses
- [ ] Acceptance criteria all met

---

## NOTES

### Design Decisions

1. **Separate `src/context.py` file**: Keeps context schema isolated from config.py (which handles LLM setup, DB URLs, etc.). Clean separation of concerns.

2. **`dict` for user_profile, not a nested dataclass**: The bot sends profile as a plain dict from the Supabase query. Using `dict` in ContextSchema avoids serialization complexity. The `UserProfile` TypedDict provides type hints for documentation without runtime enforcement.

3. **Defaults for Studio compatibility**: `ContextSchema` has defaults for both fields so LangGraph Studio works without the bot (falls back to dev user + dev profile).

4. **No more `config=config` passthrough**: This is the biggest simplification. Currently every node passes `config=config` to every `ainvoke` call. After migration, tools receive runtime context automatically. Nodes just call `tool.ainvoke(args)`.

5. **Profile in SystemMessage content, not a separate mechanism**: The LLM API only accepts messages with role + content. There's no metadata channel. The standard pattern is to put user context in the SystemMessage content string.

### Risks

- **`context` + checkpointing**: Issue #6342 reports a bug where context-only invocations may not enable checkpointing in some SDK versions. Our setup uses thread_id in the URL path, which may avoid this. Must verify via E2E tests.
- **Tool auto-injection**: We're relying on tools automatically receiving runtime context when called via `ainvoke()` from within a graph node. If this doesn't work, we'd need to pass config explicitly. Verify early (Task 3 + Task 5 together, then run tests).
- **Breaking change scope**: This touches every node and tool. If something goes wrong, many tests will fail simultaneously. Consider committing after each phase and running tests.

### Incremental Rollback Strategy

If Runtime doesn't work as expected:
1. `ContextSchema` and `context_schema` on graph are additive — can be added without changing nodes
2. Nodes can accept both `config` and `runtime` simultaneously — migrate one node at a time
3. Tools can keep `config: RunnableConfig` while we verify ToolRuntime works

### Confidence Score: 7/10

Medium-high confidence. The pattern is well-documented, but:
- Large surface area (6 nodes, 7 tools, bot, tests)
- `context` vs `configurable` 400 error needs careful handling
- Tool auto-injection of runtime context is a new pattern we haven't verified locally
- Checkpointing interaction needs E2E verification
