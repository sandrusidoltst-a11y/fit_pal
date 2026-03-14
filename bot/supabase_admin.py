"""Supabase admin helpers for Telegram user management and JWT generation.

Handles auto-registration of Telegram users in Supabase Auth and session
management (sign-in, token refresh). Uses synthetic emails and server-side
deterministic passwords so Telegram users never need credentials.
"""

import hashlib
import hmac
import logging
import os

from supabase import AsyncClient, acreate_client
from supabase_auth.errors import AuthApiError

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BOT_PASSPHRASE = os.environ.get("BOT_PASSPHRASE", "")
BOT_PASSWORD_SEED = os.environ.get("BOT_PASSWORD_SEED", "") or BOT_PASSPHRASE

_supabase_admin: AsyncClient | None = None


async def _get_client() -> AsyncClient:
    """Lazy-initialize the Supabase admin client (avoids import-time errors when env vars are unset)."""
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = await acreate_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
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
    Uses HMAC with BOT_PASSWORD_SEED as key. This is separate from
    BOT_PASSPHRASE so the invite code can be rotated without breaking
    existing user accounts.
    """
    return hmac.new(
        BOT_PASSWORD_SEED.encode(),
        str(telegram_chat_id).encode(),
        hashlib.sha256,
    ).hexdigest()


async def get_or_create_user(telegram_chat_id: int) -> dict:
    """Get or create a Supabase Auth user for a Telegram chat ID.

    Returns dict with keys: user_id, access_token, refresh_token, is_new.
    """
    email = _synthetic_email(telegram_chat_id)
    password = _server_password(telegram_chat_id)
    client = await _get_client()

    # Try signing in first (existing user)
    try:
        response = await client.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        logger.info("Signed in existing user for chat_id=%s", telegram_chat_id)
        return {
            "user_id": response.user.id,
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "is_new": False,
        }
    except AuthApiError:
        logger.debug("User not found for chat_id=%s, creating new user", telegram_chat_id)

    # Create new user via admin API
    await client.auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"telegram_chat_id": telegram_chat_id},
        }
    )

    # Sign in to get a session with tokens
    response = await client.auth.sign_in_with_password(
        {"email": email, "password": password}
    )
    logger.info("Created new user for chat_id=%s", telegram_chat_id)
    return {
        "user_id": response.user.id,
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
        "is_new": True,
    }


async def refresh_session(refresh_token: str) -> dict:
    """Refresh an expired session using the refresh token.

    Returns dict with keys: access_token, refresh_token.
    """
    client = await _get_client()
    response = await client.auth.refresh_session(refresh_token)
    logger.info("Refreshed session")
    return {
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
    }
