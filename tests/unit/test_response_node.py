from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.nodes.response_node import (
    _build_context,
    _current_time_str,
    _format_daily_log,
    response_node,
)
from src.context import ContextSchema, DEFAULT_DEV_PROFILE
from tests.conftest import TEST_RUNTIME_A, TEST_USER_A


# ---------------------------------------------------------------------------
# Helper: minimal AgentState dict
# ---------------------------------------------------------------------------

def _make_state(**overrides):
    """Build a minimal AgentState dict with sensible defaults.

    Existing tests pass ``last_action`` with values that may be either an
    intent (``LOG_FOOD``, ``QUERY_DAILY_STATS``, ``CHITCHAT``) or a stage
    (``LOGGED``, ``FAILED``, ``NO_MATCH``, ``CONFIRMED``, ...). Post-ADR-0005,
    ``_build_context`` dispatches on ``user_intent``. To keep the existing 27
    assertions on ``parsed["last_action"]`` working without per-test edits,
    auto-derive ``user_intent`` from the legacy value when it's an intent;
    otherwise default to ``LOG_FOOD`` (every existing test that passes a
    stage value is simulating a LOG flow that reached that stage).
    """
    from src.agents.state import intent_from_legacy, stage_from_legacy

    legacy = overrides.get("last_action", "LOGGED")
    default_intent = intent_from_legacy(legacy)
    if default_intent is None and legacy:
        # Non-empty legacy value that isn't an intent → it's a stage
        # (LOGGED/FAILED/CONFIRMED/…) — the originating intent for these
        # tests is LOG_FOOD. Empty legacy stays "" (the test is checking
        # the minimal-context path).
        default_intent = "LOG_FOOD"
    elif default_intent is None:
        default_intent = ""
    default_stage = stage_from_legacy(legacy) or ""

    state = {
        "messages": [HumanMessage(content="I ate 200g chicken")],
        "pending_food_items": [],
        "log_food": {"consumed_at": datetime(2026, 2, 20, 12, 0)},
        "query_stats": {},
        "last_action": legacy,
        "user_intent": overrides.get("user_intent", default_intent),
        "pipeline_stage": overrides.get("pipeline_stage", default_stage),
        "search_results": [],
        "selected_food_id": None,
        "processing_results": [],
        "daily_log_today": [],
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Tests for _build_context (unit-level, no LLM)
# ---------------------------------------------------------------------------

class TestBuildContext:
    """Verify selective context construction based on last_action."""

    def test_logged_action_includes_processing_results(self):
        """LOGGED action should include processing_results in context."""
        results = [
            {
                "food_name": "chicken",
                "amount": 200.0,
                "unit": "g",
                "original_text": "200g chicken",
                "status": "LOGGED",
                "message": "Logged chicken (330kcal)",
            }
        ]
        state = _make_state(last_action="LOGGED", processing_results=results)

        ctx = _build_context(state)
        import json
        parsed = json.loads(ctx)

        assert parsed["last_action"] == "LOGGED"
        assert len(parsed["processing_results"]) == 1
        assert parsed["processing_results"][0]["status"] == "LOGGED"
        # consumed_at injects on LOG-family actions (gated, no longer unconditional).
        assert parsed["consumed_at"] == "2026-02-20T12:00:00"
        assert "query_logs" not in parsed

    def test_failed_action_includes_processing_results(self):
        """FAILED action should also include processing_results."""
        results = [
            {
                "food_name": "xyz",
                "amount": 100.0,
                "unit": "g",
                "original_text": "xyz",
                "status": "FAILED",
                "message": "No search results found for xyz",
            }
        ]
        state = _make_state(last_action="FAILED", processing_results=results)

        ctx = _build_context(state)
        import json
        parsed = json.loads(ctx)

        assert parsed["last_action"] == "FAILED"
        assert parsed["processing_results"][0]["status"] == "FAILED"

    def test_no_match_includes_processing_results(self):
        """NO_MATCH action should include processing_results."""
        state = _make_state(last_action="NO_MATCH", processing_results=[])

        ctx = _build_context(state)
        import json
        parsed = json.loads(ctx)

        assert parsed["last_action"] == "NO_MATCH"
        assert "processing_results" in parsed

    def test_query_stats_includes_query_logs(self):
        """QUERY_DAILY_STATS should include query_logs, not processing_results."""
        logs = [
            {
                "id": "log-uuid-1",
                "food_id": "food-uuid-10",
                "amount_g": 200.0,
                "calories": 330.0,
                "protein": 62.0,
                "carbs": 0.0,
                "fat": 7.2,
                "timestamp": datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc),
                "meal_type": "lunch",
                "original_text": "200g chicken",
            }
        ]
        state = _make_state(
            last_action="QUERY_DAILY_STATS",
            query_logs=logs,
            query_stats={
                "start_date": date(2026, 2, 18),
                "end_date": date(2026, 2, 20),
            },
        )

        ctx = _build_context(state)
        import json
        parsed = json.loads(ctx)

        assert parsed["last_action"] == "QUERY_DAILY_STATS"
        assert len(parsed["query_logs"]) == 1
        assert parsed["start_date"] == "2026-02-18"
        assert parsed["end_date"] == "2026-02-20"
        assert "processing_results" not in parsed

    def test_response_chitchat(self):
        """CHITCHAT action should produce a minimal context — no date or logging fields."""
        state = _make_state(last_action="CHITCHAT")

        ctx = _build_context(state)
        import json
        parsed = json.loads(ctx)

        assert parsed["last_action"] == "CHITCHAT"
        # Action-gated: consumed_at only injects on LOG-family actions.
        assert "consumed_at" not in parsed
        assert "processing_results" not in parsed
        assert "query_logs" not in parsed

    def test_empty_last_action(self):
        """Empty/missing last_action should produce minimal context."""
        state = _make_state(last_action="")

        ctx = _build_context(state)
        import json
        parsed = json.loads(ctx)

        assert parsed["last_action"] == ""
        assert "processing_results" not in parsed


