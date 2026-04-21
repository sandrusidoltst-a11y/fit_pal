"""Service layer for FoodItem + CoachFoodMapping CRUD and macro calculation.

Provides async functions for searching food items (bilingual), fetching by ID
joined with a coach's overlay, computing macros for a given amount, and creating
new food entries (optionally with a coach mapping). All service functions accept
an explicit SQLAlchemy AsyncSession for testability.

Also provides @tool wrappers (search_food, calculate_food_macros, create_food_item)
that own their own session — used by graph nodes and LLM tool-calling.
"""

import uuid as uuid_mod
from typing import Optional, Tuple

import structlog
from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import DEFAULT_COACH_ID
from src.database import get_async_db_session
from src.models import CoachFoodMapping, FoodItem

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers — no DB, no I/O
# ---------------------------------------------------------------------------

def resolve_amount_g(food: FoodItem, unit: str, count: float) -> float:
    """Convert a (unit, count) tuple to grams using the food's unit definition.

    - unit == "g": count is already grams → return count
    - food has no default_unit/weight: fall back to treating count as grams
    - unit matches food.default_unit: return count * food.default_unit_weight_g
    - unit mismatch: raise ValueError (caller handles as FAILED processing result)
    """
    if unit == "g":
        return count
    if food.default_unit is None or food.default_unit_weight_g is None:
        return count
    if unit != food.default_unit:
        raise ValueError(
            f"Unit mismatch: user gave {unit!r}, food {food.name_en!r} expects {food.default_unit!r}"
        )
    return count * food.default_unit_weight_g


def compute_servings(amount_g: float, serving_amount_g: Optional[float]) -> Optional[float]:
    """Compute serving count from grams; None when the food has no serving definition.

    None semantics: free veggies, forbidden_main foods — serving concept doesn't apply.
    """
    if serving_amount_g is None or serving_amount_g == 0:
        return None
    return round(amount_g / serving_amount_g, 2)


def compute_food_macros(
    food: FoodItem,
    mapping: Optional[CoachFoodMapping],
    amount_g: float,
) -> dict:
    """Pure macro calculation + mapping enrichment. No DB, no I/O.

    Returns the shape consumed by tools and nodes downstream.
    """
    ratio = amount_g / 100.0
    return {
        "id": str(food.id),
        "name_en": food.name_en,
        "name_he": food.name_he,
        "source": food.source,
        "amount_g": amount_g,
        "calories": round((food.calories or 0.0) * ratio, 2),
        "protein": round((food.protein or 0.0) * ratio, 2),
        "fat": round((food.fat or 0.0) * ratio, 2),
        "carbs": round((food.carbs or 0.0) * ratio, 2),
        "default_unit": food.default_unit,
        "default_unit_weight_g": food.default_unit_weight_g,
        "category": mapping.category if mapping else None,
        "tag": mapping.tag if mapping else None,
        "serving_amount_g": mapping.serving_amount_g if mapping else None,
        "servings": compute_servings(
            amount_g, mapping.serving_amount_g if mapping else None
        ),
    }


# ---------------------------------------------------------------------------
# Service functions — accept session, return ORM objects or tuples
# ---------------------------------------------------------------------------

