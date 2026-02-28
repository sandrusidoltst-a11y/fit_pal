"""Integration tests for the input parser node using the real LLM."""
from langchain_core.messages import HumanMessage
from src.agents.nodes.input_node import input_parser_node

def test_input_parser_real_llm_log_food(basic_state):
    """Integration: Test logging food with real LLM."""
    basic_state["messages"] = [HumanMessage(content="I had 200g of chicken breast")]
    result = input_parser_node(basic_state)
    assert result["last_action"] == "LOG_FOOD"
    items = result.get("pending_food_items", [])
    assert len(items) == 1
    assert "chicken" in items[0]["food_name"].lower()

def test_input_parser_real_llm_chitchat(basic_state):
    """Integration: Test chitchat with real LLM."""
    basic_state["messages"] = [HumanMessage(content="Hello, how are you?")]
    result = input_parser_node(basic_state)
    assert result["last_action"] == "CHITCHAT"

def test_input_parser_real_llm_query_stats(basic_state):
    """Integration: Test querying stats with real LLM."""
    basic_state["messages"] = [HumanMessage(content="How much protein have I eaten today?")]
    result = input_parser_node(basic_state)
    assert result["last_action"] == "QUERY_DAILY_STATS"
