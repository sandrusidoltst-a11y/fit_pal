from datetime import datetime, timezone

from src.agents.state import AgentState
from src.database import get_db_session
from src.services import daily_log_service
from src.tools.food_lookup import calculate_food_macros


def calculate_log_node(state: AgentState) -> dict:
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
    
    # Default to current totals if something fails
    updated_totals = state.get("daily_totals")

    # Only process if we have a valid selection
    if selected_food_id:
        amount = current_item.get("amount", 0.0)
        
        # Calculate macros
        macros = calculate_food_macros(selected_food_id, amount)
        
        if "error" not in macros:
            # Prepare timestamp
            current_date = state.get("current_date")
            now = datetime.now(timezone.utc)
            
            if current_date:
                # Use the state's date + current time
                timestamp = datetime.combine(current_date, now.time()).replace(tzinfo=timezone.utc)
            else:
                timestamp = now

            with get_db_session() as session:
                daily_log_service.create_log_entry(
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
                
                # Fetch updated totals
                if current_date:
                    updated_totals = daily_log_service.get_daily_totals(session, current_date)

    # Remove first item (processed)
    remaining_items = pending_items[1:]

    return {
        "pending_food_items": remaining_items,
        "daily_totals": updated_totals,
        "last_action": "LOGGED",
        "selected_food_id": None,  # Reset selection
    }
