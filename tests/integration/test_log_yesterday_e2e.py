"""
Integration test: log-to-yesterday lands on yesterday in the DB.

Regression guard for the bug captured in LangSmith trace ``019dd286``:
when the user asked "add to yesterday", the input parser kept range fields
and nulled ``consumed_at``, causing ``commit_node`` to fall back to ``now()``
and write the row with today's timestamp.

After the discriminated-action-state refactor, ``commit_node`` reads the
write timestamp from ``state["log_food"]["consumed_at"]``. This test sets
that field to yesterday-noon-Israel and asserts the persisted DB row's
timestamp matches.

Scope:
    Bypasses the LLM-driven input_parser; constructs the post-parse state
    directly and exercises the real commit path against Supabase Postgres.

LLM Usage:
    NONE — deterministic regression guard.
"""

import uuid as uuid_mod
from datetime import datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from src.agents.nodes.commit_node import commit_node
from src.config import USER_TIMEZONE
from src.context import ContextSchema, DEFAULT_DEV_PROFILE
from src.models import DailyLog
from tests.conftest import SEED_FOOD_ID, TEST_USER_A


@pytest.mark.asyncio
async def test_commit_uses_log_food_consumed_at_when_set(async_test_db_session):
    """
    arrange: log_food.consumed_at = yesterday at noon Israel-local; one
             pending_confirmations item.
    act:     run commit_node, then query DailyLog rows for the user.
    assert:  the row's timestamp matches yesterday's date in Israel-local
             (the bug wrote today; this asserts yesterday).
    """
    yesterday_local = (datetime.now(USER_TIMEZONE) - timedelta(days=1)).date()
    yesterday_noon_local = datetime.combine(
        yesterday_local, time(12, 0), tzinfo=USER_TIMEZONE
    )
    yesterday_noon_utc = yesterday_noon_local.astimezone(timezone.utc)

    state = {
        "messages": [],
        "pending_food_items": [],
        "pending_confirmations": [
            {
                "name_en": "Test Chicken",
                "name_he": "עוף לבדיקה",
                "amount_g": 100.0,
                "calories": 165.0,
                "protein": 31.0,
                "carbs": 0.0,
                "fat": 3.6,
                "source": "database",
                "category": "protein",
                "tag": "lean",
                "serving_amount_g": 100.0,
                "servings": 1.0,
                "amount_g_estimated": None,
                "original_text": "100g chicken yesterday",
                "food_id": SEED_FOOD_ID,
            }
        ],
        "log_food": {"consumed_at": yesterday_noon_utc, "meal_type": None},
        "query_stats": {},
        "processing_results": [],
        "daily_log_today": [],
        "query_logs": [],
        "last_action": "CONFIRMED",
        "user_intent": "LOG_FOOD",
        "pipeline_stage": "CONFIRMED",
        "search_results": [],
        "selected_food_id": None,
    }

    runtime = MagicMock()
    runtime.context = ContextSchema(
        user_id=TEST_USER_A,
        user_profile=DEFAULT_DEV_PROFILE.copy(),
    )

    # commit_node uses tool wrappers that open their own sessions, so we
    # patch them to write through the test session (transactional rollback).
    from src.services.daily_log_service import create_log_entry

    async def _fake_log_food_tool(payload):
        ts = datetime.fromisoformat(payload["timestamp"])
        log = await create_log_entry(
            async_test_db_session,
            user_id=payload["user_id"],
            food_id=payload.get("food_id"),
            amount_g=payload["amount_g"],
            calories=payload["calories"],
            protein=payload["protein"],
            carbs=payload["carbs"],
            fat=payload["fat"],
            timestamp=ts,
            meal_type=payload.get("meal_type"),
            original_text=payload.get("original_text"),
        )
        return {"id": str(log.id), "status": "logged"}

    with patch("src.agents.nodes.commit_node.log_food_entry") as mock_log_tool:
        mock_log_tool.ainvoke = _fake_log_food_tool
        await commit_node(state, runtime)

    # Filter by the test-unique original_text to avoid pre-existing prod rows
    # (TEST_USER_A is the dev user and may have historical data outside this TX).
    rows = (
        await async_test_db_session.execute(
            select(DailyLog).where(
                DailyLog.user_id == uuid_mod.UUID(TEST_USER_A),
                DailyLog.original_text == "100g chicken yesterday",
            )
        )
    ).scalars().all()

    assert len(rows) == 1, f"expected exactly one matching log row, got {len(rows)}"
    persisted_ts = rows[0].timestamp
    if persisted_ts.tzinfo is None:
        persisted_ts = persisted_ts.replace(tzinfo=timezone.utc)
    assert persisted_ts.astimezone(USER_TIMEZONE).date() == yesterday_local, (
        f"expected timestamp on yesterday ({yesterday_local}), got "
        f"{persisted_ts.astimezone(USER_TIMEZONE).date()}"
    )
