"""
Unit tests for Feedback Accumulation logic across selection and calculation nodes.

Scope:
    Purely isolated unit tests. Verify that the agent captures state processing metrics correctly across nodes.

LLM Usage:
    MOCKED — all LLM calls in disambiguation scenarios are mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.nodes.calculate_log_node import calculate_log_node
from src.agents.nodes.selection_node import agent_selection_node
from src.models import FoodItem
from src.schemas.selection_schema import FoodSelectionResult, SelectionStatus


def _make_food(food_id=123, name="Test Apple", calories=95.0, protein=0.5, fat=0.3, carbs=25.0):
    """Create a mock FoodItem for testing."""
    food = MagicMock(spec=FoodItem)
    food.id = food_id
    food.name = name
    food.calories = calories
    food.protein = protein
    food.fat = fat
    food.carbs = carbs
    return food


class TestCalculateLogFeedback:
    """Test feedback payload manipulations within Calculate Log context."""

    async def test_calculate_log_success_result(self, basic_state, mock_calculate_log_db_session, mock_daily_log_service_for_calc):
        """
        arrange: set up pending_food_items state alongside DB mock.
        act:     run calculate_log_node.
        assert:  verifies processing_results array populates with success feedback messages.
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
            "selected_food_id": 123
        })

        mock_calculate_log_db_session.get = AsyncMock(return_value=_make_food())
        mock_daily_log_service_for_calc.create_log_entry = AsyncMock()
        mock_daily_log_service_for_calc.get_logs_by_date = AsyncMock(return_value=[])

        result = await calculate_log_node(basic_state)

        assert "processing_results" in result
        assert len(result["processing_results"]) == 1
        res = result["processing_results"][0]
        assert res["status"] == "LOGGED"
        assert "Logged Test Apple" in res["message"]
        assert res["original_text"] == "one medium apple"

    async def test_calculate_log_accumulates_results(self, basic_state, mock_calculate_log_db_session, mock_daily_log_service_for_calc):
        """
        arrange: append existing results into current state loop tracking.
        act:     run calculate_log_node.
        assert:  verifies new results stack safely atop pre-existing statuses.
        """
        existing = {
            "food_name": "Prev", "amount": 1, "unit": "g", "original_text": "p",
            "status": "LOGGED", "message": "Prev logged"
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
            "selected_food_id": 123,
            "processing_results": [existing]
        })

        mock_calculate_log_db_session.get = AsyncMock(return_value=_make_food())
        mock_daily_log_service_for_calc.create_log_entry = AsyncMock()
        mock_daily_log_service_for_calc.get_logs_by_date = AsyncMock(return_value=[])

        result = await calculate_log_node(basic_state)

        assert len(result["processing_results"]) == 2
        assert result["processing_results"][0] == existing
        assert result["processing_results"][1]["status"] == "LOGGED"


class TestAgentSelectionFeedback:
    """Test feedback payload logic within Agent Selection behaviors."""

    def test_selection_failure_no_results(self, basic_state):
        """
        arrange: stage no search results resolving.
        act:     run agent_selection_node.
        assert:  ensure FAILED payload processes appropriately within response status messages.
        """
        basic_state.update({
            "search_results": [],
            "pending_food_items": [{"food_name": "Test Apple", "amount": 1, "unit": "medium", "original_text": "one medium apple"}],
        })

        result = agent_selection_node(basic_state)

        assert result["last_action"] == "NO_MATCH"
        assert "processing_results" in result
        assert len(result["processing_results"]) == 1
        res = result["processing_results"][0]
        assert res["status"] == "FAILED"
        assert "No search results" in res["message"]

    def test_selection_failure_llm(self, basic_state):
        """
        arrange: stage mocked LLM to return invalid/incommunicable payload properties.
        act:     run agent_selection_node.
        assert:  failure routes effectively catch incorrect states and surface a detailed failed message via node logic block.
        """
        basic_state.update({
            "search_results": [
                {"id": 1, "name": "Apple"},
                {"id": 2, "name": "Apple Pie"}
            ],
            "pending_food_items": [{"food_name": "Test Apple", "amount": 1, "unit": "medium", "original_text": "one medium apple"}],
        })

        with patch("src.agents.nodes.selection_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_structured = MagicMock()
            mock_llm.with_structured_output.return_value = mock_structured

            # Simulate LLM returning SELECTED but no ID (invalid state handled by node)
            mock_structured.invoke.return_value = FoodSelectionResult(
                food_id=None,
                status=SelectionStatus.SELECTED,
                reasoning="Error"
            )

            result = agent_selection_node(basic_state)

            assert result["last_action"] == "NO_MATCH"
            assert len(result["processing_results"]) == 1
            assert result["processing_results"][0]["status"] == "FAILED"
