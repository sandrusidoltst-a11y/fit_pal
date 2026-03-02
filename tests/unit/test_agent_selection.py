"""
Unit tests for Agent Selection Node (`selection_node.py`).

Scope:
    Purely isolated unit tests. Verify the conditional logic and state mutations
    of the agent selection node, including LLM-based disambiguation and
    auto-selection logic.

LLM Usage:
    MOCKED — all LLM calls in disambiguation scenarios are mocked.
"""
from unittest.mock import MagicMock, patch

from src.agents.nodes.selection_node import agent_selection_node
from src.schemas.selection_schema import FoodSelectionResult


class TestAgentSelectionAutoRouting:
    """Test standard auto-routing execution path."""

    def test_selection_no_results(self, basic_state):
        """
        arrange: set empty search results.
        act:     run agent_selection_node.
        assert:  returns NO_MATCH and None for selected_food_id.
        """
        basic_state["search_results"] = []
        basic_state["pending_food_items"] = [{"food_name": "xyz", "amount": 100.0, "unit": "g", "original_text": "xyz"}]

        result = agent_selection_node(basic_state)

        assert result["selected_food_id"] is None
        assert result["last_action"] == "NO_MATCH"

    def test_selection_single_result(self, basic_state):
        """
        arrange: set a single search result.
        act:     run agent_selection_node.
        assert:  returns SELECTED and the result's ID as selected_food_id.
        """
        basic_state["search_results"] = [{"id": 45, "name": "Beef"}]
        basic_state["pending_food_items"] = [
            {"food_name": "beef", "amount": 100.0, "unit": "g", "original_text": "100g beef"}
        ]

        result = agent_selection_node(basic_state)

        assert result["selected_food_id"] == 45
        assert result["last_action"] == "SELECTED"

    def test_selection_empty_pending_items(self, basic_state):
        """
        arrange: empty pending items list.
        act:     run agent_selection_node.
        assert:  auto-selects first search result ID and doesn't crash.
        """
        basic_state["search_results"] = [{"id": 45, "name": "Beef"}]
        basic_state["pending_food_items"] = []

        result = agent_selection_node(basic_state)
        assert result["selected_food_id"] == 45


class TestAgentSelectionLLMRouting:
    """Test logic related to LLM resolving disambiguation."""

    def test_selection_multiple_results_clear_match(self, basic_state):
        """
        arrange: Multiple options for 'apple', LLM mocked to select 'Apples, raw'.
        act:     run agent_selection_node.
        assert:  Returns SELECTED with matching food ID.
        """
        basic_state["search_results"] = [
            {"id": 165, "name": "Apples, raw"},
            {"id": 275, "name": "Apple betty"},
            {"id": 163, "name": "Apple juice canned"},
        ]
        basic_state["pending_food_items"] = [
            {"food_name": "apple", "amount": 150.0, "unit": "g", "original_text": "I ate an apple"}
        ]

        with patch("src.agents.nodes.selection_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_structured = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_llm.with_structured_output.return_value = mock_structured
            mock_structured.invoke.return_value = FoodSelectionResult(status="SELECTED", food_id=165)

            result = agent_selection_node(basic_state)

        assert result["selected_food_id"] == 165
        assert result["last_action"] == "SELECTED"

    def test_selection_multiple_results_ambiguous(self, basic_state):
        """
        arrange: Highly ambiguous options (e.g., 'meat' vs 'Bacon' and 'Beef'), LLM mocked to NO_MATCH.
        act:     run agent_selection_node.
        assert:  Returns NO_MATCH, no food ID selected.
        """
        basic_state["search_results"] = [
            {"id": 44, "name": "Bacon"},
            {"id": 45, "name": "Beef"},
        ]
        basic_state["pending_food_items"] = [
            {"food_name": "meat", "amount": 100.0, "unit": "g", "original_text": "some meat"}
        ]

        with patch("src.agents.nodes.selection_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_structured = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_llm.with_structured_output.return_value = mock_structured
            mock_structured.invoke.return_value = FoodSelectionResult(status="NO_MATCH", food_id=None)

            result = agent_selection_node(basic_state)

        assert result["last_action"] == "NO_MATCH"
        assert result["selected_food_id"] is None
