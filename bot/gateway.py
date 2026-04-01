"""Telegram bot gateway for FitPal.

Connects Telegram users to the LangGraph FitPal agent via webhook.
Handles passphrase-based access control, auto-registration via Supabase,
onboarding profile collection, message relay, and HITL interrupt/resume flow.
"""

import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, TypedDict

import httpx
import structlog
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.supabase_admin import get_or_create_user
from src.database import get_async_db_session
from src.services.user_profile_service import create_user_profile, get_user_profile

logger = structlog.get_logger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_BASE_URL", "")
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/webhook")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
BOT_PASSPHRASE = os.environ.get("BOT_PASSPHRASE", "")
LANGGRAPH_API_URL = os.environ.get("LANGGRAPH_API_URL", "http://localhost:2024")
INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "")

ASSISTANT_ID = "fitpal"
SESSION_TIMEOUT = timedelta(minutes=30)

ONBOARDING_QUESTIONS = {
    "name": "What's your name?",
    "height": "What's your height in cm?",
    "age": "How old are you?",
    "gender": "What's your gender? (male/female/other)",
}
ONBOARDING_ORDER = ["name", "height", "age", "gender"]


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
        "config": {"configurable": {"user_id": user_id}},
    }
    if user_profile:
        body["config"]["configurable"]["user_profile"] = user_profile
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
    lines = []
    question = value.get("question", "")
    if question:
        lines.append(question)
        lines.append("")

    items = value.get("items", [])
    for item in items:
        desc = item.get("description", "")
        cals = item.get("calories", 0)
        protein = item.get("protein", 0)
        carbs = item.get("carbs", 0)
        fat = item.get("fat", 0)
        source = item.get("source", "")
        source_tag = " (estimated)" if source == "estimated" else ""
        lines.append(
            f"• {desc}{source_tag}\n"
            f"  {cals} kcal | P: {protein}g | C: {carbs}g | F: {fat}g"
        )

    totals = value.get("totals")
    if totals:
        lines.append("")
        lines.append(
            f"Total: {totals.get('calories', 0)} kcal | "
            f"P: {totals.get('protein', 0)}g | "
            f"C: {totals.get('carbs', 0)}g | "
            f"F: {totals.get('fat', 0)}g"
        )

    lines.append("")
    lines.append("Reply 'yes' to confirm, 'no' to reject, or describe edits.")

    return "\n".join(lines)


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
            await message.answer("Please enter a number for height (cm).")
            return True
    elif step == "age":
        try:
            session["onboarding_data"]["age"] = int(text)
        except ValueError:
            await message.answer("Please enter a number for age.")
            return True
    elif step == "gender":
        if text.lower() not in ("male", "female", "other"):
            await message.answer("Please enter male, female, or other.")
            return True
        session["onboarding_data"]["gender"] = text.lower()

    # Advance to next step
    current_idx = ONBOARDING_ORDER.index(step)
    if current_idx + 1 < len(ONBOARDING_ORDER):
        next_step = ONBOARDING_ORDER[current_idx + 1]
        session["onboarding_step"] = next_step
        await message.answer(ONBOARDING_QUESTIONS[next_step])
        return True

    # Onboarding complete — save profile to DB
    session["onboarding_step"] = None
    await _save_user_profile(session["user_id"], session["onboarding_data"])
    name = session["onboarding_data"]["name"]
    # Cache profile on session for config injection
    session["user_profile"] = {
        "name": name,
        "height_cm": session["onboarding_data"]["height_cm"],
        "age": session["onboarding_data"]["age"],
        "gender": session["onboarding_data"]["gender"],
    }
    await message.answer(
        f"Great, {name}! Your profile is set up. You can start logging food now."
    )
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
            await message.answer(
                "Something went wrong. Please try again later."
            )
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
        await message.answer("I processed your request but have no response to show.")

    except httpx.HTTPStatusError as exc:
        logger.exception("HTTP error relaying message", chat_id=chat_id, status_code=exc.response.status_code)
        await message.answer(
            "Something went wrong processing your request. Please try again."
        )
    except Exception:
        logger.exception("Error relaying message", chat_id=chat_id)
        await message.answer(
            "Something went wrong processing your request. Please try again."
        )


@router.message()
async def handle_message(message: Message) -> None:
    """Main message handler -- routes through passphrase check or to LangGraph."""
    if not message.text:
        await message.answer("I can only process text messages.")
        return

    chat_id = message.chat.id

    # Check if user has an active session
    if chat_id not in user_sessions:
        # Passphrase check for new users
        if hmac.compare_digest(message.text.strip(), BOT_PASSPHRASE):
            try:
                result = await get_or_create_user(chat_id)
                thread_id = await _create_thread()
                is_new = result.get("is_new", False)
                user_sessions[chat_id] = {
                    "user_id": result["user_id"],
                    "thread_id": thread_id,
                    "last_activity": datetime.now(timezone.utc),
                    "interrupted": False,
                    "onboarding_step": "name" if is_new else None,
                    "onboarding_data": {},
                    "user_profile": None,
                }
                logger.info("User registered for chat_id=%s, is_new=%s", chat_id, is_new)
                if is_new:
                    await message.answer(
                        "Welcome to FitPal! Let's set up your profile."
                    )
                    await message.answer(ONBOARDING_QUESTIONS["name"])
                else:
                    await message.answer(
                        "Welcome back to FitPal! You can start logging food now."
                    )
            except Exception:
                logger.exception("Registration failed for chat_id=%s", chat_id)
                await message.answer(
                    "Something went wrong during registration. Please try again."
                )
        else:
            await message.answer("Send the invite code to get started.")
        return

    # Authenticated user -- relay to LangGraph
    await _handle_authenticated_message(message, user_sessions[chat_id])


async def on_startup(bot: Bot) -> None:
    """Set the webhook URL when the bot starts."""
    await bot.set_webhook(
        f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}",
        secret_token=WEBHOOK_SECRET,
    )


def main():
    """Entry point for the Telegram bot gateway."""
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


if __name__ == "__main__":
    main()
