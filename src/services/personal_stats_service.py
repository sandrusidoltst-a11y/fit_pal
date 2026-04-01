"""Personal stats service for body measurement logging.

Provides async functions for creating and querying personal stats entries
(weight, body fat %). Follows the service + tool dual-layer pattern:
core functions accept an explicit AsyncSession, @tool wrappers own their session.
"""

import uuid as uuid_mod
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_user_id
from src.database import get_async_db_session
from src.models import PersonalStatsLog

logger = structlog.get_logger(__name__)


async def create_stat_entry(
    session: AsyncSession,
    user_id: str,
    weight_kg: Optional[float] = None,
    body_fat_pct: Optional[float] = None,
    recorded_at: Optional[datetime] = None,
) -> PersonalStatsLog:
    """Create and persist a new personal stats log entry.

    Args:
        session: Active async database session.
        user_id: The user ID string (UUID format).
        weight_kg: Body weight in kilograms (optional).
        body_fat_pct: Body fat percentage (optional).
        recorded_at: When the measurement was taken (defaults to now UTC).

    Returns:
        The created PersonalStatsLog instance.
    """
    if recorded_at is None:
        recorded_at = datetime.now(timezone.utc)

    entry = PersonalStatsLog(
        user_id=uuid_mod.UUID(user_id),
        weight_kg=weight_kg,
        body_fat_pct=body_fat_pct,
        recorded_at=recorded_at,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    logger.info(
        "Personal stat logged",
        user_id=user_id,
        weight_kg=weight_kg,
        body_fat_pct=body_fat_pct,
    )
    return entry


async def get_latest_stats(
    session: AsyncSession,
    user_id: str,
) -> Optional[dict]:
    """Get the most recent stats entry for a user."""
    stmt = (
        select(PersonalStatsLog)
        .where(PersonalStatsLog.user_id == uuid_mod.UUID(user_id))
        .order_by(PersonalStatsLog.recorded_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    return _serialize_stat(entry)


async def get_stat_history(
    session: AsyncSession,
    user_id: str,
    stat_type: str = "weight",
    limit: int = 30,
) -> List[dict]:
    """Get stat history for a user, ordered by most recent first.

    Args:
        session: Active async database session.
        user_id: The user ID string (UUID format).
        stat_type: "weight" or "body_fat" — filters out entries where that column is null.
        limit: Maximum number of entries to return.

    Returns:
        List of stat dicts ordered by recorded_at descending.
    """
    column = PersonalStatsLog.weight_kg if stat_type == "weight" else PersonalStatsLog.body_fat_pct
    stmt = (
        select(PersonalStatsLog)
        .where(
            PersonalStatsLog.user_id == uuid_mod.UUID(user_id),
            column.isnot(None),
        )
        .order_by(PersonalStatsLog.recorded_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    entries = result.scalars().all()
    return [_serialize_stat(e) for e in entries]


def _serialize_stat(entry: PersonalStatsLog) -> dict:
    """Convert a PersonalStatsLog ORM object to a JSON-serializable dict."""
    return {
        "id": str(entry.id),
        "weight_kg": entry.weight_kg,
        "body_fat_pct": entry.body_fat_pct,
        "recorded_at": entry.recorded_at.isoformat() if entry.recorded_at else None,
    }


# ---------------------------------------------------------------------------
# @tool wrappers — own their session, used by graph nodes
# ---------------------------------------------------------------------------


@tool
async def log_personal_stat(
    stat_type: str,
    value: float,
    config: RunnableConfig = None,
) -> dict:
    """Log a personal body measurement (weight or body fat).

    Args:
        stat_type: "weight" for body weight in kg, "body_fat" for body fat percentage.
        value: The numeric value of the measurement.
    """
    user_id = get_user_id(config)
    weight_kg = value if stat_type == "weight" else None
    body_fat_pct = value if stat_type == "body_fat" else None

    async with get_async_db_session() as session:
        entry = await create_stat_entry(
            session=session,
            user_id=user_id,
            weight_kg=weight_kg,
            body_fat_pct=body_fat_pct,
        )
        return {"id": str(entry.id), "status": "logged", "stat_type": stat_type, "value": value}


@tool
async def get_latest_personal_stats(
    config: RunnableConfig = None,
) -> dict:
    """Get the most recent body measurements for the user.

    Returns the latest recorded weight and/or body fat percentage,
    or a message indicating no stats have been logged yet.
    """
    user_id = get_user_id(config)
    async with get_async_db_session() as session:
        latest = await get_latest_stats(session, user_id)
        if latest is None:
            return {"status": "no_stats", "message": "No body measurements logged yet."}
        logger.debug("Fetched latest stats", user_id=user_id, stats=latest)
        return latest


@tool
async def get_personal_stat_history(
    stat_type: str = "weight",
    limit: int = 30,
    config: RunnableConfig = None,
) -> list[dict]:
    """Get history of personal body measurements.

    Args:
        stat_type: "weight" or "body_fat".
        limit: Maximum number of entries to return.
    """
    user_id = get_user_id(config)
    async with get_async_db_session() as session:
        history = await get_stat_history(session, user_id, stat_type, limit)
        logger.debug("Queried stat history", user_id=user_id, stat_type=stat_type, results=len(history))
        return history
