# Feature: Refactor Tests With Skill Standards

The following plan should be complete, but its important that you validate documentation and codebase patterns
and task sanity before you start implementing.

Pay special attention to importing from the correct paths, mock target strings (must match the module where
the symbol is *used*, not where it is *defined*), and the fixture names already available in `conftest.py`.

## Feature Description

Bring every test file in `tests/unit/` into alignment with the three mandatory standards defined by the
`test-engineering` skill:

1. **Module-level docstring** — scope declaration + LLM usage statement.
2. **Class-based grouping** — related test functions grouped into `Test<What><Condition>` classes.
3. **AAA docstring** — every test method has `arrange / act / assert` labels.

Additionally, fix two correctness bugs discovered during the audit:
- `test_agent_selection.py` calls the *real* LLM for multi-result cases (integration violation in unit folder).
- `test_feedback_logic.py` duplicates conftest fixtures inline instead of using the shared ones.

Finally, create the missing `tests/graph_api/` tier (conftest + test file) exactly as described in
`graph-api-testing.md`.

## User Story

As a developer on FitPal,
I want every test file to follow the test-engineering skill standards (docstring, class grouping, AAA),
So that tests are scannable, self-documenting, and strictly enforce their tier's I/O contract.

## Problem Statement

The test suite was built incrementally and predates the formal `test-engineering` skill. As a result:

- All unit test files lack the mandatory module-level scope/LLM docstring.
- Most files use flat free functions instead of grouped classes, making them hard to scan.
- No test method has an AAA docstring.
- `test_agent_selection.py` — two tests call the real LLM (no mock), violating the unit-test tier.
- `test_feedback_logic.py` — duplicates mock setup inline instead of using conftest fixtures.
- `tests/graph_api/` does not exist at all.

## Solution Statement

Perform a file-by-file rewrite of each unit test to add the docstring header, group into classes, and add
AAA docstrings. Fix the two correctness bugs. Create the graph-api tier from the template in the skill.
No production code changes are required.

## Feature Metadata

**Feature Type**: Refactor  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: `tests/unit/` (all 12 files), `tests/graph_api/` (new)  
**Dependencies**: `langgraph-sdk` (must be added to dev deps for graph-api tier)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `.agent/skills/test-engineering/references/unit-testing.md` — canonical unit-test standards (header, class grouping, AAA, mock patterns)
- `.agent/skills/test-engineering/references/fitpal-test-strategy.md` — mock boundary rules, tier definitions
- `.agent/skills/test-engineering/references/graph-api-testing.md` — graph-api conftest template, test file template, path matrix
- `tests/conftest.py` (lines 1–105) — existing shared fixtures; never redefine these in individual files
- `tests/unit/test_response_node.py` — **gold-standard example**: already has class grouping + private helper; use as style reference
- `tests/unit/test_agent_selection.py` (lines 28–59) — BUG: `test_selection_multiple_results_clear_match` and `test_selection_multiple_results_ambiguous` call the real LLM
- `tests/unit/test_feedback_logic.py` (lines 7–23, 27–69) — BUG: local `base_state` fixture and inline DB/service mocks duplicate conftest
- `src/agents/nutritionist.py` — graph assistant name is `fitpal` (from `langgraph.json`)
- `langgraph.json` (line 4) — `"fitpal": "./src/agents/nutritionist.py:define_graph"` → `ASSISTANT_ID = "fitpal"`

### New Files to Create

- `tests/graph_api/__init__.py` — empty, marks package
- `tests/graph_api/conftest.py` — `lg_client` (session-scoped) + `thread` (function-scoped) fixtures
- `tests/graph_api/test_graph_flows.py` — 5 test classes covering all routing paths

### Patterns to Follow

