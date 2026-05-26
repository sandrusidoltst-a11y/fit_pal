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

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BOT_PASSPHRASE = os.environ.get("BOT_PASSPHRASE", "")
BOT_PASSWORD_SEED = os.environ.get("BOT_PASSWORD_SEED", "") or BOT_PASSPHRASE
BOT_EMAIL_DOMAIN = os.environ.get("BOT_EMAIL_DOMAIN", "telegram.fitpal.bot")

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
    return f"{telegram_chat_id}@{BOT_EMAIL_DOMAIN}"


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


async def _find_user_by_email(client: AsyncClient, email: str):
    """Return the auth user with this email, or None.

    Admin-only: paginates the admin list endpoint and never signs in, so the
    shared client's Authorization header is never overwritten with a user JWT.
    """
    page = 1
    per_page = 200
    target = email.lower()
    while True:
        users = await client.auth.admin.list_users(page=page, per_page=per_page)
        if not users:
            return None
        for user in users:
            if (user.email or "").lower() == target:
                return user
        if len(users) < per_page:
            return None
        page += 1


async def get_or_create_user(telegram_chat_id: int) -> dict:
    """Get or create a Supabase Auth user for a Telegram chat ID.

    Admin-API only: looks up by synthetic email, creates if missing. Never calls
    sign_in_with_password, so the shared admin client's Authorization header stays
    the service key (avoids the expired-user-JWT 403 on admin/users).

    Returns dict with keys: user_id, is_new.
    """
    email = _synthetic_email(telegram_chat_id)
    client = await _get_client()

    existing = await _find_user_by_email(client, email)
    if existing is not None:
        logger.info("Found existing user for chat_id=%s", telegram_chat_id)
        return {"user_id": existing.id, "is_new": False}

    response = await client.auth.admin.create_user(
        {
            "email": email,
            "password": _server_password(telegram_chat_id),
            "email_confirm": True,
            "user_metadata": {"telegram_chat_id": telegram_chat_id},
        }
    )
    logger.info("Created new user for chat_id=%s", telegram_chat_id)
    return {"user_id": response.user.id, "is_new": True}
