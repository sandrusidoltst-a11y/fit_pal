# Feature: Refactor Test Suite to Match Test Strategy

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Refactor the existing test suite to fully comply with the test strategy document (`.agent/reference/test-strategy.md`). Three known tech debt items have been identified:

1. `test_input_parser.py` calls the real LLM inside the unit suite — making it non-deterministic and slow.
2. `test_food_search_node.py` hits the real `nutrition.db` file — making it depend on disk I/O.
3. `mock_db_session` and `mock_calculate_macros` fixtures are duplicated across `test_calculate_log_node.py` and `test_multi_item_loop.py`.

Additionally, there is no `tests/integration/` directory and no graph compilation integration test. The `tests/test_food_lookup.py` file sits outside any category folder and hits the real DB.

This refactoring creates a solid, deterministic, sub-second unit test suite and a clearly separated integration suite.

## User Story

As a developer
I want my unit tests to be deterministic, fast, and properly isolated from external systems
So that I can trust test results and catch regressions immediately

## Problem Statement

The current test suite violates its own test strategy rules: unit tests call real LLMs and real DBs, fixtures are duplicated, and there is no integration test directory. This means:
- Unit test runs are slow (~26s when they should be <5s for true unit tests)
- Failures can be caused by LLM non-determinism or missing DB files, not code bugs
- The graph compilation test (`test_feedback_integration.py`) mocks the checkpointer, missing real compile errors

## Solution Statement

Refactor unit tests to mock ALL external dependencies. Move real-LLM and real-DB tests to `tests/integration/`. Consolidate shared fixtures into `conftest.py`. Add a dedicated graph compilation integration test.

## Feature Metadata

**Feature Type**: Refactor
**Estimated Complexity**: Medium
**Primary Systems Affected**: `tests/` directory only — zero production code changes
**Dependencies**: None (only test infrastructure)

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `.agent/reference/test-strategy.md` (lines 1-207) - Why: THE source of truth for what the tests should look like. Every decision here must comply with this document.
- `tests/conftest.py` (lines 1-62) - Why: Existing shared fixtures. New shared fixtures go here.
- `tests/unit/test_input_parser.py` (lines 1-85) - Why: MUST be refactored — currently calls real LLM via `input_parser_node` which internally calls `get_llm_for_node("input_node")`
- `tests/unit/test_food_search_node.py` (lines 1-25) - Why: MUST be refactored — calls `food_search_node` which internally calls `search_food.invoke()` hitting real `nutrition.db`
- `tests/unit/test_calculate_log_node.py` (lines 7-28) - Why: Contains duplicate fixtures `mock_db_session`, `mock_daily_log_service`, `mock_calculate_macros` that should move to conftest
- `tests/unit/test_multi_item_loop.py` (lines 7-35) - Why: Contains SAME duplicate fixtures as above
- `tests/unit/test_feedback_integration.py` (lines 1-87) - Why: Current graph-level test — mocks AsyncSqliteSaver and all nodes. Good pattern to reference.
- `tests/test_food_lookup.py` (lines 1-41) - Why: Sits outside folder structure. Hits real DB. Should move to `tests/integration/`
- `src/agents/nodes/input_node.py` (lines 1-68) - Why: The node being tested — must understand its dependencies to mock correctly. Uses `get_llm_for_node("input_node")` and `.with_structured_output(FoodIntakeEvent)`
- `src/agents/nodes/food_search_node.py` (lines 1-25) - Why: The node being tested — calls `search_food.invoke()`. That's the mock target.
- `src/config.py` (lines 28-53) - Why: `get_llm_for_node` factory pattern — this is what we mock in unit tests
- `src/schemas/input_schema.py` (lines 1-44) - Why: `FoodIntakeEvent`, `ActionType`, `SingleFoodItem` — the structured output schemas we need to construct mock LLM responses
- `src/agents/nutritionist.py` (lines 1-85) - Why: `define_graph()` — the function the graph compilation integration test will call
- `src/tools/food_lookup.py` (lines 1-47) - Why: `search_food` and `calculate_food_macros` tools — understand what to mock
- `tests/unit/test_feedback_logic.py` (lines 1-115) - Why: Contains ANOTHER set of inline `mock_db_session`/`mock_calculate_macros` patches (via `with patch(...)`) — these are test-local but show the same pattern
- `tests/unit/test_stats_node.py` (lines 1-81) - Why: Contains ANOTHER `mock_db_session` and `mock_daily_log_service` fixture — same pattern that should be shared

