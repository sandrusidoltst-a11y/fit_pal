"""
Unit tests for Food Search Node (`food_search_node.py`).

Scope:
    Purely isolated unit tests. Verify the search_food tool call works
    correctly when the state requires food items searches.

LLM Usage:
    NONE — food_search_node does not call an LLM.
"""
from unittest.mock import AsyncMock

from tests.conftest import TEST_CONFIG_A
from src.agents.nodes.food_search_node import food_search_node


class TestFoodSearchNodeHappyPath:
    """Test functionality of search with valid targets."""

    async def test_food_search_basic(self, basic_state, mock_search_food):
        """
        arrange: mock pending items and valid target returned by search_food tool.
        act:     run food_search_node.
        assert:  returns correctly populated search_results property on state payload.
        """
        mock_search_food.ainvoke = AsyncMock(return_value=[
            {"id": "food-uuid-1", "name": "Chicken breast", "source": "database"},
            {"id": "food-uuid-2", "name": "Chicken thigh", "source": "database"},
        ])

        basic_state["pending_food_items"] = [
            {"food_name": "chicken", "amount": 100.0, "unit": "g", "original_text": "100g chicken"}
        ]

        result = await food_search_node(basic_state, TEST_CONFIG_A)

        mock_search_food.ainvoke.assert_called_once_with(
            {"query": "chicken"}, config=TEST_CONFIG_A
        )
        assert "search_results" in result
        assert isinstance(result["search_results"], list)
        assert len(result["search_results"]) == 2
        assert result["search_results"][0]["id"] == "food-uuid-1"


class TestFoodSearchNodeEdgeCases:
    """Test failing or edge case branches."""

    async def test_food_search_no_pending_items(self, basic_state):
        """
        arrange: empty pending_food_items state tracking parameter.
        act:     run food_search_node.
        assert:  returns an empty search results parameter gracefully.
        """
        basic_state["pending_food_items"] = []

        result = await food_search_node(basic_state, TEST_CONFIG_A)

        assert result["search_results"] == []
