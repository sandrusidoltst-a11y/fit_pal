"""
Unit tests for Food Search Node (`food_search_node.py`).

Scope:
    Purely isolated unit tests. Verify the external database tool call works
    correctly when the state requires food items searches.

LLM Usage:
    NONE — food_search_node does not call an LLM.
"""
from unittest.mock import patch

from src.agents.nodes.food_search_node import food_search_node


class TestFoodSearchNodeHappyPath:
    """Test functionality of search with valid targets."""

    @patch("src.agents.nodes.food_search_node.search_food")
    def test_food_search_basic(self, mock_search_food, basic_state):
        """
        arrange: mock pending items and valid target returned by mock_search_food tool.
        act:     run food_search_node.
        assert:  returns correctly populated search_results property on state payload.
        """
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


class TestFoodSearchNodeEdgeCases:
    """Test failing or edge case branches."""

    def test_food_search_no_pending_items(self, basic_state):
        """
        arrange: empty pending_food_items state tracking parameter.
        act:     run food_search_node.
        assert:  returns an empty search results parameter gracefully.
        """
        basic_state["pending_food_items"] = []

        result = food_search_node(basic_state)

        assert result["search_results"] == []
