"""
Unit tests for Calculate Macros Node (`calculate_macros_node.py`).

Scope:
    Purely isolated unit tests. Verify macro calculation for both DB and estimation paths.

LLM Usage:
    MOCKED — estimation path LLM is mocked via get_llm_for_node.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import TEST_RUNTIME_A
from src.agents.nodes.calculate_macros_node import calculate_macros_node


def _macros_return(
    *,
    name_en="Chicken breast",
    name_he="חזה עוף",
    amount_g=200.0,
    calories=330.0,
    protein=62.0,
    carbs=0.0,
    fat=7.2,
    source="database",
    category="protein",
    tag="lean",
    serving_amount_g=100.0,
    servings=2.0,
    default_unit="g",
    default_unit_weight_g=None,
):
    """Build a calculate_food_macros tool return-value dict."""
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "name_en": name_en,
        "name_he": name_he,
        "amount_g": amount_g,
        "calories": calories,
        "protein": protein,
        "carbs": carbs,
        "fat": fat,
        "source": source,
        "category": category,
        "tag": tag,
        "serving_amount_g": serving_amount_g,
        "servings": servings,
        "default_unit": default_unit,
        "default_unit_weight_g": default_unit_weight_g,
    }


class TestCalculateMacrosDBPath:
    """Tests for the DB lookup path (selected_food_id is set)."""

    async def test_db_path_success(self, basic_state, mock_calculate_macros):
        """
        arrange: mock calculate_food_macros returns enriched macros dict.
        act:     run calculate_macros_node with selected_food_id.
        assert:  MacroResult with all fields added to pending_confirmations.
        """
        mock_calculate_macros.ainvoke = AsyncMock(return_value=_macros_return())

        basic_state.update({
            "pending_food_items": [
                {"food_name": "chicken", "count": 200.0, "unit": "g", "original_text": "200g chicken"}
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000001",
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert len(result["pending_confirmations"]) == 1
        macro = result["pending_confirmations"][0]
        assert macro["name_en"] == "Chicken breast"
        assert macro["name_he"] == "חזה עוף"
        assert macro["amount_g"] == 200.0
        assert macro["calories"] == 330.0
        assert macro["source"] == "database"
        assert macro["category"] == "protein"
        assert macro["tag"] == "lean"
        assert macro["servings"] == 2.0
        assert macro["food_id"] == "00000000-0000-0000-0000-000000000001"
        assert result["pending_food_items"] == []
        assert result["selected_food_id"] is None
        mock_calculate_macros.ainvoke.assert_called_once_with(
            {
                "food_id": "00000000-0000-0000-0000-000000000001",
                "count": 200.0,
                "unit": "g",
            }
        )

    async def test_db_path_error(self, basic_state, mock_calculate_macros):
        """
        arrange: tool returns {"error": "..."} (not found or unit mismatch).
        act:     run calculate_macros_node.
        assert:  FAILED result; last_action=NO_MATCH; no confirmation added.
        """
        mock_calculate_macros.ainvoke = AsyncMock(return_value={"error": "Food not found"})

        basic_state.update({
            "pending_food_items": [
                {"food_name": "mystery", "count": 100.0, "unit": "g", "original_text": "100g mystery"}
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000999",
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert len(result["processing_results"]) == 1
        assert result["processing_results"][0]["status"] == "FAILED"
        assert result["last_action"] == "NO_MATCH"
        assert "pending_confirmations" not in result

    async def test_db_path_unit_mismatch_error(self, basic_state, mock_calculate_macros):
        """
        arrange: tool returns unit-mismatch error (food expects 'slice', user gave 'piece').
        act:     run calculate_macros_node.
        assert:  FAILED with unit-mismatch message.
        """
        mock_calculate_macros.ainvoke = AsyncMock(
            return_value={"error": "Unit mismatch: user gave 'piece', food 'Bread' expects 'slice'"}
        )

        basic_state.update({
            "pending_food_items": [
                {"food_name": "bread", "count": 1.0, "unit": "piece", "original_text": "a piece of bread"}
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000001",
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert result["processing_results"][0]["status"] == "FAILED"
        assert "Unit mismatch" in result["processing_results"][0]["message"]
        assert result["last_action"] == "NO_MATCH"

    async def test_db_path_passes_count_and_unit_to_tool(
        self, basic_state, mock_calculate_macros
    ):
        """
        arrange: user input has natural unit (piece), selected_food_id set.
        act:     run calculate_macros_node.
        assert:  tool called with count=2 and unit='piece' — resolution happens in tool.
        """
        mock_calculate_macros.ainvoke = AsyncMock(
            return_value=_macros_return(name_en="Egg", amount_g=100.0, calories=155.0)
        )

        basic_state.update({
            "pending_food_items": [
                {"food_name": "egg", "count": 2.0, "unit": "piece", "original_text": "2 eggs"}
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000001",
        })

        await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        mock_calculate_macros.ainvoke.assert_called_once_with(
            {
                "food_id": "00000000-0000-0000-0000-000000000001",
                "count": 2.0,
                "unit": "piece",
            }
        )

    async def test_accumulates_confirmations(self, basic_state, mock_calculate_macros):
        """
        arrange: set existing pending_confirmations in state.
        act:     run calculate_macros_node.
        assert:  new item appended to existing confirmations.
        """
        existing = {
            "name_en": "rice",
            "name_he": None,
            "amount_g": 200,
            "calories": 260,
            "protein": 5,
            "carbs": 56,
            "fat": 0.6,
            "source": "database",
            "category": "carb",
            "tag": None,
            "serving_amount_g": 100.0,
            "servings": 2.0,
            "default_unit": "g",
            "default_unit_weight_g": None,
            "original_text": "200g rice",
            "food_id": "food-uuid-2",
        }

        mock_calculate_macros.ainvoke = AsyncMock(return_value=_macros_return())

        basic_state.update({
            "pending_food_items": [
                {"food_name": "chicken", "count": 100.0, "unit": "g", "original_text": "100g chicken"}
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000001",
            "pending_confirmations": [existing],
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert len(result["pending_confirmations"]) == 2
        assert result["pending_confirmations"][0] == existing
        assert result["pending_confirmations"][1]["name_en"] == "Chicken breast"

    async def test_db_path_preserves_estimated_source(
        self, basic_state, mock_calculate_macros
    ):
        """
        arrange: tool returns source='estimated' (re-used estimated food).
        act:     run calculate_macros_node.
        assert:  MacroResult preserves source='estimated'.
        """
        mock_calculate_macros.ainvoke = AsyncMock(
            return_value=_macros_return(
                name_en="Protein Shake",
                source="estimated",
                category=None,
                tag=None,
                serving_amount_g=None,
                servings=None,
            )
        )

        basic_state.update({
            "pending_food_items": [
                {"food_name": "protein shake", "count": 300.0, "unit": "g", "original_text": "a protein shake"}
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000001",
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        macro = result["pending_confirmations"][0]
        assert macro["source"] == "estimated"
        assert macro["category"] is None
        assert macro["tag"] is None

    async def test_pops_pending_item(self, basic_state, mock_calculate_macros):
        """
        arrange: set two pending items.
        act:     run calculate_macros_node.
        assert:  first item removed, second remains.
        """
        mock_calculate_macros.ainvoke = AsyncMock(return_value=_macros_return())

        basic_state.update({
            "pending_food_items": [
                {"food_name": "chicken", "count": 100.0, "unit": "g", "original_text": "100g chicken"},
                {"food_name": "rice", "count": 200.0, "unit": "g", "original_text": "200g rice"},
            ],
            "selected_food_id": "00000000-0000-0000-0000-000000000001",
        })

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert len(result["pending_food_items"]) == 1
        assert result["pending_food_items"][0]["food_name"] == "rice"


def _estimate_return(
    *,
    name_en="Pizza",
    name_he="פיצה",
    amount_g_estimated=200.0,
    calories=540.0,
    protein=22.0,
    carbs=60.0,
    fat=22.0,
    category=None,
    tag=None,
    default_unit="slice",
    default_unit_weight_g=100.0,
):
    """Build a MacroEstimation-shaped LLM mock return."""
    m = MagicMock()
    m.name_en = name_en
    m.name_he = name_he
    m.amount_g_estimated = amount_g_estimated
    m.calories = calories
    m.protein = protein
    m.carbs = carbs
    m.fat = fat
    m.category = category
    m.tag = tag
    m.default_unit = default_unit
    m.default_unit_weight_g = default_unit_weight_g
    return m


def _patch_estimation_llm(return_value):
    """Patch get_llm_for_node so structured ainvoke returns the given mock."""
    patcher = patch("src.agents.nodes.calculate_macros_node.get_llm_for_node")
    mock_get_llm = patcher.start()
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=return_value)
    mock_llm.with_structured_output.return_value = mock_structured
    mock_get_llm.return_value = mock_llm
    return patcher, mock_structured


class TestCalculateMacrosEstimationPath:
    """Tests for the LLM estimation path (selected_food_id is None)."""

    async def test_estimation_path(self, basic_state):
        """
        arrange: selected_food_id=None and mocked LLM estimation.
        act:     run calculate_macros_node.
        assert:  MacroResult with source='estimated' and food_id=None.
        """
        basic_state.update({
            "pending_food_items": [
                {"food_name": "homemade pizza", "count": 300.0, "unit": "g", "original_text": "3 slices of pizza"}
            ],
            "selected_food_id": None,
            "last_action": "NO_MATCH",
        })

        patcher, _ = _patch_estimation_llm(
            _estimate_return(
                name_en="homemade pizza",
                name_he=None,
                amount_g_estimated=300.0,
                calories=750.0,
                protein=30.0,
                carbs=85.0,
                fat=32.0,
                category=None,
                tag=None,
                default_unit=None,
                default_unit_weight_g=None,
            )
        )
        try:
            result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)
        finally:
            patcher.stop()

        assert len(result["pending_confirmations"]) == 1
        macro = result["pending_confirmations"][0]
        assert macro["source"] == "estimated"
        assert macro["food_id"] is None
        assert macro["calories"] == 750.0
        assert macro["name_en"] == "homemade pizza"
        assert macro["category"] is None

    async def test_estimation_grams_input_passes_count_through(self, basic_state):
        """
        arrange: pending_food_items=[{count:300, unit:"g", food_name:"pizza"}],
                 selected_food_id=None; mock LLM returns amount_g_estimated=300.
        act:     run calculate_macros_node.
        assert:  resulting MacroResult has amount_g=300, original_count=300,
                 original_unit="g".
        """
        basic_state.update({
            "pending_food_items": [
                {"food_name": "pizza", "count": 300.0, "unit": "g", "original_text": "300g pizza"}
            ],
            "selected_food_id": None,
        })

        patcher, _ = _patch_estimation_llm(_estimate_return(amount_g_estimated=300.0))
        try:
            result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)
        finally:
            patcher.stop()

        macro = result["pending_confirmations"][0]
        assert macro["amount_g"] == 300.0
        assert macro["original_count"] == 300.0
        assert macro["original_unit"] == "g"

    async def test_estimation_natural_unit_uses_llm_amount_g(self, basic_state):
        """
        arrange: pending_food_items=[{count:2, unit:"slice", food_name:"pizza"}];
                 mock LLM returns amount_g_estimated=200, default_unit_weight_g=100,
                 calories=540.
        act:     run calculate_macros_node.
        assert:  MacroResult.amount_g=200 (from LLM, not 2g),
                 original_count=2, original_unit="slice", calories=540.
        """
        basic_state.update({
            "pending_food_items": [
                {"food_name": "pizza", "count": 2.0, "unit": "slice", "original_text": "2 slices pizza"}
            ],
            "selected_food_id": None,
        })

        patcher, _ = _patch_estimation_llm(
            _estimate_return(
                amount_g_estimated=200.0,
                calories=540.0,
                default_unit="slice",
                default_unit_weight_g=100.0,
            )
        )
        try:
            result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)
        finally:
            patcher.stop()

        macro = result["pending_confirmations"][0]
        assert macro["amount_g"] == 200.0
        assert macro["original_count"] == 2.0
        assert macro["original_unit"] == "slice"
        assert macro["calories"] == 540.0

    async def test_estimation_call_passes_count_and_unit_in_human_message(
        self, basic_state
    ):
        """
        arrange: pending_food_items=[{count:2, unit:"slice", food_name:"pizza"}].
        act:     run calculate_macros_node, capture LLM invocation messages.
        assert:  HumanMessage content contains "2 slice" and "pizza".
        """
        basic_state.update({
            "pending_food_items": [
                {"food_name": "pizza", "count": 2.0, "unit": "slice", "original_text": "2 slices pizza"}
            ],
            "selected_food_id": None,
        })

        patcher, mock_structured = _patch_estimation_llm(_estimate_return())
        try:
            await calculate_macros_node(basic_state, TEST_RUNTIME_A)
        finally:
            patcher.stop()

        call_messages = mock_structured.ainvoke.call_args.args[0]
        human_msg = next(m for m in call_messages if m.__class__.__name__ == "HumanMessage")
        assert "2" in human_msg.content
        assert "slice" in human_msg.content
        assert "pizza" in human_msg.content


class TestCalculateMacrosEdgeCases:
    """Test edge cases."""

    async def test_empty_pending_items(self, basic_state):
        """
        arrange: empty pending_food_items.
        act:     run calculate_macros_node.
        assert:  returns empty dict.
        """
        basic_state["pending_food_items"] = []

        result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

        assert result == {}
