"""
Unit tests for food_lookup tools — user_id scoping and data isolation.

Scope:
    Tests against in-memory SQLite with real DB operations.
    Patches get_async_db_session to use the test session.

LLM Usage:
    NONE — food_lookup tools do not call LLMs.
"""
import uuid as uuid_mod
from contextlib import asynccontextmanager
from unittest.mock import patch

from tests.conftest import TEST_CONFIG_A, TEST_CONFIG_B, TEST_USER_A
from src.models import FoodItem
from src.tools.food_lookup import create_food_item, search_food


def _patch_session(session):
    """Create a context manager patch that yields the test session."""
    @asynccontextmanager
    async def _fake_session():
        yield session

    return patch("src.tools.food_lookup.get_async_db_session", _fake_session)


class TestSearchFoodSharedAccess:
    """Shared database foods should be visible to all users."""

    async def test_shared_db_food_visible_to_all_users(self, async_test_db_session):
        """
        arrange: Seed a source="database" food with user_id=None (already seeded in conftest).
        act:     search_food with user_a config, then user_b config.
        assert:  Both users find the same shared food.
        """
        with _patch_session(async_test_db_session):
            results_a = await search_food.ainvoke({"query": "Chicken"}, config=TEST_CONFIG_A)
            results_b = await search_food.ainvoke({"query": "Chicken"}, config=TEST_CONFIG_B)

        assert len(results_a) >= 1
        assert len(results_b) >= 1
        assert any(r["name"] == "Test Chicken" for r in results_a)
        assert any(r["name"] == "Test Chicken" for r in results_b)


class TestSearchFoodEstimatedIsolation:
    """Estimated foods should be scoped to the owner user."""

    async def test_estimated_food_scoped_to_owner(self, async_test_db_session):
        """
        arrange: Create source="estimated" food with user_id=user_a.
        act:     search_food with user_b config.
        assert:  User B does NOT find user A's estimated food.
        """
        # Create an estimated food for user A
        estimated = FoodItem(
            name="User A Special Smoothie",
            calories=150.0, protein=10.0, fat=5.0, carbs=20.0,
            source="estimated",
            user_id=uuid_mod.UUID(TEST_USER_A),
        )
        async_test_db_session.add(estimated)
        await async_test_db_session.commit()

        with _patch_session(async_test_db_session):
            results_b = await search_food.ainvoke({"query": "Smoothie"}, config=TEST_CONFIG_B)

        assert len(results_b) == 0

    async def test_estimated_food_visible_to_owner(self, async_test_db_session):
        """
        arrange: Create source="estimated" food with user_id=user_a.
        act:     search_food with user_a config.
        assert:  User A finds their own estimated food.
        """
        estimated = FoodItem(
            name="User A Special Shake",
            calories=200.0, protein=25.0, fat=3.0, carbs=15.0,
            source="estimated",
            user_id=uuid_mod.UUID(TEST_USER_A),
        )
        async_test_db_session.add(estimated)
        await async_test_db_session.commit()

        with _patch_session(async_test_db_session):
            results_a = await search_food.ainvoke({"query": "Shake"}, config=TEST_CONFIG_A)

        assert len(results_a) >= 1
        assert any("Shake" in r["name"] for r in results_a)


class TestCreateFoodItemSetsUserId:
    """create_food_item should set user_id from config."""

    async def test_created_item_has_user_id(self, async_test_db_session):
        """
        arrange: user_a config.
        act:     create_food_item with user_a config.
        assert:  Created FoodItem.user_id matches user_a.
        """
        with _patch_session(async_test_db_session):
            result = await create_food_item.ainvoke(
                {
                    "name": "Test Created Food",
                    "calories_per_100g": 100.0,
                    "protein_per_100g": 10.0,
                    "carbs_per_100g": 20.0,
                    "fat_per_100g": 5.0,
                },
                config=TEST_CONFIG_A,
            )

        assert result["name"] == "Test Created Food"
        # Verify in DB
        food = await async_test_db_session.get(FoodItem, uuid_mod.UUID(result["id"]))
        assert food is not None
        assert food.user_id == uuid_mod.UUID(TEST_USER_A)
