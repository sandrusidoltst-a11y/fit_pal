# Feature: Refactor Sync Nodes to Async + Module-Level Prompt Loading

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Three graph nodes (`input_node`, `selection_node`, `response_node`) are still synchronous — using `def` + `llm.invoke()` instead of `async def` + `await llm.ainvoke()`. Additionally, 6 nodes/helpers load prompt files via sync `open()` at runtime on every call. This refactor converts all nodes to async and moves prompt file reads to module-level constants, eliminating all sync I/O from the graph runtime.

## User Story

As a developer maintaining FitPal
I want all graph nodes to be consistently async with zero runtime file I/O
So that the codebase is consistent, resilient to BlockingError in ASGI, and prompt files are loaded once at startup

## Problem Statement

- 3 nodes use sync `def` + `llm.invoke()` — LangGraph wraps them in a thread executor, which works but is inconsistent and wasteful
- 6 nodes/helpers call `open()` on prompt files during every graph run — unnecessary repeated file I/O inside the async runtime
- Past `BlockingError` incidents (documented in RCA files) show that sync I/O in async nodes is a real risk

## Solution Statement

1. Convert 3 sync nodes to `async def` + `await llm.ainvoke()`
2. Move all prompt file reads to module-level constants (`_SYSTEM_PROMPT = ...`) loaded once at import time
3. Update corresponding unit tests to use `async def test_` + mock `.ainvoke()` instead of `.invoke()`

## Feature Metadata

**Feature Type**: Refactor
**Estimated Complexity**: Medium
**Primary Systems Affected**: `src/agents/nodes/`, `tests/unit/`
**Dependencies**: None (pure refactor, no new libraries)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

**Nodes to change:**

- `src/agents/nodes/input_node.py` (lines 13-72) — sync node, `open()` at line 21, `llm.invoke()` at line 45
- `src/agents/nodes/selection_node.py` (lines 13-83) — sync node, `open()` at line 43, `llm.invoke()` at line 63
- `src/agents/nodes/response_node.py` (lines 69-119) — sync node, `open()` at line 82, `llm.invoke()` at line 117
- `src/agents/nodes/calculate_macros_node.py` (lines 90-124) — async node, but `_estimate_macros` helper has `open()` at line 96
- `src/agents/nodes/confirmation_node.py` (lines 119-148) — async node, but `_parse_confirmation` helper has `open()` at line 125
- `src/agents/nodes/personal_stats_node.py` (lines 22-80) — async node, but has `open()` at line 36

**Tests to update:**

- `tests/unit/test_input_parser.py` — 7 sync tests, mock `.invoke()` at line 32
- `tests/unit/test_agent_selection.py` — 5 sync tests, mock `.invoke()` at line 67+
- `tests/unit/test_response_node.py` — 12 sync tests, mock `.invoke()` at line 159+

**Reference for correct async pattern (already done right):**

- `src/agents/nodes/food_search_node.py` — async node using `await tool.ainvoke()`
- `src/agents/nodes/commit_node.py` — async node using `await tool.ainvoke()`
- `tests/unit/test_calculate_macros_node.py` — async test pattern with mocked `.ainvoke()`

### Patterns to Follow

**Module-level prompt loading (new pattern):**

```python
import os
from src.config import BASE_DIR

_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "input_parser.md")
try:
    with open(_PROMPT_PATH, "r", encoding="utf-8") as _f:
        _SYSTEM_PROMPT = _f.read()
except FileNotFoundError:
    _SYSTEM_PROMPT = "Fallback prompt text here"
```

**Async node pattern (existing, mirror from food_search_node):**

```python
async def my_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    result = await structured_llm.ainvoke(messages)
    return {"field": value}
```

**Async test pattern (existing, mirror from test_calculate_macros_node):**

```python
async def test_something(self):
    mock_structured.ainvoke = AsyncMock(return_value=...)
    result = await my_node(state, runtime)
    assert result["field"] == expected
```

### Prompt files (all exist, verified):

- `prompts/input_parser.md`
- `prompts/agent_selection.md`
- `prompts/response_generator.md`
- `prompts/macro_estimation.md`
- `prompts/confirmation_parser.md`
- `prompts/personal_stats_extractor.md`

---

## IMPLEMENTATION PLAN

