"""Service layer for FoodItem CRUD and macro calculation.

Provides async functions for searching food items, fetching by ID, computing
macros for a given amount, and creating new food entries. All service functions
accept an explicit SQLAlchemy AsyncSession for testability.

Also provides @tool wrappers (search_food, calculate_food_macros, create_food_item)
that own their own session — these are used by graph nodes and are available
for LLM tool-calling.
"""

import uuid as uuid_mod
from typing import Optional

import structlog
from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_db_session
from src.models import FoodItem

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers — no DB, no I/O
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Service functions — accept session, return ORM objects or primitives
# ---------------------------------------------------------------------------

async def search_food_items(
    session: AsyncSession,
    query: str,
    user_id: str,
) -> list[FoodItem]:
    """Search food items by name. Two-tier: shared database foods first,
    then user-scoped estimated foods as fallback.

    Returns up to 10 FoodItem rows. Empty list if no matches.
    """
    # First: search shared database foods (no user filter)
    stmt = (
        select(FoodItem)
        .where(FoodItem.name.ilike(f"%{query}%"), FoodItem.source == "database")
        .limit(10)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if rows:
        return list(rows)

    # Fallback: search THIS USER's estimated foods
    stmt = (
        select(FoodItem)
        .where(
            FoodItem.name.ilike(f"%{query}%"),
            FoodItem.source == "estimated",
            FoodItem.user_id == uuid_mod.UUID(user_id),
        )
        .limit(10)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def get_food_by_id(
    session: AsyncSession,
    food_id: str,
) -> Optional[FoodItem]:
    """Fetch a single FoodItem by UUID string. Returns None if not found."""
    return await session.get(FoodItem, uuid_mod.UUID(food_id))


async def create_food_item_record(
    session: AsyncSession,
    name: str,
    calories_per_100g: float,
    protein_per_100g: float,
    carbs_per_100g: float,
    fat_per_100g: float,
    user_id: str,
    source: str = "estimated",
) -> FoodItem:
    """Create and persist a new FoodItem row. Commits the session."""
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
    return food_item


# ---------------------------------------------------------------------------
# @tool wrappers — own their session, used by graph nodes and LLM tool-calling
# ---------------------------------------------------------------------------

@tool
async def search_food(query: str, user_id: str) -> list[dict]:
    """
    Search for food items by name.
    Returns a list of candidates with ID, Name, and source.
    Searches database foods first, then falls back to estimated foods.
    Use this to find the correct food_id before calculating macros.
    """
    async with get_async_db_session() as session:
        items = await search_food_items(session, query, user_id)
        if items:
            logger.debug(
                "search_food matched",
                query=query,
                matched=len(items),
                source=items[0].source,
            )
        else:
            logger.info("search_food no results from DB or estimated foods", query=query)
        return [{"id": str(i.id), "name": i.name, "source": i.source} for i in items]


@tool
async def calculate_food_macros(food_id: str, amount_g: float) -> dict:
    """
    Calculate nutritional values for a specific food item and amount (in grams).
    Returns dictionary with Name, Calories, Protein, Fat, Carbs.
    """
    async with get_async_db_session() as session:
        food = await get_food_by_id(session, food_id)
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
    user_id: str = "",
) -> dict:
    """Create a new FoodItem in the database. Returns the created item's id and name."""
    async with get_async_db_session() as session:
        food_item = await create_food_item_record(
            session=session,
            name=name,
            calories_per_100g=calories_per_100g,
            protein_per_100g=protein_per_100g,
            carbs_per_100g=carbs_per_100g,
            fat_per_100g=fat_per_100g,
            user_id=user_id,
            source=source,
        )
        logger.info(
            "Created food item",
            name=name,
            food_id=str(food_item.id),
            source=source,
        )
        return {"id": str(food_item.id), "name": food_item.name}