**File Header (unit)**
```python
"""
Unit tests for <Node/Service Name> (`<source_file>.py`).

Scope:
    Purely isolated unit tests. Verify the conditional logic and state mutations
    of <brief description>.

LLM Usage:
    NONE — all LLM calls are mocked. No live API calls are made.
    [OR]
    MOCKED — <describe which LLM calls are mocked and how>.
"""
```

**Class Naming**: `Test<What><Condition>` — e.g. `TestAgentSelectionAutoRouting`, `TestInputParserLogFood`

**AAA Docstring**
```python
def test_xxx(self, basic_state):
    """
    arrange: <setup description>.
    act:     <action description>.
    assert:  <expectation description>.
    """
```

**LLM Mock (unit — use `with patch` inside method)**
```python
with patch("src.agents.nodes.selection_node.get_llm_for_node", return_value=mock_llm):
    result = agent_selection_node(basic_state)
```

**Incorrect LLM Mock (do NOT call real LLM in unit tests)**
```python
# BAD — no patch = real API call when 2+ search_results triggers LLM disambiguation
result = agent_selection_node(basic_state)
```

**Graph-API ASSISTANT_ID** (from `langgraph.json`)
```python
ASSISTANT_ID = "fitpal"  # NOT "nutritionist" — check langgraph.json line 4
```

---

## IMPLEMENTATION PLAN

### Phase 1: Install Missing Dependency

Add `langgraph-sdk` to dev deps (required for graph-api tier).

### Phase 2: Rewrite Unit Test Files (Header + Classes + AAA)

Rewrite every file in `tests/unit/` that is missing the header and/or class grouping.
Order matters only to avoid confusion — each file is independent.

### Phase 3: Fix Correctness Bugs

- `test_agent_selection.py`: mock the LLM for multi-result tests.
- `test_feedback_logic.py`: remove local `base_state` fixture and inline DB mocks; use conftest fixtures.

### Phase 4: Create `tests/graph_api/` Tier

Create three files following the template in `graph-api-testing.md` exactly.

### Phase 5: Validate

Run the full unit suite and verify zero regressions.

---

## STEP-BY-STEP TASKS

### Task 1: ADD `langgraph-sdk` to dev dependencies

- **IMPLEMENT**: Run `uv add --dev langgraph-sdk` from the project root.
- **GOTCHA**: `langgraph-cli[inmem]` is already present; `langgraph-sdk` is the *client* library — they are different packages.
- **VALIDATE**: `uv run python -c "from langgraph_sdk import get_client; print('OK')"`

---

### Task 2: REWRITE `tests/unit/test_agent_selection.py`

**Current state**: 5 flat functions, no header, two tests call real LLM.

**Target groups**:
- `TestAgentSelectionAutoRouting` — 0-result (NO_MATCH), 1-result (auto-select), empty-pending-items
- `TestAgentSelectionLLMRouting` — multiple results mocked LLM → SELECTED, multiple results mocked LLM → NO_MATCH

**Key changes**:
- Add module-level scope/LLM docstring.
- Move `test_selection_no_results`, `test_selection_single_result`, `test_selection_empty_pending_items` into `TestAgentSelectionAutoRouting`.
- Move `test_selection_multiple_results_clear_match` and `test_selection_multiple_results_ambiguous` into `TestAgentSelectionLLMRouting`.
- **FIX BUG**: Both LLM-routing tests must patch `"src.agents.nodes.selection_node.get_llm_for_node"`.
  - `test_selection_multiple_results_clear_match`: mock returns `FoodSelectionResult(status="SELECTED", food_id=165)`.
  - `test_selection_multiple_results_ambiguous`: mock returns `FoodSelectionResult(status="NO_MATCH", food_id=None)`.
  - After mocking, assert precisely: `assert result["last_action"] == "NO_MATCH"` (not `in [...]`).
- Add AAA docstring to every method.

