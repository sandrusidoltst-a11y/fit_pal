"""Telegram bot gateway for FitPal.

Connects Telegram users to the LangGraph FitPal agent via webhook.
Handles passphrase-based access control, auto-registration via Supabase,
message relay, and HITL interrupt/resume flow.
"""

import hmac
import os
from datetime import datetime, timedelta, timezone

import httpx
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.supabase_admin import get_or_create_user, refresh_session

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_BASE_URL", "")
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/webhook")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
BOT_PASSPHRASE = os.environ.get("BOT_PASSPHRASE", "")
LANGGRAPH_API_URL = os.environ.get("LANGGRAPH_API_URL", "http://localhost:2024")

ASSISTANT_ID = "fitpal"
SESSION_TIMEOUT = timedelta(minutes=30)

# In-memory session store: chat_id -> session dict
# Keys: user_id, thread_id, last_activity, access_token, refresh_token, interrupted
user_sessions: dict[int, dict] = {}

router = Router()


async def _create_thread(access_token: str) -> str:
    """Create a new LangGraph thread and return its ID."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{LANGGRAPH_API_URL}/threads",
            headers={"Authorization": f"Bearer {access_token}"},
            json={},
        )
        response.raise_for_status()
        return response.json()["thread_id"]


async def _call_langgraph(
    thread_id: str,
    access_token: str,
    *,
    input: dict | None = None,
    command: dict | None = None,
) -> dict:
    """Call LangGraph runs/wait endpoint and return the result."""
    body: dict = {"assistant_id": ASSISTANT_ID, "config": {}}
    if input is not None:
        body["input"] = input
    if command is not None:
        body["command"] = command

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{LANGGRAPH_API_URL}/threads/{thread_id}/runs/wait",
            headers={"Authorization": f"Bearer {access_token}"},
            json=body,
        )
        response.raise_for_status()
        return response.json()


async def _check_interrupted(thread_id: str, access_token: str) -> bool:
    """Check if the graph is paused at an interrupt."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{LANGGRAPH_API_URL}/threads/{thread_id}/state",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        state = response.json()
        tasks = state.get("tasks", [])
        return len(tasks) > 0


async def _handle_authenticated_message(message: Message, session: dict) -> None:
    """Process a message from an authenticated user."""
    chat_id = message.chat.id
    now = datetime.now(timezone.utc)

    # Check thread freshness -- create new thread if stale
    last_activity = session.get("last_activity")
    if last_activity is None or (now - last_activity) > SESSION_TIMEOUT:
        try:
            session["thread_id"] = await _create_thread(session["access_token"])
        except httpx.HTTPStatusError:
            # Token might be expired, try refresh
            try:
                tokens = refresh_session(session["refresh_token"])
                session["access_token"] = tokens["access_token"]
                session["refresh_token"] = tokens["refresh_token"]
                session["thread_id"] = await _create_thread(session["access_token"])
            except Exception:
                await message.answer(
                    "Session expired. Please send the invite code again to reconnect."
                )
                user_sessions.pop(chat_id, None)
                return
        session["interrupted"] = False

    session["last_activity"] = now
    access_token = session["access_token"]
    thread_id = session["thread_id"]

    try:
        # Decide whether to resume or send new input
        if session.get("interrupted"):
            result = await _call_langgraph(
                thread_id, access_token, command={"resume": message.text}
            )
        else:
            result = await _call_langgraph(
                thread_id,
                access_token,
                input={"messages": [{"role": "human", "content": message.text}]},
            )

        # Check if the graph is now interrupted (HITL)
        is_interrupted = await _check_interrupted(thread_id, access_token)
        session["interrupted"] = is_interrupted

        # Extract and send response
        messages = result.get("messages", [])
        if messages:
            response_text = messages[-1].get("content", "")
            if response_text:
                # Telegram has a 4096 char limit per message -- split if needed
                for i in range(0, len(response_text), 4096):
                    await message.answer(response_text[i : i + 4096])
                return

        await message.answer("I processed your request but have no response to show.")

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            # Token expired mid-conversation, try refresh
            try:
                tokens = refresh_session(session["refresh_token"])
                session["access_token"] = tokens["access_token"]
                session["refresh_token"] = tokens["refresh_token"]
                await message.answer("Session refreshed. Please resend your message.")
            except Exception:
                await message.answer(
                    "Session expired. Please send the invite code again to reconnect."
                )
                user_sessions.pop(chat_id, None)
        else:
            await message.answer(
                "Something went wrong processing your request. Please try again."
            )
    except Exception:
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
                result = get_or_create_user(chat_id)
                thread_id = await _create_thread(result["access_token"])
                user_sessions[chat_id] = {
                    "user_id": result["user_id"],
                    "thread_id": thread_id,
                    "last_activity": datetime.now(timezone.utc),
                    "access_token": result["access_token"],
                    "refresh_token": result["refresh_token"],
                    "interrupted": False,
                }
                await message.answer(
                    "Welcome to FitPal! You can start logging food now."
                )
            except Exception:
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
