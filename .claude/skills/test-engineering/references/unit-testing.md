# Unit Testing — FitPal Patterns

## 1. File Header Standard

Every test file MUST open with a module-level docstring declaring scope and LLM usage.
This is non-negotiable — it prevents tests drifting from their stated tier.

```python
"""
Unit tests for <Node/Service Name> (`<source_file>.py`).

Scope:
    Purely isolated unit tests. Verify the conditional logic and state mutations
    of <brief description of what the node/service does>.

LLM Usage:
    NONE — all LLM calls are mocked. No live API calls are made.
    [OR]
    MOCKED — <describe which LLM calls are mocked and how>.
"""
```

---

## 2. Class Grouping Standard

Group related test scenarios into classes by **decision branch** or **scenario type**.
This replaces a flat list of free functions and makes the file scannable.

```python
class Test<Node>AutoRouting:
    """Scenarios handled without LLM involvement (e.g., 0 or 1 result)."""

    def test_...(self, basic_state): ...
    def test_...(self, basic_state): ...


class Test<Node>LLMRouting:
    """Scenarios requiring (mocked) LLM disambiguation."""

    def test_...(self, basic_state, mock_llm): ...
```

**Naming rule**: `Test<What><Condition>` — e.g., `TestAgentSelectionAutoRouting`, `TestInputParserLogFood`.

---

## 3. AAA Docstring Standard

Every test function must have a docstring using the **Arrange / Act / Assert** pattern.
Use lowercase labels as shown:

```python
def test_selection_no_results(self, basic_state):
    """
    arrange: State where the food database search returned an empty list.
    act:     Agent selection node processes the state.
    assert:  No food ID is selected; last_action is set to NO_MATCH.
    """
    basic_state["search_results"] = []
    basic_state["pending_food_items"] = [
        {"food_name": "xyz", "amount": 100.0, "unit": "g", "original_text": "xyz"}
    ]

    result = agent_selection_node(basic_state)

    assert result["selected_food_id"] is None
    assert result["last_action"] == "NO_MATCH"
```

---

## 4. Mocking the LLM

Use `patch` targeting the import path **inside the node's module**, not the source module.

```python
from unittest.mock import MagicMock, patch

def test_input_parser_log_food(self, basic_state):
    """
    arrange: State with a food logging message; LLM mocked to return LOG_FOOD.
    act:     Input parser node processes the state.
    assert:  last_action is LOG_FOOD and pending_food_items is populated.
    """
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = FoodIntakeEvent(
        action="LOG_FOOD",
        food_items=[SingleFoodItem(food_name="chicken", amount=200.0, unit="g", original_text="200g chicken")],
    )

    with patch("src.agents.nodes.input_node.get_llm_for_node", return_value=mock_llm):
        basic_state["messages"] = [HumanMessage(content="I ate 200g of chicken")]
        result = input_parser_node(basic_state)

    assert result["last_action"] == "LOG_FOOD"
    assert len(result["pending_food_items"]) == 1
```

**Pattern for structured output mocks**: Return a real Pydantic model instance — do NOT return a raw dict.

---

## 5. Mocking Async Tools

Nodes call tools via `await tool.ainvoke(...)`. Mock the tool on the node's module. Use fixtures from `conftest.py` — do NOT redefine them in individual test files.

```python
# conftest.py provides tool mock fixtures:
#   mock_search_food               — patches search_food on food_search_node
#   mock_calculate_macros          — patches calculate_food_macros on calculate_log_node
#   mock_log_food_entry            — patches log_food_entry on calculate_log_node
#   mock_query_food_logs_for_calc  — patches query_food_logs on calculate_log_node
#   mock_query_food_logs_for_stats — patches query_food_logs on stats_node

async def test_calculate_log_writes_entry(
    self, basic_state, mock_calculate_macros, mock_log_food_entry, mock_query_food_logs_for_calc
):
    """
    arrange: State with a selected food item; tools mocked.
    act:     calculate_log_node processes the state.
    assert:  log_food_entry.ainvoke is called once.
    """
    mock_calculate_macros.ainvoke = AsyncMock(return_value={
        "calories": 330, "protein": 62, "fat": 7.2, "carbs": 0
    })
    mock_query_food_logs_for_calc.ainvoke = AsyncMock(return_value=[])

    basic_state["selected_food_id"] = 1
    basic_state["pending_food_items"] = [
        {"food_name": "chicken", "amount": 200.0, "unit": "g", "original_text": "200g chicken"}
    ]

    result = await calculate_log_node(basic_state)

    mock_log_food_entry.ainvoke.assert_called_once()
    assert result["last_action"] == "LOGGED"
```

---

## 6. Testing Service Functions (Real DB, Zero Mocks)

Service functions accept a `session` parameter (DI). Test them with `async_test_db_session` — a real in-memory SQLite with `FoodItem(id=1)` seeded. No mocks needed.

