"""
Graph-API end-to-end test: log-to-yesterday flow drives the real graph and
asserts ``log_food.consumed_at`` lands on yesterday in the post-confirm state.

Regression guard for LangSmith trace ``019dd286`` (the ``consumed_at`` got
overwritten by range-field branch in input_parser_node, and commit_node
silently fell back to ``now()``). After the discriminated-action-state
refactor, the schema makes that bug shape unrepresentable: a ``LogFoodEvent``
cannot carry range fields and a ``QueryStatsEvent`` cannot carry
``consumed_at``.

LLM Usage:
    LIVE — single LLM-driven turn. The LLM must extract the relative date
    "yesterday" from the user message into ``LogFoodEvent.consumed_at``.
"""

from datetime import datetime, timedelta

import pytest

from src.config import USER_TIMEZONE
from tests.graph_api.test_graph_flows import (
    DEV_USER_CONTEXT,
    _assert_interrupted,
    _run,
)


@pytest.mark.asyncio
async def test_log_yesterday_records_yesterday_in_substate(lg_client, thread):
    """
    arrange: User says "log 100g chicken for yesterday".
    act:     Turn 1 hits HITL interrupt; turn 2 confirms with "yes".
    assert:  After Turn 1, thread state's `log_food.consumed_at` is on
             yesterday (Israel-local). After Turn 2 the run completes.
    """
    tn = "test_log_yesterday_records_yesterday_in_substate"
    await _run(
        lg_client, thread,
        input={"messages": [{"role": "human", "content": "log 100g chicken for yesterday"}]},
        context=DEV_USER_CONTEXT,
        test_name=tn,
    )
    await _assert_interrupted(lg_client, thread)

    state = await lg_client.threads.get_state(thread)
    values = state.get("values", {})
    log_food = values.get("log_food", {})
    consumed_at_raw = log_food.get("consumed_at")
    assert consumed_at_raw, (
        f"expected log_food.consumed_at to be set after parsing 'yesterday', "
        f"got log_food={log_food}"
    )

    consumed_at = datetime.fromisoformat(consumed_at_raw.replace("Z", "+00:00"))
    expected_yesterday = (datetime.now(USER_TIMEZONE) - timedelta(days=1)).date()
    actual_local_date = consumed_at.astimezone(USER_TIMEZONE).date()
    assert actual_local_date == expected_yesterday, (
        f"expected consumed_at on {expected_yesterday} (Israel-local), "
        f"got {actual_local_date}"
    )

    result = await _run(lg_client, thread, command={"resume": "yes"}, context=DEV_USER_CONTEXT, test_name=tn)
    messages = result.get("messages", [])
    assert len(messages) >= 2
    assert messages[-1]["content"].strip() != ""
