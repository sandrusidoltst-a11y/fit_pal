# Feature: Configurable Bot Email Domain

## Feature Description

Add a `BOT_EMAIL_DOMAIN` environment variable to `bot/supabase_admin.py` so the dev bot creates separate Supabase auth users from the production bot. Enables onboarding testing with the same Telegram account.

## User Story

As a developer testing the bot locally
I want the dev bot to create a separate auth user from production
So that I can test onboarding without needing a second Telegram account

## Problem Statement

The synthetic email is hardcoded to `{chat_id}@telegram.fitpal.bot`. Both production and dev bots generate the same email for the same Telegram user, so the dev bot reuses the production auth user and skips onboarding.

## Solution Statement

Replace the hardcoded domain with an env var `BOT_EMAIL_DOMAIN` defaulting to `telegram.fitpal.bot`. Set it to `dev.fitpal.bot` locally. Same chat_id → different email → different auth user → `is_new: True` → onboarding.

**Production safety**: `BOT_EMAIL_DOMAIN` is not set on Railway → defaults to `telegram.fitpal.bot` → zero change in production behavior.

---

## STEP-BY-STEP TASKS

### Task 1: UPDATE `bot/supabase_admin.py` — Add BOT_EMAIL_DOMAIN

Line 41: `return f"{telegram_chat_id}@telegram.fitpal.bot"`

Change to read from env var with existing value as default:

```python
BOT_EMAIL_DOMAIN = os.environ.get("BOT_EMAIL_DOMAIN", "telegram.fitpal.bot")
```

Add this constant near the other env vars (line 18-21), then update `_synthetic_email`:

```python
return f"{telegram_chat_id}@{BOT_EMAIL_DOMAIN}"
```

- **VALIDATE**: `uv run ruff check bot/supabase_admin.py`

### Task 2: UPDATE `.env` — Add domain for local dev

Add to `.env`:
```
BOT_EMAIL_DOMAIN=dev.fitpal.bot
```

- **VALIDATE**: Env var is set

### Task 3: VALIDATE — Unit tests pass

- `uv run pytest tests/unit/test_supabase_admin.py -v`
- `uv run pytest tests/unit/test_gateway.py -v`

### Task 4: VALIDATE — Manual test

1. Restart bot: `uv run python -m bot.gateway`
2. Send passphrase to dev bot on Telegram
3. Bot should say "Welcome to FitPal! Let's set up your profile."
4. Complete onboarding (name, height, age, gender)

---

## ACCEPTANCE CRITERIA

- [ ] `BOT_EMAIL_DOMAIN` defaults to `telegram.fitpal.bot` (production unchanged)
- [ ] Local dev uses `dev.fitpal.bot` → creates separate auth user
- [ ] Onboarding triggers for the new dev auth user
- [ ] Unit tests pass
- [ ] No changes to production behavior

## Confidence Score: 10/10

Two lines of code, env var with safe default.
