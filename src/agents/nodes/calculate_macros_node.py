import os

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from src.agents.state import AgentState, MacroResult
from src.config import BASE_DIR, get_llm_for_node
from src.context import ContextSchema
from src.database import get_async_db_session
from src.schemas.estimation_schema import MacroEstimation
from src.services.food_service import (
    compute_food_macros,
    get_food_by_id,
    resolve_amount_g,
)

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
    1. DB match (selected_food_id exists): fetch food+mapping via get_food_by_id,
       resolve unit/count to grams, compute macros via pure helper.
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
        # DB path — single query for food+mapping, then pure compute
        async with get_async_db_session() as session:
            row = await get_food_by_id(session, selected_food_id)

        if row is None:
            logger.error("Selected food vanished", food=food_name, food_id=selected_food_id)
            result_item = {
                **current_item,
                "status": "FAILED",
                "message": f"Could not find food {food_name} with id {selected_food_id}",
            }
            remaining = pending_items[1:]
            return {
                "pending_food_items": remaining,
                "processing_results": state.get("processing_results", [])
                + [result_item],
                "last_action": "NO_MATCH",
                "selected_food_id": None,
            }

        food, mapping = row
        try:
            amount_g = resolve_amount_g(food, unit, count)
        except ValueError as e:
            logger.warning(
                "Unit resolution failed", food=food.name_en, unit=unit, error=str(e)
            )
            result_item = {
                **current_item,
                "status": "FAILED",
                "message": str(e),
            }
            remaining = pending_items[1:]
            return {
                "pending_food_items": remaining,
                "processing_results": state.get("processing_results", [])
                + [result_item],
                "last_action": "NO_MATCH",
                "selected_food_id": None,
            }

        macros = compute_food_macros(food, mapping, amount_g)
        macro_result: MacroResult = {
            "name_en": macros["name_en"],
            "name_he": macros.get("name_he"),
            "amount_g": amount_g,
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
        }
    else:
        # Estimation path — use LLM. No food row yet; treat count as grams
        # (Plan 3 estimation prompt may teach the LLM to emit default_unit/weight).
        amount_g = count
        logger.info("Estimating macros via LLM", food=food_name, amount_g=amount_g)
        macro_result = await _estimate_macros(
            food_name, amount_g, current_item.get("original_text", "")
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
    llm = get_llm_for_node("estimation_node")
    structured_llm = llm.with_structured_output(MacroEstimation)

    messages = [
        SystemMessage(content=_ESTIMATION_PROMPT),
        HumanMessage(content=f"Estimate macros for: {food_name}, amount: {amount_g}g"),
    ]

    result = await structured_llm.ainvoke(messages)

    return {
        "name_en": result.name_en,
        "name_he": result.name_he,
        "amount_g": amount_g,
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
    }
