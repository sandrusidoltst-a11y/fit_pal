"""
Unit tests for Food Search Node (`food_search_node.py`).

Scope:
    Purely isolated unit tests. Verify the async database query works
    correctly when the state requires food items searches.

LLM Usage:
    NONE — food_search_node does not call an LLM.
"""
from unittest.mock import AsyncMock, MagicMock

from src.agents.nodes.food_search_node import food_search_node


class TestFoodSearchNodeHappyPath:
    """Test functionality of search with valid targets."""

    async def test_food_search_basic(self, basic_state, mock_food_search_db_session):
        """
        arrange: mock pending items and valid DB results.
        act:     run food_search_node.
        assert:  returns correctly populated search_results property on state payload.
        """
        # Mock DB execute to return rows with id and name attributes
        row1 = MagicMock()
        row1.id = 1
        row1.name = "Chicken breast"
        row2 = MagicMock()
        row2.id = 2
        row2.name = "Chicken thigh"

        mock_result = MagicMock()
        mock_result.all.return_value = [row1, row2]
        mock_food_search_db_session.execute = AsyncMock(return_value=mock_result)

        basic_state["pending_food_items"] = [
            {"food_name": "chicken", "amount": 100.0, "unit": "g", "original_text": "100g chicken"}
        ]

        result = await food_search_node(basic_state)

        mock_food_search_db_session.execute.assert_called_once()
        assert "search_results" in result
        assert isinstance(result["search_results"], list)
        assert len(result["search_results"]) == 2
        assert result["search_results"][0]["id"] == 1


class TestFoodSearchNodeEdgeCases:
    """Test failing or edge case branches."""

    async def test_food_search_no_pending_items(self, basic_state):
        """
        arrange: empty pending_food_items state tracking parameter.
        act:     run food_search_node.
        assert:  returns an empty search results parameter gracefully.
        """
        basic_state["pending_food_items"] = []

        result = await food_search_node(basic_state)

        assert result["search_results"] == []