### New Files to Create

- `tests/integration/__init__.py` - Empty init for test discovery
- `tests/integration/test_llm_prompts.py` - Real-LLM tests moved from `tests/unit/test_input_parser.py`
- `tests/integration/test_graph_compilation.py` - Graph compilation with real `MemorySaver` checkpointer
- `tests/integration/test_food_db.py` - Real DB tests moved from `tests/test_food_lookup.py` and `tests/unit/test_food_search_node.py`

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- `.agent/reference/test-strategy.md` - Sections 3.1, 4.1, 6, 9 are most relevant
- `.agent/rules/main_rule.md` (lines 91-107) - Validation commands

### Patterns to Follow

**Mock Pattern for LLM in Node Tests** (from `test_feedback_logic.py` lines 97-108):
```python
with patch("src.agents.nodes.<module>.get_llm_for_node") as mock_get_llm:
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = <pydantic_model_instance>
```

**Mock Pattern for Async DB Session** (from `test_calculate_log_node.py` lines 8-13):
```python
@pytest.fixture
def mock_db_session():
    with patch("src.agents.nodes.<module>.get_async_db_session") as mock:
        session = AsyncMock()
        mock.return_value.__aenter__ = AsyncMock(return_value=session)
        mock.return_value.__aexit__ = AsyncMock(return_value=False)
        yield session
```

**Mock Pattern for LangChain Tools** (from `test_calculate_log_node.py` lines 25-27):
```python
@pytest.fixture
def mock_calculate_macros():
    with patch("src.agents.nodes.calculate_log_node.calculate_food_macros") as mock:
        yield mock
```

**Graph Compilation Test Pattern** (from `test_feedback_integration.py` lines 23-26):
```python
with patch("src.agents.nutritionist.AsyncSqliteSaver") as mock_mem:
    mock_mem.from_conn_string.return_value = MemorySaver()
    app = await define_graph()
```

**Naming Conventions:**
- Test files: `test_<module_name>.py`
- Test functions: `test_<behavior_description>`
- Fixtures: `snake_case` descriptive names
- No class wrappers for simple tests (only `TestBuildContext` and `TestResponseNode` use them)

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — Create Integration Directory & Consolidate Fixtures

Set up the integration test directory and move shared fixtures to `conftest.py`.

**Tasks:**
- Create `tests/integration/__init__.py`
- Move duplicate fixtures from `test_calculate_log_node.py`, `test_multi_item_loop.py`, `test_stats_node.py` to `tests/conftest.py`

### Phase 2: Refactor `test_input_parser.py` — Mock the LLM

Convert all 7 tests to use a mocked LLM with pre-built `FoodIntakeEvent` responses.

### Phase 3: Refactor `test_food_search_node.py` — Mock the DB Tool

Convert `test_food_search_basic` to use a mocked `search_food.invoke()`.

### Phase 4: Move Real-System Tests to Integration

Move real-LLM tests and real-DB tests to `tests/integration/`.

### Phase 5: Add Graph Compilation Integration Test

Create a test that compiles the graph with a real `MemorySaver` to catch compile errors.

### Phase 6: Cleanup & Validation

Remove stale file, run full suite, verify test counts.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Task 1: CREATE `tests/integration/__init__.py`

- **IMPLEMENT**: Create an empty `__init__.py` file so pytest discovers the integration directory.
- **VALIDATE**: `uv run pytest --collect-only tests/integration/` — should show 0 tests, no errors

### Task 2: UPDATE `tests/conftest.py` — Add shared mock fixtures

- **IMPLEMENT**: Add these shared fixtures below the existing `async_test_db_session` fixture:
  1. `mock_calculate_log_db_session` — patches `src.agents.nodes.calculate_log_node.get_async_db_session`
  2. `mock_daily_log_service_for_calc` — patches `src.agents.nodes.calculate_log_node.daily_log_service`
  3. `mock_calculate_macros` — patches `src.agents.nodes.calculate_log_node.calculate_food_macros`
  4. `mock_stats_db_session` — patches `src.agents.nodes.stats_node.get_async_db_session`
  5. `mock_daily_log_service_for_stats` — patches `src.agents.nodes.stats_node.daily_log_service`
