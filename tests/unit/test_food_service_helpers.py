"""
Unit tests for food_service pure helpers.

Scope:
    Pure function tests — no DB, no LLM, no I/O.

LLM Usage:
    NONE.
"""
import uuid as uuid_mod
from unittest.mock import MagicMock

import pytest

from src.services.food_service import (
    compute_food_macros,
    compute_servings,
    resolve_amount_g,
)


class TestResolveAmountG:
    def test_grams_passthrough(self):
        food = MagicMock(default_unit="g", default_unit_weight_g=None, name_en="Rice")
        assert resolve_amount_g(food, "g", 180.0) == 180.0

    def test_piece_unit_multiplies_weight(self):
        food = MagicMock(default_unit="piece", default_unit_weight_g=50.0, name_en="Egg")
        assert resolve_amount_g(food, "piece", 2.0) == 100.0

    def test_slice_unit(self):
        food = MagicMock(default_unit="slice", default_unit_weight_g=25.0, name_en="Yellow cheese")
        assert resolve_amount_g(food, "slice", 3.0) == 75.0

    def test_unit_mismatch_raises(self):
        food = MagicMock(default_unit="piece", default_unit_weight_g=50.0, name_en="Egg")
        with pytest.raises(ValueError, match="Unit mismatch"):
            resolve_amount_g(food, "slice", 2.0)

    def test_no_default_unit_falls_back_to_grams(self):
        food = MagicMock(default_unit=None, default_unit_weight_g=None, name_en="Mystery")
        assert resolve_amount_g(food, "piece", 2.0) == 2.0


class TestComputeServings:
    def test_none_when_serving_amount_g_is_none(self):
        assert compute_servings(100, None) is None

    def test_none_when_serving_amount_g_is_zero(self):
        assert compute_servings(100, 0) is None

    def test_simple_division(self):
        assert compute_servings(200, 100) == 2.0

    def test_fractional(self):
        assert compute_servings(50, 100) == 0.5

    def test_rounds_to_two_decimals(self):
        assert compute_servings(150, 100) == 1.5
        assert compute_servings(100, 150) == 0.67


class TestComputeFoodMacros:
    def _food(self, **overrides):
        food = MagicMock()
        food.id = uuid_mod.UUID("11111111-1111-1111-1111-111111111111")
        food.name_en = overrides.get("name_en", "Chicken breast")
        food.name_he = overrides.get("name_he", "חזה עוף")
        food.source = overrides.get("source", "database")
        food.calories = overrides.get("calories", 165.0)
        food.protein = overrides.get("protein", 31.0)
        food.fat = overrides.get("fat", 3.6)
        food.carbs = overrides.get("carbs", 0.0)
        food.default_unit = overrides.get("default_unit", "g")
        food.default_unit_weight_g = overrides.get("default_unit_weight_g", None)
        return food

    def test_full_dict_with_mapping(self):
        food = self._food()
        mapping = MagicMock(category="protein", tag="lean", serving_amount_g=100.0)
        result = compute_food_macros(food, mapping, 200.0)
        assert result["amount_g"] == 200.0
        assert result["calories"] == 330.0
        assert result["category"] == "protein"
        assert result["tag"] == "lean"
        assert result["servings"] == 2.0
        assert result["name_en"] == "Chicken breast"
        assert result["name_he"] == "חזה עוף"
        assert result["id"] == "11111111-1111-1111-1111-111111111111"

    def test_no_mapping(self):
        food = self._food(
            name_en="Estimated pizza", name_he=None, source="estimated",
            calories=250.0, protein=10.0, fat=12.0, carbs=30.0,
            default_unit=None, default_unit_weight_g=None,
        )
        result = compute_food_macros(food, None, 100.0)
        assert result["category"] is None
        assert result["tag"] is None
        assert result["serving_amount_g"] is None
        assert result["servings"] is None
        assert result["source"] == "estimated"

    def test_none_macros_treated_as_zero(self):
        food = self._food(calories=None, protein=None, fat=None, carbs=None)
        result = compute_food_macros(food, None, 100.0)
        assert result["calories"] == 0.0
        assert result["protein"] == 0.0
