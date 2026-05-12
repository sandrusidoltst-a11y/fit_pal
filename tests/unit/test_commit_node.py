"""
Unit tests for Commit Node (`commit_node.py`).

Scope:
    Purely isolated unit tests. Verify batch DB write behavior.

LLM Usage:
    NONE — commit_node does not call an LLM.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from tests.conftest import TEST_RUNTIME_A
from src.agents.nodes.commit_node import commit_node


def _macro(
    *,
    name_en,
    amount_g,
    calories,
    protein,
    carbs,
    fat,
    source,
    food_id,
    name_he=None,
    original_text=None,
    category=None,
    tag=None,
    serving_amount_g=None,
    servings=None,
    amount_g_estimated=None,
):
    """Build a MacroResult dict for commit_node fixtures."""
    return {
        "name_en": name_en,
        "name_he": name_he,
        "amount_g": amount_g,
        "calories": calories,
        "protein": protein,
        "carbs": carbs,
        "fat": fat,
        "source": source,
        "category": category,
        "tag": tag,
        "serving_amount_g": serving_amount_g,
        "servings": servings,
        "amount_g_estimated": amount_g_estimated,
        "original_text": original_text or f"{amount_g}g {name_en}",
        "food_id": food_id,
    }


CHICKEN = _macro(
    name_en="chicken", name_he="עוף", amount_g=200, calories=330, protein=62,
    carbs=0, fat=7.2, source="database", food_id="food-uuid-1",
    category="protein", tag="lean", serving_amount_g=100.0, servings=2.0,
)
RICE = _macro(
    name_en="rice", amount_g=150, calories=195, protein=4, carbs=42, fat=0.4,
    source="database", food_id="food-uuid-2", category="carb",
    serving_amount_g=100.0, servings=1.5,
)
PIZZA = _macro(
    name_en="pizza", amount_g=300, calories=750, protein=30, carbs=85, fat=32,
    source="estimated", food_id=None, original_text="3 slices of pizza",
)


class TestCommitNodeSuccess:
    """Test successful batch commit flows."""

    async def test_commit_batch_success(
        self, basic_state, mock_log_food_entry
    ):
        """
        arrange: set pending_confirmations with two items and mock tools.
        act:     run commit_node.
        assert:  log_food_entry called for each item, processing_results populated.
        """
        mock_log_food_entry.ainvoke = AsyncMock(return_value={"id": "log-uuid-1", "status": "logged"})

        basic_state.update({
            "pending_confirmations": [CHICKEN, RICE],
            "log_food": {"consumed_at": datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)},
        })

        result = await commit_node(basic_state, TEST_RUNTIME_A)

        assert mock_log_food_entry.ainvoke.call_count == 2
        assert len(result["processing_results"]) == 2
        assert all(r["status"] == "LOGGED" for r in result["processing_results"])
        assert result["last_action"] == "LOGGED"
        assert result["pipeline_stage"] == "LOGGED"
        # food_name in ProcessingResult should carry the English name
        assert result["processing_results"][0]["food_name"] == "chicken"
        assert result["processing_results"][0]["name_he"] == "עוף"

    async def test_commit_estimated_item_creates_food_item(
        self, basic_state, mock_log_food_entry, mock_create_food_item
    ):
        """
        arrange: set pending_confirmations with estimated item (food_id=None).
        act:     run commit_node.
        assert:  create_food_item called with back-calculated per-100g values,
                 log_food_entry called with returned food_id.
        """
        mock_create_food_item.ainvoke = AsyncMock(
            return_value={"id": "food-uuid-99", "name_en": "pizza", "name_he": None, "mapping_created": False}
        )
        mock_log_food_entry.ainvoke = AsyncMock(return_value={"id": "log-uuid-1", "status": "logged"})

        basic_state.update({
            "pending_confirmations": [PIZZA],
            "log_food": {"consumed_at": datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)},
        })

        result = await commit_node(basic_state, TEST_RUNTIME_A)

        # Verify create_food_item called with the new signature + back-calculated per-100g values
        create_args = mock_create_food_item.ainvoke.call_args[0][0]
        assert create_args["name_en"] == "pizza"
        assert "name_he" in create_args
        assert create_args["calories_per_100g"] == round((750 / 300) * 100, 2)
        assert create_args["protein_per_100g"] == round((30 / 300) * 100, 2)
        assert create_args["carbs_per_100g"] == round((85 / 300) * 100, 2)
        assert create_args["fat_per_100g"] == round((32 / 300) * 100, 2)
        # Verify log_food_entry called with the created food_id
        log_args = mock_log_food_entry.ainvoke.call_args[0][0]
        assert log_args["food_id"] == "food-uuid-99"
        assert result["processing_results"][0]["source"] == "estimated"

    async def test_db_item_skips_food_item_creation(
        self, basic_state, mock_log_food_entry, mock_create_food_item
    ):
        """
        arrange: set pending_confirmations with database item (food_id set).
        act:     run commit_node.
        assert:  create_food_item NOT called, log_food_entry uses existing food_id.
        """
        mock_log_food_entry.ainvoke = AsyncMock(return_value={"id": "log-uuid-1", "status": "logged"})

        basic_state.update({
            "pending_confirmations": [CHICKEN],
            "log_food": {"consumed_at": datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)},
        })

        await commit_node(basic_state, TEST_RUNTIME_A)

        mock_create_food_item.ainvoke.assert_not_called()
        log_args = mock_log_food_entry.ainvoke.call_args[0][0]
        assert log_args["food_id"] == "food-uuid-1"

    async def test_mixed_batch(
        self, basic_state, mock_log_food_entry, mock_create_food_item
    ):
        """
        arrange: one DB item + one estimated item.
        act:     run commit_node.
        assert:  create_food_item called once (for estimated only), both items logged.
        """
        mock_create_food_item.ainvoke = AsyncMock(
            return_value={"id": "food-uuid-99", "name_en": "pizza", "name_he": None, "mapping_created": False}
        )
        mock_log_food_entry.ainvoke = AsyncMock(return_value={"id": "log-uuid-1", "status": "logged"})

        basic_state.update({
            "pending_confirmations": [CHICKEN, PIZZA],
            "log_food": {"consumed_at": datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)},
        })

        result = await commit_node(basic_state, TEST_RUNTIME_A)

        assert mock_create_food_item.ainvoke.call_count == 1
        assert mock_log_food_entry.ainvoke.call_count == 2
        assert len(result["processing_results"]) == 2

    async def test_clears_pending_confirmations(
        self, basic_state, mock_log_food_entry
    ):
        """
        arrange: set pending_confirmations with one item.
        act:     run commit_node.
        assert:  pending_confirmations is empty after commit.
        """
        mock_log_food_entry.ainvoke = AsyncMock(return_value={"id": "log-uuid-1", "status": "logged"})

        basic_state.update({
            "pending_confirmations": [CHICKEN],
            "log_food": {"consumed_at": datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)},
        })

        result = await commit_node(basic_state, TEST_RUNTIME_A)

        assert result["pending_confirmations"] == []

    async def test_processing_results_accumulated(
        self, basic_state, mock_log_food_entry
    ):
        """
        arrange: set existing processing_results in state.
        act:     run commit_node.
        assert:  new results appended to existing ones.
        """
        mock_log_food_entry.ainvoke = AsyncMock(return_value={"id": "log-uuid-1", "status": "logged"})

        existing = {
            "food_name": "prev",
            "name_he": None,
            "count": 100,
            "unit": "g",
            "original_text": "prev",
            "status": "LOGGED",
            "message": "Logged prev",
            "source": "database",
        }

        basic_state.update({
            "pending_confirmations": [CHICKEN],
            "processing_results": [existing],
            "log_food": {"consumed_at": datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)},
        })

        result = await commit_node(basic_state, TEST_RUNTIME_A)

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

        result = await commit_node(basic_state, TEST_RUNTIME_A)

        assert result == {}
