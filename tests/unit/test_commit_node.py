"""
Unit tests for Commit Node (`commit_node.py`).

Scope:
    Purely isolated unit tests. Verify batch DB write behavior.

LLM Usage:
    NONE — commit_node does not call an LLM.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from src.agents.nodes.commit_node import commit_node


class TestCommitNodeSuccess:
    """Test successful batch commit flows."""

    async def test_commit_batch_success(self, basic_state, mock_log_food_entry, mock_query_food_logs_for_commit):
        """
        arrange: set pending_confirmations with two items and mock tools.
        act:     run commit_node.
        assert:  log_food_entry called for each item, processing_results populated.
        """
        mock_log_food_entry.ainvoke = AsyncMock(return_value={"id": 1, "status": "logged"})
        mock_query_food_logs_for_commit.ainvoke = AsyncMock(return_value=[])

        basic_state.update({
            "pending_confirmations": [
                {
                    "food_name": "chicken",
                    "amount_g": 200,
                    "calories": 330,
                    "protein": 62,
                    "carbs": 0,
                    "fat": 7.2,
                    "source": "database",
                    "original_text": "200g chicken",
                    "food_id": 1,
                },
                {
                    "food_name": "rice",
                    "amount_g": 150,
                    "calories": 195,
                    "protein": 4,
                    "carbs": 42,
                    "fat": 0.4,
                    "source": "database",
                    "original_text": "150g rice",
                    "food_id": 2,
                },
            ],
            "consumed_at": datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc),
        })

        result = await commit_node(basic_state)

        assert mock_log_food_entry.ainvoke.call_count == 2
        assert len(result["processing_results"]) == 2
        assert all(r["status"] == "LOGGED" for r in result["processing_results"])
        assert result["last_action"] == "LOGGED"

    async def test_commit_estimated_item(self, basic_state, mock_log_food_entry, mock_query_food_logs_for_commit):
        """
        arrange: set pending_confirmations with estimated item (food_id=None).
        act:     run commit_node.
        assert:  log_food_entry called with food_id=None.
        """
        mock_log_food_entry.ainvoke = AsyncMock(return_value={"id": 1, "status": "logged"})
        mock_query_food_logs_for_commit.ainvoke = AsyncMock(return_value=[])

        basic_state.update({
            "pending_confirmations": [
                {
                    "food_name": "pizza",
                    "amount_g": 300,
                    "calories": 750,
                    "protein": 30,
                    "carbs": 85,
                    "fat": 32,
                    "source": "estimated",
                    "original_text": "3 slices of pizza",
                    "food_id": None,
                },
            ],
            "consumed_at": datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc),
        })

        result = await commit_node(basic_state)

        call_args = mock_log_food_entry.ainvoke.call_args[0][0]
        assert call_args["food_id"] is None
        assert result["processing_results"][0]["source"] == "estimated"

    async def test_clears_pending_confirmations(self, basic_state, mock_log_food_entry, mock_query_food_logs_for_commit):
        """
        arrange: set pending_confirmations with one item.
        act:     run commit_node.
        assert:  pending_confirmations is empty after commit.
        """
        mock_log_food_entry.ainvoke = AsyncMock(return_value={"id": 1, "status": "logged"})
        mock_query_food_logs_for_commit.ainvoke = AsyncMock(return_value=[])

        basic_state.update({
            "pending_confirmations": [
                {
                    "food_name": "chicken",
                    "amount_g": 200,
                    "calories": 330,
                    "protein": 62,
                    "carbs": 0,
                    "fat": 7.2,
                    "source": "database",
                    "original_text": "200g chicken",
                    "food_id": 1,
                },
            ],
            "consumed_at": datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc),
        })

        result = await commit_node(basic_state)

        assert result["pending_confirmations"] == []

    async def test_processing_results_accumulated(self, basic_state, mock_log_food_entry, mock_query_food_logs_for_commit):
        """
        arrange: set existing processing_results in state.
        act:     run commit_node.
        assert:  new results appended to existing ones.
        """
        mock_log_food_entry.ainvoke = AsyncMock(return_value={"id": 1, "status": "logged"})
        mock_query_food_logs_for_commit.ainvoke = AsyncMock(return_value=[])

        existing = {
            "food_name": "prev",
            "amount": 100,
            "unit": "g",
            "original_text": "prev",
            "status": "LOGGED",
            "message": "Logged prev",
            "source": "database",
        }

        basic_state.update({
            "pending_confirmations": [
                {
                    "food_name": "chicken",
                    "amount_g": 200,
                    "calories": 330,
                    "protein": 62,
                    "carbs": 0,
                    "fat": 7.2,
                    "source": "database",
                    "original_text": "200g chicken",
                    "food_id": 1,
                },
            ],
            "processing_results": [existing],
            "consumed_at": datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc),
        })

        result = await commit_node(basic_state)

        assert len(result["processing_results"]) == 2
        assert result["processing_results"][0] == existing


class TestCommitNodeEdgeCases:
    """Test edge cases."""

    async def test_no_pending_confirmations(self, basic_state):
        """
        arrange: empty pending_confirmations.
        act:     run commit_node.
        assert:  returns empty dict.
        """
        basic_state["pending_confirmations"] = []

        result = await commit_node(basic_state)

        assert result == {}
