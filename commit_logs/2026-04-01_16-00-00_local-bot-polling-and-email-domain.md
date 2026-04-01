# Local Bot Development: Polling Mode + Email Domain

**Date**: 2026-04-01
**Branch**: Menu-and-Personal-Details
**Commit**: a98ea1c

## Changes Implemented

### `bot/gateway.py`
- Added `POLLING_MODE` env var — branches `main()` into `_run_polling()` (local dev) or `_run_webhook()` (production)
- Polling mode uses `dp.start_polling(bot)` — no public URL needed
- Added `load_dotenv()` before imports so `.env` vars are available locally
- Production webhook path is unchanged (just extracted into `_run_webhook()`)

### `bot/supabase_admin.py`
- Added `BOT_EMAIL_DOMAIN` env var (default: `telegram.fitpal.bot`)
- `_synthetic_email()` now uses `{chat_id}@{BOT_EMAIL_DOMAIN}`
- Dev bot generates `@dev.fitpal.bot` emails → separate auth users from production

### Local `.env` additions (not committed)
- `BOT_TOKEN`, `POLLING_MODE=true`, `BOT_PASSPHRASE`, `BOT_PASSWORD_SEED`
- `SUPABASE_SERVICE_KEY`, `BOT_EMAIL_DOMAIN=dev.fitpal.bot`

## Production Safety
- `POLLING_MODE` not set on Railway → defaults to webhook mode
- `BOT_EMAIL_DOMAIN` not set on Railway → defaults to `telegram.fitpal.bot`
- Zero changes to production code paths

## Next Steps
- Test onboarding flow via dev bot (restart bot with new env vars)
- Test full food logging + HITL flow via Telegram
- Once validated, merge branch to main for production deploy
