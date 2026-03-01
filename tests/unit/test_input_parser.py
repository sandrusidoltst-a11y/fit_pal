"""
Unit tests for Input Parser Node (`input_node.py`).

Scope:
    Purely isolated unit tests. Verify the parsing logic classifying the user input.

LLM Usage:
    MOCKED — all LLM calls are mocked.
"""
from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from src.agents.nodes.input_node import input_parser_node
from src.schemas.input_schema import ActionType, FoodIntakeEvent, SingleFoodItem


class TestInputParserLogFood:
    """Tests for actions classifying as LOG_FOOD."""

    def test_log_food_basic(self, basic_state):
        """
        arrange: mocked LLM to return LOG_FOOD Action with 200g of chicken breast.
        act:     run input_parser_node.
        assert:  returns correctly structured data with one item and LOG_FOOD.
        """
        with patch("src.agents.nodes.input_node.get_llm_for_node") as mock_get_llm:
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

    def test_unit_normalization(self, basic_state):
        """
        arrange: mocked LLM returning logged food translated to unit `g`.
        act:     run input_parser_node.
        assert:  returns a single valid food item with amount > 0 and unit normalized to 'g'.
        """
        with patch("src.agents.nodes.input_node.get_llm_for_node") as mock_get_llm:
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

    def test_complex_meal_decomposition(self, basic_state):
        """
        arrange: mocked LLM to return three food items.
        act:     run input_parser_node.
        assert:  returns correct parsing of multiple food items for one user sentence.
        """
        with patch("src.agents.nodes.input_node.get_llm_for_node") as mock_get_llm:
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


class TestInputParserOtherActions:
    """Tests for actions classifying non LOG_FOOD categories."""

    def test_chitchat(self, basic_state):
        """
        arrange: mock LLM returns CHITCHAT for conversational input.
        act:     run input_parser_node.
        assert:  action is registered as CHITCHAT and pending_food_items is empty.
        """
        with patch("src.agents.nodes.input_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_structured = MagicMock()
            mock_llm.with_structured_output.return_value = mock_structured
            mock_structured.invoke.return_value = FoodIntakeEvent(action=ActionType.CHITCHAT, items=[])
            
            basic_state["messages"] = [HumanMessage(content="Hello, how are you?")]
            result = input_parser_node(basic_state)
            
            assert result["last_action"] == "CHITCHAT"
            assert len(result.get("pending_food_items", [])) == 0

    def test_nonsense_input(self, basic_state):
        """
        arrange: mock LLM returns CHITCHAT for nonsense input.
        act:     run input_parser_node.
        assert:  nonsense correctly maps to CHITCHAT.
        """
        with patch("src.agents.nodes.input_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_structured = MagicMock()
            mock_llm.with_structured_output.return_value = mock_structured
            mock_structured.invoke.return_value = FoodIntakeEvent(action=ActionType.CHITCHAT, items=[])
            
            basic_state["messages"] = [HumanMessage(content="asdfasdf")]
            result = input_parser_node(basic_state)
            
            assert result["last_action"] == "CHITCHAT"

    def test_query_daily_stats(self, basic_state):
        """
        arrange: mock LLM to detect daily stats query.
        act:     run input_parser_node.
        assert:  correct QUERY_DAILY_STATS mapping is applied.
        """
        with patch("src.agents.nodes.input_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_structured = MagicMock()
            mock_llm.with_structured_output.return_value = mock_structured
            mock_structured.invoke.return_value = FoodIntakeEvent(action=ActionType.QUERY_DAILY_STATS, items=[])
            
            basic_state["messages"] = [HumanMessage(content="How much protein have I eaten today?")]
            result = input_parser_node(basic_state)
            
            assert result["last_action"] == "QUERY_DAILY_STATS"
            assert len(result.get("pending_food_items", [])) == 0

    def test_query_food_info(self, basic_state):
        """
        arrange: mock LLM detecting food info query.
        act:     run input_parser_node.
        assert:  returns correct QUERY_FOOD_INFO mapping.
        """
        with patch("src.agents.nodes.input_node.get_llm_for_node") as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            mock_structured = MagicMock()
            mock_llm.with_structured_output.return_value = mock_structured
            mock_structured.invoke.return_value = FoodIntakeEvent(action=ActionType.QUERY_FOOD_INFO, items=[])
            
            basic_state["messages"] = [HumanMessage(content="How many calories in an apple?")]
            result = input_parser_node(basic_state)
            
            assert result["last_action"] == "QUERY_FOOD_INFO"
            assert len(result.get("pending_food_items", [])) == 0
