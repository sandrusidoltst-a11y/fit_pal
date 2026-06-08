"""Trainee routes for the coach dashboard API."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.dashboard.dependencies import get_current_coach_id, get_db_session
from src.services.coach_service import list_trainees_for_coach

router = APIRouter(prefix="/api/dashboard", tags=["trainees"])


@router.get("/trainees")
async def list_trainees(
    coach_id: str = Depends(get_current_coach_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """Return the authenticated coach's trainees."""
    return await list_trainees_for_coach(session, coach_id)
