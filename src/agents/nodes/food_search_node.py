from sqlalchemy import select

from src.agents.state import AgentState
from src.database import get_async_db_session
from src.models import FoodItem


async def food_search_node(state: AgentState) -> dict:
    """
    Search for food items based on pending_food_items.

    Queries the database directly (async) for the first pending item
    and populates search_results in state.
    """
    pending_items = state.get("pending_food_items", [])

    if not pending_items:
        return {"search_results": []}

    # Search for first pending item
    first_item = pending_items[0]
    food_name = first_item.get("food_name", "")

    async with get_async_db_session() as session:
        stmt = (
            select(FoodItem.id, FoodItem.name)
            .where(FoodItem.name.ilike(f"%{food_name}%"))
            .limit(10)
        )
        rows = (await session.execute(stmt)).all()
        results = [{"id": r.id, "name": r.name} for r in rows]

    return {"search_results": results}
