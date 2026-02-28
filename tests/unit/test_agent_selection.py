from src.agents.nodes.selection_node import agent_selection_node


from unittest.mock import MagicMock, patch
from src.schemas.selection_schema import FoodSelectionResult, SelectionStatus

@patch("src.agents.nodes.selection_node.get_llm_for_node")
def test_selection_no_results_estimation(mock_get_llm, basic_state):
    """Test handling of empty search results triggers estimation."""
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()
    
    # Mock LLM returning ESTIMATED
    result_mock = FoodSelectionResult(
        status=SelectionStatus.ESTIMATED, 
        food_id=None,
        confidence="It's off-menu",
        estimated_calories=200.0,
        estimated_protein=10.0,
        estimated_carbs=20.0,
        estimated_fat=5.0
    )
    mock_structured_llm.invoke.return_value = result_mock
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    basic_state["search_results"] = []
    basic_state["pending_food_items"] = [{"food_name": "Zinger Burger", "amount": 100.0, "unit": "g", "original_text": "Zinger Burger"}]

    result = agent_selection_node(basic_state)

    assert result["selected_food_id"] is None
    assert result["last_action"] == "ESTIMATED"
    assert "current_estimation" in result
    assert result["current_estimation"]["calories"] == 200.0
    assert result["current_estimation"]["protein"] == 10.0
    assert result["current_estimation"]["carbs"] == 20.0
    assert result["current_estimation"]["fat"] == 5.0

def test_selection_single_result(basic_state):
    """Test auto-selection with single search result."""
    basic_state["search_results"] = [{"id": 45, "name": "Beef"}]
    basic_state["pending_food_items"] = [
        {"food_name": "beef", "amount": 100.0, "unit": "g", "original_text": "100g beef"}
    ]

    result = agent_selection_node(basic_state)

    assert result["selected_food_id"] == 45
    assert result["last_action"] == "SELECTED"


def test_selection_multiple_results_clear_match(basic_state):
    """Test LLM selection with multiple results (clear winner)."""
    basic_state["search_results"] = [
        {"id": 165, "name": "Apples, raw"},
        {"id": 275, "name": "Apple betty"},
        {"id": 163, "name": "Apple juice canned"},
    ]
    basic_state["pending_food_items"] = [
        {"food_name": "apple", "amount": 150.0, "unit": "g", "original_text": "I ate an apple"}
    ]

    result = agent_selection_node(basic_state)

    # Should select "Apples, raw" as most appropriate for whole fruit
    assert result["selected_food_id"] == 165
    assert result["last_action"] == "SELECTED"


def test_selection_multiple_results_ambiguous(basic_state):
    """Test handling of truly ambiguous cases."""
    basic_state["search_results"] = [
        {"id": 44, "name": "Bacon"},
        {"id": 45, "name": "Beef"},
    ]
    basic_state["pending_food_items"] = [
        {"food_name": "meat", "amount": 100.0, "unit": "g", "original_text": "some meat"}
    ]

    result = agent_selection_node(basic_state)

    # LLM should always select one; AMBIGUOUS is handled as NO_MATCH in code
    assert result["last_action"] in ["SELECTED", "NO_MATCH"]


def test_selection_empty_pending_items(basic_state):
    """Test graceful handling when pending_food_items is empty."""
    basic_state["search_results"] = [{"id": 45, "name": "Beef"}]
    basic_state["pending_food_items"] = []

    # Should not crash, auto-select single result
    result = agent_selection_node(basic_state)
    assert result["selected_food_id"] == 45
