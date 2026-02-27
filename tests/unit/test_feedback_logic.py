import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.nodes.calculate_log_node import calculate_log_node
from src.agents.nodes.selection_node import agent_selection_node
from src.schemas.selection_schema import FoodSelectionResult, SelectionStatus

@pytest.fixture
def base_state():
    return {
        "pending_food_items": [
            {
                "food_name": "Test Apple",
                "amount": 1,
                "unit": "medium",
                "original_text": "one medium apple"
            }
        ],
        "processing_results": [],
        "daily_log_report": [],
        "consumed_at": None,
        "start_date": None,
        "selected_food_id": 123
    }

async def test_calculate_log_success_result(base_state):
    """Test that calculate_log_node appends a LOGGED result."""
    with patch("src.agents.nodes.calculate_log_node.calculate_food_macros") as mock_macros, \
         patch("src.agents.nodes.calculate_log_node.get_async_db_session") as mock_db, \
         patch("src.agents.nodes.calculate_log_node.daily_log_service") as mock_service:
        
        # Setup async context manager mock
        session = AsyncMock()
        mock_db.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_service.create_log_entry = AsyncMock()
        mock_service.get_logs_by_date = AsyncMock(return_value=[])

        mock_macros.invoke.return_value = {"calories": 95, "protein": 0.5, "carbs": 25, "fat": 0.3}
        
        result = await calculate_log_node(base_state)
        
        assert "processing_results" in result
        assert len(result["processing_results"]) == 1
        res = result["processing_results"][0]
        assert res["status"] == "LOGGED"
        assert "Logged Test Apple" in res["message"]
        assert res["original_text"] == "one medium apple"

async def test_calculate_log_accumulates_results(base_state):
    """Test that results accumulate over multiple steps."""
    existing = {
        "food_name": "Prev", "amount": 1, "unit": "g", "original_text": "p",
        "status": "LOGGED", "message": "Prev logged"
    }
    base_state["processing_results"] = [existing]
    
    with patch("src.agents.nodes.calculate_log_node.calculate_food_macros") as mock_macros, \
         patch("src.agents.nodes.calculate_log_node.get_async_db_session") as mock_db, \
         patch("src.agents.nodes.calculate_log_node.daily_log_service") as mock_service:
        
        # Setup async context manager mock
        session = AsyncMock()
        mock_db.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_service.create_log_entry = AsyncMock()
        mock_service.get_logs_by_date = AsyncMock(return_value=[])

        mock_macros.invoke.return_value = {"calories": 100, "protein": 0, "carbs": 0, "fat": 0}
        result = await calculate_log_node(base_state)
        
        assert len(result["processing_results"]) == 2
        assert result["processing_results"][0] == existing
        assert result["processing_results"][1]["status"] == "LOGGED"

def test_selection_failure_no_results(base_state):
    """Test NO_MATCH due to empty search results and LLM declining to estimate."""
    base_state["search_results"] = []
    
    with patch("src.agents.nodes.selection_node.get_llm_for_node") as mock_get_llm:
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_structured = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured
        
        mock_structured.invoke.return_value = FoodSelectionResult(
            food_id=None, 
            status=SelectionStatus.NO_MATCH,
            confidence="Cannot estimate"
        )
        
        result = agent_selection_node(base_state)
        
        assert result["last_action"] == "NO_MATCH"
        assert "processing_results" in result
        assert len(result["processing_results"]) == 1
        res = result["processing_results"][0]
        assert res["status"] == "FAILED"
        assert "No appropriate match found" in res["message"]

def test_selection_failure_llm(base_state):
    """Test failure when LLM returns NO_MATCH or issue."""
    base_state["search_results"] = [
        {"id": 1, "name": "Apple"},
        {"id": 2, "name": "Apple Pie"}
    ]
    # Force LLM path
    # We need to mock the LLM
    
    with patch("src.agents.nodes.selection_node.get_llm_for_node") as mock_get_llm:
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_structured = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured
        
        # Simulate LLM returning SELECTED but no ID (invalid state handled by node)
        mock_structured.invoke.return_value = FoodSelectionResult(
            food_id=None, 
            status=SelectionStatus.SELECTED,
            reasoning="Error"
        )
        
        result = agent_selection_node(base_state)
        
        assert result["last_action"] == "NO_MATCH"
        assert len(result["processing_results"]) == 1
        assert result["processing_results"][0]["status"] == "FAILED"
