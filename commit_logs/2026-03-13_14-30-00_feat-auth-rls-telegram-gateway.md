# feat: Auth Handler, RLS Policies, and Telegram Bot Gateway (Phase 3 Steps 4-6)

**Date**: 2026-03-13
**Branch**: auth
**Commit**: 71b27ff

## Changes Implemented

### Phase A: Auth Handler (Step 4)
- Created `src/security/auth.py` — LangGraph custom auth handler:
  - `@auth.authenticate`: Validates Supabase JWTs via `/auth/v1/user` endpoint using httpx
  - `@auth.on`: Scopes all resources (threads, runs) to the authenticated user via metadata filtering
- Updated `src/config.py` `get_user_id()` — priority chain: `langgraph_auth_user` > `user_id` > `DEFAULT_DEV_USER_ID`
- Created `langgraph.production.json` — production config with auth path (dev config unchanged)
- Added `httpx` dependency

### Phase B: RLS Policies (Step 5)
- Enabled Row Level Security on `food_items` and `daily_logs` tables
- Created user-scoped policies:
  - `daily_logs`: full CRUD scoped to `auth.uid()`
  - `food_items`: shared DB foods readable by all, estimated foods scoped to owner

### Phase C: Telegram Bot Gateway (Step 6)
- Created `bot/gateway.py` — aiogram v3 webhook bot:
  - Passphrase-based access control (constant-time comparison)
  - Auto-registration via Supabase admin API
  - Message relay to LangGraph API with JWT auth
  - HITL interrupt/resume flow over Telegram
  - 30-minute session timeout with thread recreation
  - 4096-char message splitting for Telegram limits
- Created `bot/supabase_admin.py`:
  - Lazy-initialized Supabase client
  - Synthetic email + HMAC-derived server-side passwords
  - `get_or_create_user()` and `refresh_session()` helpers
- Added `aiogram` and `supabase` dependencies

### Documentation
- Updated `CLAUDE.md` — tech stack, project structure
- Updated `PRD.md` — Phase 3 steps 4-6 marked complete, tech stack, directory structure

### Security Fixes (from review)
- Constant-time passphrase comparison (`hmac.compare_digest`)
- Narrowed bare `except Exception` to `except AuthApiError`
- Fixed stale variable reference (`supabase_admin` → `_get_client()`)
- Removed dead code (unused import, unused function)

### Tests
- `tests/unit/test_auth_handler.py` — 10 tests (token validation, get_user_id priority)
- `tests/unit/test_gateway.py` — 10 tests (passphrase flow, message relay, thread management, HITL)
- All 99 unit tests pass

## Files Created
- `src/security/__init__.py`
- `src/security/auth.py`
- `langgraph.production.json`
- `bot/__init__.py`
- `bot/gateway.py`
- `bot/supabase_admin.py`
- `tests/unit/test_auth_handler.py`
- `tests/unit/test_gateway.py`
- `.agent/plans/phase3-auth-rls-telegram-gateway.md`

## Files Modified
- `src/config.py`
- `pyproject.toml`
- `uv.lock`
- `CLAUDE.md`
- `PRD.md`

## Next Steps
- Step 7: Deploy LangGraph standalone server (Docker Compose) + Telegram webhook setup
- Step 8: Smoke test end-to-end
- Set up env vars (BOT_TOKEN, WEBHOOK_BASE_URL, etc.)
- Create Telegram bot via BotFather
