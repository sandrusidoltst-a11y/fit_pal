"""Unit tests for the Telegram bot gateway logic.

Scope:
    Tests passphrase flow, message relay to LangGraph, thread management,
    and HITL interrupt/resume. All external calls (httpx, supabase) are mocked.

LLM Usage:
    NONE — all external calls are mocked.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bot.gateway as gw


@pytest.fixture(autouse=True)
def clear_sessions():
    """Clear user_sessions before each test."""
    gw.user_sessions.clear()
    yield
    gw.user_sessions.clear()


@pytest.fixture
def mock_message():
    """Create a mock aiogram Message."""
    msg = AsyncMock()
    msg.chat = MagicMock()
    msg.chat.id = 12345
    msg.text = "hello"
    msg.answer = AsyncMock()
    return msg


class TestPassphraseFlow:
    """Tests for initial passphrase-based access control."""

    async def test_unknown_user_prompted_for_passphrase(self, mock_message):
        """
        arrange: Message from unknown chat_id with text 'hello'.
        act:     Process message.
        assert:  Bot replies with invite code prompt.
        """
        mock_message.text = "hello"

        await gw.handle_message(mock_message)

        mock_message.answer.assert_called_once_with(
            "Send the invite code to get started."
        )

    async def test_wrong_passphrase_rejected(self, mock_message):
        """
        arrange: Message from unknown chat_id with wrong passphrase.
        act:     Process message.
        assert:  Bot replies with invite code prompt (same as unknown).
        """
        mock_message.text = "wrong-passphrase"

        await gw.handle_message(mock_message)

        mock_message.answer.assert_called_once_with(
            "Send the invite code to get started."
        )

    @patch("bot.gateway.BOT_PASSPHRASE", "secret123")
    @patch("bot.gateway.get_or_create_user", new_callable=AsyncMock)
    @patch("bot.gateway._create_thread", new_callable=AsyncMock)
    async def test_correct_passphrase_registers_user(
        self, mock_create_thread, mock_get_or_create, mock_message
    ):
        """
        arrange: Message from unknown chat_id with correct passphrase.
        act:     Process message.
        assert:  Bot replies with welcome, user added to sessions.
        """
        mock_message.text = "secret123"
        mock_get_or_create.return_value = {
            "user_id": "uuid-abc",
            "access_token": "jwt-token",
            "refresh_token": "refresh-token",
            "is_new": True,
        }
        mock_create_thread.return_value = "thread-123"

        await gw.handle_message(mock_message)

        mock_message.answer.assert_called_once_with(
            "Welcome to FitPal! You can start logging food now."
        )
        assert 12345 in gw.user_sessions
        assert gw.user_sessions[12345]["user_id"] == "uuid-abc"
        assert gw.user_sessions[12345]["thread_id"] == "thread-123"

    async def test_non_text_message_rejected(self, mock_message):
        """
        arrange: Message with no text (e.g., photo, sticker).
        act:     Process message.
        assert:  Bot replies that only text is supported.
        """
        mock_message.text = None

        await gw.handle_message(mock_message)

        mock_message.answer.assert_called_once_with(
            "I can only process text messages."
        )


class TestMessageRelay:
    """Tests for authenticated message relay to LangGraph."""

    @patch("bot.gateway._call_langgraph", new_callable=AsyncMock)
    @patch("bot.gateway._check_interrupted", new_callable=AsyncMock)
    async def test_authenticated_user_message_relayed(
        self, mock_check, mock_call, mock_message
    ):
        """
        arrange: Known user in sessions, message 'I ate 200g of chicken'.
        act:     Process message.
        assert:  LangGraph called with correct input, bot replies with response.
        """
        gw.user_sessions[12345] = {
            "user_id": "uuid-abc",
            "thread_id": "thread-123",
            "last_activity": datetime.now(timezone.utc),
            "access_token": "jwt-token",
            "refresh_token": "refresh-token",
            "interrupted": False,
        }
        mock_message.text = "I ate 200g of chicken"
        mock_call.return_value = {
            "messages": [
                {"role": "human", "content": "I ate 200g of chicken"},
                {"role": "assistant", "content": "Got it! Logged 200g of chicken."},
            ]
        }
        mock_check.return_value = False

        await gw.handle_message(mock_message)

        mock_call.assert_called_once_with(
            "thread-123",
            "jwt-token",
            input={"messages": [{"role": "human", "content": "I ate 200g of chicken"}]},
        )
        mock_message.answer.assert_called_once_with(
            "Got it! Logged 200g of chicken."
        )

    @patch("bot.gateway._call_langgraph", new_callable=AsyncMock)
    @patch("bot.gateway._check_interrupted", new_callable=AsyncMock)
    async def test_interrupted_state_resumes_with_command(
        self, mock_check, mock_call, mock_message
    ):
        """
        arrange: Known user with thread in interrupted state.
        act:     Process 'yes' message.
        assert:  LangGraph called with resume command, not new input.
        """
        gw.user_sessions[12345] = {
            "user_id": "uuid-abc",
            "thread_id": "thread-123",
            "last_activity": datetime.now(timezone.utc),
            "access_token": "jwt-token",
            "refresh_token": "refresh-token",
            "interrupted": True,
        }
        mock_message.text = "yes"
        mock_call.return_value = {
            "messages": [
                {"role": "assistant", "content": "Food logged successfully!"},
            ]
        }
        mock_check.return_value = False

        await gw.handle_message(mock_message)

        mock_call.assert_called_once_with(
            "thread-123",
            "jwt-token",
            command={"resume": "yes"},
        )


class TestThreadManagement:
    """Tests for session timeout and thread recreation."""

    @patch("bot.gateway._create_thread", new_callable=AsyncMock)
    @patch("bot.gateway._call_langgraph", new_callable=AsyncMock)
    @patch("bot.gateway._check_interrupted", new_callable=AsyncMock)
    async def test_stale_session_creates_new_thread(
        self, mock_check, mock_call, mock_create_thread, mock_message
    ):
        """
        arrange: Known user with last_activity 45 min ago.
        act:     Process message.
        assert:  New thread created before relaying message.
        """
        gw.user_sessions[12345] = {
            "user_id": "uuid-abc",
            "thread_id": "old-thread",
            "last_activity": datetime.now(timezone.utc) - timedelta(minutes=45),
            "access_token": "jwt-token",
            "refresh_token": "refresh-token",
            "interrupted": True,  # Should reset after new thread
        }
        mock_create_thread.return_value = "new-thread-456"
        mock_message.text = "I ate rice"
        mock_call.return_value = {
            "messages": [{"role": "assistant", "content": "Logged!"}]
        }
        mock_check.return_value = False

        await gw.handle_message(mock_message)

        mock_create_thread.assert_called_once_with("jwt-token")
        assert gw.user_sessions[12345]["thread_id"] == "new-thread-456"
        assert gw.user_sessions[12345]["interrupted"] is False

    @patch("bot.gateway._call_langgraph", new_callable=AsyncMock)
    @patch("bot.gateway._check_interrupted", new_callable=AsyncMock)
    async def test_fresh_session_reuses_thread(
        self, mock_check, mock_call, mock_message
    ):
        """
        arrange: Known user with last_activity 5 min ago.
        act:     Process message.
        assert:  Same thread reused (no _create_thread call).
        """
        gw.user_sessions[12345] = {
            "user_id": "uuid-abc",
            "thread_id": "existing-thread",
            "last_activity": datetime.now(timezone.utc) - timedelta(minutes=5),
            "access_token": "jwt-token",
            "refresh_token": "refresh-token",
            "interrupted": False,
        }
        mock_message.text = "I ate rice"
        mock_call.return_value = {
            "messages": [{"role": "assistant", "content": "Logged!"}]
        }
        mock_check.return_value = False

        await gw.handle_message(mock_message)

        assert gw.user_sessions[12345]["thread_id"] == "existing-thread"


class TestHITLFlow:
    """Tests for Human-in-the-Loop interrupt detection."""

    @patch("bot.gateway._call_langgraph", new_callable=AsyncMock)
    @patch("bot.gateway._check_interrupted", new_callable=AsyncMock)
    async def test_interrupt_detected_sets_flag(
        self, mock_check, mock_call, mock_message
    ):
        """
        arrange: Known user, LangGraph pauses at interrupt after run.
        act:     Process food logging message.
        assert:  Session marked as interrupted.
        """
        gw.user_sessions[12345] = {
            "user_id": "uuid-abc",
            "thread_id": "thread-123",
            "last_activity": datetime.now(timezone.utc),
            "access_token": "jwt-token",
            "refresh_token": "refresh-token",
            "interrupted": False,
        }
        mock_message.text = "I ate 200g of chicken"
        mock_call.return_value = {
            "messages": [
                {"role": "assistant", "content": "Please confirm: 200g chicken..."},
            ]
        }
        mock_check.return_value = True  # Graph is interrupted

        await gw.handle_message(mock_message)

        assert gw.user_sessions[12345]["interrupted"] is True

    @patch("bot.gateway._call_langgraph", new_callable=AsyncMock)
    @patch("bot.gateway._check_interrupted", new_callable=AsyncMock)
    async def test_resume_clears_interrupt_flag(
        self, mock_check, mock_call, mock_message
    ):
        """
        arrange: Known user with interrupted thread, user confirms.
        act:     Process 'yes' message (resume).
        assert:  Session interrupted flag cleared after successful resume.
        """
        gw.user_sessions[12345] = {
            "user_id": "uuid-abc",
            "thread_id": "thread-123",
            "last_activity": datetime.now(timezone.utc),
            "access_token": "jwt-token",
            "refresh_token": "refresh-token",
            "interrupted": True,
        }
        mock_message.text = "yes"
        mock_call.return_value = {
            "messages": [{"role": "assistant", "content": "Logged successfully!"}]
        }
        mock_check.return_value = False  # Run completed, no more interrupt

        await gw.handle_message(mock_message)

        assert gw.user_sessions[12345]["interrupted"] is False