### Phase 1: Module-Level Prompt Loading (6 files)

Move all `open()` calls from runtime functions to module-level constants. This is the safest change — it doesn't change function signatures or test interfaces.

### Phase 2: Convert 3 Sync Nodes to Async

Convert `input_node`, `selection_node`, `response_node` from `def` + `.invoke()` to `async def` + `await .ainvoke()`.

### Phase 3: Update Tests

Convert corresponding test functions from `def` to `async def` and mock `.ainvoke` instead of `.invoke`.

### Phase 4: Validation

Run full unit test suite to confirm zero regressions.

---

## STEP-BY-STEP TASKS

### Task 1: UPDATE `src/agents/nodes/input_node.py` — module-level prompt + async

- **REFACTOR**: Move `open()` block (lines 18-26) to module level as `_SYSTEM_PROMPT`
- **REFACTOR**: `def input_parser_node` → `async def input_parser_node`
- **REFACTOR**: `structured_llm.invoke(messages)` (line 45) → `await structured_llm.ainvoke(messages)`
- **REMOVE**: `try/except FileNotFoundError` from function body (moved to module level)
- **KEEP**: `_serialize_date` helper stays sync (pure computation)
- **IMPORTS**: No new imports needed
- **GOTCHA**: The function prepends system time to the prompt at runtime (line 35-36) — this must stay in the function body, not at module level. Use `_SYSTEM_PROMPT` as the base, format with time at call time
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py -v`

### Task 2: UPDATE `src/agents/nodes/selection_node.py` — module-level prompt + async

- **REFACTOR**: Move `open()` block (lines 40-47) to module level as `_SYSTEM_PROMPT`
- **REFACTOR**: `def agent_selection_node` → `async def agent_selection_node`
- **REFACTOR**: `structured_llm.invoke(messages)` (line 63) → `await structured_llm.ainvoke(messages)`
- **GOTCHA**: The `open()` is inside an `if len(search_results) > 1` branch — the prompt is only used for multi-result LLM selection. Module-level loading is fine since the prompt is tiny and always needed eventually
- **GOTCHA**: Early returns for 0 and 1 results (lines 26-37) don't use LLM — those paths stay unchanged
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py -v`

### Task 3: UPDATE `src/agents/nodes/response_node.py` — module-level prompt + async

- **REFACTOR**: Move `open()` block (lines 79-89) to module level as `_SYSTEM_PROMPT`
- **REFACTOR**: `def response_node` → `async def response_node`
- **REFACTOR**: `llm.invoke(full_messages)` (line 117) → `await llm.ainvoke(full_messages)`
- **KEEP**: `_build_context` and `_serialize_date` helpers stay sync (pure computation, no I/O)
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

### Task 4: UPDATE `src/agents/nodes/calculate_macros_node.py` — module-level prompt

- **REFACTOR**: Move `open()` block in `_estimate_macros` (lines 94-102) to module level as `_ESTIMATION_PROMPT`
- **KEEP**: Both `calculate_macros_node` and `_estimate_macros` are already async — no signature changes
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_macros_node.py -v`

### Task 5: UPDATE `src/agents/nodes/confirmation_node.py` — module-level prompt

- **REFACTOR**: Move `open()` block in `_parse_confirmation` (lines 123-131) to module level as `_CONFIRMATION_PROMPT`
- **KEEP**: `confirmation_node`, `_parse_confirmation`, `_apply_edits` are already async — no signature changes
- **GOTCHA**: `_parse_confirmation` does `system_prompt.replace("{batch_context}", batch_context)` at line 138 — this must still happen at runtime. Load the template at module level, do the `.replace()` in the function
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v`

### Task 6: UPDATE `src/agents/nodes/personal_stats_node.py` — module-level prompt

- **REFACTOR**: Move `open()` block (lines 34-40) to module level as `_SYSTEM_PROMPT`
- **KEEP**: `personal_stats_node` is already async — no signature change
- **VALIDATE**: `uv run pytest tests/unit/test_personal_stats_node.py -v`

### Task 7: UPDATE `tests/unit/test_input_parser.py` — async tests

