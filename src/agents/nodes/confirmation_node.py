import os
from datetime import datetime
from typing import Literal

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from src.agents.state import AgentState, MacroResult, ProcessingResult
from src.config import BASE_DIR, get_llm_for_node
from src.context import ContextSchema
from src.i18n import MESSAGES
from src.schemas.confirmation_schema import ConfirmationResponse, ItemEdit
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


def _unit_label_key(unit: str, count: float) -> str:
    """Pick the singular/plural i18n key for a natural-unit label."""
    suffix = "singular" if count == 1 else "plural"
    return f"confirmation_unit_label_{unit}_{suffix}"


def _format_batch_preview(
    items: list[MacroResult],
    consumed_at: datetime | str | None = None,
) -> dict:
    """Build human-readable batch preview payload for interrupt.

    Renders the food name in the user's language (he if BOT_LANGUAGE=he).
    Includes servings + category info per item when available — the bot
    gateway renders them via the confirmation_serving_line i18n template.

    `consumed_at` (when set) is surfaced as a top-level ISO date string so
    the bot can render a date label and the user can verify the routing
    target before confirming. Accepts both `datetime` (fresh state) and
    `str` (LangGraph state round-trip) — see response_node.py:166-171 for
    the same defensive pattern.
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
        if item["original_unit"] == "g":
            description = f"{name} — {item['amount_g']}g{source_tag}"
        else:
            # Defensive i18n lookup — natural units are now free-form, so the
            # MESSAGES table won't always have a singular/plural label entry.
            # Render the raw unit string as a graceful fallback.
            label = MESSAGES.get(
                _unit_label_key(item["original_unit"], item["original_count"]),
                item["original_unit"],
            )
            description = (
                f"{name} — {item['original_count']:g} {label} "
                f"({item['amount_g']}g){source_tag}"
            )
        formatted_items.append(
            {
                "index": i,
                "description": description,
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

    consumed_at_iso: str | None = None
    if consumed_at is not None:
        if isinstance(consumed_at, datetime):
            consumed_at_iso = consumed_at.date().isoformat()
        else:
            # Already serialized (LangGraph state round-trip) — take date portion.
            consumed_at_iso = str(consumed_at)[:10]

    return {
        "question": MESSAGES["confirmation_question"],
        "items": formatted_items,
        "consumed_at": consumed_at_iso,
        "totals": totals,
    }


async def confirmation_node(
    state: AgentState, runtime: Runtime[ContextSchema],
) -> Command[Literal["commit", "load_daily_context"]]:
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
        return Command(goto="load_daily_context")

    consumed_at = state.get("log_food", {}).get("consumed_at")
    preview = _format_batch_preview(batch, consumed_at)
    # Accumulate edit-time FAILED results across the loop; merged into the
    # final Command's update so they survive the LangGraph state merge.
    accumulated_edit_errors: list[ProcessingResult] = []

    while True:
        user_response = interrupt(preview)

        # Parse user response with LLM
        decision = await _parse_confirmation(user_response, batch)

        logger.info("User confirmation", action=decision.action, items=len(batch))

        if decision.action == "confirm":
            update: dict = {
                "pending_confirmations": batch,
                "last_action": "CONFIRMED",
                "pipeline_stage": "CONFIRMED",
            }
            if accumulated_edit_errors:
                update["processing_results"] = (
                    state.get("processing_results", []) + accumulated_edit_errors
                )
            return Command(goto="commit", update=update)

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
                goto="load_daily_context",
                update={
                    "last_action": "REJECTED",
                    "pipeline_stage": "REJECTED",
                    "pending_confirmations": [],
                    "processing_results": state.get("processing_results", [])
                    + accumulated_edit_errors
                    + failed_results,
                },
            )

        elif decision.action == "edit":
            # Apply edits to batch — collect any FAILED results for
            # unit-mismatch / unconvertible edits.
            batch, edit_errors = await _apply_edits(batch, decision.edits or [])
            accumulated_edit_errors.extend(edit_errors)
            # Re-build preview with updated batch (date unchanged across edits)
            preview = _format_batch_preview(batch, consumed_at)
            # Loop continues → interrupt again with updated preview


async def _parse_confirmation(
    user_text: str, batch: list[MacroResult]
) -> ConfirmationResponse:
    """Use LLM to parse user's natural language confirmation response."""
    # Build batch context and inject into prompt template
    batch_context = "\n".join(
        f"[{i}] {item.get('name_he') or item['name_en']} — "
        f"{item['original_count']:g} {item['original_unit']} "
        f"({item['amount_g']}g, {item['source']})"
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


def _surface_edit_error(
    item: MacroResult,
    edit: ItemEdit,
    message: str,
) -> ProcessingResult:
    """Build a FAILED ProcessingResult for an edit we couldn't apply."""
    return {
        "food_name": item["name_en"],
        "name_he": item.get("name_he"),
        "count": edit.new_count or 0.0,
        "unit": edit.new_unit or "g",
        "original_text": item["original_text"],
        "status": "FAILED",
        "message": message,
        "source": item.get("source"),
    }


async def _apply_edits(
    batch: list[MacroResult], edits: list[ItemEdit],
) -> tuple[list[MacroResult], list[ProcessingResult]]:
    """Apply user edits to the batch. Recalculate macros for amount changes.

    Returns (updated_batch, edit_errors). The caller is responsible for
    appending edit_errors to state.processing_results — keeping this function
    free of state mutation.
    """
    edit_errors: list[ProcessingResult] = []

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
        if edit.edit_type != "change_amount" or edit.new_count is None or edit.new_unit is None:
            continue
        if not (0 <= edit.item_index < len(batch)):
            continue

        item = batch[edit.item_index]
        old_amount = item["amount_g"]
        logger.info(
            "User edit: changed amount",
            index=edit.item_index,
            old_g=old_amount,
            new_count=edit.new_count,
            new_unit=edit.new_unit,
        )

        if item["food_id"] is not None:
            # DB item — recalculate via tool with the new (count, unit) and
            # the parser's amount_g safety net for unknown units.
            macros = await calculate_food_macros.ainvoke(
                {
                    "food_id": item["food_id"],
                    "count": edit.new_count,
                    "unit": edit.new_unit,
                    "llm_estimated_amount_g": edit.new_amount_g,
                }
            )
            if "error" not in macros:
                item["amount_g"] = macros["amount_g"]
                item["calories"] = macros["calories"]
                item["protein"] = macros["protein"]
                item["carbs"] = macros["carbs"]
                item["fat"] = macros["fat"]
                item["servings"] = macros.get("servings")
                item["original_count"] = edit.new_count
                item["original_unit"] = edit.new_unit
            else:
                edit_errors.append(_surface_edit_error(item, edit, macros["error"]))
        else:
            # Estimated item — no FoodItem row to look up. Resolve new grams
            # via the same chain: explicit grams → confirmation parser estimate
            # → proportional scale from original (only when unit is unchanged).
            if edit.new_unit == "g":
                new_grams = edit.new_count
            elif edit.new_amount_g is not None:
                new_grams = edit.new_amount_g
            elif (
                edit.new_unit == item.get("original_unit")
                and item["original_count"] > 0
            ):
                # Same unit as original — scale proportionally from per-unit gram weight.
                new_grams = (item["amount_g"] / item["original_count"]) * edit.new_count
            else:
                edit_errors.append(
                    _surface_edit_error(
                        item,
                        edit,
                        "Could not resolve unit for estimated item",
                    )
                )
                continue

            if old_amount > 0:
                ratio = new_grams / old_amount
                item["amount_g"] = new_grams
                item["calories"] = round(item["calories"] * ratio, 1)
                item["protein"] = round(item["protein"] * ratio, 1)
                item["carbs"] = round(item["carbs"] * ratio, 1)
                item["fat"] = round(item["fat"] * ratio, 1)
                item["original_count"] = edit.new_count
                item["original_unit"] = edit.new_unit

    return batch, edit_errors
