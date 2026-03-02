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
from src.models import FoodItem


def _make_food(food_id=123, name="Test Food", calories=200.0, protein=20.0, fat=5.0, carbs=10.0):
    """Create a mock FoodItem for testing."""
    food = MagicMock(spec=FoodItem)
    food.id = food_id
    food.name = name
    food.calories = calories
    food.protein = protein
    food.fat = fat
    food.carbs = carbs
    return food


class TestCalculateLogNodeSuccess:
    """Tests corresponding to a successful calculation and DB entry recording."""

    async def test_calculate_log_node_success(self, basic_state, mock_calculate_log_db_session, mock_daily_log_service_for_calc):
        """
        arrange: set mock behaviors and properties for active item to log.
        act:     run calculate_log_node.
        assert:  triggers mock DB lookup, records database entry via create_log_entry logic, updates daily logs payload and resets processing status.
        """
        mock_calculate_log_db_session.get = AsyncMock(return_value=_make_food())

        # Mock return of get_logs_by_date
        log_mock = MagicMock()
        log_mock.id = 1
        log_mock.food_id = 123
        log_mock.amount_g = 100.0
        log_mock.calories = 200.0
        log_mock.protein = 20.0
        log_mock.carbs = 10.0
        log_mock.fat = 5.0
        log_mock.timestamp = datetime(2023, 10, 26, 12, 0)
        log_mock.meal_type = "Lunch"
        log_mock.original_text = "100g test food"

        mock_daily_log_service_for_calc.get_logs_by_date = AsyncMock(return_value=[log_mock])

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

        # Assert DB lookup
        mock_calculate_log_db_session.get.assert_called_once_with(FoodItem, 123)

        mock_daily_log_service_for_calc.create_log_entry.assert_called_once()
        call_args = mock_daily_log_service_for_calc.create_log_entry.call_args[1]
        assert call_args["food_id"] == 123
        assert call_args["amount_g"] == 100.0
        assert call_args["calories"] == 200
        assert call_args["timestamp"].date() == date(2023, 10, 26)

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

    async def test_calculate_log_node_no_selection_or_processed(self, basic_state, mock_calculate_log_db_session, mock_daily_log_service_for_calc):
        """
        arrange: simulation where there is no food active to selection.
        act:     run calculate_log_node.
        assert:  no operations execute and the empty state is returned cleanly.
        """
        basic_state.update({
            "pending_food_items": [{"food_name": "Test", "amount": 100.0, "unit": "g", "original_text": "test"}],
            "selected_food_id": None,
            "consumed_at": datetime(2023, 10, 26, 12, 0, tzinfo=timezone.utc),
            "last_action": "SELECTED",  # Simulation
        })

        # Execute
        result = await calculate_log_node(basic_state)

        # Assert
        mock_calculate_log_db_session.get.assert_not_called()
        mock_daily_log_service_for_calc.create_log_entry.assert_not_called()
        assert result["pending_food_items"] == []  # Should still remove item to avoid loop
        assert result["selected_food_id"] is None
        # Report should remain unchanged (empty list in this case)
        assert result["daily_log_report"] == []

    async def test_calculate_log_node_macro_error(self, basic_state, mock_calculate_log_db_session, mock_daily_log_service_for_calc):
        """
        arrange: set DB to return None for food lookup (food not found).
        act:     run calculate_log_node.
        assert:  process catches error natively, bypasses DB additions returning with state intact parameters.
        """
        mock_calculate_log_db_session.get = AsyncMock(return_value=None)

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
        mock_daily_log_service_for_calc.create_log_entry.assert_not_called()
        # Report should remain unchanged
        assert result["daily_log_report"] == [{"id": 1}]
        assert result["pending_food_items"] == []
