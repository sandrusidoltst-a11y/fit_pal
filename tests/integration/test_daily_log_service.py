"""Unit tests for the daily_log_service async CRUD operations."""

import uuid as uuid_mod
from datetime import date, datetime, time, timedelta, timezone

import pytest

from src.config import DEFAULT_COACH_ID, USER_TIMEZONE
from src.models import FoodItem
from tests.conftest import SEED_FOOD_ID, TEST_USER_A, TEST_USER_B
from src.services.daily_log_service import (
    _serialize_log,
    create_log_entry,
    get_daily_totals,
    get_logs_by_date,
    get_logs_by_date_range,
    get_logs_by_date_range_with_mappings,
    get_logs_by_date_with_mappings,
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


# ---------------------------------------------------------------------------
# Plan 3d: enriched query with coach_food_mappings LEFT JOIN
# ---------------------------------------------------------------------------

class TestEnrichedQuery:
    """Verify get_logs_by_date_with_mappings LEFT-joins coach mappings correctly.

    Three mapping states to cover:
    - Log with food_id + valid coach mapping → tuple has non-None mapping
    - Log with food_id but no mapping for the coach → tuple has None mapping
    - Log with no food_id (CASCADE SET NULL survivor) → tuple has None mapping

    Also verifies the serialized form (via get_todays_logs_serialized) carries
    category/tag/serving_amount_g only when the mapping is present.
    """

    async def test_log_with_coach_mapping_returns_populated_tuple(
        self, async_test_db_session
    ):
        """
        arrange: log against SEED_FOOD_ID (which conftest seeded with a coach mapping).
        act:     get_logs_by_date_with_mappings.
        assert:  tuple mapping is non-None and carries category/tag.
        """
        session = async_test_db_session
        now = datetime.now(timezone.utc)
        await create_log_entry(
            session=session,
            user_id=TEST_USER_A,
            food_id=SEED_FOOD_ID,
            amount_g=100.0,
            calories=165.0,
            protein=31.0,
            carbs=0.0,
            fat=3.6,
            timestamp=now,
            original_text="seeded food",
        )

        rows = await get_logs_by_date_with_mappings(
            session, TEST_USER_A, now.date()
        )

        assert len(rows) == 1
        log, mapping = rows[0]
        assert log.original_text == "seeded food"
        assert mapping is not None
        assert mapping.coach_id == DEFAULT_COACH_ID
        # conftest seeds the mapping with a known category/tag — any non-empty
        # string passes this structural check.
        assert isinstance(mapping.category, str) and mapping.category

    async def test_log_with_food_but_no_coach_mapping_returns_none_mapping(
        self, async_test_db_session
    ):
        """
        arrange: create a FoodItem with NO CoachFoodMapping row, log against it.
        act:     get_logs_by_date_with_mappings.
        assert:  tuple mapping is None (LEFT JOIN yields NULL right side).
        """
        session = async_test_db_session
        # New FoodItem without a coach mapping
        orphan_food = FoodItem(
            id=uuid_mod.uuid4(),
            name_en="Orphan food",
            name_he="אוכל ללא מיפוי",
            calories=100.0,
            protein=5.0,
            fat=1.0,
            carbs=15.0,
            source="database",
        )
        session.add(orphan_food)
        await session.commit()

        now = datetime.now(timezone.utc)
        await create_log_entry(
            session=session,
            user_id=TEST_USER_A,
            food_id=str(orphan_food.id),
            amount_g=100.0,
            calories=100.0,
            protein=5.0,
            carbs=15.0,
            fat=1.0,
            timestamp=now,
            original_text="orphan log",
        )

        rows = await get_logs_by_date_with_mappings(
            session, TEST_USER_A, now.date()
        )

        # Find the orphan log in the results
        orphan_row = next(
            (r for r in rows if r[0].original_text == "orphan log"), None
        )
        assert orphan_row is not None
        log, mapping = orphan_row
        assert log.food_id == orphan_food.id
        assert mapping is None

    async def test_log_with_null_food_id_returns_none_mapping(
        self, async_test_db_session
    ):
        """
        arrange: log with food_id=None (CASCADE SET NULL survivor).
        act:     get_logs_by_date_with_mappings.
        assert:  tuple mapping is None; no join match possible without food_id.
        """
        session = async_test_db_session
        now = datetime.now(timezone.utc)
        await create_log_entry(
            session=session,
            user_id=TEST_USER_A,
            food_id=None,
            amount_g=50.0,
            calories=75.0,
            protein=2.0,
            carbs=10.0,
            fat=3.0,
            timestamp=now,
            original_text="unlinked log",
        )

        rows = await get_logs_by_date_with_mappings(
            session, TEST_USER_A, now.date()
        )

        unlinked = next(
            (r for r in rows if r[0].original_text == "unlinked log"), None
        )
        assert unlinked is not None
        log, mapping = unlinked
        assert log.food_id is None
        assert mapping is None

    async def test_serialized_log_carries_category_when_mapping_present(
        self, async_test_db_session
    ):
        """
        arrange: log against the seeded food (has coach mapping).
        act:     get_logs_by_date_with_mappings + _serialize_log.
        assert:  serialized dict contains category/tag/serving_amount_g keys.
        """
        session = async_test_db_session
        today_israel = datetime.now(USER_TIMEZONE).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        await create_log_entry(
            session=session,
            user_id=TEST_USER_A,
            food_id=SEED_FOOD_ID,
            amount_g=100.0,
            calories=165.0,
            protein=31.0,
            carbs=0.0,
            fat=3.6,
            timestamp=today_israel.astimezone(timezone.utc),
            original_text="seeded today meal",
        )

        rows = await get_logs_by_date_with_mappings(
            session, TEST_USER_A, today_israel.date()
        )
        result = [_serialize_log(log, mapping) for log, mapping in rows]
        assert len(result) == 1
        entry = result[0]
        assert "category" in entry
        assert entry["category"]  # non-empty string from conftest seed
        assert "tag" in entry
        assert "serving_amount_g" in entry

    async def test_serialized_log_omits_mapping_fields_when_no_mapping(
        self, async_test_db_session
    ):
        """
        arrange: log with food_id=None (no mapping possible).
        act:     get_logs_by_date_with_mappings + _serialize_log.
        assert:  serialized dict does NOT contain category/tag/serving_amount_g keys.
        """
        session = async_test_db_session
        today_israel = datetime.now(USER_TIMEZONE).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        await create_log_entry(
            session=session,
            user_id=TEST_USER_A,
            food_id=None,
            amount_g=50.0,
            calories=75.0,
            protein=2.0,
            carbs=10.0,
            fat=3.0,
            timestamp=today_israel.astimezone(timezone.utc),
            original_text="unlinked today meal",
        )

        rows = await get_logs_by_date_with_mappings(
            session, TEST_USER_A, today_israel.date()
        )
        result = [_serialize_log(log, mapping) for log, mapping in rows]
        assert len(result) == 1
        entry = result[0]
        # Optional-fields contract: absent, not None.
        assert "category" not in entry
        assert "tag" not in entry
        assert "serving_amount_g" not in entry


# ---------------------------------------------------------------------------
# Range version of the enriched-query helper (added for query_food_logs migration)
# ---------------------------------------------------------------------------

class TestGetLogsByDateRangeWithMappings:
    """Verify get_logs_by_date_range_with_mappings — mirror of the single-date
    helper, but covering an inclusive range. Same coach-join semantics.
    """

    async def test_log_with_mapping_returns_populated_tuple(
        self, async_test_db_session
    ):
        """SEED_FOOD_ID has a coach mapping in conftest — within-range log
        carries the mapping in its tuple.
        """
        session = async_test_db_session
        now = datetime.now(timezone.utc)
        await create_log_entry(
            session=session,
            user_id=TEST_USER_A,
            food_id=SEED_FOOD_ID,
            amount_g=100.0,
            calories=165.0,
            protein=31.0,
            carbs=0.0,
            fat=3.6,
            timestamp=now,
            original_text="seeded range log",
        )

        start = (now - timedelta(days=2)).date()
        end = (now + timedelta(days=1)).date()
        rows = await get_logs_by_date_range_with_mappings(
            session, TEST_USER_A, start, end
        )

        assert len(rows) == 1
        log, mapping = rows[0]
        assert log.original_text == "seeded range log"
        assert mapping is not None
        assert mapping.coach_id == DEFAULT_COACH_ID
        assert isinstance(mapping.category, str) and mapping.category

    async def test_log_with_no_mapping_returns_none_mapping(
        self, async_test_db_session
    ):
        """A log with food_id=NULL yields (log, None) — LEFT JOIN preserves it."""
        session = async_test_db_session
        now = datetime.now(timezone.utc)
        await create_log_entry(
            session=session,
            user_id=TEST_USER_A,
            food_id=None,
            amount_g=50.0,
            calories=75.0,
            protein=2.0,
            carbs=10.0,
            fat=3.0,
            timestamp=now,
            original_text="orphan range log",
        )

        rows = await get_logs_by_date_range_with_mappings(
            session, TEST_USER_A, now.date(), now.date()
        )

        target = next(
            (r for r in rows if r[0].original_text == "orphan range log"), None
        )
        assert target is not None
        log, mapping = target
        assert log.food_id is None
        assert mapping is None

    async def test_range_inclusive_on_both_ends(self, async_test_db_session):
        """A log at exactly start_date and another at exactly end_date are both included."""
        session = async_test_db_session
        # Use Israel-noon to avoid date-boundary edge cases (Bug 1)
        anchor = datetime.now(USER_TIMEZONE).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        day_minus_1 = anchor - timedelta(days=1)
        day_plus_1 = anchor + timedelta(days=1)

        for ts, label in [(day_minus_1, "yesterday"), (anchor, "today"), (day_plus_1, "tomorrow")]:
            await create_log_entry(
                session=session,
                user_id=TEST_USER_A,
                food_id=SEED_FOOD_ID,
                amount_g=100.0,
                calories=100.0,
                protein=10.0,
                carbs=10.0,
                fat=5.0,
                timestamp=ts.astimezone(timezone.utc),
                original_text=label,
            )

        rows = await get_logs_by_date_range_with_mappings(
            session, TEST_USER_A, day_minus_1.date(), day_plus_1.date()
        )

        labels = sorted(log.original_text for log, _ in rows)
        assert labels == ["today", "tomorrow", "yesterday"]

    async def test_user_scoping(self, async_test_db_session):
        """User A's range query never returns User B's logs."""
        session = async_test_db_session
        now = datetime.now(timezone.utc)

        await create_log_entry(
            session=session,
            user_id=TEST_USER_A,
            food_id=SEED_FOOD_ID,
            amount_g=100.0, calories=100.0, protein=10.0, carbs=10.0, fat=5.0,
            timestamp=now, original_text="user A log",
        )
        await create_log_entry(
            session=session,
            user_id=TEST_USER_B,
            food_id=SEED_FOOD_ID,
            amount_g=200.0, calories=200.0, protein=20.0, carbs=20.0, fat=10.0,
            timestamp=now, original_text="user B log",
        )

        a_rows = await get_logs_by_date_range_with_mappings(
            session, TEST_USER_A, now.date(), now.date()
        )
        b_rows = await get_logs_by_date_range_with_mappings(
            session, TEST_USER_B, now.date(), now.date()
        )

        # TEST_USER_A is the dev user and may have pre-existing real logs on
        # today's date — assert scoping via set membership (the test data each
        # user sees is theirs, never the other user's), not via exclusivity.
        a_originals = {log.original_text for log, _ in a_rows}
        b_originals = {log.original_text for log, _ in b_rows}
        assert "user A log" in a_originals
        assert "user A log" not in b_originals
        assert "user B log" in b_originals
        assert "user B log" not in a_originals


# ---------------------------------------------------------------------------
# Regression: UTC-midnight boundary
#
# A log saved at 01:30 Asia/Jerusalem is ~22:30 UTC on the *previous* day. The
# old `func.date(timestamp) == target_date` predicate evaluated `date()` in the
# DB session timezone (UTC on Supabase), so this entry would silently fall on
# the previous UTC date and be excluded from "today's logs" queries. These
# tests guard the helper-based fix (timestamp_in_local_day / _range).
# ---------------------------------------------------------------------------

async def test_get_logs_by_date_returns_post_midnight_israel_local(async_test_db_session):
    """A log written at 01:30 Israel-local (≈22:30 UTC prev day) belongs to today."""
    target_local_date = date(2026, 5, 10)
    local_dt = datetime.combine(target_local_date, time(1, 30), tzinfo=USER_TIMEZONE)
    utc_ts = local_dt.astimezone(timezone.utc)
    # Sanity: the UTC date is the previous day — confirms the bug condition.
    assert utc_ts.date() != target_local_date

    await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        food_id=SEED_FOOD_ID,
        amount_g=100.0, calories=100.0, protein=10.0, carbs=10.0, fat=2.0,
        timestamp=utc_ts,
        meal_type="snack",
        original_text="late-night Israel-local snack",
    )

    logs = await get_logs_by_date(async_test_db_session, TEST_USER_A, target_local_date)
    originals = {log.original_text for log in logs}
    assert "late-night Israel-local snack" in originals


