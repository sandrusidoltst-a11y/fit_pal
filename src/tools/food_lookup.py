from langchain_core.tools import tool
from sqlalchemy import select
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
async def search_food(query: str) -> list[dict]:
    """
    Search for food items by name.
    Returns a list of candidates with ID, Name, and source.
    Searches database foods first, then falls back to estimated foods.
    Use this to find the correct food_id before calculating macros.
    """
    async with get_async_db_session() as session:
        # First: search database foods
        stmt = (
            select(FoodItem.id, FoodItem.name)
            .where(FoodItem.name.ilike(f"%{query}%"), FoodItem.source == "database")
            .limit(10)
        )
        results = (await session.execute(stmt)).all()
        if results:
            return [{"id": r.id, "name": r.name, "source": "database"} for r in results]

        # Fallback: search estimated foods
        stmt = (
            select(FoodItem.id, FoodItem.name)
            .where(FoodItem.name.ilike(f"%{query}%"), FoodItem.source == "estimated")
            .limit(10)
        )
        results = (await session.execute(stmt)).all()
        return [{"id": r.id, "name": r.name, "source": "estimated"} for r in results]


@tool
async def calculate_food_macros(food_id: int, amount_g: float) -> dict:
    """
    Calculate nutritional values for a specific food item and amount (in grams).
    Returns dictionary with Name, Calories, Protein, Fat, Carbs.
    """
    async with get_async_db_session() as session:
        food = await session.get(FoodItem, food_id)
        if not food:
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
) -> dict:
    """Create a new FoodItem in the database. Returns the created item's id and name."""
    async with get_async_db_session() as session:
        food_item = FoodItem(
            name=name,
            calories=calories_per_100g,
            protein=protein_per_100g,
            fat=fat_per_100g,
            carbs=carbs_per_100g,
            source=source,
        )
        session.add(food_item)
        await session.commit()
        await session.refresh(food_item)
        return {"id": food_item.id, "name": food_item.name}
