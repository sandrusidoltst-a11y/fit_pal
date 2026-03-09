"""
Unit tests for Stats Lookup Node (`stats_node.py`).

Scope:
    Purely isolated unit tests. Verify that querying historical tracking metrics functions correctly.

LLM Usage:
    NONE — stats_lookup_node does not call an LLM natively.
"""
from datetime import date, datetime
from unittest.mock import AsyncMock

from tests.conftest import TEST_CONFIG_A
from src.agents.nodes.stats_node import stats_lookup_node


class TestStatsNodeSingleDay:
    """Test functionality retrieving logs targeting a singular day reference."""

    async def test_stats_lookup_single_day(self, basic_state, mock_query_food_logs_for_stats):
        """
        arrange: Set parameter defaults specifying consumed_at but no date range bounds.
        act:     run stats_lookup_node.
        assert:  triggers query_food_logs tool with single date, mapping returning objects into state.
        """
        basic_state.update({
            "consumed_at": datetime(2023, 10, 27, 12, 0),
            "start_date": None,
            "end_date": None,
        })

        mock_query_food_logs_for_stats.ainvoke = AsyncMock(return_value=[{
            "id": "log-uuid-1",
            "food_id": "food-uuid-101",
            "amount_g": 100.0,
            "calories": 150.0,
            "protein": 10.0,
            "carbs": 20.0,
            "fat": 5.0,
            "timestamp": "2023-10-27T12:00:00",
            "meal_type": "Lunch",
            "original_text": "100g chicken",
        }])

        result = await stats_lookup_node(basic_state, TEST_CONFIG_A)

        mock_query_food_logs_for_stats.ainvoke.assert_called_once_with(
            {"target_date": "2023-10-27"}, config=TEST_CONFIG_A
        )

        assert "daily_log_report" in result
        report = result["daily_log_report"]
        assert len(report) == 1
        assert report[0]["id"] == "log-uuid-1"
        assert report[0]["calories"] == 150.0
        assert report[0]["original_text"] == "100g chicken"


class TestStatsNodeDateRange:
    """Test retrieving history metrics using date constraint brackets."""

    async def test_stats_lookup_date_range(self, basic_state, mock_query_food_logs_for_stats):
        """
        arrange: set bounding constraints on parameters 'start_date' and 'end_date'.
        act:     run stats_lookup_node.
        assert:  triggers query_food_logs tool with date range, bypassing single-date logic.
        """
        start = date(2023, 10, 25)
        end = date(2023, 10, 27)
        basic_state.update({
            "consumed_at": datetime.today(),
            "start_date": start,
            "end_date": end,
        })

        mock_query_food_logs_for_stats.ainvoke = AsyncMock(return_value=[])

        result = await stats_lookup_node(basic_state, TEST_CONFIG_A)

        mock_query_food_logs_for_stats.ainvoke.assert_called_once_with(
            {"target_date": "2023-10-25", "end_date": "2023-10-27"}, config=TEST_CONFIG_A
        )
        assert result["daily_log_report"] == []
