"""
Unit tests for Stats Lookup Node (`stats_node.py`).

Scope:
    Purely isolated unit tests. Verify that querying historical tracking
    metrics functions correctly across the three sub-state branches:
    target_date (single day), start_date+end_date (range), and default-today.

LLM Usage:
    NONE — stats_lookup_node does not call an LLM natively.
"""
from datetime import date, datetime
from unittest.mock import AsyncMock

from src.agents.nodes.stats_node import stats_lookup_node
from src.config import USER_TIMEZONE
from tests.conftest import TEST_RUNTIME_A


class TestStatsNodeSingleDay:
    """Single-day branch via query_stats.target_date."""

    async def test_stats_lookup_single_day(self, basic_state, mock_query_food_logs_for_stats):
        """
        arrange: query_stats has target_date set; no range fields.
        act:     run stats_lookup_node.
        assert:  query_food_logs called with target_date only.
        """
        basic_state["query_stats"] = {"target_date": date(2023, 10, 27)}

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

        result = await stats_lookup_node(basic_state, TEST_RUNTIME_A)

        mock_query_food_logs_for_stats.ainvoke.assert_called_once_with(
            {"target_date": "2023-10-27", "user_id": "fbeeb45f-d728-4c7c-9e6d-7b9b41685da7"}
        )

        assert "query_logs" in result
        report = result["query_logs"]
        assert len(report) == 1
        assert report[0]["id"] == "log-uuid-1"
        assert report[0]["calories"] == 150.0


class TestStatsNodeDateRange:
    """Range branch via query_stats.start_date + end_date."""

    async def test_stats_lookup_date_range(self, basic_state, mock_query_food_logs_for_stats):
        """
        arrange: query_stats has start_date + end_date.
        act:     run stats_lookup_node.
        assert:  query_food_logs called with target_date + end_date (range).
        """
        basic_state["query_stats"] = {
            "start_date": date(2023, 10, 25),
            "end_date": date(2023, 10, 27),
        }

        mock_query_food_logs_for_stats.ainvoke = AsyncMock(return_value=[])

        result = await stats_lookup_node(basic_state, TEST_RUNTIME_A)

        mock_query_food_logs_for_stats.ainvoke.assert_called_once_with(
            {"target_date": "2023-10-25", "end_date": "2023-10-27", "user_id": "fbeeb45f-d728-4c7c-9e6d-7b9b41685da7"}
        )
        assert result["query_logs"] == []


class TestStatsNodeDefaultToday:
    """Default branch — no target_date, no range → today (Israel-local)."""

    async def test_stats_lookup_defaults_to_today_israel_local(
        self, basic_state, mock_query_food_logs_for_stats
    ):
        """
        arrange: query_stats is {} (no date hints from user).
        act:     run stats_lookup_node.
        assert:  query_food_logs called with today's date in Israel-local tz.
        """
        basic_state["query_stats"] = {}
        mock_query_food_logs_for_stats.ainvoke = AsyncMock(return_value=[])

        result = await stats_lookup_node(basic_state, TEST_RUNTIME_A)

        expected_today = str(datetime.now(USER_TIMEZONE).date())
        mock_query_food_logs_for_stats.ainvoke.assert_called_once_with(
            {"target_date": expected_today, "user_id": "fbeeb45f-d728-4c7c-9e6d-7b9b41685da7"}
        )
        assert result["query_logs"] == []
