from datetime import date
from langchain_core.messages import HumanMessage
from src.agents.nodes.input_node import input_parser_node

def test_log_food_basic(basic_state):
    """Test standard food logging scenario."""
    basic_state["messages"] = [HumanMessage(content="I had 200g of chicken breast")]
    result = input_parser_node(basic_state)
    
    assert result["last_action"] == "LOG_FOOD"
    items = result.get("pending_food_items", [])
    assert len(items) == 1
    
    # Generic naming check (based on prompt update)
    # The prompt now prefers "Chicken breast" over "Grilled chicken breast" or similar
    assert "chicken" in items[0]["food_name"].lower()
    
    # Quantity check (Schema v2)
    assert items[0]["amount"] == 200.0
    assert items[0]["unit"] == "g"

def test_unit_normalization(basic_state):
    """Test that units like 'cup' are converted to grams."""
    basic_state["messages"] = [HumanMessage(content="I ate a cup of rice")]
    result = input_parser_node(basic_state)
    
    items = result.get("pending_food_items", [])
    assert len(items) == 1
    
    # Verify name is generic
    assert "rice" in items[0]["food_name"].lower()
    
    # Verify quantity is normalized to grams (matches prompt instruction)
    # We expect roughly 150g-250g for a cup of rice
    amt = items[0]["amount"]
    unit = items[0]["unit"]
    
    assert isinstance(amt, float)
    assert amt > 0
    assert unit == "g"

def test_complex_meal_decomposition(basic_state):
    """Test breaking down a meal into components."""
    basic_state["messages"] = [HumanMessage(content="I had pasta with cheese and a tomato")]
    result = input_parser_node(basic_state)
    
    assert result["last_action"] == "LOG_FOOD"
    items = result.get("pending_food_items", [])
    assert len(items) >= 3
    
    food_names = [i["food_name"].lower() for i in items]
    assert any("pasta" in name for name in food_names)
    assert any("cheese" in name for name in food_names)
    assert any("tomato" in name for name in food_names)

def test_chitchat(basic_state):
    """Test chitchat detection."""
    basic_state["messages"] = [HumanMessage(content="Hello, how are you?")]
    result = input_parser_node(basic_state)
    
    assert result["last_action"] == "CHITCHAT"
    assert len(result.get("pending_food_items", [])) == 0

def test_nonsense_input(basic_state):
    """Test valid handling of nonsense input as Chitchat (per new prompt rules)."""
    basic_state["messages"] = [HumanMessage(content="100 200")]
    result = input_parser_node(basic_state)
    
    assert result["last_action"] == "CHITCHAT"

def test_query_daily_stats(basic_state):
    """Test detection of daily stats query."""
    basic_state["messages"] = [HumanMessage(content="How much protein have I eaten today?")]
    result = input_parser_node(basic_state)
    
    assert result["last_action"] == "QUERY_DAILY_STATS"
    assert len(result.get("pending_food_items", [])) == 0

def test_query_food_info(basic_state):
    """Test detection of generic food info query."""
    basic_state["messages"] = [HumanMessage(content="How many calories in an apple?")]
    result = input_parser_node(basic_state)
    
    assert result["last_action"] == "QUERY_FOOD_INFO"
    assert len(result.get("pending_food_items", [])) == 0
