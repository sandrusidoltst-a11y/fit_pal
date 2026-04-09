import structlog
from langgraph.runtime import Runtime

from src.agents.state import AgentState
from src.context import ContextSchema
from src.services.food_service import search_food

logger = structlog.get_logger(__name__)


async def food_search_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    """
    Search for food items based on pending_food_items.

    Calls search_food tool for the first pending item and
    populates search_results in state.
    """
    pending_items = state.get("pending_food_items", [])

    if not pending_items:
        logger.warning("food_search_node called with empty pending_food_items")
        return {"search_results": []}

    # Search for first pending item
    first_item = pending_items[0]
    food_name = first_item.get("food_name", "")

    # Call search_food tool (async)
    user_id = runtime.context.user_id
    results = await search_food.ainvoke({"query": food_name, "user_id": user_id})

    return {"search_results": results}
