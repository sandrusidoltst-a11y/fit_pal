"""Telegram bot gateway for FitPal.

Connects Telegram users to the LangGraph FitPal agent via webhook (production)
or polling (local development). Set POLLING_MODE=true for local dev.

Handles passphrase-based access control, auto-registration via Supabase,
onboarding profile collection, message relay, and HITL interrupt/resume flow.
"""

import asyncio
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, TypedDict

import httpx
import structlog
from dotenv import load_dotenv

# Load .env before any imports that read env vars at module level (e.g. supabase_admin)
load_dotenv()

from aiogram import Bot, Dispatcher, Router  # noqa: E402
from aiogram.types import Message  # noqa: E402
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application  # noqa: E402
from aiohttp import web  # noqa: E402

from bot.supabase_admin import get_or_create_user  # noqa: E402
from src.database import get_async_db_session  # noqa: E402
from src.i18n import MESSAGES  # noqa: E402
from src.services.user_profile_service import create_user_profile, get_user_profile  # noqa: E402

logger = structlog.get_logger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_BASE_URL", "")
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/webhook")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
BOT_PASSPHRASE = os.environ.get("BOT_PASSPHRASE", "")
LANGGRAPH_API_URL = os.environ.get("LANGGRAPH_API_URL", "http://localhost:2024")
INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "")
POLLING_MODE = os.environ.get("POLLING_MODE", "").lower() in ("true", "1", "yes")

ASSISTANT_ID = "fitpal"
SESSION_TIMEOUT = timedelta(minutes=30)

ONBOARDING_ORDER = ["name", "height", "age", "gender"]


def _onboarding_question(step: str) -> str:
    """Look up the localized prompt for a given onboarding step."""
    return MESSAGES[f"onboarding_q_{step}"]  # type: ignore[literal-required]


class SessionData(TypedDict):
    """Telegram user session -- tracks user identity and LangGraph thread state."""

    user_id: str
    thread_id: str
    last_activity: datetime
    interrupted: bool
    onboarding_step: Optional[str]
    onboarding_data: dict
    user_profile: Optional[dict]


# In-memory session store: chat_id -> session dict
user_sessions: dict[int, SessionData] = {}

router = Router()


def _internal_headers() -> dict[str, str]:
    """Return headers with the shared secret for service-to-service auth."""
    return {"X-Internal-Token": INTERNAL_API_SECRET}


async def _create_thread() -> str:
    """Create a new LangGraph thread and return its ID."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{LANGGRAPH_API_URL}/threads",
            headers=_internal_headers(),
            json={},
        )
        response.raise_for_status()
        return response.json()["thread_id"]


async def _call_langgraph(
    thread_id: str,
    user_id: str,
    *,
    input: dict | None = None,
    command: dict | None = None,
    user_profile: dict | None = None,
) -> dict:
    """Call LangGraph runs/wait endpoint and return the result."""
    body: dict = {
        "assistant_id": ASSISTANT_ID,
        "context": {"user_id": user_id},
    }
    if user_profile:
        body["context"]["user_profile"] = user_profile
    if input is not None:
        body["input"] = input
    if command is not None:
        body["command"] = command

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{LANGGRAPH_API_URL}/threads/{thread_id}/runs/wait",
            headers=_internal_headers(),
            json=body,
        )
        response.raise_for_status()
        return response.json()


async def _get_interrupt_state(thread_id: str) -> tuple[bool, str | None]:
    """Check if the graph is paused at an interrupt and extract the interrupt value.

    Returns (is_interrupted, formatted_text). If interrupted, formatted_text
    contains the human-readable prompt from the interrupt value.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{LANGGRAPH_API_URL}/threads/{thread_id}/state",
            headers=_internal_headers(),
        )
        response.raise_for_status()
        state = response.json()
        tasks = state.get("tasks", [])
        if not tasks:
            return False, None

        # Extract interrupt value from the first pending task
        interrupts = tasks[0].get("interrupts", [])
        if not interrupts:
            return True, None

        value = interrupts[0].get("value")
        if isinstance(value, dict):
            return True, _format_interrupt_value(value)
        elif isinstance(value, str):
            return True, value

        return True, None