- **PATTERN**: Mirror the exact mock structure from `test_calculate_log_node.py` lines 8-27 and `test_stats_node.py` lines 9-21
- **IMPORTS**: Add `from unittest.mock import AsyncMock, MagicMock, patch` to conftest
- **GOTCHA**: The patch target must match the MODULE where the dependency is imported, not where it's defined. For `calculate_log_node`, the target is `src.agents.nodes.calculate_log_node.get_async_db_session`, NOT `src.database.get_async_db_session`.
- **GOTCHA**: Fixture names must not collide with existing ones. Use descriptive names that reflect which node they mock for.
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_log_node.py -v` — all 3 tests still pass

### Task 3: UPDATE `tests/unit/test_calculate_log_node.py` — Remove duplicate fixtures

- **IMPLEMENT**: Remove the local `mock_db_session`, `mock_daily_log_service`, and `mock_calculate_macros` fixture definitions (lines 7-27). Update all test function signatures to use the shared conftest fixture names from Task 2.
- **GOTCHA**: The test functions use `mock_db_session` as parameter name — update to match new conftest fixture names.
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_log_node.py -v` — all 3 tests pass

### Task 4: UPDATE `tests/unit/test_multi_item_loop.py` — Remove duplicate fixtures

- **IMPLEMENT**: Remove the local `mock_db_session`, `mock_daily_log_service`, and `mock_calculate_macros` fixture definitions (lines 7-35). Update all test function signatures to use the shared conftest fixture names from Task 2.
- **GOTCHA**: `mock_calculate_macros` in this file has a default `.invoke.return_value` set inside the fixture (lines 27-34). The shared fixture should NOT set a default return value — each test should set its own. Update tests that relied on the default.
- **VALIDATE**: `uv run pytest tests/unit/test_multi_item_loop.py -v` — all 5 tests pass

### Task 5: UPDATE `tests/unit/test_stats_node.py` — Remove duplicate fixtures

- **IMPLEMENT**: Remove the local `mock_db_session` and `mock_daily_log_service` fixture definitions (lines 8-21). Update test function signatures to use the shared conftest fixture names from Task 2.
- **VALIDATE**: `uv run pytest tests/unit/test_stats_node.py -v` — all 2 tests pass

### Task 6: REFACTOR `tests/unit/test_input_parser.py` — Mock the LLM

- **IMPLEMENT**: Rewrite all 7 tests to mock `get_llm_for_node` instead of calling the real LLM.
  - For each test, construct a `FoodIntakeEvent` Pydantic model as the mock LLM return value.
  - Mock chain: `patch("src.agents.nodes.input_node.get_llm_for_node")` → `mock_llm.with_structured_output.return_value = mock_structured` → `mock_structured.invoke.return_value = FoodIntakeEvent(...)`
  - Also mock `datetime.now()` to make consumed_at deterministic when the prompt prepends system time.
- **PATTERN**: Follow the LLM mock pattern from `test_feedback_logic.py` lines 97-108
- **IMPORTS**: `from src.schemas.input_schema import FoodIntakeEvent, ActionType, SingleFoodItem`
- **GOTCHA**: `input_parser_node` reads a prompt file from disk (`prompts/input_parser.md`). This is fine for unit tests — it's a local read, not an external dependency. Do NOT mock the file read.
- **GOTCHA**: The node accesses `result.action.value` and `result.items` — ensure the mock FoodIntakeEvent has proper enum values.

  **Test-by-test mock responses:**
  1. `test_log_food_basic`: `FoodIntakeEvent(action=ActionType.LOG_FOOD, items=[SingleFoodItem(food_name="Chicken breast", amount=200.0, unit="g", original_text="200g of chicken breast")])`
  2. `test_unit_normalization`: `FoodIntakeEvent(action=ActionType.LOG_FOOD, items=[SingleFoodItem(food_name="Rice", amount=185.0, unit="g", original_text="a cup of rice")])`
  3. `test_complex_meal_decomposition`: `FoodIntakeEvent(action=ActionType.LOG_FOOD, items=[SingleFoodItem(...) for pasta, cheese, tomato])`
  4. `test_chitchat`: `FoodIntakeEvent(action=ActionType.CHITCHAT, items=[])`
  5. `test_nonsense_input`: `FoodIntakeEvent(action=ActionType.CHITCHAT, items=[])`
  6. `test_query_daily_stats`: `FoodIntakeEvent(action=ActionType.QUERY_DAILY_STATS, items=[])`
  7. `test_query_food_info`: `FoodIntakeEvent(action=ActionType.QUERY_FOOD_INFO, items=[])`

- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py -v` — all 7 tests pass, runs in <1s (no LLM calls)

### Task 7: REFACTOR `tests/unit/test_food_search_node.py` — Mock the DB tool

- **IMPLEMENT**: Mock `search_food.invoke` to return canned results instead of hitting real `nutrition.db`.
  - `test_food_search_basic`: Mock `search_food.invoke` to return `[{"id": 1, "name": "Chicken breast"}, {"id": 2, "name": "Chicken thigh"}]`
  - `test_food_search_no_pending_items`: No mock needed — the node returns early before calling `search_food`
- **PATTERN**: `patch("src.agents.nodes.food_search_node.search_food")` → `mock_search.invoke.return_value = [...]`
- **VALIDATE**: `uv run pytest tests/unit/test_food_search_node.py -v` — both tests pass, no DB access

### Task 8: CREATE `tests/integration/test_llm_prompts.py` — Real LLM tests

- **IMPLEMENT**: Move the real-LLM test cases here. These tests call `input_parser_node` without mocking the LLM.
  - `test_input_parser_real_llm_log_food`: "I had 200g of chicken breast" → assert `LOG_FOOD`, assert items[0] has "chicken" in name
  - `test_input_parser_real_llm_chitchat`: "Hello, how are you?" → assert `CHITCHAT`
  - `test_input_parser_real_llm_query_stats`: "How much protein have I eaten today?" → assert `QUERY_DAILY_STATS`
- **IMPORTS**: `from src.agents.nodes.input_node import input_parser_node`; reuse `basic_state` from conftest
- **GOTCHA**: These tests call the real OpenAI API. They require `OPENAI_API_KEY` in `.env`. Mark them clearly with docstrings stating they are integration tests.
- **VALIDATE**: `uv run pytest tests/integration/test_llm_prompts.py -v` — tests pass (requires API key)

### Task 9: CREATE `tests/integration/test_food_db.py` — Real DB tests

- **IMPLEMENT**: Move the real-DB tests here.
  - Move `tests/test_food_lookup.py` content (both `test_search_food` and `test_calculate_food_macros`) into this file.
  - Add `test_food_search_node_real_db`: Call `food_search_node` with real DB to verify integration. Move from `test_food_search_node.py:test_food_search_basic` original logic.
- **IMPORTS**: `from src.tools.food_lookup import search_food, calculate_food_macros`; `from src.agents.nodes.food_search_node import food_search_node`
- **GOTCHA**: Remove the `sys.path.append` hack from old `test_food_lookup.py` — conftest already handles this.
- **VALIDATE**: `uv run pytest tests/integration/test_food_db.py -v` — tests pass

### Task 10: CREATE `tests/integration/test_graph_compilation.py` — Graph Compile Test

- **IMPLEMENT**: Test that `define_graph()` compiles without error using a real `MemorySaver` checkpointer.
  ```python
  from unittest.mock import patch
  from langgraph.checkpoint.memory import MemorySaver
  from src.agents.nutritionist import define_graph

  async def test_graph_compiles_with_checkpointer():
      """Integration test: graph compiles with a real checkpointer."""
      with patch("src.agents.nutritionist.AsyncSqliteSaver") as mock_saver:
          mock_saver.from_conn_string.return_value = MemorySaver()
          graph = await define_graph()
          assert graph is not None

  async def test_graph_has_all_expected_nodes():
      """Verify all nodes are registered in the compiled graph."""
      with patch("src.agents.nutritionist.AsyncSqliteSaver") as mock_saver:
          mock_saver.from_conn_string.return_value = MemorySaver()
          graph = await define_graph()
          node_names = set(graph.nodes.keys())
          expected = {"input_parser", "food_search", "agent_selection", "calculate_log", "stats_lookup", "response"}
          assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"
  ```
- **GOTCHA**: We patch `AsyncSqliteSaver` to avoid creating a real SQLite checkpoint file during tests. The `MemorySaver` is a real in-memory checkpointer, so the graph compilation is fully exercised.
- **VALIDATE**: `uv run pytest tests/integration/test_graph_compilation.py -v` — both tests pass

### Task 11: REMOVE `tests/test_food_lookup.py`

- **IMPLEMENT**: Delete `tests/test_food_lookup.py` — its tests have been moved to `tests/integration/test_food_db.py` in Task 9.
- **VALIDATE**: `uv run pytest tests/ --collect-only 2>&1 | Select-String "test_food_lookup"` — should show nothing

### Task 12: UPDATE `test-strategy.md` — Clear the tech debt section

- **IMPLEMENT**: Update Section 9 "Known Tech Debt" in `.agent/reference/test-strategy.md` to mark items as resolved:
  ```markdown
  ## 9. Known Tech Debt

  All previously identified tech debt items have been resolved:

  | Item | Resolution |
  |---|---|
  | `test_input_parser.py` calling real LLM | Refactored to mock LLM. Real-LLM tests moved to `tests/integration/test_llm_prompts.py` |
  | `test_food_search_node.py` hitting real DB | Refactored to mock `search_food`. Real-DB tests moved to `tests/integration/test_food_db.py` |
  | Duplicate `mock_db_session` / `mock_calculate_macros` | Consolidated into `tests/conftest.py` as shared fixtures |
  | Missing `tests/integration/` directory | Created with `test_llm_prompts.py`, `test_food_db.py`, `test_graph_compilation.py` |
  | `tests/test_food_lookup.py` outside folder structure | Moved to `tests/integration/test_food_db.py`, old file deleted |
  ```
- **ALSO UPDATE**: Section 2 folder structure to show integration directory files.
- **ALSO UPDATE**: Section 5 "Critical Paths" table — update `test_input_parser.py` entry to note it now uses mocked LLM, real-LLM version is in integration.
- **ALSO UPDATE**: Section 6 "Shared Fixtures" table — add the new shared fixtures.
- **VALIDATE**: Read the file and verify all sections are coherent

### Task 13: Final Validation — Run Full Suite

- **VALIDATE**: `uv run pytest tests/unit/ -v` — ALL unit tests pass, with 0 real LLM/DB calls
- **VALIDATE**: `uv run pytest tests/unit/ -v` — should complete in under 5 seconds (no network)
- **VALIDATE**: `uv run pytest tests/integration/ -v` — ALL integration tests pass
- **VALIDATE**: `uv run pytest tests/ -v` — full suite passes, total count should be ~58+ tests

---

## TESTING STRATEGY

### Unit Tests

All existing unit tests continue to work but now properly mock all external dependencies:
- 7 tests in `test_input_parser.py` — now mocked LLM
- 2 tests in `test_food_search_node.py` — now mocked DB tool
- All others unchanged

### Integration Tests

New integration test directory with 3 files:
- `test_llm_prompts.py` — Real LLM calls (3 tests)
- `test_food_db.py` — Real DB access (3 tests)
- `test_graph_compilation.py` — Real graph compilation (2 tests)

### Edge Cases

- Mock LLM returns valid Pydantic model instances (not dicts)
- Mock search tool returns proper list[dict] format
- Graph compilation test verifies all expected nodes exist

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
# No linter configured yet — visual review
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
uv run pytest tests/ -v
```

