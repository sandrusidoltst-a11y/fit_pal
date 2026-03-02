from datetime import datetime, timezone

from src.agents.state import AgentState
from src.services.daily_log_service import log_food_entry, query_food_logs
from src.tools.food_lookup import calculate_food_macros


async def calculate_log_node(state: AgentState) -> dict:
    """Calculate macros and log to database.

    Processes the first item in pending_food_items:
    1. Looks up food by selected_food_id via calculate_food_macros tool
    2. Logs entry via log_food_entry tool
    3. Fetches updated logs via query_food_logs tool
    4. Removes processed item from pending list
    """
    pending_items = state.get("pending_food_items", [])
    selected_food_id = state.get("selected_food_id")

    if not pending_items:
        return {}

    # Get first item
    current_item = pending_items[0]

    # Only process if we have a valid selection
    if selected_food_id:
        amount = current_item.get("amount", 0.0)

        # Calculate macros via tool
        macros = await calculate_food_macros.ainvoke({"food_id": selected_food_id, "amount_g": amount})

        if "error" not in macros:
            # Prepare timestamp
            consumed_at = state.get("consumed_at")
            now = datetime.now(timezone.utc)

            if consumed_at:
                # If naive, assume UTC for MVP.
                # TODO: Phase 2 - Update 12:00 PM default to accommodate timezone rollover edge cases.
                if consumed_at.tzinfo is None:
                    timestamp = consumed_at.replace(tzinfo=timezone.utc)
                else:
                    timestamp = consumed_at
            else:
                timestamp = now

            # Log entry via tool
            await log_food_entry.ainvoke({
                "food_id": selected_food_id,
                "amount_g": amount,
                "calories": macros["calories"],
                "protein": macros["protein"],
                "carbs": macros["carbs"],
                "fat": macros["fat"],
                "timestamp": timestamp.isoformat(),
                "original_text": current_item.get("original_text", ""),
            })

            # Fetch updated logs for report via tool
            updated_report = []
            if consumed_at:
                updated_report = await query_food_logs.ainvoke({"target_date": str(consumed_at.date())})

            # Create success result
            result_item = {
                **current_item,
                "status": "LOGGED",
                "message": f"Logged {current_item['food_name']} ({macros['calories']}kcal)"
            }

            # Append to existing results
            current_results = state.get("processing_results", [])
            updated_results = current_results + [result_item]

    # Remove first item (processed)
    remaining_items = pending_items[1:]

    return {
        "pending_food_items": remaining_items,
        "daily_log_report": updated_report if 'updated_report' in locals() else state.get("daily_log_report", []),
        "last_action": "LOGGED",
        "selected_food_id": None,  # Reset selection
        "processing_results": updated_results if 'updated_results' in locals() else state.get("processing_results", [])
    }
