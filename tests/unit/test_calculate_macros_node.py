"""
Unit tests for Calculate Macros Node (`calculate_macros_node.py`).

Scope:
    Purely isolated unit tests. Verify macro calculation for both DB and estimation paths.

LLM Usage:
    MOCKED — estimation path LLM is mocked via get_llm_for_node.
"""
import uuid as uuid_mod
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_RUNTIME_A
from src.agents.nodes.calculate_macros_node import calculate_macros_node


def _make_food(
    *,
    name_en="Chicken breast",
    name_he="חזה עוף",
    calories=165.0,
    protein=31.0,
    fat=3.6,
    carbs=0.0,
    default_unit="g",
    default_unit_weight_g=None,
    source="database",
    food_id="00000000-0000-0000-0000-000000000001",
):
    """Build a MagicMock FoodItem with the attributes compute_food_macros reads."""
    food = MagicMock()
    food.id = uuid_mod.UUID(food_id)
    food.name_en = name_en
    food.name_he = name_he
    food.calories = calories
    food.protein = protein
    food.fat = fat
    food.carbs = carbs
    food.default_unit = default_unit
    food.default_unit_weight_g = default_unit_weight_g
    food.source = source
    return food


def _make_mapping(category="protein", tag="lean", serving_amount_g=100.0):
    mapping = MagicMock()
    mapping.category = category
    mapping.tag = tag
    mapping.serving_amount_g = serving_amount_g
    return mapping


