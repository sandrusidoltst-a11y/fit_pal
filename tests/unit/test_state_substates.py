"""
Unit tests for AgentState per-action sub-states (`log_food`, `query_stats`).

Scope:
    Verify that ``input_parser_node`` always writes both sub-state keys on
    every turn — ``{}`` for the non-matching action — so cross-turn residue
    from a prior turn is structurally impossible.

LLM Usage:
    MOCKED — all LLM calls are mocked.
"""
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage

from src.agents.nodes.input_node import input_parser_node
from src.schemas.input_schema import (
    ActionType,
    ChitchatEvent,
    LogFoodEvent,
    QueryStatsEvent,
    SingleFoodItem,
)


def _mock_input_llm(variant_to_return):
    """Return a patcher context manager that wires get_llm_for_node to a mock LLM."""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=variant_to_return)
    mock_llm.with_structured_output.return_value = mock_structured
    return patch("src.agents.nodes.input_node.get_llm_for_node", return_value=mock_llm)


class TestSubStateAlwaysWritten:
    """Both sub-state keys must appear on every return (one populated, the other {})."""

    async def test_log_food_writes_log_food_substate_and_empty_query_stats(self, basic_state):
        """
        arrange: mocked LLM returns LogFoodEvent with consumed_at.
        act:     run input_parser_node.
        assert:  log_food carries consumed_at + meal_type; query_stats is {}.
        """
        consumed = datetime(2026, 4, 27, 18, 0, tzinfo=timezone.utc)
        variant = LogFoodEvent(
            action=ActionType.LOG_FOOD,
            consumed_at=consumed,
            meal_type="dinner",
            items=[SingleFoodItem(food_name="Pita", count=1, unit="piece", original_text="pita")],
        )

        with _mock_input_llm(variant):
            basic_state["messages"] = [HumanMessage(content="add a pita to yesterday's dinner")]
            result = await input_parser_node(basic_state)

        assert result["log_food"] == {"consumed_at": consumed, "meal_type": "dinner"}
        assert result["query_stats"] == {}

    async def test_query_range_writes_query_stats_and_empty_log_food(self, basic_state):
        """
        arrange: mocked LLM returns QueryStatsEvent with start_date/end_date.
        act:     run input_parser_node.
        assert:  query_stats carries the range; log_food is {}.
        """
        variant = QueryStatsEvent(
            action=ActionType.QUERY_DAILY_STATS,
            start_date=date(2026, 4, 25),
            end_date=date(2026, 4, 27),
        )

        with _mock_input_llm(variant):
            basic_state["messages"] = [HumanMessage(content="what did I eat last 3 days?")]
            result = await input_parser_node(basic_state)

        assert result["log_food"] == {}
        assert result["query_stats"]["start_date"] == date(2026, 4, 25)
        assert result["query_stats"]["end_date"] == date(2026, 4, 27)
        assert result["query_stats"]["target_date"] is None

    async def test_chitchat_writes_both_substates_as_empty(self, basic_state):
        """
        arrange: mocked LLM returns ChitchatEvent.
        act:     run input_parser_node.
        assert:  both sub-states are {} — no residue carried from any prior turn.
        """
        with _mock_input_llm(ChitchatEvent(action=ActionType.CHITCHAT)):
            basic_state["messages"] = [HumanMessage(content="hi")]
            result = await input_parser_node(basic_state)

        assert result["log_food"] == {}
        assert result["query_stats"] == {}
