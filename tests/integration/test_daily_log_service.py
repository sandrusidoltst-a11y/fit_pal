"""Unit tests for the daily_log_service async CRUD operations."""

import uuid as uuid_mod
from datetime import date, datetime, timedelta, timezone

import pytest

from src.config import USER_TIMEZONE
from tests.conftest import SEED_FOOD_ID, TEST_USER_A, TEST_USER_B
from src.services.daily_log_service import (
    _serialize_log,
    create_log_entry,
    get_daily_totals,
    get_logs_by_date,
    get_logs_by_date_range,
    get_todays_logs_serialized,
)


async def test_create_log_entry(async_test_db_session):
    """Test creating a single log entry and verifying return value."""
    now = datetime.now(timezone.utc)

    log = await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        food_id=SEED_FOOD_ID,
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
    assert log.food_id == uuid_mod.UUID(SEED_FOOD_ID)
    assert log.user_id == uuid_mod.UUID(TEST_USER_A)
    assert log.amount_g == 100.0
    assert log.calories == 165.0
    assert log.meal_type == "lunch"
    assert log.original_text == "100g chicken"


async def test_get_daily_totals_empty(async_test_db_session):
    """Test querying totals for a date with no entries returns zeros."""
    totals = await get_daily_totals(async_test_db_session, TEST_USER_A, date.today())

    assert totals["calories"] == pytest.approx(0.0)
    assert totals["protein"] == pytest.approx(0.0)
    assert totals["carbs"] == pytest.approx(0.0)
    assert totals["fat"] == pytest.approx(0.0)


async def test_get_daily_totals_with_entries(async_test_db_session):
    """Test aggregation of multiple log entries for the same day."""
    now = datetime.now(timezone.utc)
    today = now.date()

    # Create two log entries
    await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        food_id=SEED_FOOD_ID,
        amount_g=100.0,
        calories=165.0,
        protein=31.0,
        carbs=0.0,
        fat=3.6,
        timestamp=now,
    )
    await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        food_id=SEED_FOOD_ID,
        amount_g=50.0,
        calories=82.5,
        protein=15.5,
        carbs=0.0,
        fat=1.8,
        timestamp=now,
    )

    totals = await get_daily_totals(async_test_db_session, TEST_USER_A, today)

    assert totals["calories"] == pytest.approx(247.5, abs=0.1)
    assert totals["protein"] == pytest.approx(46.5, abs=0.1)
    assert totals["carbs"] == pytest.approx(0.0, abs=0.1)
    assert totals["fat"] == pytest.approx(5.4, abs=0.1)


async def test_get_logs_by_date(async_test_db_session):
    """Test retrieving individual log entries for a specific date."""
    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = now - timedelta(days=1)

    # Create entries for today and yesterday
    await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        food_id=SEED_FOOD_ID,
        amount_g=100.0,
        calories=165.0,
        protein=31.0,
        carbs=0.0,
        fat=3.6,
        timestamp=now,
        meal_type="lunch",
    )
    await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        food_id=SEED_FOOD_ID,
        amount_g=50.0,
        calories=82.5,
        protein=15.5,
        carbs=0.0,
        fat=1.8,
        timestamp=yesterday,
        meal_type="dinner",
    )

    # Query today only
    today_logs = await get_logs_by_date(async_test_db_session, TEST_USER_A, today)
    assert len(today_logs) == 1
    assert today_logs[0].meal_type == "lunch"

    # Query yesterday
    yesterday_logs = await get_logs_by_date(async_test_db_session, TEST_USER_A, yesterday.date())
    assert len(yesterday_logs) == 1
    assert yesterday_logs[0].meal_type == "dinner"


async def test_get_logs_by_date_range(async_test_db_session):
    """Test retrieving logs within a date range (inclusive)."""
    now = datetime.now(timezone.utc)
    today = now.date()

    # Create entries across 3 days
    for i in range(3):
        ts = now - timedelta(days=i)
        await create_log_entry(
            async_test_db_session,
            user_id=TEST_USER_A,
            food_id=SEED_FOOD_ID,
            amount_g=100.0,
            calories=165.0,
            protein=31.0,
            carbs=0.0,
            fat=3.6,
            timestamp=ts,
        )

    # Query last 2 days (today and yesterday)
    start = today - timedelta(days=1)
    logs = await get_logs_by_date_range(async_test_db_session, TEST_USER_A, start, today)
    assert len(logs) == 2

    # Query all 3 days
    start_all = today - timedelta(days=2)
    all_logs = await get_logs_by_date_range(async_test_db_session, TEST_USER_A, start_all, today)
    assert len(all_logs) == 3


