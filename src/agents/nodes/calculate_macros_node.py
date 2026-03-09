import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.agents.state import AgentState, MacroResult
from src.config import BASE_DIR, get_llm_for_node
from src.schemas.estimation_schema import MacroEstimation
from src.tools.food_lookup import calculate_food_macros


async def calculate_macros_node(state: AgentState, config: RunnableConfig) -> dict:
    """Calculate macros for the current food item (preview only, no DB write).

    Two paths:
    1. DB match (selected_food_id exists): Use calculate_food_macros tool
    2. Off-menu (selected_food_id is None): Use LLM estimation

    Accumulates results into pending_confirmations for batch confirmation.
    """
    pending_items = state.get("pending_food_items", [])
    selected_food_id = state.get("selected_food_id")

    if not pending_items:
        return {}

    current_item = pending_items[0]
    amount = current_item.get("amount", 0.0)
    food_name = current_item.get("food_name", "")

    if selected_food_id:
        # DB path — use tool
        macros = await calculate_food_macros.ainvoke(
            {"food_id": selected_food_id, "amount_g": amount}, config=config
        )
        if "error" in macros:
            # Calculation failed — add FAILED result, skip this item
            result_item = {
                **current_item,
                "status": "FAILED",
                "message": f"Could not calculate macros for {food_name}: {macros['error']}",
            }
            remaining = pending_items[1:]
            return {
                "pending_food_items": remaining,
                "processing_results": state.get("processing_results", [])
                + [result_item],
                "last_action": "NO_MATCH",
                "selected_food_id": None,
            }

        macro_result: MacroResult = {
            "food_name": food_name,
            "amount_g": amount,
            "calories": macros["calories"],
            "protein": macros["protein"],
            "carbs": macros["carbs"],
            "fat": macros["fat"],
            "source": macros.get("source", "database"),
            "original_text": current_item.get("original_text", ""),
            "food_id": selected_food_id,
        }
    else:
        # Estimation path — use LLM
        macro_result = await _estimate_macros(
            food_name, amount, current_item.get("original_text", "")
        )

    # Accumulate into pending_confirmations
    current_confirmations = state.get("pending_confirmations", [])
    updated_confirmations = current_confirmations + [macro_result]

    # Pop processed item
    remaining = pending_items[1:]

    return {
        "pending_food_items": remaining,
        "pending_confirmations": updated_confirmations,
        "last_action": "AWAITING_CONFIRMATION",
        "selected_food_id": None,
    }


async def _estimate_macros(
    food_name: str, amount_g: float, original_text: str
) -> MacroResult:
    """Use LLM to estimate macros for an off-menu food item."""
    prompt_path = os.path.join(BASE_DIR, "prompts", "macro_estimation.md")
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        system_prompt = (
            "Estimate nutritional values for the given food item and amount."
        )

    llm = get_llm_for_node("estimation_node")
    structured_llm = llm.with_structured_output(MacroEstimation)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Estimate macros for: {food_name}, amount: {amount_g}g"),
    ]

    result = await structured_llm.ainvoke(messages)

    return {
        "food_name": food_name,
        "amount_g": amount_g,
        "calories": round(result.calories, 1),
        "protein": round(result.protein, 1),
        "carbs": round(result.carbs, 1),
        "fat": round(result.fat, 1),
        "source": "estimated",
        "original_text": original_text,
        "food_id": None,
    }