**PATTERN**: Mirror `test_response_node.py` — class with `self`, fixture as argument.
**IMPORTS**: Add `from unittest.mock import MagicMock, patch` and `from src.schemas.selection_schema import FoodSelectionResult`.
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py -v`

---

### Task 3: REWRITE `tests/unit/test_input_parser.py`

**Current state**: 7 flat functions with `@patch` decorators, no header, no classes.

**Target groups**:
- `TestInputParserLogFood` — `test_log_food_basic`, `test_unit_normalization`, `test_complex_meal_decomposition`
- `TestInputParserOtherActions` — `test_chitchat`, `test_nonsense_input`, `test_query_daily_stats`, `test_query_food_info`

**Key changes**:
- Add module-level docstring (LLM Usage: MOCKED).
- Convert flat functions to methods on the two classes.
- Replace `@patch` decorator pattern with `with patch(...)` context manager inside the method body.
- Add AAA docstring to every method.

**PATTERN**: `unit-testing.md` Section 4 — LLM mock pattern using `with patch`.
**IMPORTS**: Existing imports are correct (`FoodIntakeEvent`, `ActionType`, `SingleFoodItem`).
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py -v`

---

### Task 4: REWRITE `tests/unit/test_food_search_node.py`

**Current state**: 2 flat functions, no header, no classes; correct mocking already.

**Target groups**:
- `TestFoodSearchNodeHappyPath` — `test_food_search_basic`
- `TestFoodSearchNodeEdgeCases` — `test_food_search_no_pending_items`

**Key changes**:
- Add module-level docstring (LLM Usage: NONE — food_search_node does not call an LLM).
- Wrap both functions in appropriate classes.
- Add AAA docstrings.

- **VALIDATE**: `uv run pytest tests/unit/test_food_search_node.py -v`

---

### Task 5: REWRITE `tests/unit/test_calculate_log_node.py`

**Current state**: 3 flat async functions, no header, no classes; uses `AgentState(...)` constructor directly.

**Target groups**:
- `TestCalculateLogNodeSuccess` — `test_calculate_log_node_success`
- `TestCalculateLogNodeEdgeCases` — `test_calculate_log_node_no_selection_or_processed`, `test_calculate_log_node_macro_error`

**Key changes**:
- Add module-level docstring (LLM Usage: NONE — calculate_log_node does not call an LLM).
- Wrap into classes.
- Replace `AgentState(...)` constructor with plain dict (use `basic_state` fixture as base and override with `.update()` or kwarg overrides).
- Add AAA docstrings.
- Keep `mock_calculate_log_db_session`, `mock_daily_log_service_for_calc`, `mock_calculate_macros` as fixture arguments.

