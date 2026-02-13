from src.agents.state import AgentState


def calculate_log_node(state: AgentState) -> dict:
    """Calculate macros and log to database.

    Processes the first item in pending_food_items:
    1. Looks up food by selected_food_id
    2. Calculates macros based on amount
    3. Logs entry to DailyLog table
    4. Removes processed item from pending list

    TODO: Implement actual calculation and database persistence.
    For now, just removes processed item from pending list.
    """
    pending_items = state.get("pending_food_items", [])

    if not pending_items:
        return {}

    # Remove first item (processed)
    remaining_items = pending_items[1:]

    return {
        "pending_food_items": remaining_items,
        "last_action": "LOGGED",
    }