def _format_interrupt_value(value: dict) -> str:
    """Format an interrupt value dict into a user-friendly Telegram message."""
    sections: list[str] = []

    question = value.get("question", "")
    if question:
        sections.append(question)

    item_blocks: list[str] = []
    for item in value.get("items", []):
        desc = item.get("description", "")
        cals = item.get("calories", 0)
        protein = item.get("protein", 0)
        carbs = item.get("carbs", 0)
        fat = item.get("fat", 0)
        # The graph node already appends the "(estimated)" tag to desc via
        # MESSAGES["confirmation_estimated_tag"]; don't double-tag here.
        macro_line = MESSAGES["confirmation_macro_line"].format(
            cals=cals, protein=protein, carbs=carbs, fat=fat
        )
        item_blocks.append(f"{desc}\n{macro_line}")
    if item_blocks:
        sections.append("\n\n".join(item_blocks))

    totals = value.get("totals")
    if totals:
        sections.append(
            MESSAGES["confirmation_total_line"].format(
                cals=totals.get("calories", 0),
                protein=totals.get("protein", 0),
                carbs=totals.get("carbs", 0),
                fat=totals.get("fat", 0),
            )
        )

    sections.append(MESSAGES["confirmation_reply_hint"])

    return "\n\n".join(sections)


async def _save_user_profile(user_id: str, data: dict) -> None:
    """Save onboarding data to user_profiles table."""
    async with get_async_db_session() as session:
        await create_user_profile(
            session=session,
            user_id=user_id,
            name=data["name"],
            height_cm=data["height_cm"],
            age=data["age"],
            gender=data["gender"],
        )


async def _load_user_profile(user_id: str) -> dict | None:
    """Load user profile from DB for config injection."""
    async with get_async_db_session() as session:
        return await get_user_profile(session, user_id)


async def _handle_onboarding(message: Message, session: dict) -> bool:
    """Process onboarding step. Returns True if still onboarding."""
    step = session.get("onboarding_step")
    if step is None:
        return False

    text = message.text.strip()

    if step == "name":
        session["onboarding_data"]["name"] = text
    elif step == "height":
        try:
            session["onboarding_data"]["height_cm"] = float(text)
        except ValueError:
            await message.answer(MESSAGES["onboarding_invalid_height"])
            return True
    elif step == "age":
        try:
            session["onboarding_data"]["age"] = int(text)
        except ValueError:
            await message.answer(MESSAGES["onboarding_invalid_age"])
            return True
    elif step == "gender":
        if text.lower() not in ("male", "female", "other"):
            await message.answer(MESSAGES["onboarding_invalid_gender"])
            return True
        session["onboarding_data"]["gender"] = text.lower()

    # Advance to next step
    current_idx = ONBOARDING_ORDER.index(step)
    if current_idx + 1 < len(ONBOARDING_ORDER):
        next_step = ONBOARDING_ORDER[current_idx + 1]
        session["onboarding_step"] = next_step
        await message.answer(_onboarding_question(next_step))
        return True

    # Onboarding complete — save profile to DB
    session["onboarding_step"] = None
    await _save_user_profile(session["user_id"], session["onboarding_data"])
    name = session["onboarding_data"]["name"]
    # Cache profile on session for config injection
    # Preserve existing nutrition_plan if user already had a profile
    existing_plan = (
        session["user_profile"].get("nutrition_plan")
        if session.get("user_profile")
        else None
    )
    session["user_profile"] = {
        "name": name,
        "height_cm": session["onboarding_data"]["height_cm"],
        "age": session["onboarding_data"]["age"],
        "gender": session["onboarding_data"]["gender"],
        "nutrition_plan": existing_plan,
    }
    await message.answer(MESSAGES["onboarding_complete"].format(name=name))
    return True


