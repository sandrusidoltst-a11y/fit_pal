from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.nodes.response_node import _build_context, response_node


# ---------------------------------------------------------------------------
# Helper: minimal AgentState dict
# ---------------------------------------------------------------------------

def _make_state(**overrides):
    """Build a minimal AgentState dict with sensible defaults."""
    state = {
        "messages": [HumanMessage(content="I ate 200g chicken")],
        "pending_food_items": [],
        "consumed_at": datetime(2026, 2, 20, 12, 0),
        "start_date": None,
        "end_date": None,
        "last_action": "LOGGED",
        "search_results": [],
        "selected_food_id": None,
        "processing_results": [],
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
        assert "daily_log_report" not in parsed

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

    def test_query_stats_includes_daily_log_report(self):
        """QUERY_DAILY_STATS should include daily_log_report, not processing_results."""
        logs = [
            {
                "id": 1,
                "food_id": 10,
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
            daily_log_report=logs,
            start_date=date(2026, 2, 18),
            end_date=date(2026, 2, 20),
        )

        ctx = _build_context(state)
        import json
        parsed = json.loads(ctx)

        assert parsed["last_action"] == "QUERY_DAILY_STATS"
        assert len(parsed["daily_log_report"]) == 1
        assert parsed["start_date"] == "2026-02-18"
        assert parsed["end_date"] == "2026-02-20"
        assert "processing_results" not in parsed

    def test_response_chitchat(self):
        """CHITCHAT action should only include last_action and consumed_at."""
        state = _make_state(last_action="CHITCHAT")

        ctx = _build_context(state)
        import json
        parsed = json.loads(ctx)

        assert parsed["last_action"] == "CHITCHAT"
        assert "consumed_at" in parsed
        assert "processing_results" not in parsed
        assert "daily_log_report" not in parsed

    def test_empty_last_action(self):
        """Empty/missing last_action should produce minimal context."""
        state = _make_state(last_action="")

        ctx = _build_context(state)
        import json
        parsed = json.loads(ctx)

        assert parsed["last_action"] == ""
        assert "processing_results" not in parsed


# ---------------------------------------------------------------------------
# Tests for response_node (mock LLM)
# ---------------------------------------------------------------------------

class TestResponseNode:
    """Verify the response_node correctly constructs messages and invokes the LLM."""

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    def test_logging_context_invokes_llm(self, mock_get_llm):
        """Node should invoke LLM with processing_results context for LOGGED action."""
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Got it! Logged 200g chicken — that's 330kcal.")
        mock_llm.invoke.return_value = mock_ai_msg
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

        output = response_node(state)

        # Verify output structure
        assert "messages" in output
        assert len(output["messages"]) == 1
        assert output["messages"][0] == mock_ai_msg

        # Verify LLM was called with system message + conversation history
        call_args = mock_llm.invoke.call_args[0][0]
        assert len(call_args) == 2  # SystemMessage + 1 HumanMessage
        assert "processing_results" in call_args[0].content
        assert "Context JSON" in call_args[0].content

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    def test_stats_context_invokes_llm(self, mock_get_llm):
        """Node should invoke LLM with daily_log_report context for QUERY_DAILY_STATS."""
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Today you consumed 1800kcal total.")
        mock_llm.invoke.return_value = mock_ai_msg
        mock_get_llm.return_value = mock_llm

        logs = [
            {
                "id": 1,
                "food_id": 10,
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
            daily_log_report=logs,
            messages=[HumanMessage(content="What did I eat today?")],
        )

        output = response_node(state)

        assert output["messages"][0] == mock_ai_msg

        call_args = mock_llm.invoke.call_args[0][0]
        assert "daily_log_report" in call_args[0].content
        assert "processing_results" not in call_args[0].content

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    def test_no_match_context(self, mock_get_llm):
        """Node should handle NO_MATCH action and include processing_results."""
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Sorry, I couldn't find 'xyz' in the database.")
        mock_llm.invoke.return_value = mock_ai_msg
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

        output = response_node(state)

        assert output["messages"][0] == mock_ai_msg
        call_args = mock_llm.invoke.call_args[0][0]
        assert "FAILED" in call_args[0].content

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    def test_empty_messages_history(self, mock_get_llm):
        """Node should handle state with no message history gracefully."""
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Hello! How can I help?")
        mock_llm.invoke.return_value = mock_ai_msg
        mock_get_llm.return_value = mock_llm

        state = _make_state(messages=[], last_action="CHITCHAT")

        output = response_node(state)

        assert output["messages"][0] == mock_ai_msg

        # Should have exactly 1 message: the SystemMessage (no history)
        call_args = mock_llm.invoke.call_args[0][0]
        assert len(call_args) == 1

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    def test_preserves_full_conversation_history(self, mock_get_llm):
        """System message should be prepended, preserving all existing messages."""
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Done!")
        mock_llm.invoke.return_value = mock_ai_msg
        mock_get_llm.return_value = mock_llm

        history = [
            HumanMessage(content="I ate 200g rice"),
            AIMessage(content="Processing..."),
            HumanMessage(content="Also 100g chicken"),
        ]
        state = _make_state(messages=history, last_action="LOGGED")

        response_node(state)

        call_args = mock_llm.invoke.call_args[0][0]
        # SystemMessage + 3 history messages = 4
        assert len(call_args) == 4
        # First message is always the SystemMessage
        assert "FitPal" in call_args[0].content

    @patch("src.agents.nodes.response_node.get_llm_for_node")
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_fallback_prompt_on_missing_file(self, mock_open, mock_get_llm):
        """Node should use fallback prompt if response_generator.md is missing."""
        mock_llm = MagicMock()
        mock_ai_msg = AIMessage(content="Fallback response")
        mock_llm.invoke.return_value = mock_ai_msg
        mock_get_llm.return_value = mock_llm

        state = _make_state(last_action="CHITCHAT")

        output = response_node(state)

        assert output["messages"][0] == mock_ai_msg
        call_args = mock_llm.invoke.call_args[0][0]
        # Fallback prompt should contain "FitPal"
        assert "FitPal" in call_args[0].content
