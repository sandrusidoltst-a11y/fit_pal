import os

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from src.agents.state import AgentState, MacroResult
from src.config import BASE_DIR, get_llm_for_node
from src.context import ContextSchema
from src.schemas.estimation_schema import MacroEstimation
from src.services.food_service import calculate_food_macros

logger = structlog.get_logger(__name__)

# Load estimation prompt once at import time — no file I/O during graph execution
_ESTIMATION_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "macro_estimation.md")
try:
    with open(_ESTIMATION_PROMPT_PATH, "r", encoding="utf-8") as _f:
        _ESTIMATION_PROMPT = _f.read()
except FileNotFoundError:
    logger.warning("Estimation prompt file not found, using fallback")
    _ESTIMATION_PROMPT = (
        "Estimate nutritional values for the given food item and amount."
    )


async def calculate_macros_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    """Calculate macros for the current food item (preview only, no DB write).

    Two paths:
    1. DB match (selected_food_id exists): call calculate_food_macros tool
       with (count, unit) — tool resolves to grams internally.
    2. Off-menu (selected_food_id is None): Use LLM estimation.

    Accumulates results into pending_confirmations for batch confirmation.
    """
    pending_items = state.get("pending_food_items", [])
    selected_food_id = state.get("selected_food_id")

    if not pending_items:
        return {}

    current_item = pending_items[0]
    count = current_item.get("count", 0.0)
    unit = current_item.get("unit", "g")
    food_name = current_item.get("food_name", "")

    if selected_food_id:
        # DB path — tool handles fetch + unit resolution + macro compute
        macros = await calculate_food_macros.ainvoke(
            {"food_id": selected_food_id, "count": count, "unit": unit}
        )
        if "error" in macros:
            logger.warning(
                "Macro calculation failed", food=food_name, error=macros["error"]
            )
            result_item = {
                **current_item,
                "status": "FAILED",
                "message": macros["error"],
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
            "name_en": macros["name_en"],
            "name_he": macros.get("name_he"),
            "amount_g": macros["amount_g"],
            "calories": macros["calories"],
            "protein": macros["protein"],
            "carbs": macros["carbs"],
            "fat": macros["fat"],
            "source": macros.get("source", "database"),
            "category": macros.get("category"),
            "tag": macros.get("tag"),
            "serving_amount_g": macros.get("serving_amount_g"),
            "servings": macros.get("servings"),
            "default_unit": macros.get("default_unit"),
            "default_unit_weight_g": macros.get("default_unit_weight_g"),
            "original_text": current_item.get("original_text", ""),
            "food_id": selected_food_id,
            "original_count": count,
            "original_unit": unit,
        }
    else:
        # Estimation path — pass the user's (count, unit) through to the LLM,
        # which is responsible for computing amount_g_estimated and macros for
        # that exact total. Fixes the previous bug where unit was collapsed
        # to grams and "2 slices" got estimated as 2 grams.
        logger.info(
            "Estimating macros via LLM", food=food_name, count=count, unit=unit
        )
        macro_result = await _estimate_macros(
            food_name, count, unit, current_item.get("original_text", "")
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
    food_name: str, count: float, unit: str, original_text: str
) -> MacroResult:
    """Use LLM to estimate macros for an off-menu food item.

    Passes the user's stated (count, unit) through to the LLM so it can
    estimate macros for the correct gram total. The LLM emits
    ``amount_g_estimated`` directly — we use it as ``MacroResult.amount_g``.
    """
    llm = get_llm_for_node("estimation_node")
    structured_llm = llm.with_structured_output(MacroEstimation)

    messages = [
        SystemMessage(content=_ESTIMATION_PROMPT),
        HumanMessage(
            content=f"Estimate macros for: {food_name}, quantity: {count} {unit}"
        ),
    ]

    result = await structured_llm.ainvoke(messages)

    return {
        "name_en": result.name_en,
        "name_he": result.name_he,
        "amount_g": result.amount_g_estimated,
        "calories": round(result.calories, 1),
        "protein": round(result.protein, 1),
        "carbs": round(result.carbs, 1),
        "fat": round(result.fat, 1),
        "source": "estimated",
        "category": result.category,
        "tag": result.tag,
        "serving_amount_g": None,
        "servings": None,
        "default_unit": result.default_unit,
        "default_unit_weight_g": result.default_unit_weight_g,
        "original_text": original_text,
        "food_id": None,
        "original_count": count,
        "original_unit": unit,
    }