async def test_get_daily_totals_multiple_foods(async_test_db_session):
    """Test aggregation with entries for multiple different amounts."""
    now = datetime.now(timezone.utc)
    today = now.date()

    # Simulate 3 meals
    await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        food_id=SEED_FOOD_ID,
        amount_g=200.0,
        calories=330.0,
        protein=62.0,
        carbs=0.0,
        fat=7.2,
        timestamp=now,
        meal_type="breakfast",
    )
    await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        food_id=SEED_FOOD_ID,
        amount_g=150.0,
        calories=247.5,
        protein=46.5,
        carbs=0.0,
        fat=5.4,
        timestamp=now,
        meal_type="lunch",
    )
    await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        food_id=SEED_FOOD_ID,
        amount_g=100.0,
        calories=165.0,
        protein=31.0,
        carbs=0.0,
        fat=3.6,
        timestamp=now,
        meal_type="dinner",
    )

    totals = await get_daily_totals(async_test_db_session, TEST_USER_A, today)

    assert totals["calories"] == pytest.approx(742.5, abs=0.1)
    assert totals["protein"] == pytest.approx(139.5, abs=0.1)
    assert totals["fat"] == pytest.approx(16.2, abs=0.1)


class TestUserDataIsolation:
    """Verify user data isolation at the service layer."""

    async def test_get_logs_by_date_filters_by_user(self, async_test_db_session):
        """
        arrange: User A logs chicken, User B logs rice, same date.
        act:     query logs for User A.
        assert:  Only chicken returned, not rice.
        """
        now = datetime.now(timezone.utc)
        today = now.date()

        await create_log_entry(
            async_test_db_session, user_id=TEST_USER_A,
            food_id=SEED_FOOD_ID, amount_g=200, calories=330, protein=62,
            carbs=0, fat=7.2, timestamp=now, meal_type="lunch",
            original_text="200g chicken",
        )
        await create_log_entry(
            async_test_db_session, user_id=TEST_USER_B,
            food_id=SEED_FOOD_ID, amount_g=150, calories=195, protein=4,
            carbs=42, fat=0.4, timestamp=now, meal_type="lunch",
            original_text="150g rice",
        )

        logs_a = await get_logs_by_date(async_test_db_session, TEST_USER_A, today)
        assert len(logs_a) == 1
        assert logs_a[0].original_text == "200g chicken"

    async def test_get_daily_totals_filters_by_user(self, async_test_db_session):
        """
        arrange: User A logs 200 cal, User B logs 500 cal, same date.
        act:     get_daily_totals for User A.
        assert:  Total is 200, not 700.
        """
        now = datetime.now(timezone.utc)
        today = now.date()

        await create_log_entry(
            async_test_db_session, user_id=TEST_USER_A,
            food_id=SEED_FOOD_ID, amount_g=100, calories=200, protein=20,
            carbs=10, fat=5, timestamp=now,
        )
        await create_log_entry(
            async_test_db_session, user_id=TEST_USER_B,
            food_id=SEED_FOOD_ID, amount_g=200, calories=500, protein=50,
            carbs=30, fat=15, timestamp=now,
        )

        totals = await get_daily_totals(async_test_db_session, TEST_USER_A, today)
        assert totals["calories"] == pytest.approx(200.0)

    async def test_get_logs_by_date_range_filters_by_user(self, async_test_db_session):
        """
        arrange: User A and B both log on 3 consecutive days.
        act:     get_logs_by_date_range for User A.
        assert:  Only User A's logs returned.
        """
        now = datetime.now(timezone.utc)
        today = now.date()

        for i in range(3):
            ts = now - timedelta(days=i)
            await create_log_entry(
                async_test_db_session, user_id=TEST_USER_A,
                food_id=SEED_FOOD_ID, amount_g=100, calories=165, protein=31,
                carbs=0, fat=3.6, timestamp=ts,
            )
            await create_log_entry(
                async_test_db_session, user_id=TEST_USER_B,
                food_id=SEED_FOOD_ID, amount_g=100, calories=165, protein=31,
                carbs=0, fat=3.6, timestamp=ts,
            )

        start = today - timedelta(days=2)
        logs_a = await get_logs_by_date_range(async_test_db_session, TEST_USER_A, start, today)
        assert len(logs_a) == 3  # only User A's 3 entries

    async def test_create_log_entry_stores_user_id(self, async_test_db_session):
        """
        arrange: Create log with user_id=user_a.
        act:     Query the row directly.
        assert:  row.user_id matches user_a.
        """
        now = datetime.now(timezone.utc)

        log = await create_log_entry(
            async_test_db_session, user_id=TEST_USER_A,
            food_id=SEED_FOOD_ID, amount_g=100, calories=165, protein=31,
            carbs=0, fat=3.6, timestamp=now,
        )

        assert log.user_id == uuid_mod.UUID(TEST_USER_A)


# ---------------------------------------------------------------------------
# Bug 2 regression guard + new get_todays_logs_serialized helper
# Bot UX audit 2026-04-17 — Fix #2 + timestamp display bug
# ---------------------------------------------------------------------------