# ---------------------------------------------------------------------------
# Tests for _current_time_str (timezone regression guard — bot UX audit F2)
# ---------------------------------------------------------------------------

class TestCurrentTimeStr:
    """A UTC instant must render as Israel local time — not UTC.

    Regression guard for bot UX audit F2: on UTC hosts (Railway) naive
    datetime.now() produced times 3h behind for Israeli users.
    """

    def test_utc_instant_renders_in_israel_local_time(self):
        # 2026-04-16 19:11 UTC == 22:11 Israel (IDT, UTC+3). 2026-04-16 is a Thursday.
        utc_moment = datetime(2026, 4, 16, 19, 11, tzinfo=timezone.utc)
        result = _current_time_str(now=utc_moment)
        assert "22:11" in result
        assert "Thursday" in result


# ---------------------------------------------------------------------------
# Tests for _format_daily_log (system-prompt injection formatter)
# ---------------------------------------------------------------------------

class TestFormatDailyLog:
    """The daily-log section must always render — empty state is a signal, not silence.

    Supports bot UX audit Fix #2 (daily log injection) + Fix #5 (empty-log opener).
    """

    def test_empty_log_renders_explicit_empty_section(self):
        result = _format_daily_log([])
        assert "## Today's Log" in result
        assert "Nothing logged yet today" in result

    def test_populated_log_renders_items(self):
        logs = [
            {
                "id": "log-1",
                "food_id": "food-1",
                "amount_g": 200.0,
                "calories": 330.0,
                "protein": 62.0,
                "carbs": 0.0,
                "fat": 7.2,
                "timestamp": "2026-04-17T14:00:00+03:00",
                "meal_type": None,
                "original_text": "200g chicken",
            },
            {
                "id": "log-2",
                "food_id": "food-2",
                "amount_g": 100.0,
                "calories": 89.0,
                "protein": 1.1,
                "carbs": 22.8,
                "fat": 0.3,
                "timestamp": "2026-04-17T09:30:00+03:00",
                "meal_type": None,
                "original_text": "banana",
            },
        ]
        result = _format_daily_log(logs)
        assert "## Today's Log" in result
        assert "200g chicken" in result
        assert "banana" in result
        # Israel-local timestamps passthrough
        assert "2026-04-17T14:00:00+03:00" in result
        assert "2026-04-17T09:30:00+03:00" in result
        # Macro formatting
        assert "330 kcal" in result
        assert "62.0g protein" in result
        # Uncategorized logs: NO totals block (preserves pre-Plan-3d shape)
        assert "## Today's Totals by Category" not in result

    def test_category_and_tag_annotation_rendered(self):
        """
        arrange: single log carrying category + tag from coach mapping.
        act:     _format_daily_log.
        assert:  the annotation `[protein,lean]` appears on the line.
        """
        logs = [
            {
                "id": "log-1",
                "food_id": "food-1",
                "amount_g": 200.0,
                "calories": 330.0,
                "protein": 62.0,
                "carbs": 0.0,
                "fat": 7.2,
                "timestamp": "2026-04-20T14:00:00+03:00",
                "meal_type": None,
                "original_text": "200g chicken",
                "category": "protein",
                "tag": "lean",
            }
        ]
        result = _format_daily_log(logs)
        assert "[protein,lean]" in result

    def test_category_only_annotation_when_no_tag(self):
        """
        arrange: log with category but no tag (e.g. carb food).
        act:     _format_daily_log.
        assert:  bracket annotation is `[carb]`, not `[carb,None]`.
        """
        logs = [
            {
                "id": "log-2",
                "food_id": "food-2",
                "amount_g": 200.0,
                "calories": 260.0,
                "protein": 5.0,
                "carbs": 56.0,
                "fat": 0.6,
                "timestamp": "2026-04-20T09:30:00+03:00",
                "meal_type": None,
                "original_text": "rice",
                "category": "carb",
                "tag": None,
            }
        ]
        result = _format_daily_log(logs)
        assert "[carb]" in result
        assert "[carb,None]" not in result
        assert "[carb,]" not in result

    def test_totals_block_computes_protein_and_carb_servings(self):
        """
        arrange: mixed log — 200g chicken (protein, 62g prot) + 200g rice (carb, 56g carbs).
        act:     _format_daily_log.
        assert:  totals block reports 3.1 protein servings (62/20) and 1.1 carb servings (56/50).
        """
        logs = [
            {
                "id": "p",
                "food_id": "p",
                "amount_g": 200.0,
                "calories": 330.0,
                "protein": 62.0,
                "carbs": 0.0,
                "fat": 7.2,
                "timestamp": "2026-04-20T14:00:00+03:00",
                "meal_type": None,
                "original_text": "chicken",
                "category": "protein",
                "tag": "lean",
            },
            {
                "id": "c",
                "food_id": "c",
                "amount_g": 200.0,
                "calories": 260.0,
                "protein": 5.0,
                "carbs": 56.0,
                "fat": 0.6,
                "timestamp": "2026-04-20T14:05:00+03:00",
                "meal_type": None,
                "original_text": "rice",
                "category": "carb",
                "tag": None,
            },
        ]
        result = _format_daily_log(logs)
        assert "## Today's Totals by Category" in result
        assert "3.1 protein servings" in result
        assert "1.1 carb servings" in result

    def test_totals_block_free_calories_reports_budget_units(self):
        """
        arrange: log with 100 kcal banana under free_calories.
        act:     _format_daily_log.
        assert:  free-calorie budget renders as 1.0 units.
        """
        logs = [
            {
                "id": "fc",
                "food_id": "fc",
                "amount_g": 120.0,
                "calories": 107.0,
                "protein": 1.3,
                "carbs": 27.0,
                "fat": 0.4,
                "timestamp": "2026-04-20T10:00:00+03:00",
                "meal_type": None,
                "original_text": "banana",
                "category": "free_calories",
                "tag": None,
            }
        ]
        result = _format_daily_log(logs)
        assert "## Today's Totals by Category" in result
        assert "free-calorie units" in result

    def test_uncategorized_logs_excluded_from_totals(self):
        """
        arrange: one categorized log + one uncategorized log.
        act:     _format_daily_log.
        assert:  totals block appears (one log has category) but excludes the uncategorized one.
        """
        logs = [
            {
                "id": "p",
                "food_id": "p",
                "amount_g": 100.0,
                "calories": 165.0,
                "protein": 31.0,
                "carbs": 0.0,
                "fat": 3.6,
                "timestamp": "2026-04-20T14:00:00+03:00",
                "meal_type": None,
                "original_text": "chicken",
                "category": "protein",
                "tag": "lean",
            },
            {
                "id": "u",
                "food_id": None,
                "amount_g": 50.0,
                "calories": 100.0,
                "protein": 5.0,
                "carbs": 15.0,
                "fat": 2.0,
                "timestamp": "2026-04-20T15:00:00+03:00",
                "meal_type": None,
                "original_text": "mystery food",
            },
        ]
        result = _format_daily_log(logs)
        # Totals block renders (because at least one log has a category)
        assert "## Today's Totals by Category" in result
        # Protein line reflects only the categorized 100g chicken (31g protein = 1.6 servings)
        assert "1.6 protein servings" in result
        # Uncategorized entry still appears in per-log section
        assert "mystery food" in result


