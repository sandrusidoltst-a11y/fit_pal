"""User profile service for bot-level CRUD operations.

Handles creation and retrieval of user profiles during onboarding
and for config injection. Not exposed as LangGraph tools — the bot
accesses these directly.
"""

import uuid as uuid_mod
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import UserProfile

logger = structlog.get_logger(__name__)


async def create_user_profile(
    session: AsyncSession,
    user_id: str,
    name: str,
    height_cm: float,
    age: int,
    gender: str,
    nutrition_plan: Optional[str] = None,
) -> UserProfile:
    """Create a new user profile."""
    profile = UserProfile(
        user_id=uuid_mod.UUID(user_id),
        name=name,
        height_cm=height_cm,
        age=age,
        gender=gender,
        nutrition_plan=nutrition_plan,
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    logger.info("User profile created", user_id=user_id, name=name)
    return profile


async def set_nutrition_plan(
    session: AsyncSession,
    user_id: str,
    nutrition_plan: str,
) -> None:
    """Set or update the nutrition plan for a user."""
    stmt = select(UserProfile).where(UserProfile.user_id == uuid_mod.UUID(user_id))
    result = await session.execute(stmt)
    profile = result.scalar_one_or_none()
    if profile is None:
        raise ValueError(f"No profile found for user_id={user_id}")
    profile.nutrition_plan = nutrition_plan
    await session.commit()
    logger.info("Nutrition plan updated", user_id=user_id)


async def get_user_profile(
    session: AsyncSession,
    user_id: str,
) -> Optional[dict]:
    """Get user profile as a dict, or None if not found."""
    stmt = select(UserProfile).where(
        UserProfile.user_id == uuid_mod.UUID(user_id)
    )
    result = await session.execute(stmt)
    profile = result.scalar_one_or_none()
    if profile is None:
        return None
    return {
        "name": profile.name,
        "height_cm": profile.height_cm,
        "age": profile.age,
        "gender": profile.gender,
        "nutrition_plan": profile.nutrition_plan,
    }
