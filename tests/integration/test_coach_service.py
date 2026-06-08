"""Integration tests for coach_service.

Hits the real Supabase Postgres database with transaction rollback isolation.
Requires the dashboard_phase1_foundation migration (user_profiles.coach_id) to
be applied.

Isolation note: the DB holds real profiles owned by DEFAULT_COACH_ID, so these
tests scope to TEST_USER_B as a *coach* — a valid auth user that owns no
committed profiles — to keep assertions independent of production data.

LLM Usage:
    NONE — coach_service does not call LLMs.
"""

import uuid as uuid_mod

from tests.conftest import TEST_USER_A, TEST_USER_B
from src.models import UserProfile
from src.services.coach_service import list_trainees_for_coach


def _make_profile(user_id: str, coach_id: uuid_mod.UUID, name: str) -> UserProfile:
    """Build a UserProfile ORM row owned by ``coach_id``."""
    return UserProfile(
        user_id=uuid_mod.UUID(user_id),
        name=name,
        height_cm=175.0,
        age=30,
        gender="male",
        coach_id=coach_id,
    )


async def test_lists_only_the_coachs_trainees(async_test_db_session):
    """
    arrange: assign trainee A to coach TEST_USER_B (which owns no other profiles);
             the DB already holds profiles owned by DEFAULT_COACH_ID.
    act:     list_trainees_for_coach(TEST_USER_B).
    assert:  exactly trainee A is returned — DEFAULT_COACH_ID's trainees excluded.
    """
    session = async_test_db_session
    coach_id = uuid_mod.UUID(TEST_USER_B)
    session.add(_make_profile(TEST_USER_A, coach_id, "Trainee A"))
    await session.flush()

    trainees = await list_trainees_for_coach(session, TEST_USER_B)

    assert len(trainees) == 1
    assert trainees[0]["user_id"] == TEST_USER_A
    assert trainees[0]["name"] == "Trainee A"


async def test_returns_empty_when_coach_has_no_trainees(async_test_db_session):
    """
    arrange: no profiles are owned by TEST_USER_B.
    act:     list_trainees_for_coach(TEST_USER_B).
    assert:  empty list.
    """
    session = async_test_db_session

    trainees = await list_trainees_for_coach(session, TEST_USER_B)

    assert trainees == []