# ---------------------------------------------------------------------------
# Tests for response_node (mock LLM)
# ---------------------------------------------------------------------------

class TestResponseNode:
    """Verify the response_node correctly constructs messages and invokes the LLM."""

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    async def test_logging_context_invokes_llm(self, mock_get_llm):
        """Node should invoke LLM with processing_results context for LOGGED action."""
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Got it! Logged 200g chicken — that's 330kcal.")
        mock_llm.ainvoke = AsyncMock(return_value=mock_ai_msg)
        mock_get_llm.return_value = mock_llm

        results = [
            {
                "food_name": "chicken",
                "amount": 200.0,
                "unit": "g",
                "original_text": "200g chicken",
                "status": "LOGGED",
                "message": "Logged chicken (330kcal)",
            }
        ]
        state = _make_state(last_action="LOGGED", processing_results=results)

        output = await response_node(state, TEST_RUNTIME_A)

        # Verify output structure
        assert "messages" in output
        assert len(output["messages"]) == 1
        assert output["messages"][0] == mock_ai_msg

        # Verify LLM was called with system message + conversation history
        call_args = mock_llm.ainvoke.call_args[0][0]
        assert len(call_args) == 2  # SystemMessage + 1 HumanMessage
        assert "processing_results" in call_args[0].content
        assert "Context JSON" in call_args[0].content

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    async def test_stats_context_invokes_llm(self, mock_get_llm):
        """Node should invoke LLM with query_logs context for QUERY_DAILY_STATS."""
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Today you consumed 1800kcal total.")
        mock_llm.ainvoke = AsyncMock(return_value=mock_ai_msg)
        mock_get_llm.return_value = mock_llm

        logs = [
            {
                "id": "log-uuid-1",
                "food_id": "food-uuid-10",
                "amount_g": 200.0,
                "calories": 330.0,
                "protein": 62.0,
                "carbs": 0.0,
                "fat": 7.2,
                "timestamp": datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc),
                "meal_type": None,
                "original_text": "200g chicken",
            }
        ]
        state = _make_state(
            last_action="QUERY_DAILY_STATS",
            query_logs=logs,
            messages=[HumanMessage(content="What did I eat today?")],
        )

        output = await response_node(state, TEST_RUNTIME_A)

        assert output["messages"][0] == mock_ai_msg

        call_args = mock_llm.ainvoke.call_args[0][0]
        # Scope these assertions to the Context JSON block — prompt body legitimately
        # mentions both terms in the "Before every reply" checklist, which would cause
        # a naive whole-prompt "not in" check to false-positive.
        system_content = call_args[0].content
        context_json = system_content.split("Context JSON:", 1)[1]
        assert "query_logs" in context_json
        assert "processing_results" not in context_json

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    async def test_no_match_context(self, mock_get_llm):
        """Node should handle NO_MATCH action and include processing_results."""
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Sorry, I couldn't find 'xyz' in the database.")
        mock_llm.ainvoke = AsyncMock(return_value=mock_ai_msg)
        mock_get_llm.return_value = mock_llm

        results = [
            {
                "food_name": "xyz",
                "amount": 100.0,
                "unit": "g",
                "original_text": "xyz",
                "status": "FAILED",
                "message": "No search results found for xyz",
            }
        ]
        state = _make_state(last_action="NO_MATCH", processing_results=results)

        output = await response_node(state, TEST_RUNTIME_A)

        assert output["messages"][0] == mock_ai_msg
        call_args = mock_llm.ainvoke.call_args[0][0]
        assert "FAILED" in call_args[0].content

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    async def test_empty_messages_history(self, mock_get_llm):
        """Node should handle state with no message history gracefully."""
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Hello! How can I help?")
        mock_llm.ainvoke = AsyncMock(return_value=mock_ai_msg)
        mock_get_llm.return_value = mock_llm

        state = _make_state(messages=[], last_action="CHITCHAT")

        output = await response_node(state, TEST_RUNTIME_A)

        assert output["messages"][0] == mock_ai_msg

        # Should have exactly 1 message: the SystemMessage (no history)
        call_args = mock_llm.ainvoke.call_args[0][0]
        assert len(call_args) == 1

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    async def test_preserves_full_conversation_history(self, mock_get_llm):
        """System message should be prepended, preserving all existing messages."""
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Done!")
        mock_llm.ainvoke = AsyncMock(return_value=mock_ai_msg)
        mock_get_llm.return_value = mock_llm

        history = [
            HumanMessage(content="I ate 200g rice"),
            AIMessage(content="Processing..."),
            HumanMessage(content="Also 100g chicken"),
        ]
        state = _make_state(messages=history, last_action="LOGGED")

        await response_node(state, TEST_RUNTIME_A)

        call_args = mock_llm.ainvoke.call_args[0][0]
        # SystemMessage + 3 history messages = 4
        assert len(call_args) == 4
        # First message is always the SystemMessage
        assert "FitPal" in call_args[0].content

    @patch("src.agents.nodes.response_node._SYSTEM_PROMPT", "You are FitPal, a helpful fitness and nutrition coach. Respond based on the provided context.")
    @patch("src.agents.nodes.response_node.get_llm_for_node")
    async def test_fallback_prompt_on_missing_file(self, mock_get_llm):
        """Node should work with fallback prompt content."""
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Fallback response")
        mock_llm.ainvoke = AsyncMock(return_value=mock_ai_msg)
        mock_get_llm.return_value = mock_llm

        state = _make_state(last_action="CHITCHAT")

        output = await response_node(state, TEST_RUNTIME_A)

        assert output["messages"][0] == mock_ai_msg
        call_args = mock_llm.ainvoke.call_args[0][0]
        # Fallback prompt should contain "FitPal"
        assert "FitPal" in call_args[0].content

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    async def test_current_time_in_system_message(self, mock_get_llm):
        """System message should include a current time prefix."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))
        mock_get_llm.return_value = mock_llm

        state = _make_state(last_action="CHITCHAT")
        await response_node(state, TEST_RUNTIME_A)

        call_args = mock_llm.ainvoke.call_args[0][0]
        system_content = call_args[0].content
        assert system_content.startswith("Current time:")

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    async def test_plan_injected_in_system_message(self, mock_get_llm):
        """System message should include the user's nutrition plan when set."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))
        mock_get_llm.return_value = mock_llm

        plan_text = "Daily targets: 2000 kcal, 150g protein."
        profile_with_plan = {**DEFAULT_DEV_PROFILE, "nutrition_plan": plan_text}
        runtime = MagicMock()
        runtime.context = ContextSchema(
            user_id=TEST_USER_A,
            user_profile=profile_with_plan,
        )

        state = _make_state(last_action="CHITCHAT")
        await response_node(state, runtime)

        call_args = mock_llm.ainvoke.call_args[0][0]
        system_content = call_args[0].content
        assert "## User Nutrition Plan" in system_content
        assert plan_text in system_content

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    async def test_no_plan_shows_placeholder(self, mock_get_llm):
        """System message should show fallback text when no plan is set."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))
        mock_get_llm.return_value = mock_llm

        profile_no_plan = {
            "name": "No Plan User",
            "height_cm": 170.0,
            "age": 30,
            "gender": "female",
        }
        runtime = MagicMock()
        runtime.context = ContextSchema(
            user_id=TEST_USER_A,
            user_profile=profile_no_plan,
        )

        state = _make_state(last_action="CHITCHAT")
        await response_node(state, runtime)

        call_args = mock_llm.ainvoke.call_args[0][0]
        system_content = call_args[0].content
        assert "No plan set for this user yet." in system_content

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    async def test_daily_log_section_shown_when_log_present(self, mock_get_llm):
        """System message should include the daily log section when context carries logs."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))
        mock_get_llm.return_value = mock_llm

        logs = [
            {
                "id": "log-1",
                "food_id": "food-1",
                "amount_g": 200.0,
                "calories": 330.0,
                "protein": 62.0,
                "carbs": 0.0,
                "fat": 7.2,
                "timestamp": "2026-04-17T14:00:00+03:00",
                "meal_type": None,
                "original_text": "200g chicken",
            }
        ]
        runtime = MagicMock()
        runtime.context = ContextSchema(
            user_id=TEST_USER_A,
            user_profile=DEFAULT_DEV_PROFILE.copy(),
        )

        state = _make_state(last_action="CHITCHAT", daily_log_today=logs)
        await response_node(state, runtime)

        call_args = mock_llm.ainvoke.call_args[0][0]
        system_content = call_args[0].content
        assert "## Today's Log" in system_content
        assert "200g chicken" in system_content
        # The injected log section is appended after the prompt body, and the
        # "Context JSON:" block is the last thing in the system message. So the
        # injected log lives between "---\n## User Profile" and "---\nContext JSON:"
        # — slice there to isolate it from prompt-body mentions of "## Today's Log"
        # (checklist step 2) and "Nothing logged yet today" (empty-log-opener rule).
        injected = system_content.split("## User Profile", 1)[1].split(
            "Context JSON:", 1
        )[0]
        assert "200g chicken" in injected
        assert "Nothing logged yet today" not in injected

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    async def test_daily_log_empty_section_shown_when_log_empty(self, mock_get_llm):
        """System message should explicitly state nothing logged when state.daily_log_today is empty."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))
        mock_get_llm.return_value = mock_llm

        runtime = MagicMock()
        runtime.context = ContextSchema(
            user_id=TEST_USER_A,
            user_profile=DEFAULT_DEV_PROFILE.copy(),
        )

        state = _make_state(last_action="CHITCHAT", daily_log_today=[])
        await response_node(state, runtime)

        call_args = mock_llm.ainvoke.call_args[0][0]
        system_content = call_args[0].content
        assert "## Today's Log" in system_content
        assert "Nothing logged yet today" in system_content