async def _handle_authenticated_message(message: Message, session: dict) -> None:
    """Process a message from an authenticated user."""
    # Handle onboarding first
    if await _handle_onboarding(message, session):
        return

    chat_id = message.chat.id
    now = datetime.now(timezone.utc)

    # Check thread freshness -- create new thread if stale
    last_activity = session.get("last_activity")
    if last_activity is None or (now - last_activity) > SESSION_TIMEOUT:
        try:
            session["thread_id"] = await _create_thread()
            logger.info("Created new thread %s for chat_id=%s", session["thread_id"], chat_id)
        except Exception:
            logger.exception("Failed to create thread for chat_id=%s", chat_id)
            await message.answer(MESSAGES["error_generic_thread"])
            return
        session["interrupted"] = False

    session["last_activity"] = now
    user_id = session["user_id"]
    thread_id = session["thread_id"]

    # Load profile if not cached
    if "user_profile" not in session or session["user_profile"] is None:
        session["user_profile"] = await _load_user_profile(user_id)

    logger.info("User message", chat_id=chat_id, text=message.text)

    try:
        # Decide whether to resume or send new input
        if session.get("interrupted"):
            result = await _call_langgraph(
                thread_id, user_id,
                command={"resume": message.text},
                user_profile=session.get("user_profile"),
            )
        else:
            result = await _call_langgraph(
                thread_id,
                user_id,
                input={"messages": [{"role": "human", "content": message.text}]},
                user_profile=session.get("user_profile"),
            )

        # Check if the graph is now interrupted (HITL)
        is_interrupted, interrupt_text = await _get_interrupt_state(thread_id)
        session["interrupted"] = is_interrupted

        # Choose what to send: interrupt prompt or last AI message
        response_text = ""
        if is_interrupted and interrupt_text:
            response_text = interrupt_text
        else:
            messages = result.get("messages", [])
            if messages:
                response_text = messages[-1].get("content", "")

        if response_text:
            logger.info("Bot response", chat_id=chat_id, text=response_text[:500])
            # Telegram has a 4096 char limit per message -- split if needed
            for i in range(0, len(response_text), 4096):
                await message.answer(response_text[i : i + 4096])
            return

        logger.warning("No response to send", chat_id=chat_id, thread_id=thread_id)
        await message.answer(MESSAGES["error_empty_response"])

    except httpx.HTTPStatusError as exc:
        logger.exception("HTTP error relaying message", chat_id=chat_id, status_code=exc.response.status_code)
        await message.answer(MESSAGES["error_generic_request"])
    except Exception:
        logger.exception("Error relaying message", chat_id=chat_id)
        await message.answer(MESSAGES["error_generic_request"])


@router.message()
async def handle_message(message: Message) -> None:
    """Main message handler -- routes through passphrase check or to LangGraph."""
    if not message.text:
        await message.answer(MESSAGES["error_non_text"])
        return

    chat_id = message.chat.id

    # Check if user has an active session
    if chat_id not in user_sessions:
        # Passphrase check for new users
        # Encode to bytes before compare_digest — it refuses non-ASCII strings,
        # and any non-English first message (Hebrew, emoji, etc.) would crash.
        if hmac.compare_digest(
            message.text.strip().encode("utf-8"), BOT_PASSPHRASE.encode("utf-8")
        ):
            try:
                result = await get_or_create_user(chat_id)
                thread_id = await _create_thread()
                is_new = result.get("is_new", False)

                # Check if existing user has a profile — trigger onboarding if missing
                existing_profile = None
                if not is_new:
                    existing_profile = await _load_user_profile(result["user_id"])
                needs_onboarding = is_new or existing_profile is None

                user_sessions[chat_id] = {
                    "user_id": result["user_id"],
                    "thread_id": thread_id,
                    "last_activity": datetime.now(timezone.utc),
                    "interrupted": False,
                    "onboarding_step": "name" if needs_onboarding else None,
                    "onboarding_data": {},
                    "user_profile": existing_profile,
                }
                logger.info(
                    "User registered",
                    chat_id=chat_id,
                    is_new=is_new,
                    needs_onboarding=needs_onboarding,
                )
                if needs_onboarding:
                    await message.answer(MESSAGES["onboarding_welcome"])
                    await message.answer(_onboarding_question("name"))
                else:
                    await message.answer(MESSAGES["onboarding_welcome_back"])
            except Exception:
                logger.exception("Registration failed for chat_id=%s", chat_id)
                await message.answer(MESSAGES["auth_registration_error"])
        else:
            await message.answer(MESSAGES["auth_invite_prompt"])
        return

    # Authenticated user -- relay to LangGraph
    await _handle_authenticated_message(message, user_sessions[chat_id])


async def on_startup(bot: Bot) -> None:
    """Set the webhook URL when the bot starts."""
    await bot.set_webhook(
        f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}",
        secret_token=WEBHOOK_SECRET,
    )


async def _run_polling():
    """Run bot in polling mode for local development."""
    logger.info("Starting bot in POLLING mode (local dev)")
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook deleted, starting polling")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def _run_webhook():
    """Run bot in webhook mode for production."""
    logger.info("Starting bot in WEBHOOK mode (production)")
    dp = Dispatcher()
    dp.include_router(router)
    dp.startup.register(on_startup)

    bot = Bot(token=BOT_TOKEN)
    app = web.Application()

    webhook_handler = SimpleRequestHandler(
        dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET
    )
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    port = int(os.environ.get("BOT_PORT", "8080"))
    web.run_app(app, host="0.0.0.0", port=port)


def main():
    """Entry point for the Telegram bot gateway."""
    if POLLING_MODE:
        asyncio.run(_run_polling())
    else:
        _run_webhook()


if __name__ == "__main__":
    main()
