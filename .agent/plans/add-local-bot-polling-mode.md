# Feature: Local Bot Development Flow with Polling Mode

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Add polling mode support to the Telegram bot (`bot/gateway.py`) so it can run locally against `langgraph dev` without needing a public URL or ngrok. This enables a fast local feedback loop: run two processes, chat with the dev bot on Telegram, and see changes instantly.

## User Story

As a developer working on FitPal
I want to run the Telegram bot locally in polling mode
So that I can test conversation flows interactively on Telegram without deploying to Railway

## Problem Statement

Currently the bot only supports webhook mode, which requires a publicly accessible HTTPS URL (Railway production). There's no way to test the bot interactively on Telegram during local development — the only testing paths are unit tests (mocked), integration tests (DB only), and E2E graph-api tests (HTTP API, no Telegram). This means every conversation UX change requires a full deploy-to-main cycle before it can be experienced.

## Solution Statement

1. Add a `POLLING_MODE` environment variable to `bot/gateway.py`
2. When `POLLING_MODE=true`, use aiogram's `dp.start_polling(bot)` instead of the aiohttp webhook server
3. Delete any existing webhook before starting polling (Telegram requires this)
4. All handlers, session management, and HITL logic remain identical — only the transport layer changes
5. User creates a separate dev bot via BotFather (`@FitPalDevBot`) so production bot is unaffected
6. Document the local dev flow in a simple guide

## Feature Metadata

**Feature Type**: Enhancement
**Estimated Complexity**: Low
**Primary Systems Affected**: `bot/gateway.py`
**Dependencies**: None (aiogram already supports polling natively)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `bot/gateway.py` (lines 393-413) — Current `main()` function with webhook-only setup. This is what we're modifying to support both modes.
- `bot/gateway.py` (lines 385-390) — `on_startup()` handler that registers the webhook with Telegram. Must NOT run in polling mode.
- `bot/gateway.py` (lines 26-43) — Environment variables and constants. `POLLING_MODE` will be added here.
- `bot/gateway.py` (lines 336-382) — `handle_message()` main handler. Unchanged — handlers are transport-agnostic in aiogram.
- `bot/Dockerfile` (all) — Entry point is `uv run python -m bot.gateway`. No changes needed — Dockerfile always runs in webhook mode (production).

### Relevant Documentation

