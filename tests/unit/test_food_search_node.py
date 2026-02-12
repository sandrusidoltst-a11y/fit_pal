from src.agents.nodes.food_search_node import food_search_node


def test_food_search_basic(basic_state):
    """Test basic food search functionality."""
    basic_state["pending_food_items"] = [
        {"food_name": "chicken", "original_text": "100g chicken"}
    ]

    result = food_search_node(basic_state)

    assert "search_results" in result
    assert isinstance(result["search_results"], list)
    # Should find at least one chicken-related item
    assert len(result["search_results"]) > 0


def test_food_search_no_pending_items(basic_state):
    """Test handling of empty pending items."""
    basic_state["pending_food_items"] = []

    result = food_search_node(basic_state)

    assert result["search_results"] == []
