"""
Integration tests for food_service tools — user_id scoping, bilingual search,
coach mapping join.

Scope:
    Tests against the test Postgres DB with real DB operations.
    Patches get_async_db_session to use the test session.

LLM Usage:
    NONE — food_service tools do not call LLMs.
"""
import uuid as uuid_mod
from contextlib import asynccontextmanager
from unittest.mock import patch

from tests.conftest import TEST_USER_A, TEST_USER_B
from src.models import FoodItem
from src.services.food_service import create_food_item, search_food


def _patch_session(session):
    """Create a context manager patch that yields the test session."""
    @asynccontextmanager
    async def _fake_session():
        yield session

    return patch("src.services.food_service.get_async_db_session", _fake_session)


class TestSearchFoodSharedAccess:
    """Shared database foods should be visible to all users."""

    async def test_shared_db_food_visible_to_all_users(self, async_test_db_session):
        """
        arrange: Seed a source="database" food with user_id=None (already seeded in conftest).
        act:     search_food with user_a, then user_b.
        assert:  Both users find the same shared food.
        """
        with _patch_session(async_test_db_session):
            results_a = await search_food.ainvoke({"query": "Chicken", "user_id": TEST_USER_A})
            results_b = await search_food.ainvoke({"query": "Chicken", "user_id": TEST_USER_B})

        assert len(results_a) >= 1
        assert len(results_b) >= 1
        assert any(r["name_en"] == "Test Chicken" for r in results_a)
        assert any(r["name_en"] == "Test Chicken" for r in results_b)


class TestSearchFoodEstimatedIsolation:
    """Estimated foods should be scoped to the owner user."""

    async def test_estimated_food_scoped_to_owner(self, async_test_db_session):
        """
        arrange: Create source="estimated" food with user_id=user_a.
        act:     search_food with user_b.
        assert:  User B does NOT find user A's estimated food.
        """
        estimated = FoodItem(
            name_en="User A Special Smoothie",
            name_he=None,
            calories=150.0, protein=10.0, fat=5.0, carbs=20.0,
            source="estimated",
            user_id=uuid_mod.UUID(TEST_USER_A),
        )
        async_test_db_session.add(estimated)
        await async_test_db_session.commit()

        with _patch_session(async_test_db_session):
            results_b = await search_food.ainvoke({"query": "Smoothie", "user_id": TEST_USER_B})

        assert len(results_b) == 0

    async def test_estimated_food_visible_to_owner(self, async_test_db_session):
        """
        arrange: Create source="estimated" food with user_id=user_a.
        act:     search_food with user_a.
        assert:  User A finds their own estimated food.
        """
        estimated = FoodItem(
            name_en="User A Special Shake",
            name_he=None,
            calories=200.0, protein=25.0, fat=3.0, carbs=15.0,
            source="estimated",
            user_id=uuid_mod.UUID(TEST_USER_A),
        )
        async_test_db_session.add(estimated)
        await async_test_db_session.commit()

        with _patch_session(async_test_db_session):
            results_a = await search_food.ainvoke({"query": "Shake", "user_id": TEST_USER_A})

        assert len(results_a) >= 1
        assert any("Shake" in r["name_en"] for r in results_a)


class TestCreateFoodItemSetsUserId:
    """create_food_item should set user_id from the parameter."""

    async def test_created_item_has_user_id(self, async_test_db_session):
        """
        arrange: Pass user_id directly.
        act:     create_food_item with user_a, no category (food only).
        assert:  Created FoodItem.user_id matches user_a, no mapping created.
        """
        with _patch_session(async_test_db_session):
            result = await create_food_item.ainvoke(
                {
                    "name_en": "Test Created Food",
                    "calories_per_100g": 100.0,
                    "protein_per_100g": 10.0,
                    "carbs_per_100g": 20.0,
                    "fat_per_100g": 5.0,
                    "user_id": TEST_USER_A,
                },
            )

        assert result["name_en"] == "Test Created Food"
        assert result["mapping_created"] is False
        # Verify in DB
        food = await async_test_db_session.get(FoodItem, uuid_mod.UUID(result["id"]))
        assert food is not None
        assert food.user_id == uuid_mod.UUID(TEST_USER_A)
        assert food.name_en == "Test Created Food"

    async def test_create_with_category_creates_mapping(self, async_test_db_session):
        """
        arrange: Pass category="protein" with tag="lean".
        act:     create_food_item.
        assert:  FoodItem + CoachFoodMapping both persisted atomically.
        """
        with _patch_session(async_test_db_session):
            result = await create_food_item.ainvoke(
                {
                    "name_en": "Protein Shake",
                    "name_he": "שייק חלבון",
                    "calories_per_100g": 80.0,
                    "protein_per_100g": 15.0,
                    "carbs_per_100g": 3.0,
                    "fat_per_100g": 1.0,
                    "user_id": TEST_USER_A,
                    "category": "protein",
                    "tag": "lean",
                    "serving_amount_g": 250.0,
                },
            )

        assert result["mapping_created"] is True
        assert result["name_en"] == "Protein Shake"
        assert result["name_he"] == "שייק חלבון"


class TestBilingualSearch:
    """Search should match Hebrew OR English names."""

    async def test_hebrew_query_matches_hebrew_name(self, async_test_db_session):
        """
        arrange: Seeded food has name_he="עוף לבדיקה".
        act:     search_food with Hebrew query.
        assert:  Returns the seeded food.
        """
        with _patch_session(async_test_db_session):
            results = await search_food.ainvoke({"query": "עוף", "user_id": TEST_USER_A})
        assert any(r["name_en"] == "Test Chicken" for r in results)

    async def test_english_query_matches_english_name(self, async_test_db_session):
        """
        arrange: Seeded food has name_en="Test Chicken".
        act:     search_food with English query.
        assert:  Returns the seeded food.
        """
        with _patch_session(async_test_db_session):
            results = await search_food.ainvoke({"query": "Chicken", "user_id": TEST_USER_A})
        assert any(r["name_en"] == "Test Chicken" for r in results)


class TestCoachMappingJoin:
    """Seeded food has a coach mapping; search result exposes category + tag."""

    async def test_search_surfaces_coach_mapping_fields(self, async_test_db_session):
        """
        arrange: Seed food + coach mapping (category=protein, tag=lean).
        act:     search_food.
        assert:  Result contains category + tag fields from the mapping.
        """
        with _patch_session(async_test_db_session):
            results = await search_food.ainvoke({"query": "Chicken", "user_id": TEST_USER_A})
        seed = next(r for r in results if r["name_en"] == "Test Chicken")
        assert seed["category"] == "protein"
        assert seed["tag"] == "lean"

    async def test_search_no_mapping_yields_null_fields(self, async_test_db_session):
        """
        arrange: Create an estimated food WITHOUT a coach mapping.
        act:     search_food for that food.
        assert:  category + tag fields are None (LEFT JOIN with no match).
        """
        estimated = FoodItem(
            name_en="Orphan Estimated Food",
            name_he=None,
            calories=200.0, protein=5.0, fat=10.0, carbs=20.0,
            source="estimated",
            user_id=uuid_mod.UUID(TEST_USER_A),
        )
        async_test_db_session.add(estimated)
        await async_test_db_session.commit()

        with _patch_session(async_test_db_session):
            results = await search_food.ainvoke({"query": "Orphan", "user_id": TEST_USER_A})
        assert len(results) >= 1
        orphan = results[0]
        assert orphan["category"] is None
        assert orphan["tag"] is None
