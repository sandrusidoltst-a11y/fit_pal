"""
Integration tests for user_profile_service — nutrition_plan round-trip.

Scope:
    Tests against the test Postgres DB with real DB operations.
    Patches get_async_db_session to use the test session.

LLM Usage:
    NONE — user_profile_service does not call LLMs.
"""
from contextlib import asynccontextmanager
from unittest.mock import patch

from tests.conftest import TEST_USER_A
from src.services.user_profile_service import (
    create_user_profile,
    get_user_profile,
    set_nutrition_plan,
)


def _patch_session(session):
    """Create a context manager patch that yields the test session."""
    @asynccontextmanager
    async def _fake_session():
        yield session

    return patch("src.services.user_profile_service.get_async_db_session", _fake_session)


class TestGetUserProfileNutritionPlan:
    """Verify get_user_profile returns the nutrition_plan field."""

    async def test_returns_none_when_no_plan_set(self, async_test_db_session):
        """
        arrange: Create a profile without a nutrition plan.
        act:     get_user_profile.
        assert:  nutrition_plan is None in returned dict.
        """
        session = async_test_db_session
        await create_user_profile(
            session=session,
            user_id=TEST_USER_A,
            name="Test User",
            height_cm=175.0,
            age=25,
            gender="male",
        )

        result = await get_user_profile(session, TEST_USER_A)

        assert result is not None
        assert "nutrition_plan" in result
        assert result["nutrition_plan"] is None


class TestSetNutritionPlan:
    """Verify set_nutrition_plan updates the DB correctly."""

    async def test_sets_plan_on_existing_profile(self, async_test_db_session):
        """
        arrange: Create a profile.
        act:     set_nutrition_plan with plan text.
        assert:  get_user_profile returns the updated plan.
        """
        session = async_test_db_session
        await create_user_profile(
            session=session,
            user_id=TEST_USER_A,
            name="Test User",
            height_cm=175.0,
            age=25,
            gender="male",
        )

        plan_text = "Daily targets: 2000 kcal, 150g protein, 200g carbs, 60g fat."
        await set_nutrition_plan(session, TEST_USER_A, plan_text)

        result = await get_user_profile(session, TEST_USER_A)
        assert result is not None
        assert result["nutrition_plan"] == plan_text

    async def test_raises_on_missing_profile(self, async_test_db_session):
        """
        arrange: No profile exists for user.
        act:     set_nutrition_plan.
        assert:  Raises ValueError.
        """
        import pytest
        session = async_test_db_session
        fake_user_id = "00000000-0000-0000-0000-000000000099"

        with pytest.raises(ValueError, match="No profile found"):
            await set_nutrition_plan(session, fake_user_id, "some plan")

    async def test_overwrites_existing_plan(self, async_test_db_session):
        """
        arrange: Create profile, set initial plan.
        act:     set_nutrition_plan with new text.
        assert:  get_user_profile returns the new plan.
        """
        session = async_test_db_session
        await create_user_profile(
            session=session,
            user_id=TEST_USER_A,
            name="Test User",
            height_cm=175.0,
            age=25,
            gender="male",
        )

        await set_nutrition_plan(session, TEST_USER_A, "Plan v1")
        await set_nutrition_plan(session, TEST_USER_A, "Plan v2")

        result = await get_user_profile(session, TEST_USER_A)
        assert result is not None
        assert result["nutrition_plan"] == "Plan v2"
