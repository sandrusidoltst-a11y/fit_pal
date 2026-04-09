"""Unit tests for bot onboarding flow.

Scope:
    Tests the deterministic onboarding Q&A for new users, including
    validation of inputs and profile saving. All external calls are mocked.

LLM Usage:
    NONE — onboarding is fully deterministic.
"""

from datetime import datetime, timezone
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
    msg.chat.id = 99999
    msg.text = ""
    msg.answer = AsyncMock()
    return msg


def _onboarding_session(step="name"):
    """Helper to create a session in onboarding state."""
    return {
        "user_id": "uuid-new-user",
        "thread_id": "thread-onb",
        "last_activity": datetime.now(timezone.utc),
        "interrupted": False,
        "onboarding_step": step,
        "onboarding_data": {},
        "user_profile": None,
    }


class TestOnboardingStart:
    """Test that onboarding starts for new users."""

    @patch("bot.gateway._create_thread", new_callable=AsyncMock, return_value="thread-new")
    @patch("bot.gateway.get_or_create_user", new_callable=AsyncMock)
    async def test_new_user_starts_onboarding(self, mock_get_or_create, mock_create_thread, mock_message):
        """
        arrange: user sends correct passphrase, get_or_create_user returns is_new=True.
        act:     handle_message processes the passphrase.
        assert:  session created with onboarding_step="name", welcome + name question sent.
        """
        mock_get_or_create.return_value = {
            "user_id": "uuid-new",
            "access_token": "tok",
            "refresh_token": "ref",
            "is_new": True,
        }
        mock_message.text = gw.BOT_PASSPHRASE or "test-passphrase"
        with patch.object(gw, "BOT_PASSPHRASE", mock_message.text):
            await gw.handle_message(mock_message)

        session = gw.user_sessions[mock_message.chat.id]
        assert session["onboarding_step"] == "name"
        assert mock_message.answer.call_count == 2  # welcome + name question

    @patch("bot.gateway._create_thread", new_callable=AsyncMock, return_value="thread-existing")
    @patch("bot.gateway.get_or_create_user", new_callable=AsyncMock)
    async def test_existing_user_skips_onboarding(self, mock_get_or_create, mock_create_thread, mock_message):
        """
        arrange: user sends correct passphrase, get_or_create_user returns is_new=False.
        act:     handle_message processes the passphrase.
        assert:  session created with onboarding_step=None, welcome back message sent.
        """
        mock_get_or_create.return_value = {
            "user_id": "uuid-existing",
            "access_token": "tok",
            "refresh_token": "ref",
            "is_new": False,
        }
        mock_message.text = gw.BOT_PASSPHRASE or "test-passphrase"
        with patch.object(gw, "BOT_PASSPHRASE", mock_message.text):
            await gw.handle_message(mock_message)

        session = gw.user_sessions[mock_message.chat.id]
        assert session["onboarding_step"] is None
        assert mock_message.answer.call_count == 1


class TestOnboardingCollectsData:
    """Test that onboarding collects name, height, age, gender step by step."""

    async def test_onboarding_collects_name(self, mock_message):
        """
        arrange: session at onboarding_step="name".
        act:     user sends "Dolev".
        assert:  name stored, step advances to "height", height question sent.
        """
        gw.user_sessions[mock_message.chat.id] = _onboarding_session("name")
        mock_message.text = "Dolev"

        await gw._handle_onboarding(mock_message, gw.user_sessions[mock_message.chat.id])

        session = gw.user_sessions[mock_message.chat.id]
        assert session["onboarding_data"]["name"] == "Dolev"
        assert session["onboarding_step"] == "height"
        mock_message.answer.assert_called_once()

    async def test_onboarding_validates_height(self, mock_message):
        """
        arrange: session at onboarding_step="height".
        act:     user sends non-numeric "tall".
        assert:  error message sent, step stays at "height".
        """
        gw.user_sessions[mock_message.chat.id] = _onboarding_session("height")
        mock_message.text = "tall"

        result = await gw._handle_onboarding(mock_message, gw.user_sessions[mock_message.chat.id])

        assert result is True
        session = gw.user_sessions[mock_message.chat.id]
        assert session["onboarding_step"] == "height"
        assert "number" in mock_message.answer.call_args[0][0].lower()

    async def test_onboarding_validates_age(self, mock_message):
        """
        arrange: session at onboarding_step="age".
        act:     user sends non-integer "twenty".
        assert:  error message sent, step stays at "age".
        """
        gw.user_sessions[mock_message.chat.id] = _onboarding_session("age")
        mock_message.text = "twenty"

        result = await gw._handle_onboarding(mock_message, gw.user_sessions[mock_message.chat.id])

        assert result is True
        session = gw.user_sessions[mock_message.chat.id]
        assert session["onboarding_step"] == "age"

    async def test_onboarding_validates_gender(self, mock_message):
        """
        arrange: session at onboarding_step="gender".
        act:     user sends invalid "xyz".
        assert:  error message sent, step stays at "gender".
        """
        gw.user_sessions[mock_message.chat.id] = _onboarding_session("gender")
        mock_message.text = "xyz"

        result = await gw._handle_onboarding(mock_message, gw.user_sessions[mock_message.chat.id])

        assert result is True
        session = gw.user_sessions[mock_message.chat.id]
        assert session["onboarding_step"] == "gender"


class TestOnboardingCompletion:
    """Test that onboarding saves profile when all steps complete."""

    @patch("bot.gateway._save_user_profile", new_callable=AsyncMock)
    async def test_onboarding_completes_saves_profile(self, mock_save, mock_message):
        """
        arrange: session at onboarding_step="gender" with name/height/age already collected.
        act:     user sends "male".
        assert:  _save_user_profile called with correct data, step set to None.
        """
        session = _onboarding_session("gender")
        session["onboarding_data"] = {"name": "Dolev", "height_cm": 180.0, "age": 28}
        gw.user_sessions[mock_message.chat.id] = session
        mock_message.text = "male"

        result = await gw._handle_onboarding(mock_message, gw.user_sessions[mock_message.chat.id])

        assert result is True
        mock_save.assert_called_once_with(
            "uuid-new-user",
            {"name": "Dolev", "height_cm": 180.0, "age": 28, "gender": "male"},
        )
        assert gw.user_sessions[mock_message.chat.id]["onboarding_step"] is None
        assert gw.user_sessions[mock_message.chat.id]["user_profile"]["name"] == "Dolev"
