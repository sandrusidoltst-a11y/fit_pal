"""
Service layer for DailyLog CRUD operations.

Provides async functions for creating, querying, and aggregating daily food log entries.
All functions accept an explicit SQLAlchemy AsyncSession for testability.

Also provides @tool wrappers (log_food_entry, query_food_logs) that own their own
session — these are used by graph nodes and are available for LLM tool-calling.
"""

import uuid as uuid_mod
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import structlog
from langchain_core.tools import tool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import DEFAULT_COACH_ID, USER_TIMEZONE, serialize_timestamp
from src.database import get_async_db_session
from src.models import CoachFoodMapping, DailyLog

logger = structlog.get_logger(__name__)


async def create_log_entry(
    session: AsyncSession,
    user_id: str,
    food_id: Optional[str],
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
        user_id: The user ID string (UUID format).
        food_id: Foreign key to FoodItem (UUID string or None).
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
        user_id=uuid_mod.UUID(user_id),
        food_id=uuid_mod.UUID(food_id) if food_id else None,
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


async def get_daily_totals(session: AsyncSession, user_id: str, target_date: date) -> Dict[str, float]:
    """
    Aggregate nutritional totals for a specific date, scoped to a user.

    Args:
        session: Active async database session.
        user_id: The user ID string (UUID format).
        target_date: The date to aggregate totals for.

    Returns:
        Dict with keys: calories, protein, carbs, fat (all floats, default 0.0).
    """
    stmt = select(
        func.coalesce(func.sum(DailyLog.calories), 0.0).label("calories"),
        func.coalesce(func.sum(DailyLog.protein), 0.0).label("protein"),
        func.coalesce(func.sum(DailyLog.carbs), 0.0).label("carbs"),
        func.coalesce(func.sum(DailyLog.fat), 0.0).label("fat"),
    ).where(
        DailyLog.user_id == uuid_mod.UUID(user_id),
        func.date(DailyLog.timestamp) == target_date,
    )

    result = (await session.execute(stmt)).one()

    return {
        "calories": float(result.calories),
        "protein": float(result.protein),
        "carbs": float(result.carbs),
        "fat": float(result.fat),
    }


async def get_logs_by_date(session: AsyncSession, user_id: str, target_date: date) -> List[DailyLog]:
    """
    Retrieve all log entries for a specific date, scoped to a user.

    Args:
        session: Active async database session.
        user_id: The user ID string (UUID format).
        target_date: The date to query logs for.

    Returns:
        List of DailyLog objects for the given date, ordered by timestamp.
    """
    stmt = (
        select(DailyLog)
        .where(
            DailyLog.user_id == uuid_mod.UUID(user_id),
            func.date(DailyLog.timestamp) == target_date,
        )
        .order_by(DailyLog.timestamp)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_logs_by_date_with_mappings(
    session: AsyncSession,
    user_id: str,
    target_date: date,
    coach_id: uuid_mod.UUID = DEFAULT_COACH_ID,
) -> List[Tuple[DailyLog, Optional[CoachFoodMapping]]]:
    """Retrieve logs for a date, LEFT-joined with the coach's food mappings.

    Returns ``(DailyLog, Optional[CoachFoodMapping])`` tuples — the mapping is
    ``None`` when the log has no ``food_id`` (CASCADE SET NULL survivor) or when
    the food has no mapping for the given coach. Mirrors the LEFT JOIN pattern
    from ``search_food_items`` in ``food_service.py``.
    """
    stmt = (
        select(DailyLog, CoachFoodMapping)
        .outerjoin(
            CoachFoodMapping,
            (CoachFoodMapping.food_id == DailyLog.food_id)
            & (CoachFoodMapping.coach_id == coach_id),
        )
        .where(
            DailyLog.user_id == uuid_mod.UUID(user_id),
            func.date(DailyLog.timestamp) == target_date,
        )
        .order_by(DailyLog.timestamp)
    )
    rows = (await session.execute(stmt)).all()
    return [(r[0], r[1]) for r in rows]


async def get_logs_by_date_range(
    session: AsyncSession, user_id: str, start_date: date, end_date: date
) -> List[DailyLog]:
    """
    Retrieve all log entries within a date range (inclusive), scoped to a user.

    Args:
        session: Active async database session.
        user_id: The user ID string (UUID format).
        start_date: Start of the range (inclusive).
        end_date: End of the range (inclusive).

    Returns:
        List of DailyLog objects within the range, ordered by timestamp.
    """
    stmt = (
        select(DailyLog)
        .where(
            DailyLog.user_id == uuid_mod.UUID(user_id),
            func.date(DailyLog.timestamp) >= start_date,
            func.date(DailyLog.timestamp) <= end_date,
        )
        .order_by(DailyLog.timestamp)
    )
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# @tool wrappers — own their session, used by graph nodes and LLM tool-calling
# ---------------------------------------------------------------------------

def _serialize_log(
    log: DailyLog, mapping: Optional[CoachFoodMapping] = None
) -> dict:
    """Convert a DailyLog ORM object to a JSON-serializable dict.

    Timestamps are stored UTC in Postgres; we emit them in the user's local
    timezone so downstream consumers (LLM, response_node, stats_node) read
    the time the user actually experienced. See bot UX audit F2 / Bug 2.

    When ``mapping`` is provided (via ``get_logs_by_date_with_mappings``), the
    returned dict carries ``category``, ``tag``, and ``serving_amount_g``
    fields so the response-node renderer can surface coach-method metadata
    to the LLM. When ``mapping`` is ``None`` (legacy callers, or logs without
    a coach mapping), the shape is unchanged from the pre-Plan-3d version.
    """
    ts_local = serialize_timestamp(log.timestamp)
    serialized = {
        "id": str(log.id),
        "food_id": str(log.food_id) if log.food_id else None,
        "amount_g": log.amount_g,
        "calories": log.calories,
        "protein": log.protein,
        "carbs": log.carbs,
        "fat": log.fat,
        "timestamp": ts_local,
        "meal_type": log.meal_type,
        "original_text": log.original_text,
    }
    if mapping is not None:
        serialized["category"] = mapping.category
        serialized["tag"] = mapping.tag
        serialized["serving_amount_g"] = mapping.serving_amount_g
    return serialized


async def get_todays_logs_serialized(
    session: AsyncSession, user_id: str
) -> list[dict]:
    """Return today's logs for a user (Israel local day), serialized for context injection.

    Encapsulates the 'today in Israel' date computation + serialization in one place
    so the bot gateway doesn't need to touch ORM objects or the private serializer.

    KNOWN LIMITATION: `get_logs_by_date` uses `func.date(timestamp) == target_date`
    which evaluates in the DB session's timezone (UTC on Supabase). Logs made
    00:00-03:00 Israel local time fall on the previous UTC date and are missed.
    Follow-up tracked in brain/TASKS.md (Bug 1 from bot UX audit 2026-04-17).
    """
    today = datetime.now(USER_TIMEZONE).date()
    rows = await get_logs_by_date_with_mappings(session, user_id, today)
    return [_serialize_log(log, mapping) for log, mapping in rows]


@tool
async def log_food_entry(
    food_id: Optional[str],
    amount_g: float,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    timestamp: str,
    original_text: str = "",
    user_id: str = "",
) -> dict:
    """Log a food entry to the daily log. Timestamp should be ISO format string."""
    parsed_ts = datetime.fromisoformat(timestamp)
    async with get_async_db_session() as session:
        log = await create_log_entry(
            session=session,
            user_id=user_id,
            food_id=food_id,
            amount_g=amount_g,
            calories=calories,
            protein=protein,
            carbs=carbs,
            fat=fat,
            timestamp=parsed_ts,
            original_text=original_text or None,
        )
        logger.info("Daily log created", log_id=str(log.id), user_id=user_id, calories=calories)
        return {"id": str(log.id), "status": "logged"}


@tool
async def query_food_logs(target_date: str, end_date: str = "", user_id: str = "") -> list[dict]:
    """Query food log entries by date or date range. Dates should be ISO format (YYYY-MM-DD)."""
    parsed_date = date.fromisoformat(target_date)
    async with get_async_db_session() as session:
        if end_date:
            parsed_end = date.fromisoformat(end_date)
            logs = await get_logs_by_date_range(session, user_id, parsed_date, parsed_end)
        else:
            logs = await get_logs_by_date(session, user_id, parsed_date)
        logger.debug("Queried food logs", user_id=user_id, date=target_date, results=len(logs))
        return [_serialize_log(log) for log in logs]
