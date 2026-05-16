"""
Unit tests for ADR-0005 invariants — user_intent vs pipeline_stage.

Scope:
    Verify two contracts the refactor introduces:
    1. user_intent is set once by input_parser_node and is not overwritten by
       any downstream node.
    2. pipeline_stage transitions through the expected values as nodes run.

LLM Usage:
    MOCKED — no live LLM calls. Tools are mocked at the node module boundary
    via the conftest fixtures.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage

from src.agents.nodes.input_node import input_parser_node
from src.agents.nodes.selection_node import agent_selection_node
from src.schemas.input_schema import (
    ActionType,
    LogFoodEvent,
    QueryFoodInfoEvent,
    SingleFoodItem,
)


def _mock_input_llm(variant_to_return):
    """Patcher that wires get_llm_for_node to a mock returning the given variant."""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=variant_to_return)
    mock_llm.with_structured_output.return_value = mock_structured
    return patch("src.agents.nodes.input_node.get_llm_for_node", return_value=mock_llm)


class TestUserIntentImmutability:
    """user_intent set by input_parser must survive subsequent node writes.

    The dual-write pattern means downstream nodes never include user_intent in
    their return dicts. Because LangGraph applies returns as partial updates,
    omitting the key preserves the parser's value.
    """

    async def test_selection_node_does_not_overwrite_user_intent(self, basic_state, mock_search_food):
        """
        arrange: state pre-populated by parser (user_intent=LOG_FOOD); selection_node runs.
        act:     invoke agent_selection_node on the no-results edge case.
        assert:  the node return dict does NOT include `user_intent` — preserving the parser's value.
        """
        basic_state["search_results"] = []
        basic_state["pending_food_items"] = [
            {"food_name": "xyz", "count": 100.0, "unit": "g", "original_text": "xyz"}
        ]
        basic_state["user_intent"] = "LOG_FOOD"

        result = await agent_selection_node(basic_state)

        # The node writes pipeline_stage but must NOT write user_intent.
        assert "pipeline_stage" in result
        assert "user_intent" not in result, (
            "selection_node returned a user_intent key — this would overwrite "
            "the parser's value via LangGraph's partial-merge. user_intent is "
            "immutable for the turn (ADR-0005)."
        )

    async def test_query_food_info_intent_survives_through_parser(self, basic_state):
        """
        arrange: parser receives a nutrition question, emits QueryFoodInfoEvent.
        act:     run input_parser_node.
        assert:  user_intent="QUERY_FOOD_INFO" and pipeline_stage="PENDING".
        """
        variant = QueryFoodInfoEvent(
            action=ActionType.QUERY_FOOD_INFO,
            items=[SingleFoodItem(food_name="egg", count=1, unit="piece", original_text="egg")],
        )
        with _mock_input_llm(variant):
            basic_state["messages"] = [HumanMessage(content="how much protein in an egg?")]
            result = await input_parser_node(basic_state)

        assert result["user_intent"] == "QUERY_FOOD_INFO"
        assert result["pipeline_stage"] == "PENDING"


class TestPipelineStageTransitions:
    """Each writer node must set the expected pipeline_stage value."""

    async def test_input_parser_emits_pending(self, basic_state):
        """parser → PENDING."""
        variant = LogFoodEvent(
            action=ActionType.LOG_FOOD,
            items=[SingleFoodItem(food_name="rice", count=200, unit="g", original_text="200g rice")],
        )
        with _mock_input_llm(variant):
            basic_state["messages"] = [HumanMessage(content="200g rice")]
            result = await input_parser_node(basic_state)
        assert result["pipeline_stage"] == "PENDING"

    async def test_selection_no_results_emits_no_match(self, basic_state):
        """selection (empty) → NO_MATCH."""
        basic_state["search_results"] = []
        basic_state["pending_food_items"] = [
            {"food_name": "xyz", "count": 100.0, "unit": "g", "original_text": "xyz"}
        ]
        result = await agent_selection_node(basic_state)
        assert result["pipeline_stage"] == "NO_MATCH"

    async def test_selection_single_result_emits_selected(self, basic_state):
        """selection (one hit) → SELECTED."""
        basic_state["search_results"] = [
            {"id": "food-uuid-1", "name_en": "Beef", "name_he": None, "source": "database", "category": None, "tag": None}
        ]
        basic_state["pending_food_items"] = [
            {"food_name": "beef", "count": 100.0, "unit": "g", "original_text": "100g beef"}
        ]
        result = await agent_selection_node(basic_state)
        assert result["pipeline_stage"] == "SELECTED"
