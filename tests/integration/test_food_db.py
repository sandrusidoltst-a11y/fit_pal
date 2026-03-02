"""Integration tests for database access and food lookup."""
import pytest
from src.tools.food_lookup import search_food, calculate_food_macros
from src.agents.nodes.food_search_node import food_search_node


async def test_search_food():
    # Search for something common
    results = await search_food.ainvoke({"query": "chicken"})
    assert isinstance(results, list)
    assert len(results) > 0
    assert "id" in results[0]
    assert "name" in results[0]
    # Ensure no macros leaked in search
    assert "calories" not in results[0]


async def test_calculate_food_macros():
    # First find an item to ensure ID exists
    results = await search_food.ainvoke({"query": "egg"})
    if not results:
        # Fallback if DB is empty or weird
        pytest.skip("No 'egg' found in DB, skipping calc test")

    item = results[0]
    pk = item["id"]

    # Calculate for 100g
    macros_100 = await calculate_food_macros.ainvoke({"food_id": pk, "amount_g": 100})
    # Calculate for 200g
    macros_200 = await calculate_food_macros.ainvoke({"food_id": pk, "amount_g": 200})

    # Verify linearity
    # approx is needed for float math
    assert macros_200["calories"] == pytest.approx(macros_100["calories"] * 2, abs=0.1)
    assert macros_200["protein"] == pytest.approx(macros_100["protein"] * 2, abs=0.1)
    assert macros_200["fat"] == pytest.approx(macros_100["fat"] * 2, abs=0.1)
    assert macros_200["carbs"] == pytest.approx(macros_100["carbs"] * 2, abs=0.1)


async def test_food_search_node_real_db(basic_state):
    """Integration test using the real database search."""
    basic_state["pending_food_items"] = [
        {"food_name": "chicken", "amount": 100.0, "unit": "g", "original_text": "100g chicken"}
    ]

    result = await food_search_node(basic_state)

    assert "search_results" in result
    assert isinstance(result["search_results"], list)
    # Should find at least one chicken-related item from the real DB
    assert len(result["search_results"]) > 0