class TestSerializeLogIsraelLocalTimestamp:
    """Verify _serialize_log emits Israel-local ISO timestamps (Bug 2 regression guard).

    Logs are stored as UTC in Postgres; the serializer must convert them back
    to the user's local timezone before handing them to the LLM, otherwise
    downstream code reasons over UTC times and the user sees wrong hours.
    """

    async def test_aware_utc_stored_log_serializes_as_israel_iso(
        self, async_test_db_session
    ):
        """
        arrange: Create a log with a known UTC timestamp during IDT (April, UTC+3).
        act:     Fetch via get_logs_by_date + _serialize_log.
        assert:  Timestamp string ends with +03:00 and hour is shifted +3.
        """
        session = async_test_db_session
        # 2026-04-16 19:11 UTC == 22:11 Israel (IDT).
        utc_moment = datetime(2026, 4, 16, 19, 11, tzinfo=timezone.utc)
        await create_log_entry(
            session=session,
            user_id=TEST_USER_A,
            food_id=SEED_FOOD_ID,
            amount_g=100.0,
            calories=100.0,
            protein=10.0,
            carbs=10.0,
            fat=5.0,
            timestamp=utc_moment,
        )

        logs = await get_logs_by_date(session, TEST_USER_A, utc_moment.date())
        assert len(logs) >= 1

        serialized = _serialize_log(logs[0])
        ts = serialized["timestamp"]
        assert ts is not None
        # IDT offset in April
        assert ts.endswith("+03:00")
        # Hour shifted from 19 UTC to 22 Israel
        assert "T22:11" in ts


class TestGetTodaysLogsSerialized:
    """Verify the bot-side helper: today-in-Israel scope, serialized output, user-scoped."""

    async def test_returns_empty_list_for_user_with_no_logs(
        self, async_test_db_session
    ):
        """
        arrange: No log entries exist for TEST_USER_A.
        act:     Call get_todays_logs_serialized.
        assert:  Returns an empty list.
        """
        session = async_test_db_session
        result = await get_todays_logs_serialized(session, TEST_USER_A)
        assert result == []

    async def test_returns_only_todays_logs(self, async_test_db_session):
        """
        arrange: Create one log for today (Israel) and one for yesterday.
        act:     Call get_todays_logs_serialized.
        assert:  Only today's log is returned, with Israel-local timestamp.
        """
        session = async_test_db_session
        # Noon today-in-Israel, safe vs. DST edges and date boundaries
        today_israel = datetime.now(USER_TIMEZONE).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        yesterday_israel = today_israel - timedelta(days=1)

        await create_log_entry(
            session=session,
            user_id=TEST_USER_A,
            food_id=SEED_FOOD_ID,
            amount_g=100.0,
            calories=100.0,
            protein=10.0,
            carbs=10.0,
            fat=5.0,
            timestamp=today_israel.astimezone(timezone.utc),
            original_text="today meal",
        )
        await create_log_entry(
            session=session,
            user_id=TEST_USER_A,
            food_id=SEED_FOOD_ID,
            amount_g=200.0,
            calories=200.0,
            protein=20.0,
            carbs=20.0,
            fat=10.0,
            timestamp=yesterday_israel.astimezone(timezone.utc),
            original_text="yesterday meal",
        )

        result = await get_todays_logs_serialized(session, TEST_USER_A)

        assert len(result) == 1
        assert result[0]["original_text"] == "today meal"
        ts = result[0]["timestamp"]
        assert ts is not None
        # Israel ISO — IDT (+03:00) or IST (+02:00) depending on DST
        assert ts.endswith(("+03:00", "+02:00"))

    async def test_scopes_by_user_id(self, async_test_db_session):
        """
        arrange: Both TEST_USER_A and TEST_USER_B log today.
        act:     Call get_todays_logs_serialized for each.
        assert:  Each gets only their own log.
        """
        session = async_test_db_session
        today_noon_utc = datetime.now(USER_TIMEZONE).replace(
            hour=12, minute=0, second=0, microsecond=0
        ).astimezone(timezone.utc)

        await create_log_entry(
            session=session,
            user_id=TEST_USER_A,
            food_id=SEED_FOOD_ID,
            amount_g=100.0,
            calories=100.0,
            protein=10.0,
            carbs=10.0,
            fat=5.0,
            timestamp=today_noon_utc,
            original_text="user A meal",
        )
        await create_log_entry(
            session=session,
            user_id=TEST_USER_B,
            food_id=SEED_FOOD_ID,
            amount_g=200.0,
            calories=200.0,
            protein=20.0,
            carbs=20.0,
            fat=10.0,
            timestamp=today_noon_utc,
            original_text="user B meal",
        )

        result_a = await get_todays_logs_serialized(session, TEST_USER_A)
        result_b = await get_todays_logs_serialized(session, TEST_USER_B)

        assert len(result_a) == 1
        assert result_a[0]["original_text"] == "user A meal"
        assert len(result_b) == 1
        assert result_b[0]["original_text"] == "user B meal"
