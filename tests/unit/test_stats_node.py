"""
Unit tests for Stats Lookup Node (`stats_node.py`).

Scope:
    Purely isolated unit tests. Verify that querying historical tracking metrics functions correctly.

LLM Usage:
    NONE — stats_lookup_node does not call an LLM natively.
"""
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

from src.agents.nodes.stats_node import stats_lookup_node


class TestStatsNodeSingleDay:
    """Test functionality retrieving logs targeting a singular day reference."""

    async def test_stats_lookup_single_day(self, basic_state, mock_stats_db_session, mock_daily_log_service_for_stats):
        """
        arrange: Set parameter defaults specifying consumed_at but no date range bounds.
        act:     run stats_lookup_node.
        assert:  triggers mock method get_logs_by_date logic, mapping returning objects into state.
        """
        basic_state.update({
            "consumed_at": datetime(2023, 10, 27, 12, 0),
            "start_date": None,
            "end_date": None,
        })
        
        # Mock log objects
        log1 = MagicMock()
        log1.id = 1
        log1.food_id = 101
        log1.amount_g = 100.0
        log1.calories = 150.0
        log1.protein = 10.0
        log1.carbs = 20.0
        log1.fat = 5.0
        log1.timestamp = datetime(2023, 10, 27, 12, 0, 0)
        log1.meal_type = "Lunch"
        log1.original_text = "100g chicken"
        
        mock_daily_log_service_for_stats.get_logs_by_date = AsyncMock(return_value=[log1])
        
        result = await stats_lookup_node(basic_state)
        
        mock_daily_log_service_for_stats.get_logs_by_date.assert_called_once_with(
            mock_stats_db_session, date(2023, 10, 27)
        )
        mock_daily_log_service_for_stats.get_logs_by_date_range.assert_not_called()
        
        assert "daily_log_report" in result
        report = result["daily_log_report"]
        assert len(report) == 1
        assert report[0]["id"] == 1
        assert report[0]["calories"] == 150.0
        assert report[0]["original_text"] == "100g chicken"


class TestStatsNodeDateRange:
    """Test retrieving history metrics using date constraint brackets."""

    async def test_stats_lookup_date_range(self, basic_state, mock_stats_db_session, mock_daily_log_service_for_stats):
        """
        arrange: set bounding constraints on parameters 'start_date' and 'end_date'.
        act:     run stats_lookup_node.
        assert:  triggers method range handler bypass get_logs_by_date default logic completely.
        """
        start = date(2023, 10, 25)
        end = date(2023, 10, 27)
        basic_state.update({
            "consumed_at": datetime.today(),
            "start_date": start,
            "end_date": end,
        })
        
        mock_daily_log_service_for_stats.get_logs_by_date_range = AsyncMock(return_value=[])
        
        result = await stats_lookup_node(basic_state)
        
        mock_daily_log_service_for_stats.get_logs_by_date_range.assert_called_once_with(
            mock_stats_db_session, start, end
        )
        mock_daily_log_service_for_stats.get_logs_by_date.assert_not_called()
        assert result["daily_log_report"] == []
