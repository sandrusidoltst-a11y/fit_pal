"""
Service layer for DailyLog CRUD operations.

Provides async functions for creating, querying, and aggregating daily food log entries.
All functions accept an explicit SQLAlchemy AsyncSession for testability.

Also provides @tool wrappers (log_food_entry, query_food_logs) that own their own
session — these are used by graph nodes and are available for LLM tool-calling.
"""

from datetime import date, datetime
from typing import Dict, List, Optional

from langchain_core.tools import tool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_db_session
from src.models import DailyLog


async def create_log_entry(
    session: AsyncSession,
    food_id: int,
    amount_g: float,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    timestamp: datetime,
    meal_type: Optional[str] = None,
    original_text: Optional[str] = None,
) -> DailyLog:
    """
    Create and persist a new DailyLog entry.

    Args:
        session: Active async database session.
        food_id: Foreign key to FoodItem.
        amount_g: Quantity consumed in grams.
        calories: Calculated calories for the amount.
        protein: Calculated protein (g) for the amount.
        carbs: Calculated carbs (g) for the amount.
        fat: Calculated fat (g) for the amount.
        timestamp: When the food was consumed (UTC).
        meal_type: Optional meal type (breakfast/lunch/dinner/snack).
        original_text: Optional original user input text.

    Returns:
        The created DailyLog instance with populated id and audit fields.
    """
    log = DailyLog(
        food_id=food_id,
        amount_g=amount_g,
        calories=calories,
        protein=protein,
        carbs=carbs,
        fat=fat,
        timestamp=timestamp,
        meal_type=meal_type,
        original_text=original_text,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def get_daily_totals(session: AsyncSession, target_date: date) -> Dict[str, float]:
    """
    Aggregate nutritional totals for a specific date.

    Queries all DailyLog entries whose timestamp falls on target_date
    and returns summed macro values.

    Args:
        session: Active async database session.
        target_date: The date to aggregate totals for.

    Returns:
        Dict with keys: calories, protein, carbs, fat (all floats, default 0.0).
    """
    stmt = select(
        func.coalesce(func.sum(DailyLog.calories), 0.0).label("calories"),
        func.coalesce(func.sum(DailyLog.protein), 0.0).label("protein"),
        func.coalesce(func.sum(DailyLog.carbs), 0.0).label("carbs"),
        func.coalesce(func.sum(DailyLog.fat), 0.0).label("fat"),
    ).where(func.date(DailyLog.timestamp) == target_date)

    result = (await session.execute(stmt)).one()

    return {
        "calories": float(result.calories),
        "protein": float(result.protein),
        "carbs": float(result.carbs),
        "fat": float(result.fat),
    }


async def get_logs_by_date(session: AsyncSession, target_date: date) -> List[DailyLog]:
    """
    Retrieve all log entries for a specific date.

    Args:
        session: Active async database session.
        target_date: The date to query logs for.

    Returns:
        List of DailyLog objects for the given date, ordered by timestamp.
    """
    stmt = (
        select(DailyLog)
        .where(func.date(DailyLog.timestamp) == target_date)
        .order_by(DailyLog.timestamp)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_logs_by_date_range(
    session: AsyncSession, start_date: date, end_date: date
) -> List[DailyLog]:
    """
    Retrieve all log entries within a date range (inclusive).

    Args:
        session: Active async database session.
        start_date: Start of the range (inclusive).
        end_date: End of the range (inclusive).

    Returns:
        List of DailyLog objects within the range, ordered by timestamp.
    """
    stmt = (
        select(DailyLog)
        .where(func.date(DailyLog.timestamp) >= start_date)
        .where(func.date(DailyLog.timestamp) <= end_date)
        .order_by(DailyLog.timestamp)
    )
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# @tool wrappers — own their session, used by graph nodes and LLM tool-calling
# ---------------------------------------------------------------------------

def _serialize_log(log: DailyLog) -> dict:
    """Convert a DailyLog ORM object to a JSON-serializable dict."""
    return {
        "id": log.id,
        "food_id": log.food_id,
        "amount_g": log.amount_g,
        "calories": log.calories,
        "protein": log.protein,
        "carbs": log.carbs,
        "fat": log.fat,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "meal_type": log.meal_type,
        "original_text": log.original_text,
    }


@tool
async def log_food_entry(
    food_id: int,
    amount_g: float,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    timestamp: str,
    original_text: str = "",
) -> dict:
    """Log a food entry to the daily log. Timestamp should be ISO format string."""
    parsed_ts = datetime.fromisoformat(timestamp)
    async with get_async_db_session() as session:
        log = await create_log_entry(
            session=session,
            food_id=food_id,
            amount_g=amount_g,
            calories=calories,
            protein=protein,
            carbs=carbs,
            fat=fat,
            timestamp=parsed_ts,
            original_text=original_text or None,
        )
        return {"id": log.id, "status": "logged"}


@tool
async def query_food_logs(target_date: str, end_date: str = "") -> list[dict]:
    """Query food log entries by date or date range. Dates should be ISO format (YYYY-MM-DD)."""
    parsed_date = date.fromisoformat(target_date)
    async with get_async_db_session() as session:
        if end_date:
            parsed_end = date.fromisoformat(end_date)
            logs = await get_logs_by_date_range(session, parsed_date, parsed_end)
        else:
            logs = await get_logs_by_date(session, parsed_date)
        return [_serialize_log(log) for log in logs]
