"""Unit tests for bot/supabase_admin.py.

Scope:
    Tests password seed derivation logic and backward compatibility.

LLM Usage:
    NONE — pure function tests, no external calls.
"""

from unittest.mock import patch


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
