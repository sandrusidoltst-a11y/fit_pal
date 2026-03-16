import uuid as uuid_mod

import structlog
from langchain_core.runnables import RunnableConfig

logger = structlog.get_logger(__name__)
from langchain_core.tools import tool
from sqlalchemy import select

from src.config import get_user_id
from src.database import get_async_db_session
from src.models import FoodItem


def compute_food_macros(food: FoodItem, amount_g: float) -> dict:
    """Pure macro calculation — no DB, no I/O."""
    ratio = amount_g / 100.0
    return {
        "name": food.name,
        "amount_g": amount_g,
        "calories": round((food.calories or 0.0) * ratio, 2),
        "protein": round((food.protein or 0.0) * ratio, 2),
        "fat": round((food.fat or 0.0) * ratio, 2),
        "carbs": round((food.carbs or 0.0) * ratio, 2),
    }


@tool
async def search_food(query: str, config: RunnableConfig) -> list[dict]:
    """
    Search for food items by name.
    Returns a list of candidates with ID, Name, and source.
    Searches database foods first, then falls back to estimated foods.
    Use this to find the correct food_id before calculating macros.
    """
    user_id = get_user_id(config)
    async with get_async_db_session() as session:
        # First: search shared database foods (no user filter)
        stmt = (
            select(FoodItem.id, FoodItem.name)
            .where(FoodItem.name.ilike(f"%{query}%"), FoodItem.source == "database")
            .limit(10)
        )
        results = (await session.execute(stmt)).all()
        if results:
            logger.debug("search_food matched", query=query, matched=len(results), source="database")
            return [{"id": str(r.id), "name": r.name, "source": "database"} for r in results]

        # Fallback: search THIS USER's estimated foods
        stmt = (
            select(FoodItem.id, FoodItem.name)
            .where(FoodItem.name.ilike(f"%{query}%"), FoodItem.source == "estimated")
            .where(FoodItem.user_id == uuid_mod.UUID(user_id))
            .limit(10)
        )
        results = (await session.execute(stmt)).all()
        if not results:
            logger.info("search_food no results from DB or estimated foods", query=query)
        return [{"id": str(r.id), "name": r.name, "source": "estimated"} for r in results]


@tool
async def calculate_food_macros(food_id: str, amount_g: float) -> dict:
    """
    Calculate nutritional values for a specific food item and amount (in grams).
    Returns dictionary with Name, Calories, Protein, Fat, Carbs.
    """
    async with get_async_db_session() as session:
        food = await session.get(FoodItem, uuid_mod.UUID(food_id))
        if not food:
            logger.warning("calculate_food_macros: food not found", food_id=food_id)
            return {"error": f"Food item with ID {food_id} not found"}
        result = compute_food_macros(food, amount_g)
        result["source"] = food.source
        return result


@tool
async def create_food_item(
    name: str,
    calories_per_100g: float,
    protein_per_100g: float,
    carbs_per_100g: float,
    fat_per_100g: float,
    source: str = "estimated",
    config: RunnableConfig = None,
) -> dict:
    """Create a new FoodItem in the database. Returns the created item's id and name."""
    user_id = get_user_id(config)
    async with get_async_db_session() as session:
        food_item = FoodItem(
            name=name,
            calories=calories_per_100g,
            protein=protein_per_100g,
            fat=fat_per_100g,
            carbs=carbs_per_100g,
            source=source,
            user_id=uuid_mod.UUID(user_id),
        )
        session.add(food_item)
        await session.commit()
        await session.refresh(food_item)
        logger.info("Created food item", name=name, food_id=str(food_item.id), source=source)
        return {"id": str(food_item.id), "name": food_item.name}
