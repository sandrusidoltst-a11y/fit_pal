from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage
from src.agents.nodes.input_node import input_parser_node
from src.schemas.input_schema import FoodIntakeEvent, ActionType, SingleFoodItem

@patch("src.agents.nodes.input_node.get_llm_for_node")
def test_log_food_basic(mock_get_llm, basic_state):
    """Test standard food logging scenario."""
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = FoodIntakeEvent(
        action=ActionType.LOG_FOOD,
        items=[SingleFoodItem(food_name="Chicken breast", amount=200.0, unit="g", original_text="200g of chicken breast")]
    )
    
    basic_state["messages"] = [HumanMessage(content="I had 200g of chicken breast")]
    result = input_parser_node(basic_state)
    
    assert result["last_action"] == "LOG_FOOD"
    items = result.get("pending_food_items", [])
    assert len(items) == 1
    assert "chicken" in items[0]["food_name"].lower()
    assert items[0]["amount"] == 200.0
    assert items[0]["unit"] == "g"

@patch("src.agents.nodes.input_node.get_llm_for_node")
def test_unit_normalization(mock_get_llm, basic_state):
    """Test that units like 'cup' are converted to grams."""
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = FoodIntakeEvent(
        action=ActionType.LOG_FOOD,
        items=[SingleFoodItem(food_name="Rice", amount=185.0, unit="g", original_text="a cup of rice")]
    )
    
    basic_state["messages"] = [HumanMessage(content="I ate a cup of rice")]
    result = input_parser_node(basic_state)
    
    items = result.get("pending_food_items", [])
    assert len(items) == 1
    assert "rice" in items[0]["food_name"].lower()
    amt = items[0]["amount"]
    unit = items[0]["unit"]
    assert isinstance(amt, float)
    assert amt > 0
    assert unit == "g"

@patch("src.agents.nodes.input_node.get_llm_for_node")
def test_complex_meal_decomposition(mock_get_llm, basic_state):
    """Test breaking down a meal into components."""
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = FoodIntakeEvent(
        action=ActionType.LOG_FOOD,
        items=[
            SingleFoodItem(food_name="Pasta", amount=150.0, unit="g", original_text="pasta"),
            SingleFoodItem(food_name="Cheese", amount=50.0, unit="g", original_text="cheese"),
            SingleFoodItem(food_name="Tomato", amount=100.0, unit="g", original_text="a tomato")
        ]
    )
    
    basic_state["messages"] = [HumanMessage(content="I had pasta with cheese and a tomato")]
    result = input_parser_node(basic_state)
    
    assert result["last_action"] == "LOG_FOOD"
    items = result.get("pending_food_items", [])
    assert len(items) >= 3
    food_names = [i["food_name"].lower() for i in items]
    assert any("pasta" in name for name in food_names)
    assert any("cheese" in name for name in food_names)
    assert any("tomato" in name for name in food_names)

@patch("src.agents.nodes.input_node.get_llm_for_node")
def test_chitchat(mock_get_llm, basic_state):
    """Test chitchat detection."""
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = FoodIntakeEvent(action=ActionType.CHITCHAT, items=[])
    
    basic_state["messages"] = [HumanMessage(content="Hello, how are you?")]
    result = input_parser_node(basic_state)
    
    assert result["last_action"] == "CHITCHAT"
    assert len(result.get("pending_food_items", [])) == 0

@patch("src.agents.nodes.input_node.get_llm_for_node")
def test_nonsense_input(mock_get_llm, basic_state):
    """Test valid handling of nonsense input as Chitchat (per new prompt rules)."""
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = FoodIntakeEvent(action=ActionType.CHITCHAT, items=[])
    
    basic_state["messages"] = [HumanMessage(content="asdfasdf")]
    result = input_parser_node(basic_state)
    
    assert result["last_action"] == "CHITCHAT"

@patch("src.agents.nodes.input_node.get_llm_for_node")
def test_query_daily_stats(mock_get_llm, basic_state):
    """Test detection of daily stats query."""
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = FoodIntakeEvent(action=ActionType.QUERY_DAILY_STATS, items=[])
    
    basic_state["messages"] = [HumanMessage(content="How much protein have I eaten today?")]
    result = input_parser_node(basic_state)
    
    assert result["last_action"] == "QUERY_DAILY_STATS"
    assert len(result.get("pending_food_items", [])) == 0

@patch("src.agents.nodes.input_node.get_llm_for_node")
def test_query_food_info(mock_get_llm, basic_state):
    """Test detection of generic food info query."""
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = FoodIntakeEvent(action=ActionType.QUERY_FOOD_INFO, items=[])
    
    basic_state["messages"] = [HumanMessage(content="How many calories in an apple?")]
    result = input_parser_node(basic_state)
    
    assert result["last_action"] == "QUERY_FOOD_INFO"
    assert len(result.get("pending_food_items", [])) == 0
