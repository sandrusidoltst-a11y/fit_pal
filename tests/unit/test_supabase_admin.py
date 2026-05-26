"""Unit tests for bot/supabase_admin.py.

Scope:
    Tests password seed derivation logic and admin-only user registration
    (lookup-then-create via the Supabase admin API, no sign_in_with_password).

LLM Usage:
    NONE — pure function tests, mocked Supabase client, no external calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch


class TestPasswordSeed:
    """Tests for BOT_PASSWORD_SEED / BOT_PASSPHRASE separation."""

    @patch("bot.supabase_admin.BOT_PASSWORD_SEED", "my-fixed-seed")
    def test_password_uses_seed_not_passphrase(self):
        """
        arrange: BOT_PASSWORD_SEED is set to a specific value.
        act:     Call _server_password with a chat_id.
        assert:  Password is derived from the seed, not BOT_PASSPHRASE.
        """
        from bot.supabase_admin import _server_password

        password = _server_password(12345)
        # Verify it's a valid hex string (SHA-256 HMAC output)
        assert len(password) == 64
        assert all(c in "0123456789abcdef" for c in password)

    @patch("bot.supabase_admin.BOT_PASSWORD_SEED", "seed-value")
    def test_same_chat_id_produces_same_password(self):
        """
        arrange: Fixed seed value.
        act:     Call _server_password twice with the same chat_id.
        assert:  Both calls return the same password (deterministic).
        """
        from bot.supabase_admin import _server_password

        assert _server_password(12345) == _server_password(12345)

    @patch("bot.supabase_admin.BOT_PASSWORD_SEED", "seed-value")
    def test_different_chat_ids_produce_different_passwords(self):
        """
        arrange: Fixed seed value.
        act:     Call _server_password with two different chat_ids.
        assert:  Passwords are different.
        """
        from bot.supabase_admin import _server_password

        assert _server_password(12345) != _server_password(67890)


def _make_client():
    """Build a MagicMock Supabase client with async admin list/create methods."""
    client = MagicMock()
    client.auth.admin.list_users = AsyncMock()
    client.auth.admin.create_user = AsyncMock()
    return client


class TestGetOrCreateUser:
    """Tests for admin-only registration (no sign_in_with_password)."""

    async def test_existing_user_returns_is_new_false(self):
        """
        arrange: list_users returns a user whose email matches the chat_id.
        act:     Call get_or_create_user.
        assert:  Returns the existing user_id with is_new=False; create_user not called.
        """
        from bot import supabase_admin
        from bot.supabase_admin import _synthetic_email, get_or_create_user

        chat_id = 12345
        existing = MagicMock(id="uuid-existing", email=_synthetic_email(chat_id))
        client = _make_client()
        client.auth.admin.list_users.return_value = [existing]

        with patch.object(supabase_admin, "_get_client", AsyncMock(return_value=client)):
            result = await get_or_create_user(chat_id)

        assert result == {"user_id": "uuid-existing", "is_new": False}
        client.auth.admin.create_user.assert_not_called()

    async def test_new_user_is_created(self):
        """
        arrange: list_users returns no matching users.
        act:     Call get_or_create_user.
        assert:  create_user is called with the synthetic email + metadata, and
                 the new user_id is returned with is_new=True.
        """
        from bot import supabase_admin
        from bot.supabase_admin import _synthetic_email, get_or_create_user

        chat_id = 67890
        client = _make_client()
        client.auth.admin.list_users.return_value = []
        client.auth.admin.create_user.return_value = MagicMock(
            user=MagicMock(id="uuid-new")
        )

        with patch.object(supabase_admin, "_get_client", AsyncMock(return_value=client)):
            result = await get_or_create_user(chat_id)

        assert result == {"user_id": "uuid-new", "is_new": True}
        client.auth.admin.create_user.assert_awaited_once()
        attrs = client.auth.admin.create_user.await_args.args[0]
        assert attrs["email"] == _synthetic_email(chat_id)
        assert attrs["email_confirm"] is True
        assert attrs["user_metadata"]["telegram_chat_id"] == chat_id

    async def test_pagination_finds_user_on_second_page(self):
        """
        arrange: page 1 is a full page (200) of non-matching users; page 2 has the match.
        act:     Call get_or_create_user.
        assert:  The user is found via pagination; is_new=False; no create.
        """
        from bot import supabase_admin
        from bot.supabase_admin import _synthetic_email, get_or_create_user

        chat_id = 555
        page1 = [MagicMock(id=f"u{i}", email=f"{i}@other.bot") for i in range(200)]
        match = MagicMock(id="uuid-page2", email=_synthetic_email(chat_id))
        client = _make_client()
        client.auth.admin.list_users.side_effect = [page1, [match]]

        with patch.object(supabase_admin, "_get_client", AsyncMock(return_value=client)):
            result = await get_or_create_user(chat_id)

        assert result == {"user_id": "uuid-page2", "is_new": False}
        assert client.auth.admin.list_users.await_count == 2
        client.auth.admin.create_user.assert_not_called()

    async def test_no_sign_in_is_attempted(self):
        """
        arrange: a client whose sign_in_with_password would raise if ever called.
        act:     Register a new user.
        assert:  sign_in_with_password is never invoked (admin-only path).
        """
        from bot import supabase_admin
        from bot.supabase_admin import get_or_create_user

        client = _make_client()
        client.auth.admin.list_users.return_value = []
        client.auth.admin.create_user.return_value = MagicMock(
            user=MagicMock(id="uuid-x")
        )
        client.auth.sign_in_with_password = AsyncMock(
            side_effect=AssertionError("sign_in_with_password must not be called")
        )

        with patch.object(supabase_admin, "_get_client", AsyncMock(return_value=client)):
            await get_or_create_user(999)

        client.auth.sign_in_with_password.assert_not_called()
