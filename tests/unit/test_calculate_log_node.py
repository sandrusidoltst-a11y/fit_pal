import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime, timezone
from src.agents.nodes.calculate_log_node import calculate_log_node
from src.agents.state import AgentState

@pytest.fixture
def mock_db_session():
    with patch("src.agents.nodes.calculate_log_node.get_async_db_session") as mock:
        session = AsyncMock()
        mock.return_value.__aenter__ = AsyncMock(return_value=session)
        mock.return_value.__aexit__ = AsyncMock(return_value=False)
        yield session

@pytest.fixture
def mock_daily_log_service():
    with patch("src.agents.nodes.calculate_log_node.daily_log_service") as mock:
        # Make the service functions return coroutines when awaited
        mock.create_log_entry = AsyncMock()
        mock.get_logs_by_date = AsyncMock(return_value=[])
        mock.get_logs_by_date_range = AsyncMock(return_value=[])
        yield mock

@pytest.fixture
def mock_calculate_macros():
    with patch("src.agents.nodes.calculate_log_node.calculate_food_macros") as mock:
        yield mock

async def test_calculate_log_node_success(mock_db_session, mock_daily_log_service, mock_calculate_macros):
    # Setup
    mock_calculate_macros.invoke.return_value = {
        "name": "Test Food",
        "amount_g": 100,
        "calories": 200,
        "protein": 20,
        "carbs": 10,
        "fat": 5
    }
    
    # Mock return of get_logs_by_date
    log_mock = MagicMock()
    log_mock.id = 1
    log_mock.food_id = 123
    log_mock.amount_g = 100.0
    log_mock.calories = 200.0
    log_mock.protein = 20.0
    log_mock.carbs = 10.0
    log_mock.fat = 5.0
    log_mock.timestamp = datetime(2023, 10, 26, 12, 0)
    log_mock.meal_type = "Lunch"
    log_mock.original_text = "100g test food"
    
    mock_daily_log_service.get_logs_by_date = AsyncMock(return_value=[log_mock])

    state = AgentState(
        pending_food_items=[{
            "food_name": "Test Food",
            "amount": 100.0,
            "unit": "g",
            "original_text": "100g test food"
        }],
        selected_food_id=123,
        daily_log_report=[],
        consumed_at=datetime(2023, 10, 26, 12, 0, tzinfo=timezone.utc),
        start_date=None,
        end_date=None,
        last_action="SELECTED",
        search_results=[],
        messages=[],
        processing_results=[]
    )

    # Execute
    result = await calculate_log_node(state)

    # Assert logic
    mock_calculate_macros.invoke.assert_called_once_with({"food_id": 123, "amount_g": 100.0})
    
    mock_daily_log_service.create_log_entry.assert_called_once()
    call_args = mock_daily_log_service.create_log_entry.call_args[1]
    assert call_args["food_id"] == 123
    assert call_args["amount_g"] == 100.0
    assert call_args["calories"] == 200
    assert call_args["timestamp"].date() == date(2023, 10, 26)

    # Assert state update
    assert "daily_log_report" in result
    report = result["daily_log_report"]
    assert len(report) == 1
    assert report[0]["id"] == 1
    assert report[0]["calories"] == 200.0
    
    assert result["pending_food_items"] == []
    assert result["last_action"] == "LOGGED"
    assert result["selected_food_id"] is None
    assert len(result["processing_results"]) == 1
    assert result["processing_results"][0]["status"] == "LOGGED"

