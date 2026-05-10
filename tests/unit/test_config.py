"""
Unit tests for config.py utilities.

Scope:
    Pure function tests — no DB, no LLM, no I/O.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import column

from src.config import (
    USER_TIMEZONE,
    day_bounds_utc,
    serialize_timestamp,
    timestamp_in_local_day,
    timestamp_in_local_day_range,
)


class TestSerializeTimestamp:
    """serialize_timestamp must always emit Israel-local ISO strings.

    Regression guard: services that skip this conversion send UTC times to the
    LLM, causing off-by-3h display errors for Israeli users on Railway (UTC host).
    """

    def test_none_returns_none(self):
        """
        arrange: None input.
        act:     call serialize_timestamp.
        assert:  returns None without raising.
        """
        assert serialize_timestamp(None) is None

    def test_utc_converts_to_israel_local(self):
        """
        arrange: 2026-04-16 19:11 UTC (== 22:11 Israel IDT, UTC+3).
        act:     call serialize_timestamp.
        assert:  output contains Israel-local time and +03:00 offset.
        """
        utc_moment = datetime(2026, 4, 16, 19, 11, tzinfo=timezone.utc)
        result = serialize_timestamp(utc_moment)
        assert result is not None
        assert "22:11" in result
        assert "+03:00" in result

    def test_already_local_passthrough(self):
        """
        arrange: datetime already in USER_TIMEZONE.
        act:     call serialize_timestamp.
        assert:  time value preserved, no double-conversion.
        """
        local_moment = datetime(2026, 4, 16, 22, 11, tzinfo=USER_TIMEZONE)
        result = serialize_timestamp(local_moment)
        assert result is not None
        assert "22:11" in result


class TestDayBoundsUtc:
    """day_bounds_utc must produce a [start, end) UTC window matching local midnight in tz."""

    def test_winter_offset_is_utc_plus_2(self):
        """
        arrange: 2026-01-15 (Israel winter, UTC+2).
        act:     call day_bounds_utc.
        assert:  start == 2026-01-14 22:00 UTC, end == 2026-01-15 22:00 UTC.
        """
        start, end = day_bounds_utc(date(2026, 1, 15))
        assert start == datetime(2026, 1, 14, 22, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 1, 15, 22, 0, tzinfo=timezone.utc)

    def test_summer_dst_offset_is_utc_plus_3(self):
        """
        arrange: 2026-07-15 (Israel DST, UTC+3).
        act:     call day_bounds_utc.
        assert:  start == 2026-07-14 21:00 UTC, end == 2026-07-15 21:00 UTC.
        """
        start, end = day_bounds_utc(date(2026, 7, 15))
        assert start == datetime(2026, 7, 14, 21, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 7, 15, 21, 0, tzinfo=timezone.utc)

    def test_window_is_24h(self):
        """
        arrange: any non-DST-transition date.
        act:     compute end - start.
        assert:  exactly 24 hours.
        """
        start, end = day_bounds_utc(date(2026, 5, 10))
        assert end - start == timedelta(days=1)


class TestTimestampInLocalDay:
    """timestamp_in_local_day must produce a sargable >= AND < predicate against UTC bounds."""

    def test_predicate_compiles_to_bounded_window(self):
        """
        arrange: a column reference and a target date.
        act:     compile the predicate to SQL with literal binds.
        assert:  rendered SQL contains both the start and end UTC timestamps,
                 and uses >= and < (no func.date, no equality on dates).
        """
        ts = column("ts")
        predicate = timestamp_in_local_day(ts, date(2026, 5, 10))
        sql = str(predicate.compile(compile_kwargs={"literal_binds": True}))

        assert "2026-05-09 21:00:00" in sql  # start (Israel DST = UTC+3)
        assert "2026-05-10 21:00:00" in sql  # end
        assert ">=" in sql
        assert "<" in sql
        assert "func.date" not in sql.lower()


class TestTimestampInLocalDayRange:
    """timestamp_in_local_day_range must produce inclusive-end day-range bounds."""

    def test_single_day_range_matches_single_day_predicate(self):
        """
        arrange: same start_date and end_date.
        act:     compile both range and single-day predicates.
        assert:  rendered SQL is identical (same window).
        """
        ts = column("ts")
        target = date(2026, 5, 10)

        single_sql = str(
            timestamp_in_local_day(ts, target).compile(compile_kwargs={"literal_binds": True})
        )
        range_sql = str(
            timestamp_in_local_day_range(ts, target, target).compile(
                compile_kwargs={"literal_binds": True}
            )
        )
        assert single_sql == range_sql

    def test_inclusive_end_extends_to_next_day_start(self):
        """
        arrange: Mon..Wed range in Israel-local time (DST, UTC+3).
        act:     compile the predicate.
        assert:  start == Monday 21:00 UTC the previous day; end == Wednesday 21:00 UTC.
        """
        ts = column("ts")
        predicate = timestamp_in_local_day_range(ts, date(2026, 5, 11), date(2026, 5, 13))
        sql = str(predicate.compile(compile_kwargs={"literal_binds": True}))

        assert "2026-05-10 21:00:00" in sql  # start (Mon midnight Israel = Sun 21:00 UTC)
        assert "2026-05-13 21:00:00" in sql  # end (Wed midnight + 1 = Thu midnight Israel = Wed 21:00 UTC)
