from unittest.mock import patch
from src.agents.nodes.food_search_node import food_search_node


@patch("src.agents.nodes.food_search_node.search_food")
def test_food_search_basic(mock_search_food, basic_state):
    """Test basic food search functionality."""
    mock_search_food.invoke.return_value = [{"id": 1, "name": "Chicken breast"}, {"id": 2, "name": "Chicken thigh"}]
    
    basic_state["pending_food_items"] = [
        {"food_name": "chicken", "amount": 100.0, "unit": "g", "original_text": "100g chicken"}
    ]

    result = food_search_node(basic_state)
    
    mock_search_food.invoke.assert_called_once()
    assert "search_results" in result
    assert isinstance(result["search_results"], list)
    # Should find at least one chicken-related item
    assert len(result["search_results"]) == 2
    assert result["search_results"][0]["id"] == 1


def test_food_search_no_pending_items(basic_state):
    """Test handling of empty pending items."""
    basic_state["pending_food_items"] = []

    result = food_search_node(basic_state)

    assert result["search_results"] == []