@pytest.fixture
def mock_get_food_by_id():
    """Mock get_food_by_id service used by calculate_macros_node."""
    with patch(
        "src.agents.nodes.calculate_macros_node.get_food_by_id",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
def _fake_session_cm():
    """Patch get_async_db_session to yield a dummy async session object."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake():
        yield MagicMock()

    with patch(
        "src.agents.nodes.calculate_macros_node.get_async_db_session", _fake
    ):
        yield


class TestCalculateMacrosDBPath:
    """Tests for the DB lookup path (selected_food_id is set)."""

    async def test_db_path_success(self, basic_state, _fake_session_cm, mock_get_food_by_id):
        """
        arrange: mock get_food_by_id returns (FoodItem, CoachFoodMapping).
        act:     run calculate_macros_node with selected_food_id.
        assert:  MacroResult with database fields added to pending_confirmations.
        """
        food = _make_food()
        mapping = _make_mapping()
        mock_get_food_by_id.return_value = (food, mapping)

        basic_state.update({
            "pending_food_items": [
                {"food_name": "chicken", "count": 200.0, "unit": "g", "original_text": "200g chicken"}
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000001",
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert len(result["pending_confirmations"]) == 1
        macro = result["pending_confirmations"][0]
        assert macro["name_en"] == "Chicken breast"
        assert macro["name_he"] == "חזה עוף"
        assert macro["amount_g"] == 200.0
        assert macro["calories"] == 330.0
        assert macro["source"] == "database"
        assert macro["category"] == "protein"
        assert macro["tag"] == "lean"
        assert macro["servings"] == 2.0
        assert macro["food_id"] == "00000000-0000-0000-0000-000000000001"
        assert result["pending_food_items"] == []
        assert result["selected_food_id"] is None

    async def test_db_path_food_not_found(self, basic_state, _fake_session_cm, mock_get_food_by_id):
        """
        arrange: get_food_by_id returns None (food vanished).
        act:     run calculate_macros_node.
        assert:  FAILED result; last_action=NO_MATCH; no confirmation added.
        """
        mock_get_food_by_id.return_value = None

        basic_state.update({
            "pending_food_items": [
                {"food_name": "mystery", "count": 100.0, "unit": "g", "original_text": "100g mystery"}
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000999",
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert len(result["processing_results"]) == 1
        assert result["processing_results"][0]["status"] == "FAILED"
        assert result["last_action"] == "NO_MATCH"
        assert "pending_confirmations" not in result

    async def test_db_path_unit_mismatch(self, basic_state, _fake_session_cm, mock_get_food_by_id):
        """
        arrange: food has default_unit='piece', user gave unit='slice'.
        act:     run calculate_macros_node.
        assert:  FAILED with unit-mismatch message.
        """
        food = _make_food(default_unit="piece", default_unit_weight_g=50.0)
        mapping = _make_mapping()
        mock_get_food_by_id.return_value = (food, mapping)

        basic_state.update({
            "pending_food_items": [
                {"food_name": "egg", "count": 2.0, "unit": "slice", "original_text": "2 slices of egg"}
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000001",
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert result["processing_results"][0]["status"] == "FAILED"
        assert "Unit mismatch" in result["processing_results"][0]["message"]

    async def test_db_path_piece_unit_resolves_to_grams(
        self, basic_state, _fake_session_cm, mock_get_food_by_id
    ):
        """
        arrange: food default_unit=piece, weight=50g; user said 2 pieces.
        act:     run calculate_macros_node.
        assert:  amount_g=100; macros calculated for 100g.
        """
        food = _make_food(
            name_en="Egg", default_unit="piece", default_unit_weight_g=50.0,
            calories=155.0, protein=13.0, fat=11.0, carbs=1.1,
        )
        mapping = _make_mapping(category="protein", tag="medium", serving_amount_g=50.0)
        mock_get_food_by_id.return_value = (food, mapping)

        basic_state.update({
            "pending_food_items": [
                {"food_name": "egg", "count": 2.0, "unit": "piece", "original_text": "2 eggs"}
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000001",
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        macro = result["pending_confirmations"][0]
        assert macro["amount_g"] == 100.0
        assert macro["calories"] == 155.0
        assert macro["servings"] == 2.0

    async def test_accumulates_confirmations(
        self, basic_state, _fake_session_cm, mock_get_food_by_id
    ):
        """
        arrange: set existing pending_confirmations in state.
        act:     run calculate_macros_node.
        assert:  new item appended to existing confirmations.
        """
        existing = {
            "name_en": "rice",
            "name_he": None,
            "amount_g": 200,
            "calories": 260,
            "protein": 5,
            "carbs": 56,
            "fat": 0.6,
            "source": "database",
            "category": "carb",
            "tag": None,
            "serving_amount_g": 100.0,
            "servings": 2.0,
            "default_unit": "g",
            "default_unit_weight_g": None,
            "original_text": "200g rice",
            "food_id": "food-uuid-2",
        }

        food = _make_food()
        mapping = _make_mapping()
        mock_get_food_by_id.return_value = (food, mapping)

        basic_state.update({
            "pending_food_items": [
                {"food_name": "chicken", "count": 100.0, "unit": "g", "original_text": "100g chicken"}
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000001",
            "pending_confirmations": [existing],
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert len(result["pending_confirmations"]) == 2
        assert result["pending_confirmations"][0] == existing
        assert result["pending_confirmations"][1]["name_en"] == "Chicken breast"

    async def test_db_path_preserves_estimated_source(
        self, basic_state, _fake_session_cm, mock_get_food_by_id
    ):
        """
        arrange: food.source='estimated' (re-used estimated food).
        act:     run calculate_macros_node.
        assert:  MacroResult preserves source='estimated'.
        """
        food = _make_food(source="estimated", name_en="Protein Shake")
        mapping = None
        mock_get_food_by_id.return_value = (food, mapping)

        basic_state.update({
            "pending_food_items": [
                {"food_name": "protein shake", "count": 300.0, "unit": "g", "original_text": "a protein shake"}
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000001",
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        macro = result["pending_confirmations"][0]
        assert macro["source"] == "estimated"
        assert macro["category"] is None
        assert macro["tag"] is None

    async def test_pops_pending_item(
        self, basic_state, _fake_session_cm, mock_get_food_by_id
    ):
        """
        arrange: set two pending items.
        act:     run calculate_macros_node.
        assert:  first item removed, second remains.
        """
        food = _make_food()
        mapping = _make_mapping()
        mock_get_food_by_id.return_value = (food, mapping)

        basic_state.update({
            "pending_food_items": [
                {"food_name": "chicken", "count": 100.0, "unit": "g", "original_text": "100g chicken"},
                {"food_name": "rice", "count": 200.0, "unit": "g", "original_text": "200g rice"},
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000001",
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert len(result["pending_food_items"]) == 1
        assert result["pending_food_items"][0]["food_name"] == "rice"


class TestCalculateMacrosEstimationPath:
    """Tests for the LLM estimation path (selected_food_id is None)."""

    async def test_estimation_path(self, basic_state):
        """
        arrange: selected_food_id=None and mocked LLM estimation.
        act:     run calculate_macros_node.
        assert:  MacroResult with source='estimated' and food_id=None.
        """
        basic_state.update({
            "pending_food_items": [
                {"food_name": "homemade pizza", "count": 300.0, "unit": "g", "original_text": "3 slices of pizza"}
            ],
            "selected_food_id": None,
            "last_action": "NO_MATCH",
        })

        mock_estimation = MagicMock()
        mock_estimation.calories = 750.0
        mock_estimation.protein = 30.0
        mock_estimation.carbs = 85.0
        mock_estimation.fat = 32.0
        mock_estimation.name_en = "homemade pizza"
        mock_estimation.name_he = None
        mock_estimation.category = None
        mock_estimation.tag = None
        mock_estimation.default_unit = None
        mock_estimation.default_unit_weight_g = None

        with patch("src.agents.nodes.calculate_macros_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_structured = MagicMock()
            mock_llm.with_structured_output.return_value = mock_structured
            mock_structured.ainvoke = AsyncMock(return_value=mock_estimation)

            result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert len(result["pending_confirmations"]) == 1
        macro = result["pending_confirmations"][0]
        assert macro["source"] == "estimated"
        assert macro["food_id"] is None
        assert macro["calories"] == 750.0
        assert macro["name_en"] == "homemade pizza"
        assert macro["category"] is None


class TestCalculateMacrosEdgeCases:
    """Test edge cases."""

    async def test_empty_pending_items(self, basic_state):
        """
        arrange: empty pending_food_items.
        act:     run calculate_macros_node.
        assert:  returns empty dict.
        """
        basic_state["pending_food_items"] = []

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert result == {}
