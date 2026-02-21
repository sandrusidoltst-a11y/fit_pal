from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
from src.agents.nodes.stats_node import stats_lookup_node
from src.agents.state import AgentState

@pytest.fixture
def mock_db_session():
    with patch("src.agents.nodes.stats_node.get_db_session") as mock:
        session = MagicMock()
        mock.return_value.__enter__.return_value = session
        yield session

@pytest.fixture
def mock_daily_log_service():
    with patch("src.agents.nodes.stats_node.daily_log_service") as mock:
        yield mock

def test_stats_lookup_single_day(mock_db_session, mock_daily_log_service):
    """Test retrieving logs for a single day."""
    state = AgentState(
        current_date=date(2023, 10, 27),
        start_date=None,
        end_date=None,
        daily_log_report=[]
    )
    
    # Mock log objects
    log1 = MagicMock()
    log1.id = 1
    log1.food_id = 101
    log1.amount_g = 100.0
    log1.calories = 150.0
    log1.protein = 10.0
    log1.carbs = 20.0
    log1.fat = 5.0
    log1.timestamp = datetime(2023, 10, 27, 12, 0, 0)
    log1.meal_type = "Lunch"
    log1.original_text = "100g chicken"
    
    mock_daily_log_service.get_logs_by_date.return_value = [log1]
    
    result = stats_lookup_node(state)
    
    mock_daily_log_service.get_logs_by_date.assert_called_once_with(
        mock_db_session, date(2023, 10, 27)
    )
    mock_daily_log_service.get_logs_by_date_range.assert_not_called()
    
    assert "daily_log_report" in result
    report = result["daily_log_report"]
    assert len(report) == 1
    assert report[0]["id"] == 1
    assert report[0]["calories"] == 150.0
    assert report[0]["original_text"] == "100g chicken"

def test_stats_lookup_date_range(mock_db_session, mock_daily_log_service):
    """Test retrieving logs for a date range."""
    start = date(2023, 10, 25)
    end = date(2023, 10, 27)
    state = AgentState(
        current_date=date.today(), # Should specify some date to satisfy TypedDict if mocked properly
        start_date=start,
        end_date=end,
        daily_log_report=[]
    )
    
    mock_daily_log_service.get_logs_by_date_range.return_value = []
    
    result = stats_lookup_node(state)
    
    mock_daily_log_service.get_logs_by_date_range.assert_called_once_with(
        mock_db_session, start, end
    )
    mock_daily_log_service.get_logs_by_date.assert_not_called()
    assert result["daily_log_report"] == []
