"""Integration tests for macro_targets_service.

Hits the real Supabase Postgres database with transaction rollback isolation.
Requires the dashboard_phase1_foundation migration (macro_targets table) to be
applied.

LLM Usage:
    NONE — macro_targets_service does not call LLMs.
"""

import pytest
from sqlalchemy import func, select

from tests.conftest import TEST_USER_A
from src.models import MacroTarget
from src.services.macro_targets_service import get_macro_targets, set_macro_targets


async def test_set_and_get_both_day_types(async_test_db_session):
    """
    arrange: set training and rest targets for a trainee.
    act:     get_macro_targets.
    assert:  both day types are returned with the stored values.
    """
    session = async_test_db_session
    await set_macro_targets(session, TEST_USER_A, "training", 2400, 180, 250, 70)
    await set_macro_targets(session, TEST_USER_A, "rest", 2000, 180, 150, 60)

    targets = await get_macro_targets(session, TEST_USER_A)

    assert targets["training"] is not None
    assert targets["rest"] is not None
    assert targets["training"]["calories"] == 2400
    assert targets["training"]["carbs_g"] == 250
    assert targets["rest"]["calories"] == 2000
    assert targets["rest"]["carbs_g"] == 150


async def test_set_is_upsert_not_duplicate(async_test_db_session):
    """
    arrange: set training targets, then set them again with new values.
    act:     query the macro_targets rows for this (user, day_type).
    assert:  exactly one row exists and it holds the updated values.
    """
    session = async_test_db_session
    await set_macro_targets(session, TEST_USER_A, "training", 2400, 180, 250, 70)
    await set_macro_targets(session, TEST_USER_A, "training", 2600, 190, 270, 75)

    count = await session.scalar(
        select(func.count())
        .select_from(MacroTarget)
        .where(MacroTarget.day_type == "training")
    )
    assert count == 1

    targets = await get_macro_targets(session, TEST_USER_A)
    assert targets["training"]["calories"] == 2600
    assert targets["training"]["protein_g"] == 190


async def test_get_returns_none_for_unset_day_type(async_test_db_session):
    """
    arrange: set only the training targets.
    act:     get_macro_targets.
    assert:  rest is None, training is present.
    """
    session = async_test_db_session
    await set_macro_targets(session, TEST_USER_A, "training", 2400, 180, 250, 70)

    targets = await get_macro_targets(session, TEST_USER_A)

    assert targets["training"] is not None
    assert targets["rest"] is None


async def test_invalid_day_type_raises(async_test_db_session):
    """
    arrange: an invalid day_type.
    act:     set_macro_targets.
    assert:  raises ValueError before touching the DB.
    """
    session = async_test_db_session
    with pytest.raises(ValueError, match="day_type must be one of"):
        await set_macro_targets(session, TEST_USER_A, "cheat", 3000, 180, 350, 90)
