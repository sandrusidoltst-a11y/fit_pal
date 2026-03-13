"""Supabase admin helpers for Telegram user management and JWT generation.

Handles auto-registration of Telegram users in Supabase Auth and session
management (sign-in, token refresh). Uses synthetic emails and server-side
deterministic passwords so Telegram users never need credentials.
"""

import hashlib
import hmac
import os

from supabase import Client, create_client
from supabase_auth.errors import AuthApiError

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BOT_PASSPHRASE = os.environ.get("BOT_PASSPHRASE", "")

_supabase_admin: Client | None = None


def _get_client() -> Client:
    """Lazy-initialize the Supabase admin client (avoids import-time errors when env vars are unset)."""
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _supabase_admin


def _synthetic_email(telegram_chat_id: int) -> str:
    """Generate a stable synthetic email for a Telegram user.

    Supabase Auth requires email or phone -- this synthetic email maps
    chat_id to a unique identifier without needing a real inbox.
    email_confirm=True on creation skips verification.
    """
    return f"{telegram_chat_id}@telegram.fitpal.bot"


def _server_password(telegram_chat_id: int) -> str:
    """Generate a deterministic server-side password for a Telegram user.

    The password is never shown to the user -- it's an implementation detail
    that allows the gateway to call sign_in_with_password() to obtain a JWT.
    Uses HMAC with BOT_PASSPHRASE as key so passwords change if passphrase rotates.
    """
    return hmac.new(
        BOT_PASSPHRASE.encode(),
        str(telegram_chat_id).encode(),
        hashlib.sha256,
    ).hexdigest()


def get_or_create_user(telegram_chat_id: int) -> dict:
    """Get or create a Supabase Auth user for a Telegram chat ID.

    Returns dict with keys: user_id, access_token, refresh_token, is_new.
    """
    email = _synthetic_email(telegram_chat_id)
    password = _server_password(telegram_chat_id)

    # Try signing in first (existing user)
    try:
        response = _get_client().auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        return {
            "user_id": response.user.id,
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "is_new": False,
        }
    except AuthApiError:
        pass  # User doesn't exist yet, create below

    # Create new user via admin API
    _get_client().auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"telegram_chat_id": telegram_chat_id},
        }
    )

    # Sign in to get a session with tokens
    response = _get_client().auth.sign_in_with_password(
        {"email": email, "password": password}
    )
    return {
        "user_id": response.user.id,
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
        "is_new": True,
    }


def refresh_session(refresh_token: str) -> dict:
    """Refresh an expired session using the refresh token.

    Returns dict with keys: access_token, refresh_token.
    """
    response = _get_client().auth.refresh_session(refresh_token)
    return {
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
    }