async def test_get_daily_totals_includes_post_midnight_israel_local(async_test_db_session):
    """Totals on the Israel-local date must include a 22:30 UTC (prev-day) entry.

    TEST_USER_B may carry pre-existing real logs on this date, so we assert the
    delta after insert rather than an absolute total — what matters is that the
    boundary entry is *counted*.
    """
    target_local_date = date(2026, 5, 10)
    local_dt = datetime.combine(target_local_date, time(2, 0), tzinfo=USER_TIMEZONE)
    utc_ts = local_dt.astimezone(timezone.utc)

    before = await get_daily_totals(async_test_db_session, TEST_USER_B, target_local_date)

    await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_B,
        food_id=SEED_FOOD_ID,
        amount_g=100.0, calories=250.0, protein=20.0, carbs=30.0, fat=5.0,
        timestamp=utc_ts,
        original_text="late-night totals entry",
    )

    after = await get_daily_totals(async_test_db_session, TEST_USER_B, target_local_date)
    assert after["calories"] - before["calories"] == pytest.approx(250.0)
    assert after["protein"] - before["protein"] == pytest.approx(20.0)


async def test_get_logs_by_date_range_returns_post_midnight_israel_local(async_test_db_session):
    """Single-day range query must also include the post-midnight Israel-local entry."""
    target_local_date = date(2026, 5, 10)
    local_dt = datetime.combine(target_local_date, time(1, 30), tzinfo=USER_TIMEZONE)
    utc_ts = local_dt.astimezone(timezone.utc)

    await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_B,
        food_id=SEED_FOOD_ID,
        amount_g=100.0, calories=100.0, protein=10.0, carbs=10.0, fat=2.0,
        timestamp=utc_ts,
        original_text="range boundary entry",
    )

    rows = await get_logs_by_date_range(
        async_test_db_session, TEST_USER_B, target_local_date, target_local_date
    )
    originals = {log.original_text for log in rows}
    assert "range boundary entry" in originals


async def test_get_logs_by_date_with_mappings_returns_post_midnight_israel_local(async_test_db_session):
    """Mappings join must also see the post-midnight Israel-local entry."""
    target_local_date = date(2026, 5, 10)
    local_dt = datetime.combine(target_local_date, time(2, 30), tzinfo=USER_TIMEZONE)
    utc_ts = local_dt.astimezone(timezone.utc)

    await create_log_entry(
        async_test_db_session,
        user_id=TEST_USER_B,
        food_id=SEED_FOOD_ID,
        amount_g=100.0, calories=120.0, protein=12.0, carbs=15.0, fat=3.0,
        timestamp=utc_ts,
        original_text="mappings boundary entry",
    )

    rows = await get_logs_by_date_with_mappings(
        async_test_db_session, TEST_USER_B, target_local_date
    )
    originals = {log.original_text for log, _ in rows}
    assert "mappings boundary entry" in originals

