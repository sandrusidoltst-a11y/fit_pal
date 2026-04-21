"""
Unit tests for Multi-Item Loop processing dynamics (`calculate_macros_node.py` loop tracking).

Scope:
    Purely isolated unit tests. Verify arrays modify successfully.

LLM Usage:
    NONE — calculate_macros_node DB path does not call an LLM.
"""
from unittest.mock import AsyncMock

from tests.conftest import TEST_RUNTIME_A
from src.agents.nodes.calculate_macros_node import calculate_macros_node


def _macros_return(**overrides):
    base = {
        "id": "00000000-0000-0000-0000-000000000005",
        "name_en": "Test Food",
        "name_he": None,
        "amount_g": 100.0,
        "calories": 200.0,
        "protein": 20.0,
        "carbs": 10.0,
        "fat": 5.0,
        "source": "database",
        "category": None,
        "tag": None,
        "serving_amount_g": None,
        "servings": None,
        "default_unit": "g",
        "default_unit_weight_g": None,
    }
    base.update(overrides)
    return base


class TestMultiItemLoopDraining:
    """Test standard array draining functionality."""

    async def test_calculate_macros_removes_first_item(self, basic_state, mock_calculate_macros):
        """
        arrange: set multiple items inside pending_food_items array.
        act:     run calculate_macros_node.
        assert:  verifies calculated item has been removed from pending and added to confirmations.
        """
        mock_calculate_macros.ainvoke = AsyncMock(return_value=_macros_return())

        basic_state["pending_food_items"] = [
            {"food_name": "chicken", "count": 100.0, "unit": "g", "original_text": "100g chicken"},
            {"food_name": "rice", "count": 200.0, "unit": "g", "original_text": "200g rice"},
        ]
        basic_state["selected_food_id"] = "00000000-0000-0000-0000-000000000005"

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert len(result["pending_food_items"]) == 1
        assert result["pending_food_items"][0]["food_name"] == "rice"
        assert result["last_action"] == "AWAITING_CONFIRMATION"
        assert len(result["pending_confirmations"]) == 1
        assert result["pending_confirmations"][0]["name_en"] == "Test Food"

    async def test_calculate_macros_single_item(self, basic_state, mock_calculate_macros):
        """
        arrange: setup state to reflect processing only a single remaining item.
        act:     run calculate_macros_node.
        assert:  verifies processing drops the element and adds to confirmations.
        """
        mock_calculate_macros.ainvoke = AsyncMock(return_value=_macros_return(amount_g=150.0))

        basic_state["pending_food_items"] = [
            {"food_name": "apple", "count": 150.0, "unit": "g", "original_text": "an apple"},
        ]
        basic_state["selected_food_id"] = "00000000-0000-0000-0000-000000000005"

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert len(result["pending_food_items"]) == 0
        assert result["last_action"] == "AWAITING_CONFIRMATION"
        assert len(result["pending_confirmations"]) == 1

    async def test_sequential_item_accumulation(self, basic_state, mock_calculate_macros):
        """
        arrange: initialize pending elements inside the state tracking construct.
        act:     call simulated iterative executions updating element arrays between sequences.
        assert:  verifies all items accumulate into pending_confirmations sequentially.
        """
        mock_calculate_macros.ainvoke = AsyncMock(return_value=_macros_return())

        items = [
            {"food_name": "chicken", "count": 100.0, "unit": "g", "original_text": "100g chicken"},
            {"food_name": "rice", "count": 200.0, "unit": "g", "original_text": "200g rice"},
            {"food_name": "broccoli", "count": 150.0, "unit": "g", "original_text": "150g broccoli"},
        ]
        basic_state["pending_food_items"] = items
        basic_state["selected_food_id"] = "00000000-0000-0000-0000-000000000005"

        # Process first item
        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)
        assert len(result["pending_food_items"]) == 2
        assert len(result["pending_confirmations"]) == 1

        # Simulate processing second item
        basic_state.update({
            "pending_food_items": result["pending_food_items"],
            "pending_confirmations": result["pending_confirmations"],
            "selected_food_id": "00000000-0000-0000-0000-000000000005",
        })
        result2 = await calculate_macros_node(basic_state, TEST_RUNTIME_A)
        assert len(result2["pending_food_items"]) == 1
        assert len(result2["pending_confirmations"]) == 2

        # Simulate processing third item
        basic_state.update({
            "pending_food_items": result2["pending_food_items"],
            "pending_confirmations": result2["pending_confirmations"],
            "selected_food_id": "00000000-0000-0000-0000-000000000005",
        })
        result3 = await calculate_macros_node(basic_state, TEST_RUNTIME_A)
        assert len(result3["pending_food_items"]) == 0
        assert len(result3["pending_confirmations"]) == 3


class TestMultiItemLoopEdgeCases:
    """Test functionality corresponding with potential empty or error based states."""

    async def test_calculate_macros_empty_pending(self, basic_state):
        """
        arrange: stage completely empty list without trackable references.
        act:     run calculate_macros_node.
        assert:  verifies bypassed checks output empty parameters seamlessly.
        """
        basic_state["pending_food_items"] = []

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert result == {}

    async def test_multi_item_state_setup(self, basic_state):
        """
        arrange: manually structure state overrides.
        act:     verify initialization configurations map into local object properties properly.
        assert:  length constraints matches initialized definitions accurately.
        """
        basic_state["pending_food_items"] = [
            {"food_name": "chicken", "count": 100.0, "unit": "g", "original_text": "100g chicken"},
            {"food_name": "rice", "count": 200.0, "unit": "g", "original_text": "200g rice"},
            {"food_name": "broccoli", "count": 150.0, "unit": "g", "original_text": "150g broccoli"},
        ]
        basic_state["last_action"] = "LOG_FOOD"

        assert len(basic_state["pending_food_items"]) == 3
        assert basic_state["pending_food_items"][0]["food_name"] == "chicken"
        assert basic_state["pending_food_items"][2]["food_name"] == "broccoli"