async def search_food_items(
    session: AsyncSession,
    query: str,
    user_id: str,
    coach_id: uuid_mod.UUID = DEFAULT_COACH_ID,
) -> list[Tuple[FoodItem, Optional[CoachFoodMapping]]]:
    """Search food items by name (bilingual: EN or HE). Two-tier:
    1. Shared database foods first.
    2. User-scoped estimated foods as fallback.

    Each result tuple is (FoodItem, Optional[CoachFoodMapping]) — mapping is
    scoped to the given coach_id; None if the food has no mapping for that coach.
    """
    name_filter = FoodItem.name_en.ilike(f"%{query}%") | FoodItem.name_he.ilike(f"%{query}%")

    # Tier 1: shared database
    stmt_db = (
        select(FoodItem, CoachFoodMapping)
        .outerjoin(
            CoachFoodMapping,
            (CoachFoodMapping.food_id == FoodItem.id)
            & (CoachFoodMapping.coach_id == coach_id),
        )
        .where(name_filter & (FoodItem.source == "database"))
        .limit(10)
    )
    rows = (await session.execute(stmt_db)).all()
    if rows:
        logger.debug(
            "search_food_items matched database tier",
            query=query,
            matched=len(rows),
            with_mapping=sum(1 for r in rows if r[1] is not None),
        )
        return [(r[0], r[1]) for r in rows]

    # Tier 2: user-scoped estimated
    stmt_est = (
        select(FoodItem, CoachFoodMapping)
        .outerjoin(
            CoachFoodMapping,
            (CoachFoodMapping.food_id == FoodItem.id)
            & (CoachFoodMapping.coach_id == coach_id),
        )
        .where(
            name_filter
            & (FoodItem.source == "estimated")
            & (FoodItem.user_id == uuid_mod.UUID(user_id))
        )
        .limit(10)
    )
    rows = (await session.execute(stmt_est)).all()
    logger.debug(
        "search_food_items matched estimated tier",
        query=query,
        matched=len(rows),
        with_mapping=sum(1 for r in rows if r[1] is not None),
    )
    return [(r[0], r[1]) for r in rows]


