"""
Unit tests for Confirmation Node (`confirmation_node.py`).

Scope:
    Purely isolated unit tests. Verify interrupt payload structure, confirm/reject/edit flows.

LLM Usage:
    MOCKED — _parse_confirmation LLM is mocked.
"""
from unittest.mock import AsyncMock, patch

from langgraph.types import Command

from tests.conftest import TEST_RUNTIME_A
from src.agents.nodes.confirmation_node import (
    _format_batch_preview,
    confirmation_node,
)
from src.i18n import MESSAGES
from src.schemas.confirmation_schema import ConfirmationResponse, ItemEdit


SAMPLE_BATCH = [
    {
        "name_en": "chicken",
        "name_he": "עוף",
        "amount_g": 200,
        "calories": 330,
        "protein": 62,
        "carbs": 0,
        "fat": 7.2,
        "source": "database",
        "category": "protein",
        "tag": "lean",
        "serving_amount_g": 100.0,
        "servings": 2.0,
        "default_unit": "g",
        "default_unit_weight_g": None,
        "original_text": "200g chicken",
        "food_id": "food-uuid-1",
    },
    {
        "name_en": "pizza",
        "name_he": None,
        "amount_g": 300,
        "calories": 750,
        "protein": 30,
        "carbs": 85,
        "fat": 32,
        "source": "estimated",
        "category": None,
        "tag": None,
        "serving_amount_g": None,
        "servings": None,
        "default_unit": None,
        "default_unit_weight_g": None,
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

    def test_estimated_item_tag(self, monkeypatch):
        """
        arrange: batch with an estimated item; force BOT_LANGUAGE=en.
        act:     format batch preview.
        assert:  estimated item has the localized estimated tag in description;
                 DB item does not.
        """
        monkeypatch.setenv("BOT_LANGUAGE", "en")
        preview = _format_batch_preview(SAMPLE_BATCH)

        db_item = preview["items"][0]
        est_item = preview["items"][1]
        tag = MESSAGES["confirmation_estimated_tag"]

        assert tag not in db_item["description"]
        assert tag in est_item["description"]
        assert db_item["source"] == "database"
        assert est_item["source"] == "estimated"
        assert "chicken" in db_item["description"]  # name_en renders in EN mode

    def test_hebrew_rendering(self, monkeypatch):
        """
        arrange: set BOT_LANGUAGE=he.
        act:     format batch preview.
        assert:  items with name_he render the Hebrew name;
                 items without name_he fall back to name_en.
        """
        monkeypatch.setenv("BOT_LANGUAGE", "he")
        preview = _format_batch_preview(SAMPLE_BATCH)

        db_item = preview["items"][0]  # has name_he="עוף"
        est_item = preview["items"][1]  # no name_he → falls back to name_en

        assert "עוף" in db_item["description"]
        assert "pizza" in est_item["description"]

    def test_servings_and_category_in_payload(self):
        """
        arrange: batch with db item (has servings/category) + estimated item (no mapping).
        act:     format batch preview.
        assert:  per-item payload surfaces servings + category fields for the bot to render.
        """
        preview = _format_batch_preview(SAMPLE_BATCH)

        assert preview["items"][0]["servings"] == 2.0
        assert preview["items"][0]["category"] == "protein"
        assert preview["items"][1]["servings"] is None
        assert preview["items"][1]["category"] is None

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

            result = await confirmation_node(basic_state, TEST_RUNTIME_A)

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

            result = await confirmation_node(basic_state, TEST_RUNTIME_A)

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
                "name_en": "chicken",
                "name_he": "עוף",
                "amount_g": 200,
                "calories": 330,
                "protein": 62,
                "carbs": 0,
                "fat": 7.2,
                "source": "database",
                "category": "protein",
                "tag": "lean",
                "serving_amount_g": 100.0,
                "servings": 2.0,
                "default_unit": "g",
                "default_unit_weight_g": None,
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
                "name_en": "Chicken",
                "name_he": "עוף",
                "amount_g": 150,
                "calories": 247.5,
                "protein": 46.5,
                "carbs": 0,
                "fat": 5.4,
                "source": "database",
                "category": "protein",
                "tag": "lean",
                "serving_amount_g": 100.0,
                "servings": 1.5,
            })

            result = await confirmation_node(basic_state, TEST_RUNTIME_A)

        assert interrupt_call_count == 2
        assert isinstance(result, Command)
        assert result.goto == "commit"
        # Verify the batch was updated with new amount
        assert result.update["pending_confirmations"][0]["amount_g"] == 150
        # Verify the edit called the tool with the new (count, unit) signature
        mock_calc.ainvoke.assert_called_once_with(
            {"food_id": "food-uuid-1", "count": 150.0, "unit": "g"}
        )


class TestConfirmationNodeEdgeCases:
    """Test edge cases."""

    async def test_no_pending_confirmations(self, basic_state):
        """
        arrange: empty pending_confirmations.
        act:     run confirmation_node.
        assert:  returns Command(goto="response") immediately.
        """
        basic_state["pending_confirmations"] = []

        result = await confirmation_node(basic_state, TEST_RUNTIME_A)

        assert isinstance(result, Command)
        assert result.goto == "response"