- [aiogram 3.x Polling](https://docs.aiogram.dev/en/latest/)
  - `dp.start_polling(bot)` — async coroutine for polling mode
  - `dp.run_polling(bot)` — blocking convenience wrapper
  - Must call `bot.delete_webhook(drop_pending_updates=True)` before polling if webhook was previously set
- [Telegram BotFather](https://t.me/BotFather)
  - User action: create `@FitPalDevBot`, get token

### Patterns to Follow

**Environment variable pattern** (from `bot/gateway.py` lines 26-32):
```python
LANGGRAPH_API_URL = os.environ.get("LANGGRAPH_API_URL", "http://localhost:2024")
```
Follow same pattern: `POLLING_MODE = os.environ.get("POLLING_MODE", "").lower() in ("true", "1", "yes")`

**Logging pattern** (from `bot/gateway.py`):
```python
logger = structlog.get_logger(__name__)
```
Use `structlog` for all new log lines.

---

## IMPLEMENTATION PLAN

### Phase 1: Add Polling Mode to gateway.py

Small, focused change to `main()`:
- Read `POLLING_MODE` env var
- If polling: delete webhook, use `dp.start_polling(bot)`
- If webhook (default): existing aiohttp setup unchanged
- `on_startup` webhook registration should only run in webhook mode

### Phase 2: User Setup (Manual Steps)

User creates dev bot via BotFather and sets up local env vars. These are documented in the plan as manual steps the user performs during execution.

### Phase 3: Validation

Run the bot locally, chat on Telegram, verify all flows work.

---

## STEP-BY-STEP TASKS

### Task 1: USER ACTION — Create dev bot via BotFather

This is a manual step the user performs on Telegram:

1. Open Telegram, search for `@BotFather`
2. Send `/newbot`
3. Name: `FitPal Dev` (or similar)
4. Username: `FitPalDevBot` (or any available name)
5. Copy the bot token — this becomes `BOT_TOKEN` for local dev

- **VALIDATE**: User confirms they have the dev bot token

### Task 2: UPDATE `bot/gateway.py` — Add POLLING_MODE env var

Add to the environment variables section (after line 32):

```python
POLLING_MODE = os.environ.get("POLLING_MODE", "").lower() in ("true", "1", "yes")
```

- **VALIDATE**: `uv run ruff check bot/gateway.py`

### Task 3: UPDATE `bot/gateway.py` — Modify `main()` to support both modes

Replace the current `main()` function (lines 393-409) with a version that branches on `POLLING_MODE`:

**Webhook mode** (existing behavior, default):
- Register `on_startup` for webhook setup
- Create aiohttp app, SimpleRequestHandler, run web server
- Exactly as current code — no changes to this path

**Polling mode** (new):
- Log that polling mode is active
- Create `Bot` and `Dispatcher`, include `router`
- Register a startup callback that calls `bot.delete_webhook(drop_pending_updates=True)` instead of setting a webhook
- Call `await dp.start_polling(bot)` (async version since `main()` is already `def main()` calling `web.run_app`)

Actually, the current `main()` is a sync function that calls `web.run_app()` (blocking). For polling mode, we need an async entry point. The cleanest approach:

```python
def main():
    if POLLING_MODE:
        asyncio.run(_run_polling())
    else:
        _run_webhook()
```

Where `_run_webhook()` contains the current `main()` body, and `_run_polling()` is a new async function:

```python
async def _run_polling():
    """Run bot in polling mode for local development."""
    logger.info("Starting bot in POLLING mode (local dev)")
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # Delete any existing webhook so Telegram allows getUpdates
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook deleted, starting polling")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
```

- **PATTERN**: Follow existing `main()` structure at `bot/gateway.py:393-409`
- **GOTCHA**: `on_startup()` must NOT run in polling mode — it registers the webhook. Since we're creating a new `Dispatcher` in `_run_polling()`, the startup handler registered on the module-level `dp` (if any) won't fire. But looking at the code, `on_startup` is registered via `dp.startup.register(on_startup)` inside `main()` — so just don't register it in polling mode.
- **GOTCHA**: Must call `bot.delete_webhook(drop_pending_updates=True)` before polling. If a webhook was previously set (e.g., from production), Telegram rejects `getUpdates` calls until the webhook is removed.
- **IMPORTS**: Add `import asyncio` at the top of the file (check if already imported).
- **VALIDATE**: `uv run ruff check bot/gateway.py`

### Task 4: USER ACTION — Set up local environment variables

The user needs these env vars set locally (in `.env` or exported in shell):

```bash
# Dev bot token (from Task 1)
BOT_TOKEN=<dev-bot-token-from-botfather>

# Polling mode flag
POLLING_MODE=true

# LangGraph server (local)
LANGGRAPH_API_URL=http://localhost:2024

# Supabase (same as production — dev user exists there)
SUPABASE_URL=<your-supabase-url>
SUPABASE_SERVICE_KEY=<your-supabase-service-key>

# Auth
BOT_PASSPHRASE=<any-passphrase-for-dev>
BOT_PASSWORD_SEED=<same-as-production-if-you-want-same-users>
INTERNAL_API_SECRET=<must-match-what-langgraph-dev-expects>

# Not needed in polling mode (but harmless if set)
# WEBHOOK_BASE_URL=
# WEBHOOK_SECRET=
```

**IMPORTANT**: `INTERNAL_API_SECRET` must match the value the local `langgraph dev` server expects. Check if `langgraph dev` reads this from `.env` or if it needs to be passed differently. Actually — `langgraph dev` runs without auth middleware (uses `langgraph.json`, not `langgraph.production.json`), so `INTERNAL_API_SECRET` may not be needed locally. The bot sends `X-Internal-Token` header, but the dev server doesn't validate it. Verify during testing.

- **VALIDATE**: User confirms env vars are set

### Task 5: VALIDATE — Run local dev flow

1. Start langgraph dev server:
   ```bash
   uv run langgraph dev
   ```
   Wait for "Ready!" message.

2. In a separate terminal, start the bot:
   ```bash
   uv run python -m bot.gateway
   ```
   Should see: "Starting bot in POLLING mode (local dev)"

3. Open Telegram, find the dev bot (`@FitPalDevBot`)

4. Test flows:
   - Send the passphrase → should register and start onboarding
   - Complete onboarding (name, height, age, gender)
   - Send "I ate 200g of chicken" → should get HITL confirmation
   - Confirm → should log and respond
   - Send "What did I eat today?" → should show stats
   - Send "I weigh 74kg" → should log personal stat

- **VALIDATE**: All flows complete without errors in both terminals

---

## TESTING STRATEGY

### Unit Tests

No new unit tests needed — polling mode is a transport change, not a logic change. All existing handler tests remain valid since handlers are transport-agnostic.

### Integration Tests

No changes — these test DB layer, not bot transport.

### Manual Validation

The primary validation is manual: run locally, chat on Telegram, verify all flows. This is the whole point of the feature — enabling manual testing.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
```bash
uv run ruff check bot/gateway.py
```

### Level 2: Unit Tests
```bash
uv run pytest tests/unit/ -v
```

### Level 3: Manual Validation
See Task 5 — interactive Telegram testing.

---

## ACCEPTANCE CRITERIA

- [ ] `POLLING_MODE=true` starts bot in polling mode (no webhook, no aiohttp server)
- [ ] `POLLING_MODE` unset or false starts bot in webhook mode (existing behavior unchanged)
- [ ] Polling mode deletes any existing webhook before starting
- [ ] All existing handlers work identically in polling mode
- [ ] Dev bot on Telegram responds to messages when running locally
- [ ] HITL confirmation flow works end-to-end via Telegram
- [ ] Onboarding flow works via Telegram
- [ ] Production webhook mode is completely unaffected
- [ ] No new dependencies added
- [ ] Existing unit tests still pass

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order (Tasks 1-5)
- [ ] `bot/gateway.py` updated with polling mode support
- [ ] Dev bot created on Telegram via BotFather
- [ ] Local env vars configured
- [ ] Manual testing confirms all flows work
- [ ] Unit tests pass
- [ ] Linting passes

---

## NOTES

### Design Decisions

1. **`asyncio.run()` for polling, `web.run_app()` for webhook**: Both are blocking calls that run the event loop. We branch in `main()` before either is called. This keeps the two modes cleanly separated.

2. **New Dispatcher in polling mode**: We create a fresh `Dispatcher` in `_run_polling()` and include the same `router`. This avoids any webhook-specific startup handlers leaking into polling mode.

3. **No new dependencies**: aiogram 3.x natively supports both modes. `dp.start_polling()` is built-in.

4. **Separate dev bot token**: Required because Telegram only allows one active transport (webhook OR polling) per bot token. Using the production token would kill the production webhook.

5. **`drop_pending_updates=True`**: When switching from webhook to polling, there may be queued updates from when the webhook was active. Dropping them avoids processing stale messages.

6. **`INTERNAL_API_SECRET` in dev**: The local `langgraph dev` server uses `langgraph.json` (no auth middleware), so the `X-Internal-Token` header the bot sends is ignored. The bot will work without setting this env var locally, but it's harmless to set it.

### Risks

- **Minimal**: This is a small, well-isolated change. The webhook code path is untouched. The only new code is ~15 lines in `_run_polling()` and a branch in `main()`.

### Confidence Score: 9/10

High confidence because:
- aiogram natively supports polling — no hacks needed
- Handlers are transport-agnostic (verified in codebase)
- Change is small and isolated to `main()` function
- No new dependencies
- Existing tests unaffected
