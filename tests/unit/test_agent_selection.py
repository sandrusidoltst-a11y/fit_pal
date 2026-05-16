"""
Unit tests for Agent Selection Node (`selection_node.py`).

Scope:
    Purely isolated unit tests. Verify the conditional logic and state mutations
    of the agent selection node, including LLM-based disambiguation and
    auto-selection logic.

LLM Usage:
    MOCKED — all LLM calls in disambiguation scenarios are mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.nodes.selection_node import agent_selection_node
from src.schemas.selection_schema import FoodSelectionResult


class TestAgentSelectionAutoRouting:
    """Test standard auto-routing execution path."""

    async def test_selection_no_results(self, basic_state):
        """
        arrange: set empty search results.
        act:     run agent_selection_node.
        assert:  returns NO_MATCH and None for selected_food_id.
        """
        basic_state["search_results"] = []
        basic_state["pending_food_items"] = [{"food_name": "xyz", "count": 100.0, "unit": "g", "original_text": "xyz"}]


        result = await agent_selection_node(basic_state)

        assert result["selected_food_id"] is None
        assert result["pipeline_stage"] == "NO_MATCH"

    async def test_selection_single_result(self, basic_state):
        """
        arrange: set a single search result.
        act:     run agent_selection_node.
        assert:  returns SELECTED and the result's ID as selected_food_id.
        """
        basic_state["search_results"] = [{"id": "food-uuid-45", "name_en": "Beef", "name_he": None, "source": "database", "category": None, "tag": None}]
        basic_state["pending_food_items"] = [
            {"food_name": "beef", "count": 100.0, "unit": "g", "original_text": "100g beef"}
        ]

        result = await agent_selection_node(basic_state)

        assert result["selected_food_id"] == "food-uuid-45"
        assert result["pipeline_stage"] == "SELECTED"

    async def test_selection_empty_pending_items(self, basic_state):
        """
        arrange: empty pending items list.
        act:     run agent_selection_node.
        assert:  auto-selects first search result ID and doesn't crash.
        """
        basic_state["search_results"] = [{"id": "food-uuid-45", "name_en": "Beef", "name_he": None, "source": "database", "category": None, "tag": None}]
        basic_state["pending_food_items"] = []

        result = await agent_selection_node(basic_state)
        assert result["selected_food_id"] == "food-uuid-45"


class TestAgentSelectionLLMRouting:
    """Test logic related to LLM resolving disambiguation."""

    async def test_selection_multiple_results_clear_match(self, basic_state):
        """
        arrange: Multiple options for 'apple', LLM mocked to select 'Apples, raw'.
        act:     run agent_selection_node.
        assert:  Returns SELECTED with matching food ID.
        """
        basic_state["search_results"] = [
            {"id": "food-uuid-165", "name_en": "Apples, raw", "name_he": None, "source": "database", "category": None, "tag": None},
            {"id": "food-uuid-275", "name_en": "Apple betty", "name_he": None, "source": "database", "category": None, "tag": None},
            {"id": "food-uuid-163", "name_en": "Apple juice canned", "name_he": None, "source": "database", "category": None, "tag": None},
        ]
        basic_state["pending_food_items"] = [
            {"food_name": "apple", "amount": 150.0, "unit": "g", "original_text": "I ate an apple"}
        ]

        with patch("src.agents.nodes.selection_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_structured = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_llm.with_structured_output.return_value = mock_structured
            mock_structured.ainvoke = AsyncMock(return_value=FoodSelectionResult(status="SELECTED", food_id="food-uuid-165"))

            result = await agent_selection_node(basic_state)

        assert result["selected_food_id"] == "food-uuid-165"
        assert result["pipeline_stage"] == "SELECTED"

    async def test_selection_multiple_results_ambiguous(self, basic_state):
        """
        arrange: Highly ambiguous options (e.g., 'meat' vs 'Bacon' and 'Beef'), LLM mocked to NO_MATCH.
        act:     run agent_selection_node.
        assert:  Returns NO_MATCH, no food ID selected.
        """
        basic_state["search_results"] = [
            {"id": "food-uuid-44", "name_en": "Bacon", "name_he": None, "source": "database", "category": None, "tag": None},
            {"id": "food-uuid-45", "name_en": "Beef", "name_he": None, "source": "database", "category": None, "tag": None},
        ]
        basic_state["pending_food_items"] = [
            {"food_name": "meat", "count": 100.0, "unit": "g", "original_text": "some meat"}
        ]

        with patch("src.agents.nodes.selection_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_structured = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_llm.with_structured_output.return_value = mock_structured
            mock_structured.ainvoke = AsyncMock(return_value=FoodSelectionResult(status="NO_MATCH", food_id=None))

            result = await agent_selection_node(basic_state)

        assert result["pipeline_stage"] == "NO_MATCH"
        assert result["selected_food_id"] is None
