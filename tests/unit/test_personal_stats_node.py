"""
Unit tests for Personal Stats Node (`personal_stats_node.py`).

Scope:
    Purely isolated unit tests. Verify that body measurement extraction
    and logging works correctly with mocked LLM and tool.

LLM Usage:
    MOCKED — get_llm_for_node is mocked to return a fake structured output.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage

from src.agents.nodes.personal_stats_node import personal_stats_node
from tests.conftest import TEST_RUNTIME_A


class TestPersonalStatsNodeWeight:
    """Test weight logging through personal_stats_node."""

    @patch("src.agents.nodes.personal_stats_node.get_llm_for_node")
    async def test_weight_logging(self, mock_get_llm, basic_state, mock_log_personal_stat):
        """
        arrange: mock LLM returns weight extraction (74kg), mock tool logs it.
        act:     run personal_stats_node.
        assert:  tool called with stat_type=weight, value=74.0; processing_results populated.
        """
        # Mock LLM structured output
        mock_extraction = MagicMock()
        mock_extraction.stat_type = "weight"
        mock_extraction.value = 74.0
        mock_extraction.unit = "kg"

        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(return_value=mock_extraction)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm
        mock_get_llm.return_value = mock_llm

        mock_log_personal_stat.ainvoke = AsyncMock(
            return_value={"id": "stat-uuid-1", "status": "logged", "stat_type": "weight", "value": 74.0}
        )

        basic_state["messages"] = [HumanMessage(content="I weigh 74kg")]

        result = await personal_stats_node(basic_state, TEST_RUNTIME_A)

        mock_log_personal_stat.ainvoke.assert_called_once_with(
            {"stat_type": "weight", "value": 74.0, "user_id": "fbeeb45f-d728-4c7c-9e6d-7b9b41685da7"}
        )
        assert result["pipeline_stage"] == "LOGGED"
        assert len(result["processing_results"]) == 1
        assert result["processing_results"][0]["status"] == "LOGGED"
        assert "74.0kg" in result["processing_results"][0]["message"]


class TestPersonalStatsNodeBodyFat:
    """Test body fat logging through personal_stats_node."""

    @patch("src.agents.nodes.personal_stats_node.get_llm_for_node")
    async def test_body_fat_logging(self, mock_get_llm, basic_state, mock_log_personal_stat):
        """
        arrange: mock LLM returns body fat extraction (15%), mock tool logs it.
        act:     run personal_stats_node.
        assert:  tool called with stat_type=body_fat, value=15.0; processing_results populated.
        """
        mock_extraction = MagicMock()
        mock_extraction.stat_type = "body_fat"
        mock_extraction.value = 15.0
        mock_extraction.unit = "%"

        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(return_value=mock_extraction)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm
        mock_get_llm.return_value = mock_llm

        mock_log_personal_stat.ainvoke = AsyncMock(
            return_value={"id": "stat-uuid-2", "status": "logged", "stat_type": "body_fat", "value": 15.0}
        )

        basic_state["messages"] = [HumanMessage(content="Body fat is 15%")]

        result = await personal_stats_node(basic_state, TEST_RUNTIME_A)

        mock_log_personal_stat.ainvoke.assert_called_once_with(
            {"stat_type": "body_fat", "value": 15.0, "user_id": "fbeeb45f-d728-4c7c-9e6d-7b9b41685da7"}
        )
        assert result["pipeline_stage"] == "LOGGED"
        assert len(result["processing_results"]) == 1
        assert "15.0%" in result["processing_results"][0]["message"]


class TestPersonalStatsNodeAccumulation:
    """Test that processing_results accumulate correctly."""

    @patch("src.agents.nodes.personal_stats_node.get_llm_for_node")
    async def test_processing_results_accumulated(self, mock_get_llm, basic_state, mock_log_personal_stat):
        """
        arrange: set existing processing_results in state, mock LLM and tool.
        act:     run personal_stats_node.
        assert:  new result appended to existing processing_results.
        """
        mock_extraction = MagicMock()
        mock_extraction.stat_type = "weight"
        mock_extraction.value = 73.0
        mock_extraction.unit = "kg"

        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(return_value=mock_extraction)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm
        mock_get_llm.return_value = mock_llm

        mock_log_personal_stat.ainvoke = AsyncMock(
            return_value={"id": "stat-uuid-3", "status": "logged"}
        )

        basic_state["messages"] = [HumanMessage(content="I weigh 73kg")]
        basic_state["processing_results"] = [{"status": "LOGGED", "message": "existing"}]

        result = await personal_stats_node(basic_state, TEST_RUNTIME_A)

        assert len(result["processing_results"]) == 2
        assert result["processing_results"][0]["message"] == "existing"
        assert result["processing_results"][1]["status"] == "LOGGED"
