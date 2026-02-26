from datetime import datetime, timezone

from src.agents.state import AgentState
from src.database import get_async_db_session
from src.services import daily_log_service
from src.tools.food_lookup import calculate_food_macros


async def calculate_log_node(state: AgentState) -> dict:
    """Calculate macros and log to database.

    Processes the first item in pending_food_items:
    1. Looks up food by selected_food_id
    2. Calculates macros based on amount
    3. Logs entry to DailyLog table
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
        
        # Calculate macros
        macros = calculate_food_macros.invoke({"food_id": selected_food_id, "amount_g": amount})
        
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

            async with get_async_db_session() as session:
                await daily_log_service.create_log_entry(
                    session=session,
                    food_id=selected_food_id,
                    amount_g=amount,
                    calories=macros["calories"],
                    protein=macros["protein"],
                    carbs=macros["carbs"],
                    fat=macros["fat"],
                    timestamp=timestamp,
                    original_text=current_item.get("original_text")
                )
                
                # Fetch updated logs for report
                updated_report = []
                if consumed_at:
                    logs = await daily_log_service.get_logs_by_date(session, consumed_at.date())
                    for log in logs:
                        updated_report.append({
                            "id": log.id,
                            "food_id": log.food_id,
                            "amount_g": log.amount_g,
                            "calories": log.calories,
                            "protein": log.protein,
                            "carbs": log.carbs,
                            "fat": log.fat,
                            "timestamp": log.timestamp,
                            "meal_type": log.meal_type,
                            "original_text": log.original_text,
                        })

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
