import os
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, interrupt

from src.agents.state import AgentState, MacroResult
from src.config import BASE_DIR, get_llm_for_node
from src.schemas.confirmation_schema import ConfirmationResponse
from src.tools.food_lookup import calculate_food_macros


def _format_batch_preview(items: list[MacroResult]) -> dict:
    """Build human-readable batch preview payload for interrupt."""
    formatted_items = []
    for i, item in enumerate(items):
        source_tag = " (estimated)" if item["source"] == "estimated" else ""
        formatted_items.append(
            {
                "index": i,
                "description": f"{item['food_name']} — {item['amount_g']}g{source_tag}",
                "calories": item["calories"],
                "protein": item["protein"],
                "carbs": item["carbs"],
                "fat": item["fat"],
                "source": item["source"],
            }
        )

    totals = {
        "calories": round(sum(it["calories"] for it in items), 1),
        "protein": round(sum(it["protein"] for it in items), 1),
        "carbs": round(sum(it["carbs"] for it in items), 1),
        "fat": round(sum(it["fat"] for it in items), 1),
    }

    return {
        "question": "Please review the following items before I log them. You can confirm, reject, or edit specific items.",
        "items": formatted_items,
        "totals": totals,
    }


async def confirmation_node(
    state: AgentState, config: RunnableConfig,
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
        return Command(goto="response")

    preview = _format_batch_preview(batch)

    while True:
        user_response = interrupt(preview)

        # Parse user response with LLM
        decision = await _parse_confirmation(user_response, batch)

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
                        "food_name": item["food_name"],
                        "amount": item["amount_g"],
                        "unit": "g",
                        "original_text": item["original_text"],
                        "status": "FAILED",
                        "message": f"User rejected logging {item['food_name']}",
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
            batch = await _apply_edits(batch, decision.edits or [], config)
            # Re-build preview with updated batch
            preview = _format_batch_preview(batch)
            # Loop continues → interrupt again with updated preview


async def _parse_confirmation(
    user_text: str, batch: list[MacroResult]
) -> ConfirmationResponse:
    """Use LLM to parse user's natural language confirmation response."""
    prompt_path = os.path.join(BASE_DIR, "prompts", "confirmation_parser.md")
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        system_prompt = (
            "Parse the user's response to a food logging confirmation prompt."
        )

    # Build batch context for the prompt
    batch_context = "\n".join(
        f"[{i}] {item['food_name']} — {item['amount_g']}g ({item['source']})"
        for i, item in enumerate(batch)
    )
    system_prompt = system_prompt.replace("{batch_context}", batch_context)

    llm = get_llm_for_node("confirmation_node")
    structured_llm = llm.with_structured_output(ConfirmationResponse)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_text),
    ]

    return await structured_llm.ainvoke(messages)


async def _apply_edits(
    batch: list[MacroResult], edits: list, config: RunnableConfig,
) -> list[MacroResult]:
    """Apply user edits to the batch. Recalculate macros for amount changes."""
    # Process removals in reverse order to preserve indices
    remove_indices = sorted(
        [e.item_index for e in edits if e.edit_type == "remove"],
        reverse=True,
    )
    for idx in remove_indices:
        if 0 <= idx < len(batch):
            batch.pop(idx)

    # Process amount changes
    for edit in edits:
        if edit.edit_type == "change_amount" and edit.new_amount_g is not None:
            if 0 <= edit.item_index < len(batch):
                item = batch[edit.item_index]
                old_amount = item["amount_g"]
                new_amount = edit.new_amount_g

                if item["food_id"] is not None:
                    # DB item — recalculate via tool
                    macros = await calculate_food_macros.ainvoke(
                        {"food_id": item["food_id"], "amount_g": new_amount}, config=config
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
