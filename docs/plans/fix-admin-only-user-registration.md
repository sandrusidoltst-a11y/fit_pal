# Feature: Admin-only Telegram user registration (fix poisoned Supabase admin client)

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files etc.

## Feature Description

Rewrite the bot's Supabase user-registration helper so it uses **admin-API operations only** (look up by email, then create if missing) and **never calls `sign_in_with_password`**. The current code shares one long-lived Supabase client between user sign-in and admin operations; a successful user sign-in overwrites that client's `Authorization` header with the user's short-lived JWT, and once it expires every **new-user** `admin.create_user` call fails with `403 token is expired`. Removing the sign-in step keeps the admin client's `Authorization` permanently set to the service key.

## User Story

As a **new Telegram user (e.g. Ori) entering the correct passphrase**
I want to **be registered successfully every time**
So that **I can start using the bot instead of being wrongly told "enter the correct code".**

## Problem Statement

`bot/supabase_admin.py:get_or_create_user` does two jobs on one module-level singleton client (`_supabase_admin`):
1. `sign_in_with_password` to detect existing users — **on success, the gotrue client rewrites its own `Authorization` header to the signed-in user's ~1h JWT**.
2. `admin.create_user` for new users — requires the service key in `Authorization`.

After any existing-user login, the singleton's `Authorization` holds a user JWT. When it expires, all subsequent **new-user** registrations send the dead token to `/auth/v1/admin/users` → `403 ... token is expired` → `get_or_create_user` raises → `gateway.py:451` shows `auth_registration_error` ("enter the correct code"). Confirmed in prod logs 2026-05-26 for chat_id `7521587406` (Ori). Prior related incident: `brain/planning/friend-signin-bug-resolved-stale-service-role-jwt.md` (different root cause — revoked legacy key — but same symptom; that fix is what exposed this one).

## Solution Statement

Make registration admin-only:
- Add `_find_user_by_email(client, email)` that paginates `admin.list_users()` and returns the matching `User` or `None`.
- `get_or_create_user` → find by email; return `{"user_id", "is_new": False}` if found, else `admin.create_user(...)` and return `{"user_id", "is_new": True}`.
- Delete the now-dead `sign_in_with_password` calls, the unused `access_token`/`refresh_token` return keys, and the unused `refresh_session()` function.

