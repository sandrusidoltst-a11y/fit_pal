"""
Unit tests for ADR-0005 invariants — user_intent vs pipeline_stage.

Scope:
    Verify three contracts the refactor introduces:
    1. user_intent is set once by input_parser_node and is not overwritten by
       any downstream node.
    2. pipeline_stage transitions through the expected values as nodes run.
    3. The legacy-fallback path (state has only last_action, no user_intent /
       pipeline_stage) routes correctly via intent_from_legacy /
       stage_from_legacy. Covers pre-refactor checkpoints resumed after
       deploy.

LLM Usage:
    MOCKED — no live LLM calls. Tools are mocked at the node module boundary
    via the conftest fixtures.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage

from src.agents.nodes.input_node import input_parser_node
from src.agents.nodes.selection_node import agent_selection_node
from src.agents.state import intent_from_legacy, stage_from_legacy
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
        # last_action also dual-written for back-compat:
        assert result["last_action"] == "QUERY_FOOD_INFO"


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


class TestLegacyCheckpointFallback:
    """Pre-refactor state dicts (only last_action, no user_intent/pipeline_stage)
    must still route correctly via the legacy-fallback helpers."""

    def test_intent_from_legacy_maps_intent_values(self):
        """Intent values pass through; stage values return None."""
        assert intent_from_legacy("LOG_FOOD") == "LOG_FOOD"
        assert intent_from_legacy("QUERY_FOOD_INFO") == "QUERY_FOOD_INFO"
        assert intent_from_legacy("CHITCHAT") == "CHITCHAT"
        assert intent_from_legacy("CONFIRMED") is None
        assert intent_from_legacy("LOGGED") is None
        assert intent_from_legacy("") is None
        assert intent_from_legacy(None) is None

    def test_stage_from_legacy_maps_stage_values(self):
        """Stage values pass through; intent values return None."""
        assert stage_from_legacy("SELECTED") == "SELECTED"
        assert stage_from_legacy("CONFIRMED") == "CONFIRMED"
        assert stage_from_legacy("LOGGED") == "LOGGED"
        assert stage_from_legacy("LOG_FOOD") is None
        assert stage_from_legacy("CHITCHAT") is None
        assert stage_from_legacy("") is None
        assert stage_from_legacy(None) is None

    def test_intent_and_stage_legacy_are_mutually_exclusive(self):
        """No legacy value resolves to both intent AND stage."""
        for value in (
            "LOG_FOOD", "QUERY_FOOD_INFO", "QUERY_DAILY_STATS", "CHITCHAT", "LOG_PERSONAL_STATS",
            "PENDING", "SELECTED", "NO_MATCH", "AMBIGUOUS",
            "AWAITING_CONFIRMATION", "CONFIRMED", "REJECTED", "LOGGED",
        ):
            intent = intent_from_legacy(value)
            stage = stage_from_legacy(value)
            assert not (intent and stage), (
                f"Value {value!r} resolves to both intent ({intent!r}) and "
                f"stage ({stage!r}) — UserIntent and PipelineStage must be disjoint."
            )
