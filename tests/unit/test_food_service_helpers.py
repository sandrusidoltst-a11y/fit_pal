"""
Unit tests for food_service pure helpers.

Scope:
    Pure function tests — no DB, no LLM, no I/O.

LLM Usage:
    NONE.
"""
import logging
import uuid as uuid_mod
from unittest.mock import MagicMock

from src.services.food_service import (
    compute_food_macros,
    compute_servings,
    resolve_amount_g,
)


def _food(**weights_overrides):
    """Build a FoodItem-shaped MagicMock with sensible defaults."""
    return MagicMock(
        unit_weights=weights_overrides.get("unit_weights", {}),
        unit_synonyms=weights_overrides.get("unit_synonyms", {}),
        name_en=weights_overrides.get("name_en", "Test food"),
    )


class TestResolveAmountG:
    def test_grams_passthrough(self):
        food = _food(name_en="Rice")
        assert resolve_amount_g(food, "g", 180.0) == 180.0

    def test_unit_weights_direct_hit(self):
        food = _food(unit_weights={"piece": 50.0}, name_en="Egg")
        assert resolve_amount_g(food, "piece", 2.0) == 100.0

    def test_unit_synonyms_resolution(self):
        food = _food(
            unit_weights={"slice": 110.0},
            unit_synonyms={"piece": "slice", "פרוסה": "slice"},
            name_en="Pizza",
        )
        assert resolve_amount_g(food, "piece", 2.0) == 220.0
        assert resolve_amount_g(food, "פרוסה", 1.0) == 110.0

    def test_synonym_pointing_to_missing_key_falls_through_to_estimate(self, caplog):
        food = _food(unit_synonyms={"piece": "slice"}, name_en="Broken")
        with caplog.at_level(logging.WARNING):
            assert resolve_amount_g(food, "piece", 2.0, llm_estimated_amount_g=200.0) == 200.0

    def test_falls_back_to_llm_estimate(self):
        food = _food(name_en="Mystery")
        assert resolve_amount_g(food, "bowl", 1.0, llm_estimated_amount_g=350.0) == 350.0

    def test_last_resort_returns_count_when_no_estimate(self, caplog):
        food = _food(name_en="Mystery")
        with caplog.at_level(logging.WARNING):
            assert resolve_amount_g(food, "bowl", 1.0) == 1.0

    def test_handles_none_columns_defensively(self):
        food = MagicMock(unit_weights=None, unit_synonyms=None, name_en="Edge")
        assert resolve_amount_g(food, "g", 50.0) == 50.0
        assert resolve_amount_g(food, "bowl", 1.0, llm_estimated_amount_g=300.0) == 300.0

    def test_serving_registered_in_unit_weights_wins(self):
        """Catalog's serving weight overrides the parser's amount_g estimate."""
        food = _food(unit_weights={"serving": 130.0}, name_en="Protein Pudding")
        assert resolve_amount_g(food, "serving", 1.0, llm_estimated_amount_g=100.0) == 130.0

    def test_serving_not_registered_falls_back_to_amount_g(self):
        """When the catalog has no serving key, the parser's amount_g wins."""
        food = _food(unit_weights={"piece": 50.0}, name_en="New Food")
        assert resolve_amount_g(food, "serving", 1.0, llm_estimated_amount_g=150.0) == 150.0

    def test_serving_not_registered_no_amount_g_uses_last_resort(self, caplog):
        """Neither catalog nor amount_g → last-resort fallback (count as grams)."""
        food = _food(unit_weights={}, name_en="New Food")
        with caplog.at_level(logging.WARNING):
            assert resolve_amount_g(food, "serving", 1.0) == 1.0


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
        food.unit_weights = overrides.get("unit_weights", {})
        food.unit_synonyms = overrides.get("unit_synonyms", {})
        return food

    def test_full_dict_with_mapping(self):
        food = self._food(unit_weights={"piece": 130.0})
        mapping = MagicMock(category="protein", tag="lean", serving_amount_g=100.0)
        result = compute_food_macros(food, mapping, 200.0)
        assert result["amount_g"] == 200.0
        assert result["calories"] == 330.0
        assert result["category"] == "protein"
        assert result["tag"] == "lean"
        assert result["servings"] == 2.0
        assert result["unit_weights"] == {"piece": 130.0}
        assert result["unit_synonyms"] == {}
        assert result["name_en"] == "Chicken breast"
        assert result["name_he"] == "חזה עוף"
        assert result["id"] == "11111111-1111-1111-1111-111111111111"

    def test_no_mapping(self):
        food = self._food(
            name_en="Estimated pizza", name_he=None, source="estimated",
            calories=250.0, protein=10.0, fat=12.0, carbs=30.0,
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
