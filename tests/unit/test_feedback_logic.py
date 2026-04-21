"""
Unit tests for Feedback Accumulation logic across selection and calculation nodes.

Scope:
    Purely isolated unit tests. Verify that the agent captures state processing metrics correctly across nodes.

LLM Usage:
    MOCKED — all LLM calls in disambiguation scenarios are mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import TEST_RUNTIME_A
from src.agents.nodes.calculate_macros_node import calculate_macros_node
from src.agents.nodes.selection_node import agent_selection_node
from src.schemas.selection_schema import FoodSelectionResult, SelectionStatus


def _macros_return(**overrides):
    base = {
        "id": "00000000-0000-0000-0000-000000000123",
        "name_en": "Test Apple",
        "name_he": None,
        "amount_g": 100.0,
        "calories": 95.0,
        "protein": 0.5,
        "carbs": 25.0,
        "fat": 0.3,
        "source": "database",
        "category": None,
        "tag": None,
        "serving_amount_g": None,
        "servings": None,
        "default_unit": "g",
        "default_unit_weight_g": None,
    }
    base.update(overrides)
    return base


class TestCalculateMacrosFeedback:
    """Test feedback payload manipulations within Calculate Macros context."""

    async def test_calculate_macros_success_result(self, basic_state, mock_calculate_macros):
        """
        arrange: set up pending_food_items state alongside mocked calculate_food_macros tool.
        act:     run calculate_macros_node.
        assert:  verifies pending_confirmations array populates with MacroResult.
        """
        basic_state.update({
            "pending_food_items": [
                {
                    "food_name": "Test Apple",
                    "count": 100.0,
                    "unit": "g",
                    "original_text": "one medium apple",
                }
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000123",
        })

        mock_calculate_macros.ainvoke = AsyncMock(return_value=_macros_return())

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert "pending_confirmations" in result
        assert len(result["pending_confirmations"]) == 1
        res = result["pending_confirmations"][0]
        assert res["name_en"] == "Test Apple"
        assert res["source"] == "database"
        assert res["calories"] == 95.0
        assert res["original_text"] == "one medium apple"

    async def test_calculate_macros_accumulates_results(self, basic_state, mock_calculate_macros):
        """
        arrange: append existing confirmations into current state.
        act:     run calculate_macros_node.
        assert:  verifies new results stack safely atop pre-existing confirmations.
        """
        existing = {
            "name_en": "Prev",
            "name_he": None,
            "amount_g": 100,
            "calories": 200,
            "protein": 20,
            "carbs": 10,
            "fat": 5,
            "source": "database",
            "category": None,
            "tag": None,
            "serving_amount_g": None,
            "servings": None,
            "default_unit": "g",
            "default_unit_weight_g": None,
            "original_text": "prev",
            "food_id": "food-uuid-1",
        }

        basic_state.update({
            "pending_food_items": [
                {
                    "food_name": "Test Apple",
                    "count": 100.0,
                    "unit": "g",
                    "original_text": "one medium apple",
                }
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000123",
            "pending_confirmations": [existing],
        })

        mock_calculate_macros.ainvoke = AsyncMock(
            return_value=_macros_return(calories=100.0, protein=0.0, fat=0.0, carbs=0.0)
        )

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert len(result["pending_confirmations"]) == 2
        assert result["pending_confirmations"][0] == existing
        assert result["pending_confirmations"][1]["name_en"] == "Test Apple"


class TestAgentSelectionFeedback:
    """Test feedback payload logic within Agent Selection behaviors."""

    async def test_selection_no_results_returns_no_match(self, basic_state):
        """
        arrange: stage no search results resolving.
        act:     run agent_selection_node.
        assert:  returns NO_MATCH without processing_results (estimation handles it).
        """
        basic_state.update({
            "search_results": [],
            "pending_food_items": [{"food_name": "Test Apple", "count": 1, "unit": "piece", "original_text": "one medium apple"}],
        })

        result = await agent_selection_node(basic_state)

        assert result["last_action"] == "NO_MATCH"
        assert "processing_results" not in result

    async def test_selection_failure_llm_selected_no_id(self, basic_state):
        """
        arrange: stage mocked LLM to return SELECTED but no food_id.
        act:     run agent_selection_node.
        assert:  returns NO_MATCH without processing_results.
        """
        basic_state.update({
            "search_results": [
                {"id": "food-uuid-1", "name_en": "Apple", "name_he": None, "source": "database", "category": None, "tag": None},
                {"id": "food-uuid-2", "name_en": "Apple Pie", "name_he": None, "source": "database", "category": None, "tag": None},
            ],
            "pending_food_items": [{"food_name": "Test Apple", "count": 1, "unit": "piece", "original_text": "one medium apple"}],
        })

        with patch("src.agents.nodes.selection_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_structured = MagicMock()
            mock_llm.with_structured_output.return_value = mock_structured

            mock_structured.ainvoke = AsyncMock(return_value=FoodSelectionResult(
                food_id=None,
                status=SelectionStatus.SELECTED,
                reasoning="Error"
            ))

            result = await agent_selection_node(basic_state)

            assert result["last_action"] == "NO_MATCH"
            assert "processing_results" not in result
