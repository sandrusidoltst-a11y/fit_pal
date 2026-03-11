"""
Unit tests for Calculate Macros Node (`calculate_macros_node.py`).

Scope:
    Purely isolated unit tests. Verify macro calculation for both DB and estimation paths.

LLM Usage:
    MOCKED — estimation path LLM is mocked via get_llm_for_node.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import TEST_CONFIG_A
from src.agents.nodes.calculate_macros_node import calculate_macros_node


class TestCalculateMacrosDBPath:
    """Tests for the DB lookup path (selected_food_id is set)."""

    async def test_db_path_success(self, basic_state, mock_calculate_macros):
        """
        arrange: set mock calculate_food_macros to return valid macros.
        act:     run calculate_macros_node with selected_food_id.
        assert:  MacroResult with source="database" added to pending_confirmations.
        """
        mock_calculate_macros.ainvoke = AsyncMock(return_value={
            "name": "Chicken",
            "amount_g": 200,
            "calories": 330,
            "protein": 62,
            "carbs": 0,
            "fat": 7.2,
        })

        basic_state.update({
            "pending_food_items": [
                {"food_name": "chicken", "amount": 200.0, "unit": "g", "original_text": "200g chicken"}
            ],
            "selected_food_id": "food-uuid-1",
        })

        result = await calculate_macros_node(basic_state, TEST_CONFIG_A)

        assert len(result["pending_confirmations"]) == 1
        macro = result["pending_confirmations"][0]
        assert macro["food_name"] == "chicken"
        assert macro["source"] == "database"
        assert macro["food_id"] == "food-uuid-1"
        assert macro["calories"] == 330
        assert result["pending_food_items"] == []
        assert result["selected_food_id"] is None
        # Verify config forwarded
        mock_calculate_macros.ainvoke.assert_called_once_with(
            {"food_id": "food-uuid-1", "amount_g": 200.0}, config=TEST_CONFIG_A
        )

    async def test_db_path_error(self, basic_state, mock_calculate_macros):
        """
        arrange: set calculate_food_macros to return error.
        act:     run calculate_macros_node.
        assert:  FAILED result in processing_results, no pending_confirmations change.
        """
        mock_calculate_macros.ainvoke = AsyncMock(return_value={"error": "Food not found"})

        basic_state.update({
            "pending_food_items": [
                {"food_name": "mystery", "amount": 100.0, "unit": "g", "original_text": "100g mystery"}
            ],
            "selected_food_id": "food-uuid-999",
        })

        result = await calculate_macros_node(basic_state, TEST_CONFIG_A)

        assert len(result["processing_results"]) == 1
        assert result["processing_results"][0]["status"] == "FAILED"
        assert result["last_action"] == "NO_MATCH"
        assert "pending_confirmations" not in result

    async def test_accumulates_confirmations(self, basic_state, mock_calculate_macros):
        """
        arrange: set existing pending_confirmations in state.
        act:     run calculate_macros_node.
        assert:  new item is appended to existing confirmations.
        """
        existing = {
            "food_name": "rice",
            "amount_g": 200,
            "calories": 260,
            "protein": 5,
            "carbs": 56,
            "fat": 0.6,
            "source": "database",
            "original_text": "200g rice",
            "food_id": "food-uuid-2",
        }

        mock_calculate_macros.ainvoke = AsyncMock(return_value={
            "name": "Chicken",
            "amount_g": 100,
            "calories": 165,
            "protein": 31,
            "carbs": 0,
            "fat": 3.6,
        })

        basic_state.update({
            "pending_food_items": [
                {"food_name": "chicken", "amount": 100.0, "unit": "g", "original_text": "100g chicken"}
            ],
            "selected_food_id": "food-uuid-1",
            "pending_confirmations": [existing],
        })

        result = await calculate_macros_node(basic_state, TEST_CONFIG_A)

        assert len(result["pending_confirmations"]) == 2
        assert result["pending_confirmations"][0] == existing
        assert result["pending_confirmations"][1]["food_name"] == "chicken"

    async def test_db_path_preserves_estimated_source(self, basic_state, mock_calculate_macros):
        """
        arrange: mock calculate_food_macros returns source="estimated" (re-used estimated food).
        act:     run calculate_macros_node with selected_food_id.
        assert:  MacroResult preserves source="estimated" from DB.
        """
        mock_calculate_macros.ainvoke = AsyncMock(return_value={
            "name": "Protein Shake",
            "amount_g": 300,
            "calories": 200,
            "protein": 30,
            "carbs": 15,
            "fat": 3,
            "source": "estimated",
        })

        basic_state.update({
            "pending_food_items": [
                {"food_name": "protein shake", "amount": 300.0, "unit": "g", "original_text": "a protein shake"}
            ],
            "selected_food_id": "food-uuid-42",
        })

        result = await calculate_macros_node(basic_state, TEST_CONFIG_A)

        macro = result["pending_confirmations"][0]
        assert macro["source"] == "estimated"
        assert macro["food_id"] == "food-uuid-42"

    async def test_pops_pending_item(self, basic_state, mock_calculate_macros):
        """
        arrange: set two pending items.
        act:     run calculate_macros_node.
        assert:  first item removed, second remains.
        """
        mock_calculate_macros.ainvoke = AsyncMock(return_value={
            "name": "Chicken",
            "amount_g": 100,
            "calories": 165,
            "protein": 31,
            "carbs": 0,
            "fat": 3.6,
        })

        basic_state.update({
            "pending_food_items": [
                {"food_name": "chicken", "amount": 100.0, "unit": "g", "original_text": "100g chicken"},
                {"food_name": "rice", "amount": 200.0, "unit": "g", "original_text": "200g rice"},
            ],
            "selected_food_id": "food-uuid-1",
        })

        result = await calculate_macros_node(basic_state, TEST_CONFIG_A)

        assert len(result["pending_food_items"]) == 1
        assert result["pending_food_items"][0]["food_name"] == "rice"


class TestCalculateMacrosEstimationPath:
    """Tests for the LLM estimation path (selected_food_id is None)."""

    async def test_estimation_path(self, basic_state):
        """
        arrange: set selected_food_id=None and mock LLM estimation.
        act:     run calculate_macros_node.
        assert:  MacroResult with source="estimated" and food_id=None.
        """
        basic_state.update({
            "pending_food_items": [
                {"food_name": "homemade pizza", "amount": 300.0, "unit": "g", "original_text": "3 slices of pizza"}
            ],
            "selected_food_id": None,
            "last_action": "NO_MATCH",
        })

        mock_estimation = MagicMock()
        mock_estimation.calories = 750.0
        mock_estimation.protein = 30.0
        mock_estimation.carbs = 85.0
        mock_estimation.fat = 32.0

        with patch("src.agents.nodes.calculate_macros_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_structured = MagicMock()
            mock_llm.with_structured_output.return_value = mock_structured
            mock_structured.ainvoke = AsyncMock(return_value=mock_estimation)

            result = await calculate_macros_node(basic_state, TEST_CONFIG_A)

        assert len(result["pending_confirmations"]) == 1
        macro = result["pending_confirmations"][0]
        assert macro["source"] == "estimated"
        assert macro["food_id"] is None
        assert macro["calories"] == 750.0
        assert macro["food_name"] == "homemade pizza"


class TestCalculateMacrosEdgeCases:
    """Test edge cases."""

    async def test_empty_pending_items(self, basic_state):
        """
        arrange: empty pending_food_items.
        act:     run calculate_macros_node.
        assert:  returns empty dict.
        """
        basic_state["pending_food_items"] = []

        result = await calculate_macros_node(basic_state, TEST_CONFIG_A)

        assert result == {}
