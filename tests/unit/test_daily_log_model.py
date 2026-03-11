"""
Unit tests for the DailyLog SQLAlchemy model.

Scope:
    Purely isolated unit tests exploring table parameters, required constraints, and entity relationships.

LLM Usage:
    NONE — models contain no internal logical loops calling LLMs.
"""
import uuid as uuid_mod
from datetime import datetime, timezone

from tests.conftest import SEED_FOOD_ID, TEST_USER_A
from src.models import DailyLog


class TestDailyLogModelCreation:
    """Test functionality around creation operations and requirements."""

    async def test_daily_log_creation(self, async_test_db_session):
        """
        arrange: stage object configuration using standard properties.
        act:     insert structured object natively representing database columns into test environment.
        assert:  validate object passes through validation schemas returning completely constructed database entity references.
        """
        log = DailyLog(
            food_id=uuid_mod.UUID(SEED_FOOD_ID),
            user_id=uuid_mod.UUID(TEST_USER_A),
            amount_g=100.0,
            calories=165.0,
            protein=31.0,
            carbs=0.0,
            fat=3.6,
            timestamp=datetime.now(timezone.utc),
            meal_type="lunch",
        )
        async_test_db_session.add(log)
        await async_test_db_session.commit()

        assert log.id is not None
        assert log.food_id == uuid_mod.UUID(SEED_FOOD_ID)
        assert log.user_id == uuid_mod.UUID(TEST_USER_A)
        assert log.amount_g == 100.0
        assert log.calories == 165.0
        assert log.protein == 31.0
        assert log.carbs == 0.0
        assert log.fat == 3.6
        assert log.meal_type == "lunch"

    async def test_daily_log_timestamps(self, async_test_db_session):
        """
        arrange: build and format daily log payload without creation timestamps.
        act:     add payload within test database.
        assert:  triggers server-default function natively executing schema instructions to generate value automatically safely matching requirements.
        """
        log = DailyLog(
            food_id=uuid_mod.UUID(SEED_FOOD_ID),
            user_id=uuid_mod.UUID(TEST_USER_A),
            amount_g=50.0,
            calories=82.5,
            protein=15.5,
            carbs=0.0,
            fat=1.8,
            timestamp=datetime.now(timezone.utc),
        )
        async_test_db_session.add(log)
        await async_test_db_session.commit()

        assert log.created_at is not None

    async def test_daily_log_nullable_fields(self, async_test_db_session):
        """
        arrange: configure object creation where properties allow nullable traits conditionally empty.
        act:     process execution persisting database record.
        assert:  schema correctly registers constraints without failing on exceptions while safely asserting null traits properly persist.
        """
        log = DailyLog(
            food_id=uuid_mod.UUID(SEED_FOOD_ID),
            user_id=uuid_mod.UUID(TEST_USER_A),
            amount_g=100.0,
            calories=165.0,
            protein=31.0,
            carbs=0.0,
            fat=3.6,
            timestamp=datetime.now(timezone.utc),
            meal_type=None,
            original_text=None,
        )
        async_test_db_session.add(log)
        await async_test_db_session.commit()

        assert log.id is not None
        assert log.meal_type is None
        assert log.original_text is None

    async def test_daily_log_with_original_text(self, async_test_db_session):
        """
        arrange: state test record incorporating extra nullable fields manually defined accurately.
        act:     dispatch records locally to storage interfaces correctly.
        assert:  safely ensures variables return fully parsed mappings.
        """
        log = DailyLog(
            food_id=uuid_mod.UUID(SEED_FOOD_ID),
            user_id=uuid_mod.UUID(TEST_USER_A),
            amount_g=100.0,
            calories=165.0,
            protein=31.0,
            carbs=0.0,
            fat=3.6,
            timestamp=datetime.now(timezone.utc),
            original_text="I ate 100g of chicken breast",
        )
        async_test_db_session.add(log)
        await async_test_db_session.commit()

        assert log.original_text == "I ate 100g of chicken breast"


class TestDailyLogModelRelationships:
    """Test behaviors linking internal models structure."""

    async def test_daily_log_relationship(self, async_test_db_session):
        """
        arrange: fetch food parameter components utilizing defined reference types testing standard relational operations sequentially backwards.
        act:     instantiate relationship logic checking bindings exist bidirectionally natively locally.
        assert:  demonstrates DailyLog can query its FoodItem source entity appropriately whilst resolving reversed configurations fully properly.
        """
        from src.models import FoodItem

        food_uuid = uuid_mod.UUID(SEED_FOOD_ID)

        log = DailyLog(
            food_id=food_uuid,
            user_id=uuid_mod.UUID(TEST_USER_A),
            amount_g=200.0,
            calories=330.0,
            protein=62.0,
            carbs=0.0,
            fat=7.2,
            timestamp=datetime.now(timezone.utc),
        )
        async_test_db_session.add(log)
        await async_test_db_session.commit()
        await async_test_db_session.refresh(log, ["food_item"])

        # Test DailyLog -> FoodItem direction
        assert log.food_item is not None
        assert log.food_item.name == "Test Chicken"

        # Test FoodItem -> DailyLog direction
        food = await async_test_db_session.get(FoodItem, food_uuid)
        await async_test_db_session.refresh(food, ["logs"])
        assert len(food.logs) == 1
        assert food.logs[0].id == log.id
