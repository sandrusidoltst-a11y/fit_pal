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

## 5. Mocking Async DB Sessions

Use the fixtures from `conftest.py`. Do NOT redefine them in individual test files.

```python
# conftest.py provides:
#   mock_calculate_log_db_session  — patches get_async_db_session in calculate_log_node
#   mock_daily_log_service_for_calc — patches daily_log_service in calculate_log_node
#   mock_stats_db_session          — patches get_async_db_session in stats_node
#   mock_daily_log_service_for_stats — patches daily_log_service in stats_node

async def test_calculate_log_writes_entry(
    self, basic_state, mock_calculate_log_db_session, mock_daily_log_service_for_calc, mock_calculate_macros
):
    """
    arrange: State with a selected food item; DB and service mocked.
    act:     calculate_log_node processes the state.
    assert:  create_log_entry is called once with the correct food_id.
    """
    basic_state["selected_food_id"] = 1
    basic_state["pending_food_items"] = [
        {"food_name": "chicken", "amount": 200.0, "unit": "g", "original_text": "200g chicken"}
    ]
    mock_calculate_macros.invoke.return_value = {"calories": 330, "protein": 62, "fat": 7.2, "carbs": 0}

    result = await calculate_log_node(basic_state)

    mock_daily_log_service_for_calc.create_log_entry.assert_called_once()
    assert result["last_action"] == "LOGGED"
```

---

## 6. Full File Template

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
