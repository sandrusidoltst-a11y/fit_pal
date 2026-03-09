"""
Unit tests for Confirmation Node (`confirmation_node.py`).

Scope:
    Purely isolated unit tests. Verify interrupt payload structure, confirm/reject/edit flows.

LLM Usage:
    MOCKED — _parse_confirmation LLM is mocked.
"""
from unittest.mock import AsyncMock, patch

from langgraph.types import Command

from tests.conftest import TEST_CONFIG_A
from src.agents.nodes.confirmation_node import (
    _format_batch_preview,
    confirmation_node,
)
from src.schemas.confirmation_schema import ConfirmationResponse, ItemEdit


SAMPLE_BATCH = [
    {
        "food_name": "chicken",
        "amount_g": 200,
        "calories": 330,
        "protein": 62,
        "carbs": 0,
        "fat": 7.2,
        "source": "database",
        "original_text": "200g chicken",
        "food_id": "food-uuid-1",
    },
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
]


class TestFormatBatchPreview:
    """Test the _format_batch_preview helper."""

    def test_payload_structure(self):
        """
        arrange: sample batch with DB and estimated items.
        act:     format batch preview.
        assert:  payload has question, items, and totals keys.
        """
        preview = _format_batch_preview(SAMPLE_BATCH)

        assert "question" in preview
        assert "items" in preview
        assert "totals" in preview
        assert len(preview["items"]) == 2

    def test_estimated_item_tag(self):
        """
        arrange: batch with an estimated item.
        act:     format batch preview.
        assert:  estimated item has "(estimated)" in description.
        """
        preview = _format_batch_preview(SAMPLE_BATCH)

        db_item = preview["items"][0]
        est_item = preview["items"][1]

        assert "(estimated)" not in db_item["description"]
        assert "(estimated)" in est_item["description"]

    def test_totals_calculation(self):
        """
        arrange: sample batch.
        act:     format batch preview.
        assert:  totals sum correctly.
        """
        preview = _format_batch_preview(SAMPLE_BATCH)

        assert preview["totals"]["calories"] == 1080
        assert preview["totals"]["protein"] == 92


class TestConfirmationNodeConfirm:
    """Test the confirm flow."""

    async def test_confirm_returns_commit_command(self, basic_state):
        """
        arrange: state with pending_confirmations, mock interrupt to return "yes".
        act:     run confirmation_node.
        assert:  returns Command(goto="commit") with CONFIRMED action.
        """
        basic_state["pending_confirmations"] = list(SAMPLE_BATCH)

        with patch("src.agents.nodes.confirmation_node.interrupt", return_value="yes"), \
             patch("src.agents.nodes.confirmation_node._parse_confirmation", new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = ConfirmationResponse(action="confirm")

            result = await confirmation_node(basic_state, TEST_CONFIG_A)

        assert isinstance(result, Command)
        assert result.goto == "commit"
        assert result.update["last_action"] == "CONFIRMED"


class TestConfirmationNodeReject:
    """Test the reject flow."""

    async def test_reject_returns_response_command(self, basic_state):
        """
        arrange: state with pending_confirmations, mock interrupt to return "no".
        act:     run confirmation_node.
        assert:  returns Command(goto="response") with REJECTED action and FAILED results.
        """
        basic_state["pending_confirmations"] = list(SAMPLE_BATCH)

        with patch("src.agents.nodes.confirmation_node.interrupt", return_value="no"), \
             patch("src.agents.nodes.confirmation_node._parse_confirmation", new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = ConfirmationResponse(action="reject")

            result = await confirmation_node(basic_state, TEST_CONFIG_A)

        assert isinstance(result, Command)
        assert result.goto == "response"
        assert result.update["last_action"] == "REJECTED"
        assert len(result.update["processing_results"]) == 2
        assert all(r["status"] == "FAILED" for r in result.update["processing_results"])


class TestConfirmationNodeEdit:
    """Test the edit flow."""

    async def test_edit_loops_and_re_shows(self, basic_state):
        """
        arrange: mock interrupt to return edit first, then confirm.
        act:     run confirmation_node.
        assert:  interrupt called twice, final result is commit command.
        """
        basic_state["pending_confirmations"] = [
            {
                "food_name": "chicken",
                "amount_g": 200,
                "calories": 330,
                "protein": 62,
                "carbs": 0,
                "fat": 7.2,
                "source": "database",
                "original_text": "200g chicken",
                "food_id": "food-uuid-1",
            },
        ]

        interrupt_call_count = 0

        def mock_interrupt(payload):
            nonlocal interrupt_call_count
            interrupt_call_count += 1
            if interrupt_call_count == 1:
                return "change chicken to 150g"
            return "yes"

        edit_response = ConfirmationResponse(
            action="edit",
            edits=[ItemEdit(item_index=0, edit_type="change_amount", new_amount_g=150.0)]
        )
        confirm_response = ConfirmationResponse(action="confirm")

        parse_call_count = 0

        async def mock_parse(text, batch):
            nonlocal parse_call_count
            parse_call_count += 1
            if parse_call_count == 1:
                return edit_response
            return confirm_response

        with patch("src.agents.nodes.confirmation_node.interrupt", side_effect=mock_interrupt), \
             patch("src.agents.nodes.confirmation_node._parse_confirmation", side_effect=mock_parse), \
             patch("src.agents.nodes.confirmation_node.calculate_food_macros") as mock_calc:
            mock_calc.ainvoke = AsyncMock(return_value={
                "name": "Chicken",
                "amount_g": 150,
                "calories": 247.5,
                "protein": 46.5,
                "carbs": 0,
                "fat": 5.4,
            })

            result = await confirmation_node(basic_state, TEST_CONFIG_A)

        assert interrupt_call_count == 2
        assert isinstance(result, Command)
        assert result.goto == "commit"
        # Verify the batch was updated with new amount
        assert result.update["pending_confirmations"][0]["amount_g"] == 150


class TestConfirmationNodeEdgeCases:
    """Test edge cases."""

    async def test_no_pending_confirmations(self, basic_state):
        """
        arrange: empty pending_confirmations.
        act:     run confirmation_node.
        assert:  returns Command(goto="response") immediately.
        """
        basic_state["pending_confirmations"] = []

        result = await confirmation_node(basic_state, TEST_CONFIG_A)

        assert isinstance(result, Command)
        assert result.goto == "response"
