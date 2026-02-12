"""Unit tests for the daily_log_service CRUD operations."""

from datetime import date, datetime, timedelta, timezone

import pytest

from src.services.daily_log_service import (
    create_log_entry,
    get_daily_totals,
    get_logs_by_date,
    get_logs_by_date_range,
)


def test_create_log_entry(test_db_session):
    """Test creating a single log entry and verifying return value."""
    now = datetime.now(timezone.utc)

    log = create_log_entry(
        test_db_session,
        food_id=1,
        amount_g=100.0,
        calories=165.0,
        protein=31.0,
        carbs=0.0,
        fat=3.6,
        timestamp=now,
        meal_type="lunch",
        original_text="100g chicken",
    )

    assert log.id is not None
    assert log.food_id == 1
    assert log.amount_g == 100.0
    assert log.calories == 165.0
    assert log.meal_type == "lunch"
    assert log.original_text == "100g chicken"


def test_get_daily_totals_empty(test_db_session):
    """Test querying totals for a date with no entries returns zeros."""
    totals = get_daily_totals(test_db_session, date.today())

    assert totals["calories"] == pytest.approx(0.0)
    assert totals["protein"] == pytest.approx(0.0)
    assert totals["carbs"] == pytest.approx(0.0)
    assert totals["fat"] == pytest.approx(0.0)


def test_get_daily_totals_with_entries(test_db_session):
    """Test aggregation of multiple log entries for the same day."""
    now = datetime.now(timezone.utc)
    today = now.date()

    # Create two log entries
    create_log_entry(
        test_db_session,
        food_id=1,
        amount_g=100.0,
        calories=165.0,
        protein=31.0,
        carbs=0.0,
        fat=3.6,
        timestamp=now,
    )
    create_log_entry(
        test_db_session,
        food_id=1,
        amount_g=50.0,
        calories=82.5,
        protein=15.5,
        carbs=0.0,
        fat=1.8,
        timestamp=now,
    )

    totals = get_daily_totals(test_db_session, today)

    assert totals["calories"] == pytest.approx(247.5, abs=0.1)
    assert totals["protein"] == pytest.approx(46.5, abs=0.1)
    assert totals["carbs"] == pytest.approx(0.0, abs=0.1)
    assert totals["fat"] == pytest.approx(5.4, abs=0.1)


def test_get_logs_by_date(test_db_session):
    """Test retrieving individual log entries for a specific date."""
    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = now - timedelta(days=1)

    # Create entries for today and yesterday
    create_log_entry(
        test_db_session,
        food_id=1,
        amount_g=100.0,
        calories=165.0,
        protein=31.0,
        carbs=0.0,
        fat=3.6,
        timestamp=now,
        meal_type="lunch",
    )
    create_log_entry(
        test_db_session,
        food_id=1,
        amount_g=50.0,
        calories=82.5,
        protein=15.5,
        carbs=0.0,
        fat=1.8,
        timestamp=yesterday,
        meal_type="dinner",
    )

    # Query today only
    today_logs = get_logs_by_date(test_db_session, today)
    assert len(today_logs) == 1
    assert today_logs[0].meal_type == "lunch"

    # Query yesterday
    yesterday_logs = get_logs_by_date(test_db_session, yesterday.date())
    assert len(yesterday_logs) == 1
    assert yesterday_logs[0].meal_type == "dinner"


def test_get_logs_by_date_range(test_db_session):
    """Test retrieving logs within a date range (inclusive)."""
    now = datetime.now(timezone.utc)
    today = now.date()

    # Create entries across 3 days
    for i in range(3):
        ts = now - timedelta(days=i)
        create_log_entry(
            test_db_session,
            food_id=1,
            amount_g=100.0,
            calories=165.0,
            protein=31.0,
            carbs=0.0,
            fat=3.6,
            timestamp=ts,
        )

    # Query last 2 days (today and yesterday)
    start = today - timedelta(days=1)
    logs = get_logs_by_date_range(test_db_session, start, today)
    assert len(logs) == 2

    # Query all 3 days
    start_all = today - timedelta(days=2)
    all_logs = get_logs_by_date_range(test_db_session, start_all, today)
    assert len(all_logs) == 3


def test_get_daily_totals_multiple_foods(test_db_session):
    """Test aggregation with entries for multiple different amounts."""
    now = datetime.now(timezone.utc)
    today = now.date()

    # Simulate 3 meals
    create_log_entry(
        test_db_session,
        food_id=1,
        amount_g=200.0,
        calories=330.0,
        protein=62.0,
        carbs=0.0,
        fat=7.2,
        timestamp=now,
        meal_type="breakfast",
    )
    create_log_entry(
        test_db_session,
        food_id=1,
        amount_g=150.0,
        calories=247.5,
        protein=46.5,
        carbs=0.0,
        fat=5.4,
        timestamp=now,
        meal_type="lunch",
    )
    create_log_entry(
        test_db_session,
        food_id=1,
        amount_g=100.0,
        calories=165.0,
        protein=31.0,
        carbs=0.0,
        fat=3.6,
        timestamp=now,
        meal_type="dinner",
    )

    totals = get_daily_totals(test_db_session, today)

    assert totals["calories"] == pytest.approx(742.5, abs=0.1)
    assert totals["protein"] == pytest.approx(139.5, abs=0.1)
    assert totals["fat"] == pytest.approx(16.2, abs=0.1)
