"""
Unit tests for Calculate Log Node (`calculate_log_node.py`).

Scope:
    Purely isolated unit tests. Verify the macronutrient calculations and Database entry formatting.

LLM Usage:
    NONE — calculate_log_node does not call an LLM.
"""
from unittest.mock import AsyncMock, MagicMock
from datetime import date, datetime, timezone

from src.agents.nodes.calculate_log_node import calculate_log_node


class TestCalculateLogNodeSuccess:
    """Tests corresponding to a successful calculation and DB entry recording."""

    async def test_calculate_log_node_success(self, basic_state, mock_calculate_macros, mock_log_food_entry, mock_query_food_logs_for_calc):
        """
        arrange: set mock behaviors and properties for active item to log.
        act:     run calculate_log_node.
        assert:  triggers mock calculate_macros tool, records database entry via log_food_entry tool, updates daily logs payload and resets processing status.
        """
        mock_calculate_macros.ainvoke = AsyncMock(return_value={
            "name": "Test Food",
            "amount_g": 100,
            "calories": 200,
            "protein": 20,
            "carbs": 10,
            "fat": 5,
        })

        mock_query_food_logs_for_calc.ainvoke = AsyncMock(return_value=[{
            "id": 1,
            "food_id": 123,
            "amount_g": 100.0,
            "calories": 200.0,
            "protein": 20.0,
            "carbs": 10.0,
            "fat": 5.0,
            "timestamp": "2023-10-26T12:00:00",
            "meal_type": "Lunch",
            "original_text": "100g test food",
        }])

        basic_state.update({
            "pending_food_items": [{
                "food_name": "Test Food",
                "amount": 100.0,
                "unit": "g",
                "original_text": "100g test food"
            }],
            "selected_food_id": 123,
            "consumed_at": datetime(2023, 10, 26, 12, 0, tzinfo=timezone.utc),
            "last_action": "SELECTED",
        })

        # Execute
        result = await calculate_log_node(basic_state)

        # Assert tool calls
        mock_calculate_macros.ainvoke.assert_called_once_with({"food_id": 123, "amount_g": 100.0})
        mock_log_food_entry.ainvoke.assert_called_once()
        mock_query_food_logs_for_calc.ainvoke.assert_called_once()

        # Assert state update
        assert "daily_log_report" in result
        report = result["daily_log_report"]
        assert len(report) == 1
        assert report[0]["id"] == 1
        assert report[0]["calories"] == 200.0

        assert result["pending_food_items"] == []
        assert result["last_action"] == "LOGGED"
        assert result["selected_food_id"] is None
        assert len(result["processing_results"]) == 1
        assert result["processing_results"][0]["status"] == "LOGGED"


class TestCalculateLogNodeEdgeCases:
    """Test functionality of calculation edge cases."""

    async def test_calculate_log_node_no_selection_or_processed(self, basic_state, mock_calculate_macros, mock_log_food_entry, mock_query_food_logs_for_calc):
        """
        arrange: simulation where there is no food active to selection.
        act:     run calculate_log_node.
        assert:  no operations execute and the empty state is returned cleanly.
        """
        basic_state.update({
            "pending_food_items": [{"food_name": "Test", "amount": 100.0, "unit": "g", "original_text": "test"}],
            "selected_food_id": None,
            "consumed_at": datetime(2023, 10, 26, 12, 0, tzinfo=timezone.utc),
            "last_action": "SELECTED",
        })

        # Execute
        result = await calculate_log_node(basic_state)

        # Assert
        mock_calculate_macros.ainvoke.assert_not_called()
        mock_log_food_entry.ainvoke.assert_not_called()
        assert result["pending_food_items"] == []  # Should still remove item to avoid loop
        assert result["selected_food_id"] is None
        # Report should remain unchanged (empty list in this case)
        assert result["daily_log_report"] == []

    async def test_calculate_log_node_macro_error(self, basic_state, mock_calculate_macros, mock_log_food_entry, mock_query_food_logs_for_calc):
        """
        arrange: set calculate_food_macros tool to return an error dictionary.
        act:     run calculate_log_node.
        assert:  process catches error natively, bypasses DB additions returning with state intact parameters.
        """
        mock_calculate_macros.ainvoke = AsyncMock(return_value={"error": "Food not found"})

        basic_state.update({
            "pending_food_items": [{"food_name": "Test", "amount": 100.0, "unit": "g", "original_text": "test"}],
            "selected_food_id": 999,
            "daily_log_report": [{"id": 1}],  # Existing report
            "consumed_at": datetime(2023, 10, 26, 12, 0, tzinfo=timezone.utc),
            "last_action": "SELECTED",
        })

        # Execute
        result = await calculate_log_node(basic_state)

        # Assert
        mock_log_food_entry.ainvoke.assert_not_called()
        # Report should remain unchanged
        assert result["daily_log_report"] == [{"id": 1}]
        assert result["pending_food_items"] == []
