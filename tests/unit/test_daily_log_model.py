"""Unit tests for the DailyLog SQLAlchemy model."""

from datetime import datetime, timezone

from src.models import DailyLog


async def test_daily_log_creation(async_test_db_session):
    """Test that a DailyLog entry can be created with all required fields."""
    log = DailyLog(
        food_id=1,
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
    assert log.food_id == 1
    assert log.amount_g == 100.0
    assert log.calories == 165.0
    assert log.protein == 31.0
    assert log.carbs == 0.0
    assert log.fat == 3.6
    assert log.meal_type == "lunch"


async def test_daily_log_relationship(async_test_db_session):
    """Test that the FoodItem <-> DailyLog relationship works bidirectionally."""
    from src.models import FoodItem

    log = DailyLog(
        food_id=1,
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
    food = await async_test_db_session.get(FoodItem, 1)
    await async_test_db_session.refresh(food, ["logs"])
    assert len(food.logs) == 1
    assert food.logs[0].id == log.id


async def test_daily_log_timestamps(async_test_db_session):
    """Test that created_at is automatically set on creation."""
    log = DailyLog(
        food_id=1,
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


async def test_daily_log_nullable_fields(async_test_db_session):
    """Test that meal_type and original_text can be null."""
    log = DailyLog(
        food_id=1,
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


async def test_daily_log_with_original_text(async_test_db_session):
    """Test that original_text is preserved when provided."""
    log = DailyLog(
        food_id=1,
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
