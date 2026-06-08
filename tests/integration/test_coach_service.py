"""Integration tests for coach_service.

Hits the real Supabase Postgres database with transaction rollback isolation.
Requires the dashboard_phase1_foundation migration (user_profiles.coach_id) to
be applied.

LLM Usage:
    NONE — coach_service does not call LLMs.
"""

import uuid as uuid_mod

from tests.conftest import TEST_USER_A, TEST_USER_B
from src.config import DEFAULT_COACH_ID
from src.models import UserProfile
from src.services.coach_service import list_trainees_for_coach


def _make_profile(user_id: str, coach_id, name: str) -> UserProfile:
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
    arrange: trainee A owned by DEFAULT_COACH_ID, trainee B owned by another coach.
    act:     list_trainees_for_coach(DEFAULT_COACH_ID).
    assert:  only trainee A is returned.
    """
    session = async_test_db_session
    session.add(_make_profile(TEST_USER_A, DEFAULT_COACH_ID, "Trainee A"))
    # TEST_USER_A doubles as a valid auth.users id to act as a *different* coach for B
    session.add(_make_profile(TEST_USER_B, uuid_mod.UUID(TEST_USER_A), "Trainee B"))
    await session.flush()

    trainees = await list_trainees_for_coach(session, str(DEFAULT_COACH_ID))

    assert len(trainees) == 1
    assert trainees[0]["user_id"] == TEST_USER_A
    assert trainees[0]["name"] == "Trainee A"


async def test_returns_empty_when_coach_has_no_trainees(async_test_db_session):
    """
    arrange: a trainee owned by DEFAULT_COACH_ID only.
    act:     list_trainees_for_coach for a coach that owns nobody.
    assert:  empty list.
    """
    session = async_test_db_session
    session.add(_make_profile(TEST_USER_A, DEFAULT_COACH_ID, "Trainee A"))
    await session.flush()

    trainees = await list_trainees_for_coach(session, TEST_USER_B)

    assert trainees == []
