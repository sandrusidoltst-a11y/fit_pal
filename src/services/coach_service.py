"""Coach service for the dashboard back-end.

Lists the trainees owned by a coach. Not exposed as LangGraph tools — the
dashboard back-end calls these directly (mirrors user_profile_service).
"""

import uuid as uuid_mod

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import UserProfile

logger = structlog.get_logger(__name__)


def _serialize_trainee(profile: UserProfile) -> dict:
    """Convert a UserProfile ORM object to a JSON-serializable trainee dict."""
    return {
        "user_id": str(profile.user_id),
        "name": profile.name,
        "height_cm": profile.height_cm,
        "age": profile.age,
        "gender": profile.gender,
        "nutrition_plan": profile.nutrition_plan,
    }


async def list_trainees_for_coach(session: AsyncSession, coach_id: str) -> list[dict]:
    """Return the profiles of all trainees owned by ``coach_id`` (empty list if none)."""
    stmt = select(UserProfile).where(UserProfile.coach_id == uuid_mod.UUID(coach_id))
    result = await session.execute(stmt)
    profiles = result.scalars().all()
    logger.debug("Listed trainees for coach", coach_id=coach_id, count=len(profiles))
    return [_serialize_trainee(p) for p in profiles]