**GOTCHA**: `AgentState` is a `TypedDict`. The preferred pattern is a plain dict with all required keys (as in `basic_state` fixture). You may keep `AgentState(...)` if already working — just use `basic_state` and override as needed.
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_log_node.py -v`

---

### Task 6: REWRITE `tests/unit/test_stats_node.py`

**Current state**: 2 flat async functions, no header, no classes; uses `AgentState(...)` with only partial fields.

**Target groups**:
- `TestStatsNodeSingleDay` — `test_stats_lookup_single_day`
- `TestStatsNodeDateRange` — `test_stats_lookup_date_range`

**Key changes**:
- Add module-level docstring (LLM Usage: NONE).
- Wrap into classes.
- Replace `AgentState(consumed_at=..., start_date=None, end_date=None, daily_log_report=[])` with `basic_state` fixture + overrides.
- Add AAA docstrings.

- **VALIDATE**: `uv run pytest tests/unit/test_stats_node.py -v`

---

### Task 7: REWRITE `tests/unit/test_feedback_logic.py`

**Current state**: Mixed concerns — calculate_log + selection tests, local `base_state` fixture duplicating conftest, inline DB/service mocks duplicating conftest.

**Target groups**:
- `TestCalculateLogFeedback` — `test_calculate_log_success_result`, `test_calculate_log_accumulates_results`
- `TestAgentSelectionFeedback` — `test_selection_failure_no_results`, `test_selection_failure_llm`

**Key changes**:
- Add module-level docstring.
- **REMOVE** local `base_state` fixture — use `basic_state` from conftest (populate `pending_food_items` inside each test).
- **REMOVE** inline `patch` blocks for `get_async_db_session` and `daily_log_service` in calculate-log tests — replace with conftest fixtures `mock_calculate_log_db_session` and `mock_daily_log_service_for_calc` as method arguments.
- Wrap into classes.
- Add AAA docstrings.

**GOTCHA**: `test_calculate_log_accumulates_results` sets `processing_results` with a pre-existing entry. Set `basic_state["processing_results"] = [existing]` before calling the node.
- **VALIDATE**: `uv run pytest tests/unit/test_feedback_logic.py -v`

---

### Task 8: REWRITE `tests/unit/test_multi_item_loop.py`

**Current state**: 5 async functions, no header, no classes; docstring on line 16 is misplaced (after mock setup).

**Target groups**:
- `TestMultiItemLoopDraining` — `test_calculate_log_removes_first_item`, `test_calculate_log_single_item`, `test_sequential_item_removal`
- `TestMultiItemLoopEdgeCases` — `test_calculate_log_empty_pending`, `test_multi_item_state_setup`

**Key changes**:
- Add module-level docstring (LLM Usage: NONE).
- **FIX COSMETIC BUG**: Move the string literal on line 16 to be the proper first statement (docstring) of `test_calculate_log_removes_first_item`.
- Wrap into classes.
- Add AAA docstrings to all methods.

- **VALIDATE**: `uv run pytest tests/unit/test_multi_item_loop.py -v`

---

### Task 9: REWRITE `tests/unit/test_feedback_integration.py`

**Current state**: 1 flat async function, no header, no classes.

**Target**:
- Single class `TestFullFlowIntegration` — `test_integration_full_flow`

**Key changes**:
- Add module-level docstring (explains that all nodes are patched; real graph compilation tested).
- Wrap function into class.
- Add AAA docstring.

- **VALIDATE**: `uv run pytest tests/unit/test_feedback_integration.py -v`

---

### Task 10: REWRITE `tests/unit/test_daily_log_service.py`

**Current state**: 6 async functions + module docstring already present (good!). No classes. Tests use `async_test_db_session` fixture correctly.

**Target groups**:
- `TestCreateLogEntry` — `test_create_log_entry`
- `TestGetDailyTotals` — `test_get_daily_totals_empty`, `test_get_daily_totals_with_entries`, `test_get_daily_totals_multiple_foods`
- `TestGetLogsByDate` — `test_get_logs_by_date`
- `TestGetLogsByDateRange` — `test_get_logs_by_date_range`

**Key changes**:
- Existing module docstring is good — keep it.
- Wrap all functions into the four classes above.
- Add AAA docstring to every method.

- **VALIDATE**: `uv run pytest tests/unit/test_daily_log_service.py -v`

---

### Task 11: REWRITE `tests/unit/test_daily_log_model.py`

**Action**: **READ THE FILE FIRST** before implementing — content was not reviewed during planning. Audit it and apply the same three standards (header, classes, AAA). Follow the class-naming convention.

- **VALIDATE**: `uv run pytest tests/unit/test_daily_log_model.py -v`

---

### Task 12: REWRITE `tests/unit/test_state_consistency.py`

**Current state**: 1 flat function, no header, no class.

**Target**:
- Single class `TestGraphActionConsistency` — `test_graph_action_consistency`

**Key changes**:
- Add module-level docstring (LLM Usage: NONE — schema-only test).
- Wrap into class.
- Add AAA docstring.

- **VALIDATE**: `uv run pytest tests/unit/test_state_consistency.py -v`

---

### Task 13: REWRITE `tests/unit/test_response_node.py`

**Current state**: Already has class grouping and `_make_state` helper. **No module-level docstring**. No AAA docstrings.

**Key changes**:
- Add module-level scope/LLM docstring at top of file (before imports).
- Add AAA docstrings to all 8 test methods (6 in `TestBuildContext`, 6 in `TestResponseNode`).
- Leave class structure and `_make_state` helper completely unchanged.

- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

---

### Task 14: CREATE `tests/graph_api/__init__.py`

- **IMPLEMENT**: Create an empty `__init__.py` to mark the package.
- **VALIDATE**: File exists at `tests/graph_api/__init__.py`.

---

### Task 15: CREATE `tests/graph_api/conftest.py`

- **IMPLEMENT**: Copy the template from `graph-api-testing.md` Section 2 exactly.
- **GOTCHA**: `lg_client` is `scope="session"` — shared across all tests in the session.
- **GOTCHA**: `thread` is function-scoped — creates a new thread per test, preventing state bleed.

```python
"""Shared fixtures for graph-api tests. Requires langgraph dev running on port 2024."""
import pytest
from langgraph_sdk import get_client

