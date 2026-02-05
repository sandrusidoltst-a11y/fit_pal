import pytest
import sys
import os

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.tools.food_lookup import search_food, calculate_food_macros

def test_search_food():
    # Search for something common
    results = search_food.invoke("chicken")
    assert isinstance(results, list)
    assert len(results) > 0
    assert "id" in results[0]
    assert "name" in results[0]
    # Ensure no macros leaked in search
    assert "calories" not in results[0]

def test_calculate_food_macros():
    # First find an item to ensure ID exists
    results = search_food.invoke("egg")
    if not results:
        # Fallback if DB is empty or weird
        pytest.skip("No 'egg' found in DB, skipping calc test")
    
    item = results[0]
    pk = item["id"]
    
    # Calculate for 100g
    macros_100 = calculate_food_macros.invoke({"food_id": pk, "amount_g": 100})
    # Calculate for 200g
    macros_200 = calculate_food_macros.invoke({"food_id": pk, "amount_g": 200})
    
    # Verify linearity
    # approx is needed for float math
    assert macros_200["calories"] == pytest.approx(macros_100["calories"] * 2, abs=0.1)
    assert macros_200["protein"] == pytest.approx(macros_100["protein"] * 2, abs=0.1)
    assert macros_200["fat"] == pytest.approx(macros_100["fat"] * 2, abs=0.1)
    assert macros_200["carbs"] == pytest.approx(macros_100["carbs"] * 2, abs=0.1)
