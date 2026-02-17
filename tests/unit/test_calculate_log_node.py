import pytest
from unittest.mock import MagicMock, patch
from datetime import date
from src.agents.nodes.calculate_log_node import calculate_log_node
from src.agents.state import AgentState

@pytest.fixture
def mock_db_session():
    with patch("src.agents.nodes.calculate_log_node.get_db_session") as mock:
        session = MagicMock()
        mock.return_value.__enter__.return_value = session
        yield session

@pytest.fixture
def mock_daily_log_service():
    with patch("src.agents.nodes.calculate_log_node.daily_log_service") as mock:
        yield mock

@pytest.fixture
def mock_calculate_macros():
    with patch("src.agents.nodes.calculate_log_node.calculate_food_macros") as mock:
        yield mock

def test_calculate_log_node_success(mock_db_session, mock_daily_log_service, mock_calculate_macros):
    # Setup
    mock_calculate_macros.invoke.return_value = {
        "name": "Test Food",
        "amount_g": 100,
        "calories": 200,
        "protein": 20,
        "carbs": 10,
        "fat": 5
    }
    
    # Mock return of get_daily_totals
    mock_daily_log_service.get_daily_totals.return_value = {
        "calories": 500.0,
        "protein": 50.0,
        "carbs": 30.0,
        "fat": 15.0
    }

    state: AgentState = {
        "pending_food_items": [{
            "food_name": "Test Food",
            "amount": 100.0,
            "unit": "g",
            "original_text": "100g test food"
        }],
        "selected_food_id": 123,
        "daily_totals": {"calories": 300.0, "protein": 30.0, "carbs": 20.0, "fat": 10.0},
        "current_date": date(2023, 10, 26),
        "last_action": "SELECTED",
        "search_results": [],
        "messages": [],
    }

    # Execute
    result = calculate_log_node(state)

    # Assert logic
    mock_calculate_macros.invoke.assert_called_once_with({"food_id": 123, "amount_g": 100.0})
    
    mock_daily_log_service.create_log_entry.assert_called_once()
    call_args = mock_daily_log_service.create_log_entry.call_args[1]
    assert call_args["food_id"] == 123
    assert call_args["amount_g"] == 100.0
    assert call_args["calories"] == 200
    assert call_args["timestamp"].date() == date(2023, 10, 26)

    # Assert state update
    assert result["daily_totals"] == {
        "calories": 500.0,
        "protein": 50.0,
        "carbs": 30.0,
        "fat": 15.0
    }
    assert result["pending_food_items"] == []
    assert result["last_action"] == "LOGGED"
    assert result["selected_food_id"] is None

def test_calculate_log_node_no_selection(mock_db_session, mock_daily_log_service, mock_calculate_macros):
    # Setup
    state: AgentState = {
        "pending_food_items": [{"food_name": "Test", "amount": 100.0, "unit": "g", "original_text": "test"}],
        "selected_food_id": None,
        "daily_totals": {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0},
        "current_date": date(2023, 10, 26),
        "last_action": "SELECTED", # Simulation
        "search_results": [],
        "messages": []
    }

    # Execute
    result = calculate_log_node(state)

    # Assert
    mock_calculate_macros.invoke.assert_not_called()
    mock_daily_log_service.create_log_entry.assert_not_called()
    assert result["pending_food_items"] == [] # Should still remove item to avoid loop
    assert result["selected_food_id"] is None

def test_calculate_log_node_macro_error(mock_db_session, mock_daily_log_service, mock_calculate_macros):
    # Setup
    mock_calculate_macros.invoke.return_value = {"error": "Food not found"}
    
    state: AgentState = {
        "pending_food_items": [{"food_name": "Test", "amount": 100.0, "unit": "g", "original_text": "test"}],
        "selected_food_id": 999,
        "daily_totals": {"calories": 100.0, "protein": 10.0, "carbs": 10.0, "fat": 2.0},
        "current_date": date(2023, 10, 26),
        "last_action": "SELECTED",
        "search_results": [],
        "messages": []
    }

    # Execute
    result = calculate_log_node(state)

    # Assert
    mock_daily_log_service.create_log_entry.assert_not_called()
    assert result["daily_totals"] == {"calories": 100.0, "protein": 10.0, "carbs": 10.0, "fat": 2.0} # Unchanged
    assert result["pending_food_items"] == []