LANGGRAPH_DEV_URL = "http://localhost:2024"

@pytest.fixture(scope="session")
def lg_client():
    """
    arrange: langgraph dev server must be running on localhost:2024.
    act:     Verify server health at /ok; return SDK client.
    assert:  Server reachable; skip all graph-api tests if not.
    """
    import httpx
    try:
        httpx.get(f"{LANGGRAPH_DEV_URL}/ok", timeout=2).raise_for_status()
    except Exception:
        pytest.skip(
            "langgraph dev server not running. "
            "Start it with: uv run langgraph dev"
        )
    return get_client(url=LANGGRAPH_DEV_URL)

@pytest.fixture
async def thread(lg_client):
    """Creates a fresh thread for each test and yields its thread_id."""
    t = await lg_client.threads.create()
    yield t["thread_id"]
```

- **VALIDATE**: `uv run pytest tests/graph_api/ --collect-only`

---

### Task 16: CREATE `tests/graph_api/test_graph_flows.py`

- **IMPLEMENT**: Use the template from `graph-api-testing.md` Section 5.
- **CRITICAL GOTCHA**: Set `ASSISTANT_ID = "fitpal"` — NOT `"nutritionist"`. This must match the key in `langgraph.json` line 4.
- **IMPLEMENT**: Module-level docstring (scope, LLM usage LIVE, prerequisites).
- **IMPLEMENT**: 5 test classes with AAA docstrings:
  - `TestFoodLoggingPath` — `test_log_common_food_returns_response`
  - `TestQueryStatsPath` — `test_query_todays_stats_returns_response`
  - `TestChitchatPath` — `test_greeting_routes_directly_to_response`
  - `TestNoMatchPath` — `test_unknown_food_gracefully_handled`
  - `TestMultiItemPath` — `test_multi_item_input_completes_without_error`
- **PATTERN**: Assert on structure (messages list length, non-empty content), never on exact LLM wording.

- **VALIDATE (dry-run)**: `uv run pytest tests/graph_api/ --collect-only`
- **VALIDATE (live)**: `uv run langgraph dev` in separate terminal, then `uv run pytest tests/graph_api/ -v -s`

---

## TESTING STRATEGY

### Unit Tests

All 12 files in `tests/unit/` are being *refactored* (structure only — no logic changes). If the tests still
pass after refactoring, the changes are correct.

### Integration Tests

No changes to `tests/integration/` — leave as-is.

### Graph-API Tests

New suite. Requires `uv run langgraph dev` running. Tests assert on response structure, not exact LLM content
(see `graph-api-testing.md` Section 6).

### Edge Cases to Watch

- **Task 7 (`test_feedback_logic.py`)**: After removing inline mocks, verify fixture injection works —
  function signature order matters for pytest.
- **Task 2 (`test_agent_selection.py`)**: Ambiguous-case test currently uses `in [...]`. After fixing,
  assert precisely based on what the mock returns.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
uv run ruff check tests/
```

