from src.agents.state import AgentState
from src.tools.food_lookup import search_food


def food_search_node(state: AgentState) -> dict:
    """
    Search for food items based on pending_food_items.

    Calls search_food tool for the first pending item and
    populates search_results in state.
    """
    pending_items = state.get("pending_food_items", [])

    if not pending_items:
        return {"search_results": []}

    # Search for first pending item
    first_item = pending_items[0]
    food_name = first_item.get("food_name", "")

    # Call search_food tool
    results = search_food.invoke({"query": food_name})

    return {"search_results": results}
