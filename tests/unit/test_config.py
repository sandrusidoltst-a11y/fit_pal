"""
Unit tests for config.py utilities.

Scope:
    Pure function tests — no DB, no LLM, no I/O.
"""
from datetime import datetime, timezone

from src.config import USER_TIMEZONE, serialize_timestamp


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
