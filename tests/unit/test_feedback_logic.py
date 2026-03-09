"""
Unit tests for Feedback Accumulation logic across selection and calculation nodes.

Scope:
    Purely isolated unit tests. Verify that the agent captures state processing metrics correctly across nodes.

LLM Usage:
    MOCKED — all LLM calls in disambiguation scenarios are mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import TEST_CONFIG_A
from src.agents.nodes.calculate_macros_node import calculate_macros_node
from src.agents.nodes.selection_node import agent_selection_node
from src.schemas.selection_schema import FoodSelectionResult, SelectionStatus


class TestCalculateMacrosFeedback:
    """Test feedback payload manipulations within Calculate Macros context."""

    async def test_calculate_macros_success_result(self, basic_state, mock_calculate_macros):
        """
        arrange: set up pending_food_items state alongside tool mocks.
        act:     run calculate_macros_node.
        assert:  verifies pending_confirmations array populates with MacroResult.
        """
        basic_state.update({
            "pending_food_items": [
                {
                    "food_name": "Test Apple",
                    "amount": 1,
                    "unit": "medium",
                    "original_text": "one medium apple"
                }
            ],
            "selected_food_id": "food-uuid-123"
        })

        mock_calculate_macros.ainvoke = AsyncMock(return_value={
            "name": "Test Apple",
            "amount_g": 1,
            "calories": 95,
            "protein": 0.5,
            "carbs": 25,
            "fat": 0.3,
        })

        result = await calculate_macros_node(basic_state, TEST_CONFIG_A)

        assert "pending_confirmations" in result
        assert len(result["pending_confirmations"]) == 1
        res = result["pending_confirmations"][0]
        assert res["food_name"] == "Test Apple"
        assert res["source"] == "database"
        assert res["calories"] == 95
        assert res["original_text"] == "one medium apple"

    async def test_calculate_macros_accumulates_results(self, basic_state, mock_calculate_macros):
        """
        arrange: append existing confirmations into current state.
        act:     run calculate_macros_node.
        assert:  verifies new results stack safely atop pre-existing confirmations.
        """
        existing = {
            "food_name": "Prev",
            "amount_g": 100,
            "calories": 200,
            "protein": 20,
            "carbs": 10,
            "fat": 5,
            "source": "database",
            "original_text": "prev",
            "food_id": "food-uuid-1",
        }

        basic_state.update({
            "pending_food_items": [
                {
                    "food_name": "Test Apple",
                    "amount": 1,
                    "unit": "medium",
                    "original_text": "one medium apple"
                }
            ],
            "selected_food_id": "food-uuid-123",
            "pending_confirmations": [existing]
        })

        mock_calculate_macros.ainvoke = AsyncMock(return_value={
            "name": "Test Apple",
            "amount_g": 1,
            "calories": 100,
            "protein": 0,
            "carbs": 0,
            "fat": 0,
        })

        result = await calculate_macros_node(basic_state, TEST_CONFIG_A)

        assert len(result["pending_confirmations"]) == 2
        assert result["pending_confirmations"][0] == existing
        assert result["pending_confirmations"][1]["food_name"] == "Test Apple"


class TestAgentSelectionFeedback:
    """Test feedback payload logic within Agent Selection behaviors."""

    def test_selection_no_results_returns_no_match(self, basic_state):
        """
        arrange: stage no search results resolving.
        act:     run agent_selection_node.
        assert:  returns NO_MATCH without processing_results (estimation handles it).
        """
        basic_state.update({
            "search_results": [],
            "pending_food_items": [{"food_name": "Test Apple", "amount": 1, "unit": "medium", "original_text": "one medium apple"}],
        })

        result = agent_selection_node(basic_state)

        assert result["last_action"] == "NO_MATCH"
        assert "processing_results" not in result

    def test_selection_failure_llm_selected_no_id(self, basic_state):
        """
        arrange: stage mocked LLM to return SELECTED but no food_id.
        act:     run agent_selection_node.
        assert:  returns NO_MATCH without processing_results.
        """
        basic_state.update({
            "search_results": [
                {"id": "food-uuid-1", "name": "Apple", "source": "database"},
                {"id": "food-uuid-2", "name": "Apple Pie", "source": "database"}
            ],
            "pending_food_items": [{"food_name": "Test Apple", "amount": 1, "unit": "medium", "original_text": "one medium apple"}],
        })

        with patch("src.agents.nodes.selection_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_structured = MagicMock()
            mock_llm.with_structured_output.return_value = mock_structured

            mock_structured.invoke.return_value = FoodSelectionResult(
                food_id=None,
                status=SelectionStatus.SELECTED,
                reasoning="Error"
            )

            result = agent_selection_node(basic_state)

            assert result["last_action"] == "NO_MATCH"
            assert "processing_results" not in result
