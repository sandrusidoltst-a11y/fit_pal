
from src.agents.nodes.calculate_log_node import calculate_log_node


async def test_calculate_log_removes_first_item(
    basic_state, mock_calculate_log_db_session, mock_daily_log_service_for_calc, mock_calculate_macros
):
    mock_calculate_macros.invoke.return_value = {
        "name": "Test Food",
        "amount_g": 100,
        "calories": 200,
        "protein": 20,
        "carbs": 10,
        "fat": 5,
    }
    """Test that calculate_log_node removes the first pending item."""
    basic_state["pending_food_items"] = [
        {"food_name": "chicken", "amount": 100.0, "unit": "g", "original_text": "100g chicken"},
        {"food_name": "rice", "amount": 200.0, "unit": "g", "original_text": "200g rice"},
    ]
    basic_state["selected_food_id"] = 1

    result = await calculate_log_node(basic_state)

    assert len(result["pending_food_items"]) == 1
    assert result["pending_food_items"][0]["food_name"] == "rice"
    assert result["last_action"] == "LOGGED"


async def test_calculate_log_empty_pending(basic_state):
    """Test that calculate_log_node handles empty pending items gracefully."""
    basic_state["pending_food_items"] = []

    result = await calculate_log_node(basic_state)

    assert result == {}


async def test_calculate_log_single_item(
    basic_state, mock_calculate_log_db_session, mock_daily_log_service_for_calc, mock_calculate_macros
):
    """Test that calculate_log_node processes single item correctly."""
    mock_calculate_macros.invoke.return_value = {
        "name": "Test Food",
        "amount_g": 100,
        "calories": 200,
        "protein": 20,
        "carbs": 10,
        "fat": 5,
    }
    basic_state["pending_food_items"] = [
        {"food_name": "apple", "amount": 150.0, "unit": "g", "original_text": "an apple"},
    ]
    basic_state["selected_food_id"] = 5

    result = await calculate_log_node(basic_state)

    assert len(result["pending_food_items"]) == 0
    assert result["last_action"] == "LOGGED"


async def test_multi_item_state_setup(basic_state):
    """Test that multi-item state can be correctly initialized."""
    basic_state["pending_food_items"] = [
        {"food_name": "chicken", "amount": 100.0, "unit": "g", "original_text": "100g chicken"},
        {"food_name": "rice", "amount": 200.0, "unit": "g", "original_text": "200g rice"},
        {"food_name": "broccoli", "amount": 150.0, "unit": "g", "original_text": "150g broccoli"},
    ]
    basic_state["last_action"] = "LOG_FOOD"

    assert len(basic_state["pending_food_items"]) == 3
    assert basic_state["pending_food_items"][0]["food_name"] == "chicken"
    assert basic_state["pending_food_items"][2]["food_name"] == "broccoli"


async def test_sequential_item_removal(
    basic_state, mock_calculate_log_db_session, mock_daily_log_service_for_calc, mock_calculate_macros
):
    """Test that items are removed sequentially as they are processed."""
    mock_calculate_macros.invoke.return_value = {
        "name": "Test Food",
        "amount_g": 100,
        "calories": 200,
        "protein": 20,
        "carbs": 10,
        "fat": 5,
    }
    items = [
        {"food_name": "chicken", "amount": 100.0, "unit": "g", "original_text": "100g chicken"},
        {"food_name": "rice", "amount": 200.0, "unit": "g", "original_text": "200g rice"},
        {"food_name": "broccoli", "amount": 150.0, "unit": "g", "original_text": "150g broccoli"},
    ]
    basic_state["pending_food_items"] = items

    # Process first item
    result = await calculate_log_node(basic_state)
    assert len(result["pending_food_items"]) == 2
    assert result["pending_food_items"][0]["food_name"] == "rice"

    # Simulate processing second item
    basic_state["pending_food_items"] = result["pending_food_items"]
    result2 = await calculate_log_node(basic_state)
    assert len(result2["pending_food_items"]) == 1
    assert result2["pending_food_items"][0]["food_name"] == "broccoli"

    # Simulate processing third item
    basic_state["pending_food_items"] = result2["pending_food_items"]
    result3 = await calculate_log_node(basic_state)
    assert len(result3["pending_food_items"]) == 0
    assert result3["last_action"] == "LOGGED"
