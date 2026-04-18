"""Integration tests for the personal_stats_service async CRUD operations.

Hits the real Supabase Postgres database with transaction rollback isolation.
"""

import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

from tests.conftest import TEST_USER_A, TEST_USER_B
from src.services.personal_stats_service import (
    create_stat_entry,
    get_latest_stats,
    get_stat_history,
)


# ---------------------------------------------------------------------------
# Timezone serialization regression guard
# ---------------------------------------------------------------------------

class TestSerializeStatIsraelLocalTimestamp:
    """Verify _serialize_stat emits Israel-local ISO timestamps.

    Stats are stored as UTC in Postgres; the serializer must convert them to
    the user's local timezone — same requirement as daily_log_service.
    Regression guard for the UTC bug fixed alongside the serialize_timestamp refactor.
    """

    async def test_utc_stored_stat_serializes_as_israel_iso(self, async_test_db_session):
        """
        arrange: Create a stat entry with a known UTC timestamp during IDT (April, UTC+3).
        act:     Fetch via get_latest_stats (calls _serialize_stat internally).
        assert:  recorded_at string ends with +03:00 and hour is shifted +3.
        """
        # 2026-04-16 19:11 UTC == 22:11 Israel (IDT, UTC+3).
        utc_moment = datetime(2026, 4, 16, 19, 11, tzinfo=timezone.utc)
        await create_stat_entry(
            async_test_db_session,
            user_id=TEST_USER_A,
            weight_kg=74.0,
            recorded_at=utc_moment,
        )

        latest = await get_latest_stats(async_test_db_session, TEST_USER_A)

        assert latest is not None
        ts = latest["recorded_at"]
        assert ts is not None
        assert ts.endswith("+03:00")
        assert "T22:11" in ts


async def test_create_weight_entry(async_test_db_session):
    """
    arrange: provide weight_kg value.
    act:     create_stat_entry with weight.
    assert:  returned object has correct weight_kg and user_id.
    """
    now = datetime.now(timezone.utc)

    entry = await create_stat_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        weight_kg=74.0,
        recorded_at=now,
    )

    assert entry.id is not None
    assert entry.user_id == uuid_mod.UUID(TEST_USER_A)
    assert entry.weight_kg == 74.0
    assert entry.body_fat_pct is None
    assert entry.recorded_at is not None


async def test_create_body_fat_entry(async_test_db_session):
    """
    arrange: provide body_fat_pct value.
    act:     create_stat_entry with body fat.
    assert:  returned object has correct body_fat_pct, weight_kg is None.
    """
    now = datetime.now(timezone.utc)

    entry = await create_stat_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        body_fat_pct=15.0,
        recorded_at=now,
    )

    assert entry.id is not None
    assert entry.body_fat_pct == 15.0
    assert entry.weight_kg is None


async def test_get_latest_stats(async_test_db_session):
    """
    arrange: create two weight entries at different times.
    act:     get_latest_stats.
    assert:  returns the most recent entry.
    """
    now = datetime.now(timezone.utc)
    earlier = now - timedelta(hours=2)

    await create_stat_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        weight_kg=75.0,
        recorded_at=earlier,
    )
    await create_stat_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        weight_kg=74.0,
        recorded_at=now,
    )

    latest = await get_latest_stats(async_test_db_session, TEST_USER_A)

    assert latest is not None
    assert latest["weight_kg"] == 74.0


async def test_get_stat_history(async_test_db_session):
    """
    arrange: create 3 weight entries across different days.
    act:     get_stat_history for weight.
    assert:  returns entries ordered by most recent first.
    """
    now = datetime.now(timezone.utc)

    for i in range(3):
        await create_stat_entry(
            async_test_db_session,
            user_id=TEST_USER_A,
            weight_kg=74.0 + i,
            recorded_at=now - timedelta(days=i),
        )

    history = await get_stat_history(
        async_test_db_session,
        TEST_USER_A,
        stat_type="weight",
        limit=10,
    )

    assert len(history) == 3
    # Most recent first
    assert history[0]["weight_kg"] == 74.0
    assert history[2]["weight_kg"] == 76.0


async def test_get_stat_history_filters_by_type(async_test_db_session):
    """
    arrange: create weight and body fat entries.
    act:     get_stat_history for body_fat only.
    assert:  only body fat entries returned (weight entries excluded).
    """
    now = datetime.now(timezone.utc)

    await create_stat_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        weight_kg=74.0,
        recorded_at=now,
    )
    await create_stat_entry(
        async_test_db_session,
        user_id=TEST_USER_A,
        body_fat_pct=15.0,
        recorded_at=now - timedelta(hours=1),
    )

    history = await get_stat_history(
        async_test_db_session,
        TEST_USER_A,
        stat_type="body_fat",
    )

    assert len(history) == 1
    assert history[0]["body_fat_pct"] == 15.0


class TestUserDataIsolation:
    """Verify user data isolation at the service layer."""

    async def test_stats_filtered_by_user(self, async_test_db_session):
        """
        arrange: User A logs weight 74kg, User B logs weight 80kg.
        act:     get_latest_stats for User A.
        assert:  only User A's entry returned.
        """
        now = datetime.now(timezone.utc)

        await create_stat_entry(
            async_test_db_session,
            user_id=TEST_USER_A,
            weight_kg=74.0,
            recorded_at=now,
        )
        await create_stat_entry(
            async_test_db_session,
            user_id=TEST_USER_B,
            weight_kg=80.0,
            recorded_at=now,
        )

        latest_a = await get_latest_stats(async_test_db_session, TEST_USER_A)
        assert latest_a is not None
        assert latest_a["weight_kg"] == 74.0

    async def test_stat_history_filtered_by_user(self, async_test_db_session):
        """
        arrange: User A and B each log 2 weight entries.
        act:     get_stat_history for User A.
        assert:  only User A's 2 entries returned.
        """
        now = datetime.now(timezone.utc)

        for i in range(2):
            await create_stat_entry(
                async_test_db_session,
                user_id=TEST_USER_A,
                weight_kg=74.0 + i,
                recorded_at=now - timedelta(days=i),
            )
            await create_stat_entry(
                async_test_db_session,
                user_id=TEST_USER_B,
                weight_kg=80.0 + i,
                recorded_at=now - timedelta(days=i),
            )

        history_a = await get_stat_history(
            async_test_db_session, TEST_USER_A, stat_type="weight"
        )
        assert len(history_a) == 2
