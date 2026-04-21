import os
from typing import Literal

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from src.agents.state import AgentState, MacroResult
from src.config import BASE_DIR, get_llm_for_node
from src.context import ContextSchema
from src.i18n import MESSAGES
from src.schemas.confirmation_schema import ConfirmationResponse
from src.services.food_service import calculate_food_macros

logger = structlog.get_logger(__name__)

# Load confirmation prompt template once at import time — no file I/O during graph execution
_CONFIRMATION_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "confirmation_parser.md")
try:
    with open(_CONFIRMATION_PROMPT_PATH, "r", encoding="utf-8") as _f:
        _CONFIRMATION_PROMPT = _f.read()
except FileNotFoundError:
    logger.warning("Confirmation prompt file not found, using fallback")
    _CONFIRMATION_PROMPT = (
        "Parse the user's response to a food logging confirmation prompt."
    )


def _format_batch_preview(items: list[MacroResult]) -> dict:
    """Build human-readable batch preview payload for interrupt.

    Renders the food name in the user's language (he if BOT_LANGUAGE=he).
    Includes servings + category info per item when available — the bot
    gateway renders them via the confirmation_serving_line i18n template.
    """
    lang = os.environ.get("BOT_LANGUAGE", "en").lower()
    formatted_items = []
    for i, item in enumerate(items):
        source_tag = (
            MESSAGES["confirmation_estimated_tag"] if item["source"] == "estimated" else ""
        )
        name = (
            item.get("name_he")
            if lang == "he" and item.get("name_he")
            else item["name_en"]
        )
        formatted_items.append(
            {
                "index": i,
                "description": f"{name} — {item['amount_g']}g{source_tag}",
                "calories": item["calories"],
                "protein": item["protein"],
                "carbs": item["carbs"],
                "fat": item["fat"],
                "source": item["source"],
                "servings": item.get("servings"),
                "category": item.get("category"),
            }
        )

    totals = {
        "calories": round(sum(it["calories"] for it in items), 1),
        "protein": round(sum(it["protein"] for it in items), 1),
        "carbs": round(sum(it["carbs"] for it in items), 1),
        "fat": round(sum(it["fat"] for it in items), 1),
    }

    return {
        "question": MESSAGES["confirmation_question"],
        "items": formatted_items,
        "totals": totals,
    }


async def confirmation_node(
    state: AgentState, runtime: Runtime[ContextSchema],
) -> Command[Literal["commit", "response"]]:
    """Present batch preview and await user confirmation via conversational interrupt loop.

    Uses LangGraph's interrupt() in a while loop:
    - Each interrupt() pauses the graph and shows the batch preview
    - User responds with natural text (confirm/reject/edit)
    - LLM parses the response into a structured ConfirmationResponse
    - Edits update the batch and re-show; confirm/reject exit the loop
    """
    batch = list(state.get("pending_confirmations", []))

    if not batch:
        logger.warning("Confirmation node called with empty batch, skipping to response")
        return Command(goto="response")

    preview = _format_batch_preview(batch)

    while True:
        user_response = interrupt(preview)

        # Parse user response with LLM
        decision = await _parse_confirmation(user_response, batch)

        logger.info("User confirmation", action=decision.action, items=len(batch))

        if decision.action == "confirm":
            return Command(
                goto="commit",
                update={
                    "pending_confirmations": batch,
                    "last_action": "CONFIRMED",
                },
            )

        elif decision.action == "reject":
            # Build FAILED results for all items
            failed_results = []
            for item in batch:
                failed_results.append(
                    {
                        "food_name": item["name_en"],
                        "name_he": item.get("name_he"),
                        "count": item["amount_g"],
                        "unit": "g",
                        "original_text": item["original_text"],
                        "status": "FAILED",
                        "message": f"User rejected logging {item['name_en']}",
                        "source": item.get("source"),
                    }
                )

            return Command(
                goto="response",
                update={
                    "last_action": "REJECTED",
                    "pending_confirmations": [],
                    "processing_results": state.get("processing_results", [])
                    + failed_results,
                },
            )

        elif decision.action == "edit":
            # Apply edits to batch
            batch = await _apply_edits(batch, decision.edits or [])
            # Re-build preview with updated batch
            preview = _format_batch_preview(batch)
            # Loop continues → interrupt again with updated preview


async def _parse_confirmation(
    user_text: str, batch: list[MacroResult]
) -> ConfirmationResponse:
    """Use LLM to parse user's natural language confirmation response."""
    # Build batch context and inject into prompt template
    batch_context = "\n".join(
        f"[{i}] {item.get('name_he') or item['name_en']} — {item['amount_g']}g ({item['source']})"
        for i, item in enumerate(batch)
    )
    system_prompt = _CONFIRMATION_PROMPT.replace("{batch_context}", batch_context)

    llm = get_llm_for_node("confirmation_node")
    structured_llm = llm.with_structured_output(ConfirmationResponse)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_text),
    ]

    return await structured_llm.ainvoke(messages)


async def _apply_edits(
    batch: list[MacroResult], edits: list,
) -> list[MacroResult]:
    """Apply user edits to the batch. Recalculate macros for amount changes."""
    # Process removals in reverse order to preserve indices
    remove_indices = sorted(
        [e.item_index for e in edits if e.edit_type == "remove"],
        reverse=True,
    )
    for idx in remove_indices:
        if 0 <= idx < len(batch):
            logger.info("User edit: removed item", index=idx)
            batch.pop(idx)

    # Process amount changes
    for edit in edits:
        if edit.edit_type == "change_amount" and edit.new_amount_g is not None:
            if 0 <= edit.item_index < len(batch):
                item = batch[edit.item_index]
                old_amount = item["amount_g"]
                new_amount = edit.new_amount_g
                logger.info("User edit: changed amount", index=edit.item_index, old_g=old_amount, new_g=new_amount)

                if item["food_id"] is not None:
                    # DB item — recalculate via tool. Edits are grams-only for now
                    # (unit-aware edits are a Plan 3+ concern).
                    macros = await calculate_food_macros.ainvoke(
                        {"food_id": item["food_id"], "count": new_amount, "unit": "g"}
                    )
                    if "error" not in macros:
                        item["amount_g"] = new_amount
                        item["calories"] = macros["calories"]
                        item["protein"] = macros["protein"]
                        item["carbs"] = macros["carbs"]
                        item["fat"] = macros["fat"]
                else:
                    # Estimated item — scale proportionally
                    if old_amount > 0:
                        ratio = new_amount / old_amount
                        item["amount_g"] = new_amount
                        item["calories"] = round(item["calories"] * ratio, 1)
                        item["protein"] = round(item["protein"] * ratio, 1)
                        item["carbs"] = round(item["carbs"] * ratio, 1)
                        item["fat"] = round(item["fat"] * ratio, 1)

    return batch
