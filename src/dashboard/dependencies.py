"""FastAPI dependencies for the coach dashboard API.

Phase 1 is single-coach with no authentication (see
docs/plans/dashboard-phase-1-foundation.md, decision D1). ``get_current_coach_id``
is the deliberate seam where Supabase-JWT validation will plug in later — when it
does, only this function changes (decode the Bearer token, look up the coach,
return their id). Everything downstream already flows ``coach_id`` as a string.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import DEFAULT_COACH_ID
from src.database import get_async_db_session


def get_current_coach_id() -> str:
    """Return the acting coach's id.

    Phase 1 stub: always the single V1 coach (DEFAULT_COACH_ID). DO NOT deploy
    this API publicly until real auth replaces this — it currently trusts any
    caller as the coach.
    """
    return str(DEFAULT_COACH_ID)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session for the lifetime of a request."""
    async with get_async_db_session() as session:
        yield session