The singleton client is kept (it's efficient and now safe — nothing mutates its `Authorization`). The deterministic `_server_password` is kept (still set at create time so per-user sign-in remains *possible* in the future, but is never performed here).

## Feature Metadata

**Feature Type**: Bug Fix (with small refactor)
**Estimated Complexity**: Low
**Primary Systems Affected**: `bot/supabase_admin.py` (core), `bot/gateway.py` (no logic change, return shape consumers verified), `tests/unit/test_supabase_admin.py`
**Dependencies**: `supabase` / `supabase-auth` 2.28.0 (already installed) — no new deps

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: READ THESE BEFORE IMPLEMENTING!

- `bot/supabase_admin.py` (whole file, ~120 lines) — Why: the file being rewritten. Note the singleton `_supabase_admin` (line 24), `_get_client()` (27-32), `_synthetic_email` (35-42), `_server_password` (45-58), `get_or_create_user` (61-105), `refresh_session` (108-119).
- `bot/gateway.py` (lines 403-459) — Why: the only caller. **Confirm it reads only `result["user_id"]` (428, 432) and `result.get("is_new", False)` (423).** It does NOT use `access_token`/`refresh_token` — that's what makes dropping them safe.
- `tests/unit/test_supabase_admin.py` (whole file) — Why: existing test style (class-based, `@patch` module constants, AAA docstrings). New tests go here.
- `tests/unit/test_onboarding.py` (lines 54-125) — Why: mocks `bot.gateway.get_or_create_user` return dict. Returns include `access_token`/`refresh_token` keys (62-66, 89-93, 117-121) — these become unused extra keys after the fix; harmless, but optionally trim for cleanliness.
- `tests/unit/test_gateway.py` (lines 82-95) — Why: same mock pattern for the registration path.

### New Files to Create

- None. (All changes are in-place edits + new test methods.)

### Relevant Documentation — READ BEFORE IMPLEMENTING!

- Supabase Python Admin API (`supabase-auth` 2.28.0) — verified locally via introspection:
  - `admin.list_users(page: Optional[int]=None, per_page: Optional[int]=None) -> List[User]` — **returns a plain list**; no server-side email filter exists, so filter client-side. Paginate until a short/empty page.
  - `admin.create_user(attributes) -> UserResponse` — access the created user via `.user` (i.e. `resp.user.id`).
  - `admin.get_user_by_id(uid) -> UserResponse` — not needed (we have email, not id).
  - `User` model fields include `id`, `email` (confirmed via `User.model_fields`).
  - Reference: https://supabase.com/docs/reference/python/auth-admin-listusers and https://supabase.com/docs/reference/python/auth-admin-createuser
- `docs/adr/0001-app-layer-user-authorization.md` — Why: confirms per-user isolation is app-layer (`user_id` scoping), NOT dependent on the user JWTs being removed. Removing sign-in does not weaken data isolation.
- `PRD.md` (lines 394-410, "Security: Auth Limitation") — Why: documents the accepted auth model; this fix stays within it.

### Patterns to Follow

**Async + lazy singleton (keep as-is):** `bot/supabase_admin.py:27-32`
```python
async def _get_client() -> AsyncClient:
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = await acreate_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _supabase_admin
```

**Logging:** module uses stdlib `logging` (`logger = logging.getLogger(__name__)`, line 16). Keep `logger.info("Created new user for chat_id=%s", telegram_chat_id)` and `logger.info("Found existing user for chat_id=%s", telegram_chat_id)` (replaces the old "Signed in existing user" line).

**Return contract (new):** `{"user_id": str, "is_new": bool}` — drop `access_token`/`refresh_token`.

**Test style:** `tests/unit/test_supabase_admin.py` — class grouping, `@patch("bot.supabase_admin....")`, AAA docstrings, no real network. Mock `_get_client` to return a `MagicMock` whose `auth.admin.list_users` / `auth.admin.create_user` are `AsyncMock`s.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation
Add the email-lookup helper that paginates `list_users`.

### Phase 2: Core Implementation
Rewrite `get_or_create_user` to find-then-create, admin-only. Remove `sign_in_with_password` and `refresh_session`.

### Phase 3: Integration
No caller changes required (verified). Optionally trim unused token keys from test mocks.

### Phase 4: Testing & Validation
Add unit tests for: existing-user-found, new-user-created, found-on-second-page (pagination), and that `create_user` is NOT called when the user exists. Run unit suite + ruff.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom.

### UPDATE `bot/supabase_admin.py` — add `_find_user_by_email` helper

- **IMPLEMENT**: An async helper that paginates the admin API and returns the matching user or `None`:
  ```python
  async def _find_user_by_email(client: AsyncClient, email: str):
      """Return the auth user with this email, or None. Admin-only; never signs in."""
      page = 1
      per_page = 200
      while True:
          users = await client.auth.admin.list_users(page=page, per_page=per_page)
          if not users:
              return None
          for user in users:
              if (user.email or "").lower() == email.lower():
                  return user
          if len(users) < per_page:
              return None
          page += 1
  ```
- **PATTERN**: async tool/helper style in this file; `list_users` verified signature `(page, per_page) -> List[User]`.
- **IMPORTS**: none new (`AsyncClient` already imported line 13). Type hint can be `-> "User | None"` with `from supabase_auth.types import User` if you want the import; otherwise omit the annotation to avoid an extra import.
- **GOTCHA**: `list_users` returns a **plain list** in 2.28.0 — do NOT access `.users`. If a future upgrade returns an object, this breaks; validate at runtime in the manual step. Emails are deterministic lowercase, but compare case-insensitively for safety.
- **VALIDATE**: `uv run ruff check bot/supabase_admin.py`

### REFACTOR `bot/supabase_admin.py` — rewrite `get_or_create_user` (admin-only)

- **IMPLEMENT**: Replace the entire body (current lines 61-105) with:
  ```python
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
  ```
- **PATTERN**: mirrors the existing create_user attributes block (old lines 86-93) and the `_synthetic_email`/`_server_password` helpers (unchanged).
- **IMPORTS**: `AuthApiError` import (line 14) may become unused after removing sign-in — **remove it if unused** to keep ruff clean (see next task's VALIDATE).
- **GOTCHA**: `create_user` returns `UserResponse`; the user is at `response.user.id` (NOT `response.id`). Race condition: if two messages create the same email simultaneously, the 2nd `create_user` raises `AuthApiError("email already registered")`. Single-bot/serial enough for POC; if you want belt-and-suspenders, wrap `create_user` in `try/except AuthApiError:` → re-run `_find_user_by_email` and return `is_new=False`. Keep `AuthApiError` import if you add this.
- **VALIDATE**: `uv run ruff check bot/supabase_admin.py`

### REMOVE `bot/supabase_admin.py` — delete unused `refresh_session`

- **REMOVE**: the entire `refresh_session` function (current lines 108-119). Grep confirmed zero callers outside this file.
- **GOTCHA**: after removal, re-check imports — if nothing else uses `AuthApiError`, remove `from supabase_auth.errors import AuthApiError` (line 14). (Skip removal only if you added the race-condition try/except above.)
- **VALIDATE**: `uv run ruff check bot/` (must be zero warnings, incl. unused imports)

### ADD `tests/unit/test_supabase_admin.py` — tests for admin-only registration

- **IMPLEMENT**: a new test class `TestGetOrCreateUser` with async tests. **`pyproject.toml` sets `asyncio_mode = "auto"`, so plain `async def test_...` works with NO `@pytest.mark.asyncio` decorator.** Mock `bot.supabase_admin._get_client` to return a `MagicMock()` client whose `auth.admin.list_users` and `auth.admin.create_user` are `AsyncMock`s.
  - `test_existing_user_returns_is_new_false`: `list_users` returns `[user(email=<synthetic>, id="uuid-x")]` → assert result `{"user_id": "uuid-x", "is_new": False}` and `create_user` **not called**.
  - `test_new_user_is_created`: `list_users` returns `[]` → `create_user` returns obj with `.user.id="uuid-new"` → assert `{"user_id": "uuid-new", "is_new": True}` and `create_user` called once with `email_confirm=True` + `user_metadata.telegram_chat_id`.
  - `test_pagination_finds_user_on_second_page`: first `list_users` call returns a full page (per_page items, none matching), second returns the matching user → assert found, `is_new=False`. (Use `AsyncMock(side_effect=[...])`.)
  - `test_no_sign_in_called`: assert the mock client has no `sign_in_with_password` invocation (e.g. construct client mock without it / assert not called).
- **PATTERN**: existing class + AAA docstrings in this same file (lines 13-50). Build fake users with `MagicMock(id=..., email=...)`.
- **IMPORTS**: `import pytest`, `from unittest.mock import AsyncMock, MagicMock, patch`.
- **GOTCHA**: `_synthetic_email(chat_id)` = `f"{chat_id}@{BOT_EMAIL_DOMAIN}"`; build the fake user's email with the same helper (import and call it) so the case-insensitive match hits. For pagination test, `per_page` is 200 — return a list of 200 non-matching `MagicMock`s for page 1 to force a 2nd page (or temporarily `@patch` a smaller per_page if you parametrize it; simplest: keep 200).
- **VALIDATE**: `uv run pytest tests/unit/test_supabase_admin.py -v`

### UPDATE (optional) `tests/unit/test_onboarding.py` & `test_gateway.py` — trim dead mock keys

- **UPDATE**: remove `"access_token"`/`"refresh_token"` keys from the `get_or_create_user` mock return dicts (onboarding lines 62-66, 89-93, 117-121; gateway ~94). Purely cosmetic — extra keys don't break anything since the gateway ignores them.
- **GOTCHA**: do NOT remove `user_id`/`is_new` — those ARE read.
- **VALIDATE**: `uv run pytest tests/unit/test_onboarding.py tests/unit/test_gateway.py -v`

---

## TESTING STRATEGY

### Unit Tests
New `TestGetOrCreateUser` class in `tests/unit/test_supabase_admin.py`, fully mocked (no network, no DB). Covers found / created / pagination / no-sign-in. Existing `TestPasswordSeed` must still pass (we keep `_server_password`).

### Integration Tests
Not strictly required (change is bot transport layer, mirroring the precedent in `commit_logs/2026-04-28_...`). The real proof is the manual prod check. Do NOT add a graph_api test — this path doesn't touch the graph.

### Edge Cases
- Existing user found on page 1 → no create.
- User found on page 2 (pagination correctness).
- New user → create called with correct attributes; returns `response.user.id`.
- (Optional) duplicate-create race → caught and resolved to `is_new=False`.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
```bash
uv run ruff check bot/ tests/unit/test_supabase_admin.py
```

### Level 2: Unit Tests
```bash
uv run pytest tests/unit/test_supabase_admin.py -v
uv run pytest tests/unit/ -v   # full unit suite — confirm no regressions (gateway/onboarding)
```

### Level 3: Integration Tests
```bash
# Not required for this change, but safe to confirm nothing broke:
uv run pytest tests/integration/ -v
```

### Level 4: Manual Validation (post-deploy, with user's permission)
1. Deploy bot image / restart `fitpal-bot` on Railway.
2. Have a NEW Telegram user (Ori) send the passphrase → expect onboarding welcome, NOT "enter the correct code".
3. Confirm prod logs show `Created new user for chat_id=...` and **no** `403 token is expired` on `admin/users`.
4. Confirm an EXISTING user still works (send passphrase → welcome back), proving the lookup path.

---

## ACCEPTANCE CRITERIA

- [ ] `get_or_create_user` contains no `sign_in_with_password` call.
- [ ] `get_or_create_user` returns `{"user_id", "is_new"}` (no token keys).
- [ ] `_find_user_by_email` paginates and matches case-insensitively.
- [ ] `refresh_session` removed; no unused imports (ruff clean).
- [ ] New unit tests pass; full `tests/unit/` passes with no regressions.
- [ ] Manual: a new user registers successfully in prod; logs show `Created new user`, no 403.

## COMPLETION CHECKLIST

- [ ] All tasks completed in order, each validated.
- [ ] `uv run ruff check bot/ tests/` clean.
- [ ] `uv run pytest tests/unit/ -v` green.
- [ ] Manual prod check confirms Ori can register.
- [ ] No regression for existing users.
- [ ] Commit log written (`commit_logs/`), and consider a short RCA in `docs/rca/` superseding the "no code fix needed" conclusion in `brain/planning/friend-signin-bug-resolved-stale-service-role-jwt.md`.

---

## NOTES

**Why keep the singleton client:** it was never the problem on its own — the problem was *mutating* its `Authorization` via `sign_in_with_password`. With sign-in gone, the singleton is safe and efficient.

**Why this doesn't weaken security:** per-user data isolation is enforced at the **application layer** (every service query filters by `user_id`, e.g. `src/services/daily_log_service.py:99-100`), not by the per-user JWTs being removed (those were minted and discarded — `gateway.py` reads only `result["user_id"]`). Decision documented in `docs/adr/0001` and `PRD.md:394-410`.

**Scalability of `list_users` lookup:** O(number of users) per registration. Fine at POC scale (dozens). Future optimization if the user base grows: query `auth.users` by email directly over the existing asyncpg connection (`SUPABASE_DB_URL`), or maintain a `chat_id → user_id` mapping. Out of scope here.

**Deploy/unblock note:** a `fitpal-bot` restart alone temporarily unblocks new users (fresh client → Authorization = service key until the next existing-user login poisons it again). The code fix is the durable solution; restart is only a stopgap.

**Confidence: 8.5/10** for one-pass success. Main uncertainty: exact `list_users` return shape across gotrue patch versions (verified `List[User]` on 2.28.0) and the test suite's asyncio config — both checkable in the first validation run.
```
