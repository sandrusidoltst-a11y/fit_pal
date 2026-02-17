
from unittest.mock import patch
from src.agents.nutritionist import define_graph
from langgraph.checkpoint.memory import MemorySaver

def test_integration_full_flow():
    """Integration test: Verify response node formats output from results."""
    
    # Patch dependencies inside nutritionist.py context
    with patch("src.agents.nutritionist.input_parser_node") as mock_input, \
         patch("src.agents.nutritionist.food_search_node") as mock_search, \
         patch("src.agents.nutritionist.agent_selection_node") as mock_select, \
         patch("src.agents.nutritionist.calculate_log_node") as mock_calc, \
         patch("src.agents.nutritionist.SqliteSaver") as mock_mem, \
         patch("sqlite3.connect"):
             
        # Use MemorySaver as a valid checkpointer replacement
        mock_mem.return_value = MemorySaver()
             
        # Simulating a flow where one item is successfully processed
        
        # 1. Input Parser returns initial state
        mock_input.return_value = {
            "pending_food_items": [
                {"food_name": "Apple", "original_text": "apple", "amount": 1, "unit": "unit"}
            ],
            "last_action": "LOG_FOOD",
            "processing_results": []
        }
         
        # 2. Food Search returns results
        mock_search.return_value = {
            "search_results": [{"id": 1, "name": "Apple"}]
        }
         
        # 3. Selection returns choice
        mock_select.return_value = {
            "selected_food_id": 1, 
            "last_action": "SELECTED"
        }
         
        # 4. Calculate returns logged result
        # Crucially, it returns the processing_results list with one item
        mock_calc.return_value = {
            "pending_food_items": [], 
            "processing_results": [
                {
                    "food_name": "Apple", 
                    "status": "LOGGED", 
                    "message": "Logged Apple Success", 
                    "amount": 1, 
                    "unit": "unit", 
                    "original_text": "apple"
                }
            ],
            "last_action": "LOGGED"
        }

        # Build the graph
        app = define_graph()
         
        # Invoke with user message
        final_state = app.invoke(
            {"messages": [("user", "I ate an apple")]}, 
            config={"configurable": {"thread_id": "1"}}
        )
         
        # Verify response node output
        # The last message should be the summary from processing_results
        assert "messages" in final_state
        last_msg = final_state["messages"][-1]
        
        # Check content
        # Depending on LangGraph version, messages might be BaseMessage or dict if using TypedDict.
        # But add_messages usually converts to BaseMessage.
        content = last_msg.content if hasattr(last_msg, "content") else last_msg["content"]
        assert content == "Logged Apple Success"
