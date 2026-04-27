"""
Unit tests for Load Daily Context Node (`load_daily_context_node.py`).

Scope:
    Purely isolated unit tests. Verifies the loader writes today's serialized
    logs to state by delegating to the `query_food_logs` tool with the user_id
    from runtime context and today's date in Israel local time.

LLM Usage:
    NONE — loader is a thin tool-call wrapper.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.nodes.load_daily_context_node import load_daily_context
from src.config import USER_TIMEZONE
from tests.conftest import TEST_RUNTIME_A, TEST_USER_A


SAMPLE_LOG = {
    "id": "log-uuid-1",
    "food_id": "food-uuid-1",
    "amount_g": 200.0,
    "calories": 330.0,
    "protein": 62.0,
    "carbs": 0.0,
    "fat": 7.2,
    "timestamp": "2026-04-22T22:00:00+03:00",
    "meal_type": None,
    "original_text": "200 גרם פרגית",
    "category": "protein",
    "tag": "lean",
    "serving_amount_g": 100.0,
}


def _make_mock_tool(return_value):
    """Build a MagicMock with `.ainvoke` configured as an AsyncMock."""
    tool = MagicMock()
    tool.ainvoke = AsyncMock(return_value=return_value)
    return tool


class TestLoadDailyContext:
    @pytest.mark.asyncio
    @patch("src.agents.nodes.load_daily_context_node.query_food_logs")
    async def test_returns_logs_from_tool(self, mock_tool, basic_state):
        """Returns {'daily_log_today': <list>} populated from the tool result."""
        mock_tool.ainvoke = AsyncMock(return_value=[SAMPLE_LOG])

        result = await load_daily_context(basic_state, TEST_RUNTIME_A)

        assert result == {"daily_log_today": [SAMPLE_LOG]}
        mock_tool.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.agents.nodes.load_daily_context_node.query_food_logs")
    async def test_empty_log_returns_empty_list(self, mock_tool, basic_state):
        """Empty tool result yields empty list in state — explicit signal, not silent."""
        mock_tool.ainvoke = AsyncMock(return_value=[])

        result = await load_daily_context(basic_state, TEST_RUNTIME_A)

        assert result == {"daily_log_today": []}

    @pytest.mark.asyncio
    @patch("src.agents.nodes.load_daily_context_node.query_food_logs")
    async def test_passes_today_israel_and_user_id_to_tool(self, mock_tool, basic_state):
        """Tool is invoked with target_date=today (Israel local, ISO) and user_id from runtime."""
        mock_tool.ainvoke = AsyncMock(return_value=[])

        await load_daily_context(basic_state, TEST_RUNTIME_A)

        # Computed at assertion time so the test stays green tomorrow.
        expected_today = datetime.now(USER_TIMEZONE).date().isoformat()
        call_kwargs = mock_tool.ainvoke.call_args.args[0]
        assert call_kwargs["user_id"] == TEST_USER_A
        assert call_kwargs["target_date"] == expected_today
