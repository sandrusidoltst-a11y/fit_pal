"""
Unit tests for Multi-Item Loop processing dynamics (`calculate_log_node.py` logic loop tracking).

Scope:
    Purely isolated unit tests. Verify arrays modify successfully.

LLM Usage:
    NONE — calculate_log_node does not call an LLM natively.
"""
from src.agents.nodes.calculate_log_node import calculate_log_node


class TestMultiItemLoopDraining:
    """Test standard array draining functionality."""

    async def test_calculate_log_removes_first_item(self, basic_state, mock_calculate_log_db_session, mock_daily_log_service_for_calc, mock_calculate_macros):
        """
        arrange: set multiple items inside pending_food_items array.
        act:     run calculate_log_node.
        assert:  verifies calculated item has successfully been detached from current index tracking.
        """
        mock_calculate_macros.invoke.return_value = {
            "name": "Test Food",
            "amount_g": 100,
            "calories": 200,
            "protein": 20,
            "carbs": 10,
            "fat": 5,
        }
        basic_state["pending_food_items"] = [
            {"food_name": "chicken", "amount": 100.0, "unit": "g", "original_text": "100g chicken"},
            {"food_name": "rice", "amount": 200.0, "unit": "g", "original_text": "200g rice"},
        ]
        basic_state["selected_food_id"] = 1

        result = await calculate_log_node(basic_state)

        assert len(result["pending_food_items"]) == 1
        assert result["pending_food_items"][0]["food_name"] == "rice"
        assert result["last_action"] == "LOGGED"

    async def test_calculate_log_single_item(self, basic_state, mock_calculate_log_db_session, mock_daily_log_service_for_calc, mock_calculate_macros):
        """
        arrange: setup state to reflect processing only a single remaining trackable metric.
        act:     run calculate_log_node.
        assert:  verifies processing accurately drops elements fully, triggering resolution state updates appropriately.
        """
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

    async def test_sequential_item_removal(self, basic_state, mock_calculate_log_db_session, mock_daily_log_service_for_calc, mock_calculate_macros):
        """
        arrange: initialize pending elements inside the state tracking construct.
        act:     call simulated iterative executions updating element arrays between sequences.
        assert:  verifies final output array finishes at exactly zero components with finalized loop completions logic triggered.
        """
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
        basic_state["selected_food_id"] = 5

        # Process first item
        result = await calculate_log_node(basic_state)
        assert len(result["pending_food_items"]) == 2
        assert result["pending_food_items"][0]["food_name"] == "rice"

        # Simulate processing second item
        basic_state.update({"pending_food_items": result["pending_food_items"]})
        result2 = await calculate_log_node(basic_state)
        assert len(result2["pending_food_items"]) == 1
        assert result2["pending_food_items"][0]["food_name"] == "broccoli"

        # Simulate processing third item
        basic_state.update({"pending_food_items": result2["pending_food_items"]})
        result3 = await calculate_log_node(basic_state)
        assert len(result3["pending_food_items"]) == 0
        assert result3["last_action"] == "LOGGED"


class TestMultiItemLoopEdgeCases:
    """Test functionality corresponding with potential empty or error based states."""

    async def test_calculate_log_empty_pending(self, basic_state):
        """
        arrange: stage completely empty list without trackable references.
        act:     run calculate_log_node.
        assert:  verifies bypassed checks output empty parameters seamlessly.
        """
        basic_state["pending_food_items"] = []

        result = await calculate_log_node(basic_state)

        assert result == {}

    async def test_multi_item_state_setup(self, basic_state):
        """
        arrange: manually structure state overrides.
        act:     verify initialization configurations map into local object properties properly.
        assert:  length constraints matches initialized definitions accurately.
        """
        basic_state["pending_food_items"] = [
            {"food_name": "chicken", "amount": 100.0, "unit": "g", "original_text": "100g chicken"},
            {"food_name": "rice", "amount": 200.0, "unit": "g", "original_text": "200g rice"},
            {"food_name": "broccoli", "amount": 150.0, "unit": "g", "original_text": "150g broccoli"},
        ]
        basic_state["last_action"] = "LOG_FOOD"

        assert len(basic_state["pending_food_items"]) == 3
        assert basic_state["pending_food_items"][0]["food_name"] == "chicken"
        assert basic_state["pending_food_items"][2]["food_name"] == "broccoli"