---

## ACCEPTANCE CRITERIA

- [ ] `uv run pytest tests/unit/ -v` passes with 0 real LLM or DB calls
- [ ] Unit test run completes in under 5 seconds
- [ ] `tests/integration/` directory exists with 3 test files
- [ ] `tests/integration/test_graph_compilation.py` verifies graph compiles with `MemorySaver`
- [ ] No duplicate fixtures remain in individual test files (all in conftest.py)
- [ ] `tests/test_food_lookup.py` is deleted
- [ ] `test-strategy.md` Section 9 reflects resolved tech debt
- [ ] Total test count is ≥ 56 (53 original + ~5 integration - 2 moved)
- [ ] All existing test behavior preserved — no test logic changes, only mock injection

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting or type checking errors
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability

---

## NOTES

- **Zero production code changes** — this refactoring ONLY touches `tests/` and `.agent/reference/test-strategy.md`.
- The `test_agent_selection.py` tests for `test_selection_multiple_results_clear_match` and `test_selection_multiple_results_ambiguous` currently call the REAL LLM (they don't mock `get_llm_for_node`). These are borderline — the test strategy says unit tests should mock all LLM calls. However, these tests are fast and deterministic enough for now. Flag them for future refactoring but do NOT change them in this phase to minimize scope.
- `test_feedback_logic.py` uses inline `with patch(...)` for its mocks instead of fixtures. This is acceptable per the test strategy — inline patches are fine for tests that need unique mock setups. No change needed.
- The `basic_state` fixture in conftest already covers the standard state shape. New shared fixtures should follow the same pattern.