- **REFACTOR**: All `def test_*` → `async def test_*`
- **REFACTOR**: `mock_structured.invoke.return_value = ...` → `mock_structured.ainvoke = AsyncMock(return_value=...)`
- **REFACTOR**: `result = input_parser_node(basic_state)` → `result = await input_parser_node(basic_state)`
- **IMPORTS**: Add `from unittest.mock import AsyncMock`
- **PATTERN**: Mirror `tests/unit/test_calculate_macros_node.py` for async test structure
- **GOTCHA**: `pytest.ini` has `asyncio_mode = "auto"` so no `@pytest.mark.asyncio` needed
- **GOTCHA**: The `patch` target for prompt may need updating — with module-level loading, tests that test the fallback prompt (`test_fallback_prompt_on_missing_file`) need to patch the module-level constant `_SYSTEM_PROMPT` instead of `builtins.open`
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py -v`

### Task 8: UPDATE `tests/unit/test_agent_selection.py` — async tests

- **REFACTOR**: All `def test_*` that call the node → `async def test_*`
- **REFACTOR**: Mock `.ainvoke` instead of `.invoke` for multi-result tests
- **REFACTOR**: `result = agent_selection_node(state)` → `result = await agent_selection_node(state)`
- **IMPORTS**: Add `from unittest.mock import AsyncMock`
- **GOTCHA**: Tests for 0-result and 1-result edge cases don't use LLM, but the node function is now async so they still need `await`
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py -v`

### Task 9: UPDATE `tests/unit/test_response_node.py` — async tests

- **REFACTOR**: All `def test_*` that call `response_node()` → `async def test_*`
- **REFACTOR**: Mock `.ainvoke` instead of `.invoke` for LLM calls
- **REFACTOR**: `result = response_node(state, runtime)` → `result = await response_node(state, runtime)`
- **IMPORTS**: Add `from unittest.mock import AsyncMock`
- **GOTCHA**: `TestBuildContext` tests call `_build_context()` which stays sync — those tests stay `def test_*`
- **GOTCHA**: `test_fallback_prompt_on_missing_file` — with module-level loading, this test needs to patch `src.agents.nodes.response_node._SYSTEM_PROMPT` instead of `builtins.open`
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

---

## TESTING STRATEGY

### Unit Tests

All existing unit tests continue to run with mocked LLM. The changes are:
- `def test_*` → `async def test_*` for tests calling async nodes
- Mock `.ainvoke` instead of `.invoke`
- `asyncio_mode = "auto"` in `pyproject.toml` handles async test discovery

### Tests for fallback prompts

Tests that previously mocked `builtins.open` to simulate missing prompt files need a new approach:
- Patch the module-level `_SYSTEM_PROMPT` constant directly instead of mocking file I/O
- This is actually simpler and more direct

### Edge Cases

- Module-level prompt loading failure (file missing at import time) — covered by try/except with fallback string
- Nodes that don't use runtime context still don't need it (input_node, selection_node stay single-arg unless they need user_id)

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
uv run ruff check src/agents/nodes/ tests/unit/
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

### Level 4: Full Suite

```bash
uv run pytest tests/unit/ tests/integration/ -v
```

---

## ACCEPTANCE CRITERIA

- [ ] All 6 node files use module-level prompt loading (no `open()` calls inside functions)
- [ ] `input_node`, `selection_node`, `response_node` are `async def` with `await .ainvoke()`
- [ ] All corresponding unit tests updated to async and pass
- [ ] `uv run ruff check .` passes with zero errors
- [ ] `uv run pytest tests/unit/ -v` passes with zero failures
- [ ] `uv run pytest tests/integration/ -v` passes with zero failures
- [ ] No behavioral changes — same inputs produce same outputs

---

## COMPLETION CHECKLIST

- [ ] All 9 tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting errors
- [ ] Code follows project async conventions consistently

---

## NOTES

- **No graph edge changes needed** — LangGraph handles both sync and async nodes transparently. Converting to async doesn't affect routing or graph compilation.
- **`get_llm_for_node()` stays sync** — it's a factory that returns an LLM instance. The instance's `.ainvoke()` method is what's async. The factory itself does no I/O.
- **Prompt files are static** — they don't change between graph runs. Module-level loading is safe. If a prompt is updated, the server must be restarted (same as any code change).
- **Risk**: Low. This is a pure refactor with no behavioral changes. Each task is independently testable.