```python
"""
Unit tests for the daily_log_service async CRUD operations.

Scope:
    Service-layer tests using a real in-memory SQLite session.
    Verifies CRUD logic, aggregation queries, and date filtering.

LLM Usage:
    NONE — pure database operations.
"""
from datetime import date, datetime, timezone

import pytest

from src.services.daily_log_service import create_log_entry, get_daily_totals


async def test_create_log_entry(async_test_db_session):
    """
    arrange: Empty database with seeded FoodItem(id=1).
    act:     Create a log entry via the service function.
    assert:  Returned log has correct values and a generated ID.
    """
    now = datetime.now(timezone.utc)

    log = await create_log_entry(
        async_test_db_session,
        food_id=1, amount_g=100.0, calories=165.0,
        protein=31.0, carbs=0.0, fat=3.6, timestamp=now,
    )

    assert log.id is not None
    assert log.calories == 165.0


async def test_aggregation(async_test_db_session):
    """
    arrange: Two log entries for the same day.
    act:     Query daily totals.
    assert:  Totals are the sum of both entries.
    """
    now = datetime.now(timezone.utc)

    await create_log_entry(async_test_db_session, food_id=1, amount_g=100.0,
                           calories=165.0, protein=31.0, carbs=0.0, fat=3.6, timestamp=now)
    await create_log_entry(async_test_db_session, food_id=1, amount_g=50.0,
                           calories=82.5, protein=15.5, carbs=0.0, fat=1.8, timestamp=now)

    totals = await get_daily_totals(async_test_db_session, now.date())
    assert totals["calories"] == pytest.approx(247.5, abs=0.1)
```

**Key differences from node tests:**
- **Zero mocks** — `async_test_db_session` provides a real async SQLite session
- **Flat functions** — no class grouping needed (no decision branches to organize)
- **Write-then-read** — arrange creates records, act queries them, assert checks results
- **Tests actual SQL** — verifies WHERE clauses, SUM aggregations, date filtering

---

## 7. Full File Template

```python
"""
Unit tests for the Agent Selection Node (`selection_node.py`).

Scope:
    Purely isolated unit tests. Verify the conditional logic that determines
    whether an item is automatically selected, requires LLM disambiguation,
    or yields no match.

LLM Usage:
    MOCKED in TestAgentSelectionLLMRouting — MagicMock replaces get_llm_for_node.
    NONE in TestAgentSelectionAutoRouting — no LLM call is made at all.
"""
from unittest.mock import MagicMock, patch

from src.agents.nodes.selection_node import agent_selection_node
from src.schemas.selection_schema import FoodSelectionResult


class TestAgentSelectionAutoRouting:
    """Scenarios handled without LLM involvement (0 or 1 search result)."""

    def test_no_results_yields_no_match(self, basic_state):
        """
        arrange: Search returned an empty list.
        act:     agent_selection_node processes the state.
        assert:  selected_food_id is None and last_action is NO_MATCH.
        """
        basic_state["search_results"] = []
        basic_state["pending_food_items"] = [
            {"food_name": "xyz", "amount": 100.0, "unit": "g", "original_text": "xyz"}
        ]

        result = agent_selection_node(basic_state)

        assert result["selected_food_id"] is None
        assert result["last_action"] == "NO_MATCH"

    def test_single_result_auto_selects(self, basic_state):
        """
        arrange: Search returned exactly one result (Beef, id=45).
        act:     agent_selection_node processes the state.
        assert:  food_id 45 is selected and last_action is SELECTED.
        """
        basic_state["search_results"] = [{"id": 45, "name": "Beef"}]
        basic_state["pending_food_items"] = [
            {"food_name": "beef", "amount": 100.0, "unit": "g", "original_text": "100g beef"}
        ]

        result = agent_selection_node(basic_state)

        assert result["selected_food_id"] == 45
        assert result["last_action"] == "SELECTED"


class TestAgentSelectionLLMRouting:
    """Scenarios requiring mocked LLM reasoning to disambiguate multiple results."""

    def test_multiple_results_selects_closest_match(self, basic_state):
        """
        arrange: Three apple variants in search results; mocked LLM returns 'Apples, raw' (id=165).
        act:     agent_selection_node processes the state.
        assert:  food_id 165 is selected and last_action is SELECTED.
        """
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = FoodSelectionResult(status="SELECTED", food_id=165)

        with patch("src.agents.nodes.selection_node.get_llm_for_node", return_value=mock_llm):
            basic_state["search_results"] = [
                {"id": 165, "name": "Apples, raw"},
                {"id": 275, "name": "Apple betty"},
                {"id": 163, "name": "Apple juice canned"},
            ]
            basic_state["pending_food_items"] = [
                {"food_name": "apple", "amount": 150.0, "unit": "g", "original_text": "I ate an apple"}
            ]

            result = agent_selection_node(basic_state)

        assert result["selected_food_id"] == 165
        assert result["last_action"] == "SELECTED"

    def test_no_match_llm_response_sets_no_match(self, basic_state):
        """
        arrange: Two unrelated results; mocked LLM returns NO_MATCH.
        act:     agent_selection_node processes the state.
        assert:  selected_food_id is None and last_action is NO_MATCH.
        """
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = FoodSelectionResult(status="NO_MATCH", food_id=None)

        with patch("src.agents.nodes.selection_node.get_llm_for_node", return_value=mock_llm):
            basic_state["search_results"] = [
                {"id": 44, "name": "Bacon"},
                {"id": 45, "name": "Beef"},
            ]
            basic_state["pending_food_items"] = [
                {"food_name": "meat", "amount": 100.0, "unit": "g", "original_text": "some meat"}
            ]

            result = agent_selection_node(basic_state)

        assert result["selected_food_id"] is None
        assert result["last_action"] == "NO_MATCH"
```