### Level 2: Unit Tests (pre-commit gate, mandatory)

```bash
uv run pytest tests/unit/ -v
```

### Level 3: Full Suite

```bash
uv run pytest tests/ -v
```

### Level 4: Graph-API (requires running server)

```bash
# Terminal 1:
uv run langgraph dev

# Terminal 2:
uv run pytest tests/graph_api/ -v -s
```

### Level 5: Discovery Check

```bash
uv run pytest tests/ --collect-only
```

---

## ACCEPTANCE CRITERIA

- [ ] Every file in `tests/unit/` has a module-level scope + LLM-usage docstring
- [ ] Every test function/method is inside a `Test<What><Condition>` class
- [ ] Every test method has an AAA docstring with `arrange / act / assert` labels
- [ ] `test_agent_selection.py` — multi-result tests mock the LLM (no real API calls in unit tier)
- [ ] `test_feedback_logic.py` — no local `base_state` fixture; no inline DB/service mock setup; uses conftest fixtures
- [ ] `uv run pytest tests/unit/ -v` passes with 0 failures
- [ ] `uv run pytest tests/ -v` passes with 0 failures
- [ ] `tests/graph_api/conftest.py` exists with `lg_client` (session) + `thread` (function) fixtures
- [ ] `tests/graph_api/test_graph_flows.py` exists with 5 test classes covering all routing paths
- [ ] `ASSISTANT_ID = "fitpal"` in `test_graph_flows.py` (matches `langgraph.json`)
- [ ] `uv run pytest tests/graph_api/ --collect-only` succeeds with no import errors
- [ ] `uv run ruff check tests/` reports 0 errors

---

## COMPLETION CHECKLIST

- [ ] Task 1: `langgraph-sdk` added to dev deps
- [ ] Task 2: `test_agent_selection.py` — header + classes + AAA + LLM bug fixed
- [ ] Task 3: `test_input_parser.py` — header + classes + AAA
- [ ] Task 4: `test_food_search_node.py` — header + classes + AAA
- [ ] Task 5: `test_calculate_log_node.py` — header + classes + AAA
- [ ] Task 6: `test_stats_node.py` — header + classes + AAA
- [ ] Task 7: `test_feedback_logic.py` — header + classes + AAA + fixture bug fixed
- [ ] Task 8: `test_multi_item_loop.py` — header + classes + AAA + misplaced docstring fixed
- [ ] Task 9: `test_feedback_integration.py` — header + class + AAA
- [ ] Task 10: `test_daily_log_service.py` — classes + AAA (header already exists)
- [ ] Task 11: `test_daily_log_model.py` — audit + header + classes + AAA
- [ ] Task 12: `test_state_consistency.py` — header + class + AAA
- [ ] Task 13: `test_response_node.py` — header added + AAA added to all methods
- [ ] Task 14: `tests/graph_api/__init__.py` created
- [ ] Task 15: `tests/graph_api/conftest.py` created
- [ ] Task 16: `tests/graph_api/test_graph_flows.py` created
- [ ] All validation commands pass

---

## NOTES

### On `test_feedback_integration.py`

This file compiles the real graph with `MemorySaver` and patches all nodes. Strictly speaking it is a
compilation-integration test, but since all external I/O is mocked and it lives in `tests/unit/`, it is
treated as unit per the folder-name rule. No move required.

### On Task Order

Tasks 2–13 are all independent — they can be done in any order. Tasks 14–16 depend on Task 1 (sdk install).

### On `test_daily_log_model.py` (Task 11)

**Read the file first** before implementing — it was not reviewed during planning. Determine correct class
groupings from the existing test function names.

### Confidence Score

**8/10** — all patterns are documented in the skill references, bugs are clearly identified, and no
production code is being changed. Main risk: `test_daily_log_model.py` content is unknown.