async def get_food_by_id(
    session: AsyncSession,
    food_id: str,
    coach_id: uuid_mod.UUID = DEFAULT_COACH_ID,
) -> Optional[Tuple[FoodItem, Optional[CoachFoodMapping]]]:
    """Fetch a single FoodItem by UUID string, joined with its coach mapping
    (if any) for the given coach_id. Returns None if food not found.
    """
    stmt = (
        select(FoodItem, CoachFoodMapping)
        .outerjoin(
            CoachFoodMapping,
            (CoachFoodMapping.food_id == FoodItem.id)
            & (CoachFoodMapping.coach_id == coach_id),
        )
        .where(FoodItem.id == uuid_mod.UUID(food_id))
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return (row[0], row[1])


async def create_food_item_record(
    session: AsyncSession,
    name_en: str,
    name_he: Optional[str],
    calories_per_100g: float,
    protein_per_100g: float,
    carbs_per_100g: float,
    fat_per_100g: float,
    user_id: str,
    default_unit: Optional[str] = None,
    default_unit_weight_g: Optional[float] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    serving_amount_g: Optional[float] = None,
    source: str = "estimated",
    coach_id: uuid_mod.UUID = DEFAULT_COACH_ID,
) -> Tuple[FoodItem, Optional[CoachFoodMapping]]:
    """Create a FoodItem. If ``category`` is provided, also create the paired
    CoachFoodMapping row atomically in the same transaction.

    Returns (FoodItem, Optional[CoachFoodMapping]).
    """
    food_item = FoodItem(
        name_en=name_en,
        name_he=name_he,
        calories=calories_per_100g,
        protein=protein_per_100g,
        fat=fat_per_100g,
        carbs=carbs_per_100g,
        default_unit=default_unit,
        default_unit_weight_g=default_unit_weight_g,
        source=source,
        user_id=uuid_mod.UUID(user_id) if user_id else None,
    )
    session.add(food_item)
    await session.flush()  # make food_item.id available for the mapping FK

    mapping: Optional[CoachFoodMapping] = None
    if category is not None:
        mapping = CoachFoodMapping(
            food_id=food_item.id,
            coach_id=coach_id,
            category=category,
            tag=tag,
            serving_amount_g=serving_amount_g,
        )
        session.add(mapping)

    await session.commit()
    await session.refresh(food_item)
    if mapping is not None:
        await session.refresh(mapping)

    return (food_item, mapping)


# ---------------------------------------------------------------------------
# @tool wrappers — own their session, used by graph nodes and LLM tool-calling
# ---------------------------------------------------------------------------


def _serialize_food_candidate(
    food: FoodItem, mapping: Optional[CoachFoodMapping]
) -> dict:
    """Convert (FoodItem, Optional[CoachFoodMapping]) tuple into a minimal
    JSON-safe candidate dict for selection_node.

    Intentionally omits serving_amount_g / default_unit / default_unit_weight_g:
    selection doesn't use them, and calculate_food_macros fetches them fresh
    via get_food_by_id.
    """
    return {
        "id": str(food.id),
        "name_en": food.name_en,
        "name_he": food.name_he,
        "source": food.source,
        "category": mapping.category if mapping else None,
        "tag": mapping.tag if mapping else None,
    }


@tool
async def search_food(query: str, user_id: str) -> list[dict]:
    """Search for food items by name (bilingual — Hebrew or English).

    Returns a list of candidates with id, name_en, name_he, source, category, tag.
    Database foods first, then estimated fallback. Use this to find the correct
    food_id before calculating macros.
    """
    async with get_async_db_session() as session:
        results = await search_food_items(session, query, user_id)
        if results:
            first_food, first_mapping = results[0]
            logger.debug(
                "search_food matched",
                query=query,
                matched=len(results),
                tier=first_food.source,
                first_has_mapping=first_mapping is not None,
            )
        else:
            logger.info("search_food no results from DB or estimated foods", query=query)
        return [_serialize_food_candidate(food, mapping) for food, mapping in results]


@tool
async def calculate_food_macros(food_id: str, count: float, unit: str = "g") -> dict:
    """Calculate nutritional values + coach mapping fields for a food item at a given (count, unit).

    Resolves (count, unit) to grams internally via resolve_amount_g — unit="g"
    always passes through; any other unit must match the food's configured
    default_unit, otherwise returns ``{"error": "Unit mismatch: ..."}``.

    Returns a dict with: name_en, name_he, amount_g (resolved), calories, protein,
    fat, carbs, source, category, tag, serving_amount_g, servings, default_unit,
    default_unit_weight_g. Returns ``{"error": "..."}`` if food is not found or
    unit resolution fails.
    """
    async with get_async_db_session() as session:
        result = await get_food_by_id(session, food_id)
        if result is None:
            logger.warning("calculate_food_macros: food not found", food_id=food_id)
            return {"error": f"Food item with ID {food_id} not found"}
        food, mapping = result
        try:
            amount_g = resolve_amount_g(food, unit, count)
        except ValueError as e:
            logger.warning(
                "calculate_food_macros: unit resolution failed",
                food_id=food_id, food=food.name_en, unit=unit, count=count,
            )
            return {"error": str(e)}
        return compute_food_macros(food, mapping, amount_g)


@tool
async def create_food_item(
    name_en: str,
    calories_per_100g: float,
    protein_per_100g: float,
    carbs_per_100g: float,
    fat_per_100g: float,
    user_id: str,
    name_he: Optional[str] = None,
    default_unit: Optional[str] = None,
    default_unit_weight_g: Optional[float] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    serving_amount_g: Optional[float] = None,
    source: str = "estimated",
) -> dict:
    """Create a new FoodItem (optionally with a coach mapping).

    If ``category`` is provided, a paired coach_food_mappings row is also created
    atomically. Returns the created item's id, name_en, name_he, and whether a
    mapping was created.
    """
    async with get_async_db_session() as session:
        food, mapping = await create_food_item_record(
            session=session,
            name_en=name_en,
            name_he=name_he,
            calories_per_100g=calories_per_100g,
            protein_per_100g=protein_per_100g,
            carbs_per_100g=carbs_per_100g,
            fat_per_100g=fat_per_100g,
            user_id=user_id,
            default_unit=default_unit,
            default_unit_weight_g=default_unit_weight_g,
            category=category,
            tag=tag,
            serving_amount_g=serving_amount_g,
            source=source,
        )
        logger.info(
            "Created food item",
            name_en=name_en,
            name_he=name_he,
            food_id=str(food.id),
            source=source,
            mapping_created=mapping is not None,
        )
        return {
            "id": str(food.id),
            "name_en": food.name_en,
            "name_he": food.name_he,
            "mapping_created": mapping is not None,
        }