async def test_calculate_log_node_no_selection_or_processed(mock_db_session, mock_daily_log_service, mock_calculate_macros):
    # Setup
    state = AgentState(
        pending_food_items=[{"food_name": "Test", "amount": 100.0, "unit": "g", "original_text": "test"}],
        selected_food_id=None,
        daily_log_report=[],
        consumed_at=datetime(2023, 10, 26, 12, 0, tzinfo=timezone.utc),
        start_date=None,
        end_date=None,
        last_action="SELECTED", # Simulation
        search_results=[],
        messages=[],
        processing_results=[],
        current_estimation=None
    )

    # Execute
    result = await calculate_log_node(state)

    # Assert
    mock_calculate_macros.invoke.assert_not_called()
    mock_daily_log_service.create_log_entry.assert_not_called()
    assert result["pending_food_items"] == [] # Should still remove item to avoid loop
    assert result["selected_food_id"] is None
    # Report should remain unchanged (empty list in this case)
    assert result["daily_log_report"] == []

async def test_calculate_log_node_macro_error(mock_db_session, mock_daily_log_service, mock_calculate_macros):
    # Setup
    mock_calculate_macros.invoke.return_value = {"error": "Food not found"}
    
    state = AgentState(
        pending_food_items=[{"food_name": "Test", "amount": 100.0, "unit": "g", "original_text": "test"}],
        selected_food_id=999,
        daily_log_report=[{"id": 1}], # Existing report
        consumed_at=datetime(2023, 10, 26, 12, 0, tzinfo=timezone.utc),
        start_date=None,
        end_date=None,
        last_action="SELECTED",
        search_results=[],
        messages=[],
        processing_results=[],
        current_estimation=None
    )

    # Execute
    result = await calculate_log_node(state)

    # Assert
    mock_daily_log_service.create_log_entry.assert_not_called()
    # Report should remain unchanged
    assert result["daily_log_report"] == [{"id": 1}]
    assert result["pending_food_items"] == []

async def test_calculate_log_node_current_estimation(mock_db_session, mock_daily_log_service, mock_calculate_macros):
    # Setup
    # Mock return of get_logs_by_date
    log_mock = MagicMock()
    log_mock.id = 2
    log_mock.food_id = None
    log_mock.amount_g = 200.0
    log_mock.calories = 300.0
    log_mock.protein = 15.0
    log_mock.carbs = 40.0
    log_mock.fat = 10.0
    log_mock.timestamp = datetime(2023, 10, 26, 12, 0)
    log_mock.meal_type = "Lunch"
    log_mock.original_text = "200g unknown item"
    
    mock_daily_log_service.get_logs_by_date = AsyncMock(return_value=[log_mock])

    state = AgentState(
        pending_food_items=[{
            "food_name": "Unknown Item",
            "amount": 200.0,
            "unit": "g",
            "original_text": "200g unknown item"
        }],
        selected_food_id=None,
        daily_log_report=[],
        consumed_at=datetime(2023, 10, 26, 12, 0, tzinfo=timezone.utc),
        start_date=None,
        end_date=None,
        last_action="CONFIRM_ESTIMATION",
        search_results=[],
        messages=[],
        processing_results=[],
        current_estimation={
            "calories": 150.0,
            "protein": 7.5,
            "carbs": 20.0,
            "fat": 5.0
        }
    )

    # Execute
    result = await calculate_log_node(state)

    # Assert logic
    mock_calculate_macros.invoke.assert_not_called()
    
    mock_daily_log_service.create_log_entry.assert_called_once()
    call_args = mock_daily_log_service.create_log_entry.call_args[1]
    assert call_args["food_id"] is None
    assert call_args["amount_g"] == 200.0
    # Expected: (amount / 100) * estimated = (200 / 100) * 150 = 300
    assert call_args["calories"] == 300.0
    assert call_args["protein"] == 15.0
    assert call_args["carbs"] == 40.0
    assert call_args["fat"] == 10.0

    # Assert state update
    assert result["pending_food_items"] == []
    assert result["last_action"] == "LOGGED"
    assert result["selected_food_id"] is None
    assert result["current_estimation"] is None
    assert len(result["processing_results"]) == 1
    assert result["processing_results"][0]["status"] == "LOGGED"
    assert "Logged Off-Menu item" in result["processing_results"][0]["message"]
