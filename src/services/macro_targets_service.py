"""Macro targets service for the coach dashboard.

CRUD for structured numeric macro targets per trainee, split by training vs
rest day. Not exposed as LangGraph tools — the dashboard back-end calls these
directly (mirrors user_profile_service).
"""

import uuid as uuid_mod
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import MacroTarget

logger = structlog.get_logger(__name__)

VALID_DAY_TYPES = {"training", "rest"}


def _serialize_target(target: MacroTarget) -> dict:
    """Convert a MacroTarget ORM object to a JSON-serializable dict."""
    return {
        "id": str(target.id),
        "user_id": str(target.user_id),
        "day_type": target.day_type,
        "calories": target.calories,
        "protein_g": target.protein_g,
        "carbs_g": target.carbs_g,
        "fat_g": target.fat_g,
    }


async def set_macro_targets(
    session: AsyncSession,
    user_id: str,
    day_type: str,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
) -> dict:
    """Upsert the macro targets for a trainee's day_type.

    One row per (user_id, day_type): updates in place if it exists, else inserts.
    """
    if day_type not in VALID_DAY_TYPES:
        raise ValueError(f"day_type must be one of {sorted(VALID_DAY_TYPES)}, got {day_type!r}")

    stmt = select(MacroTarget).where(
        MacroTarget.user_id == uuid_mod.UUID(user_id),
        MacroTarget.day_type == day_type,
    )
    result = await session.execute(stmt)
    target = result.scalar_one_or_none()

    if target is None:
        target = MacroTarget(
            user_id=uuid_mod.UUID(user_id),
            day_type=day_type,
            calories=calories,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
        )
        session.add(target)
    else:
        target.calories = calories
        target.protein_g = protein_g
        target.carbs_g = carbs_g
        target.fat_g = fat_g

    await session.commit()
    await session.refresh(target)
    logger.info("Macro targets set", user_id=user_id, day_type=day_type)
    return _serialize_target(target)


async def get_macro_targets(session: AsyncSession, user_id: str) -> dict:
    """Return both day-type targets for a trainee.

    Returns ``{"training": {...} | None, "rest": {...} | None}``.
    """
    stmt = select(MacroTarget).where(MacroTarget.user_id == uuid_mod.UUID(user_id))
    result = await session.execute(stmt)
    targets = result.scalars().all()

    by_day_type: dict[str, Optional[dict]] = {"training": None, "rest": None}
    for target in targets:
        by_day_type[target.day_type] = _serialize_target(target)
    return by_day_type
