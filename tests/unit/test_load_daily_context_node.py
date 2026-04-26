"""
Unit tests for Load Daily Context Node (`load_daily_context_node.py`).

Scope:
    Purely isolated unit tests. Verifies the loader writes today's serialized
    logs to state by delegating to `get_todays_logs_serialized` with the user_id
    from runtime context.

LLM Usage:
    NONE — loader is a thin DB-fetch wrapper.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.nodes.load_daily_context_node import load_daily_context
from tests.conftest import TEST_RUNTIME_A, TEST_USER_A


@asynccontextmanager
async def _fake_session_cm():
    """Async context manager yielding a MagicMock session.

    The loader does not touch the session itself — it passes it through to
    `get_todays_logs_serialized`, which is mocked separately. So a MagicMock
    session is safe.
    """
    yield MagicMock()


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


class TestLoadDailyContext:
    @pytest.mark.asyncio
    @patch(
        "src.agents.nodes.load_daily_context_node.get_todays_logs_serialized",
        new_callable=AsyncMock,
    )
    @patch(
        "src.agents.nodes.load_daily_context_node.get_async_db_session",
        return_value=_fake_session_cm(),
    )
    async def test_returns_logs_from_service(
        self, mock_session, mock_get_logs, basic_state
    ):
        """Returns {'daily_log_today': <list>} populated from the service."""
        mock_get_logs.return_value = [SAMPLE_LOG]

        result = await load_daily_context(basic_state, TEST_RUNTIME_A)

        assert result == {"daily_log_today": [SAMPLE_LOG]}
        mock_get_logs.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(
        "src.agents.nodes.load_daily_context_node.get_todays_logs_serialized",
        new_callable=AsyncMock,
    )
    @patch(
        "src.agents.nodes.load_daily_context_node.get_async_db_session",
        return_value=_fake_session_cm(),
    )
    async def test_empty_log_returns_empty_list(
        self, mock_session, mock_get_logs, basic_state
    ):
        """Empty service result yields empty list in state — explicit signal, not silent."""
        mock_get_logs.return_value = []

        result = await load_daily_context(basic_state, TEST_RUNTIME_A)

        assert result == {"daily_log_today": []}

    @pytest.mark.asyncio
    @patch(
        "src.agents.nodes.load_daily_context_node.get_todays_logs_serialized",
        new_callable=AsyncMock,
    )
    @patch(
        "src.agents.nodes.load_daily_context_node.get_async_db_session",
        return_value=_fake_session_cm(),
    )
    async def test_passes_user_id_from_runtime_context(
        self, mock_session, mock_get_logs, basic_state
    ):
        """user_id is read from runtime.context and forwarded to the service."""
        mock_get_logs.return_value = []

        await load_daily_context(basic_state, TEST_RUNTIME_A)

        # Second positional arg of get_todays_logs_serialized(session, user_id)
        call_args = mock_get_logs.call_args
        assert call_args.args[1] == TEST_USER_A
