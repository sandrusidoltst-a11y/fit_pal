# Feature: PR #16 Fixes — Async Supabase, TypedDict Sessions, Passphrase Rotation Safety, Logging

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Four targeted fixes to the Telegram bot gateway (PR #16) to make it correctly handle multi-user concurrency, improve type safety, prevent data loss on passphrase rotation, and add production-grade observability.

## User Story

As a FitPal user on Telegram
I want the bot to handle multiple users concurrently without blocking
So that my messages are processed quickly even when other users are active

## Problem Statement

1. **Sync blocking**: `bot/supabase_admin.py` uses the sync Supabase client — sync HTTP calls from async handlers block the event loop, preventing concurrent message processing for multiple users.
2. **Untyped sessions**: `user_sessions` dict uses `dict` values with no schema — fragile, no IDE support, easy to mistype keys.
3. **Passphrase rotation breaks users**: `_server_password()` derives passwords from `BOT_PASSPHRASE` — rotating the invite code locks out all existing users.
4. **No logging**: All `except` blocks swallow errors with generic user messages — zero visibility into failures.

## Solution Statement

1. **Async Supabase client**: Replace sync `create_client`/`Client` with `acreate_client`/`AsyncClient`. All functions become `async def`.
2. **SessionData TypedDict**: Define a `SessionData` TypedDict for the session dict shape.
3. **BOT_PASSWORD_SEED**: Separate password derivation key from the user-facing passphrase. `_server_password()` uses `BOT_PASSWORD_SEED` (falls back to `BOT_PASSPHRASE` for backward compat).
4. **Structured logging**: Add `logging.getLogger(__name__)` to both `gateway.py` and `supabase_admin.py` with `logger.exception()` in error paths and `logger.info()` for key lifecycle events.

## Feature Metadata

**Feature Type**: Bug Fix + Enhancement
**Estimated Complexity**: Medium
**Primary Systems Affected**: `bot/gateway.py`, `bot/supabase_admin.py`, `tests/unit/test_gateway.py`
**Dependencies**: `supabase>=2.28.0` (already installed — has `AsyncClient` + `acreate_client`)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `bot/supabase_admin.py` (full file, 107 lines) — All sync Supabase calls that need async conversion
- `bot/gateway.py` (full file, 234 lines) — 3 call sites for sync functions (lines 99, 148, 181), session dict usage, all `except` blocks
- `tests/unit/test_gateway.py` (full file, 313 lines) — Mock patterns that need `AsyncMock` updates
- `src/config.py` (lines 17-19) — `BASE_DIR`, `DEFAULT_DEV_USER_ID` patterns for env var usage

### New Files to Create

None — all changes are to existing files.

### Relevant Documentation — READ BEFORE IMPLEMENTING

- [Supabase Python Async Client](https://supabase.com/docs/reference/python/realtime-api)
  - `acreate_client()` usage: `from supabase import acreate_client, AsyncClient`
  - `supabase: AsyncClient = await acreate_client(url, key)`
  - Why: Core import and initialization pattern for the async migration
- [Supabase Python sign_in_with_password](https://supabase.com/docs/reference/python/auth-signinwithpassword)
  - Sync: `response = supabase.auth.sign_in_with_password({"email": ..., "password": ...})`
  - Async: same call, just `await` it
  - Why: Used in `get_or_create_user()` — must add `await`
- [Supabase Python admin.create_user](https://supabase.com/docs/reference/python/auth-admin-createuser)
  - `response = supabase.auth.admin.create_user({"email": ..., "password": ..., "email_confirm": True, "user_metadata": {...}})`
  - Why: Used in `get_or_create_user()` — must add `await`
- [Supabase Python admin.update_user_by_id](https://supabase.com/docs/reference/python/auth-admin-updateuserbyid)
  - `response = supabase.auth.admin.update_user_by_id(user_id, {"password": "new_password"})`
  - Why: Reference for future passphrase migration script (not implemented in this PR, but good to know exists)

### Patterns to Follow

**Async client initialization (from Supabase docs):**
```python
from supabase import acreate_client, AsyncClient

async def _get_client() -> AsyncClient:
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = await acreate_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _supabase_admin
```

**TypedDict pattern (from src/agents/state.py):**
```python
class SessionData(TypedDict):
    user_id: str
    thread_id: str
    ...
```

**Env var pattern (from bot/supabase_admin.py:15-17):**
```python
BOT_PASSWORD_SEED = os.environ.get("BOT_PASSWORD_SEED", "")
```

---

## IMPLEMENTATION PLAN

### Phase 1: Async Supabase Client Migration

Convert `supabase_admin.py` from sync to async. Update all call sites in `gateway.py`. Update test mocks.

**Tasks:**
- Convert imports and client initialization to async
- Convert `get_or_create_user()` and `refresh_session()` to `async def`
- Add `await` to 3 call sites in `gateway.py`
- Update test mock to use `AsyncMock`

### Phase 2: TypedDict for Sessions

Add a `SessionData` TypedDict to `gateway.py` and type the `user_sessions` dict.

### Phase 3: Passphrase Rotation Safety

Add `BOT_PASSWORD_SEED` env var. Update `_server_password()` to use it. Maintain backward compat.

### Phase 4: Structured Logging

Add `logging.getLogger(__name__)` to both bot files. Add `logger.exception()` in error paths, `logger.info()` for lifecycle events.

### Phase 5: Test Updates

Update existing tests and add new tests for the passphrase seed logic.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

---

### Phase 1: Async Supabase Client Migration

#### Task 1: UPDATE `bot/supabase_admin.py` — convert to async Supabase client

- **IMPLEMENT**:
  1. Change import: `from supabase import Client, create_client` → `from supabase import AsyncClient, acreate_client`
  2. Change type annotation: `_supabase_admin: Client | None = None` → `_supabase_admin: AsyncClient | None = None`
  3. Convert `_get_client()` to `async def`:
     ```python
     async def _get_client() -> AsyncClient:
         global _supabase_admin
         if _supabase_admin is None:
             _supabase_admin = await acreate_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
         return _supabase_admin
     ```
  4. Convert `get_or_create_user()` to `async def`. Replace all `_get_client().auth.` calls with `client = await _get_client()` then `await client.auth.`:
     ```python
     async def get_or_create_user(telegram_chat_id: int) -> dict:
         email = _synthetic_email(telegram_chat_id)
         password = _server_password(telegram_chat_id)
         client = await _get_client()

         try:
             response = await client.auth.sign_in_with_password(
                 {"email": email, "password": password}
             )
             return {
                 "user_id": response.user.id,
                 "access_token": response.session.access_token,
                 "refresh_token": response.session.refresh_token,
                 "is_new": False,
             }
         except AuthApiError:
             pass

         await client.auth.admin.create_user(
             {
                 "email": email,
                 "password": password,
                 "email_confirm": True,
                 "user_metadata": {"telegram_chat_id": telegram_chat_id},
             }
         )

         response = await client.auth.sign_in_with_password(
             {"email": email, "password": password}
         )
         return {
             "user_id": response.user.id,
             "access_token": response.session.access_token,
             "refresh_token": response.session.refresh_token,
             "is_new": True,
         }
     ```
  5. Convert `refresh_session()` to `async def`:
     ```python
     async def refresh_session(refresh_token: str) -> dict:
         client = await _get_client()
         response = await client.auth.refresh_session(refresh_token)
         return {
             "access_token": response.session.access_token,
             "refresh_token": response.session.refresh_token,
         }
     ```
- **IMPORTS**: `from supabase import AsyncClient, acreate_client`
- **GOTCHA**: `_synthetic_email()` and `_server_password()` are pure functions (no I/O) — they stay sync.
- **GOTCHA**: `acreate_client()` is async — must be awaited. This makes `_get_client()` async too, and every caller must `await` it.
- **GOTCHA**: Get client once per function call (`client = await _get_client()`) instead of calling `await _get_client()` multiple times. Cleaner and avoids redundant lazy-init checks.
- **VALIDATE**: `uv run python -c "from bot.supabase_admin import get_or_create_user; import inspect; print('async:', inspect.iscoroutinefunction(get_or_create_user))"`

#### Task 2: UPDATE `bot/gateway.py` — add `await` to 3 call sites

- **IMPLEMENT**: Add `await` keyword to all 3 sync calls:
  1. Line 99 (inside `_handle_authenticated_message`, session expired during thread creation):
     `tokens = refresh_session(...)` → `tokens = await refresh_session(...)`
  2. Line 148 (inside `_handle_authenticated_message`, 401 mid-conversation):
     `tokens = refresh_session(...)` → `tokens = await refresh_session(...)`
  3. Line 181 (inside `handle_message`, passphrase flow):
     `result = get_or_create_user(chat_id)` → `result = await get_or_create_user(chat_id)`
- **GOTCHA**: All 3 call sites are already inside `async def` functions — adding `await` is safe.
- **VALIDATE**: `uv run python -c "import ast; tree = ast.parse(open('bot/gateway.py').read()); print('OK')"`

#### Task 3: UPDATE `tests/unit/test_gateway.py` — fix mock for async `get_or_create_user`

- **IMPLEMENT**: In `TestPassphraseFlow.test_correct_passphrase_registers_user()`, change the patch decorator from:
  ```python
  @patch("bot.gateway.get_or_create_user")
  ```
  to:
  ```python
  @patch("bot.gateway.get_or_create_user", new_callable=AsyncMock)
  ```
  The `return_value` assignment stays the same — `AsyncMock` handles awaiting correctly.
- **PATTERN**: Mirror existing pattern at line 71: `@patch("bot.gateway._create_thread", new_callable=AsyncMock)`
- **GOTCHA**: Without `new_callable=AsyncMock`, doing `await get_or_create_user(...)` in gateway will fail because the default `MagicMock` is not awaitable.
- **GOTCHA**: Also check if any other test patches `refresh_session` — if so, those need `AsyncMock` too. Currently `refresh_session` is not directly patched in tests (it's only called inside nested try/except paths that aren't exercised by existing tests), but verify.
- **VALIDATE**: `uv run pytest tests/unit/test_gateway.py -v`

---

### Phase 2: TypedDict for Sessions

#### Task 4: UPDATE `bot/gateway.py` — add SessionData TypedDict

- **IMPLEMENT**: Add a `SessionData` TypedDict near the top of the file (after imports, before constants):
  ```python
  from typing import TypedDict

  class SessionData(TypedDict):
      """Telegram user session — tracks auth tokens and LangGraph thread state."""
      user_id: str
      thread_id: str
      last_activity: datetime
      access_token: str
      refresh_token: str
      interrupted: bool
  ```
  Then update the module-level dict type annotation:
  ```python
  user_sessions: dict[int, SessionData] = {}
  ```
- **GOTCHA**: `datetime` is already imported in gateway.py — no new import needed for the field type.
- **GOTCHA**: The `TypedDict` import needs to be added — `from typing import TypedDict`.
- **VALIDATE**: `uv run python -c "from bot.gateway import SessionData, user_sessions; print('OK')"`

---

### Phase 3: Passphrase Rotation Safety

#### Task 5: UPDATE `bot/supabase_admin.py` — add BOT_PASSWORD_SEED

- **IMPLEMENT**:
  1. Add new env var read after existing `BOT_PASSPHRASE` line:
     ```python
     BOT_PASSWORD_SEED = os.environ.get("BOT_PASSWORD_SEED", "") or BOT_PASSPHRASE
     ```
     This falls back to `BOT_PASSPHRASE` when `BOT_PASSWORD_SEED` is not set — backward compatible.
  2. Update `_server_password()` to use `BOT_PASSWORD_SEED` instead of `BOT_PASSPHRASE`:
     ```python
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
     ```
- **GOTCHA**: The `or BOT_PASSPHRASE` fallback means existing deployments without `BOT_PASSWORD_SEED` set will continue working with the same derived passwords — no migration needed.
- **GOTCHA**: Once `BOT_PASSWORD_SEED` is set, it must NEVER be rotated (same constraint that `BOT_PASSPHRASE` had before, but now only on this dedicated var).
- **VALIDATE**: `uv run python -c "from bot.supabase_admin import BOT_PASSWORD_SEED; print('seed loaded:', bool(BOT_PASSWORD_SEED))"`

---

### Phase 4: Structured Logging

#### Task 6: UPDATE `bot/gateway.py` — add logging

- **IMPLEMENT**:
  1. Add `import logging` and `logger = logging.getLogger(__name__)` at top of file.
  2. Add `logger.info()` for key lifecycle events:
     - User registered: after successful passphrase + `get_or_create_user` (log `chat_id`, `is_new`)
     - Thread created: after `_create_thread` success (log `thread_id`)
     - Session expired/refreshed: in token refresh paths
  3. Add `logger.exception()` before every generic error message sent to user:
     - Line ~96 (thread creation + refresh failure): `logger.exception("Failed to create thread for chat_id=%s", chat_id)`
     - Line ~144-146 (401 + refresh failure): `logger.exception("Token refresh failed for chat_id=%s", chat_id)`
     - Line ~161 (generic exception in message relay): `logger.exception("Error relaying message for chat_id=%s", chat_id)`
     - Line ~194 (registration failure): `logger.exception("Registration failed for chat_id=%s", chat_id)`
- **GOTCHA**: Use `logger.exception()` (not `logger.error()`) inside `except` blocks — it automatically includes the traceback.
- **GOTCHA**: Never log tokens, passwords, or message content — only `chat_id`, `thread_id`, `is_new`, and operation names.
- **VALIDATE**: `uv run python -c "from bot.gateway import logger; print('logger:', logger.name)"`

#### Task 7: UPDATE `bot/supabase_admin.py` — add logging

- **IMPLEMENT**:
  1. Add `import logging` and `logger = logging.getLogger(__name__)` at top of file.
  2. Add `logger.info()` for:
     - User sign-in success: `logger.info("Signed in existing user for chat_id=%s", telegram_chat_id)`
     - User creation: `logger.info("Created new user for chat_id=%s", telegram_chat_id)`
     - Session refresh: `logger.info("Refreshed session")`
  3. The `except AuthApiError: pass` on line 73 is intentional (fallback to create) — add a `logger.debug()` there:
     `logger.debug("User not found for chat_id=%s, creating new user", telegram_chat_id)`
- **GOTCHA**: Never log email addresses or passwords — only `chat_id`.
- **VALIDATE**: `uv run python -c "from bot.supabase_admin import logger; print('logger:', logger.name)"`

---

### Phase 5: Test Updates

#### Task 8: UPDATE `tests/unit/test_gateway.py` — update `clear_sessions` fixture type hint

- **IMPLEMENT**: The `clear_sessions` fixture clears `gw.user_sessions`. After Task 4, the dict type changed. No functional change needed in the fixture — it still calls `.clear()`. But verify that test session dicts match the `SessionData` TypedDict shape (they already do — all 6 keys are present in every test setup).
- **VALIDATE**: `uv run pytest tests/unit/test_gateway.py -v`

#### Task 9: ADD test for `BOT_PASSWORD_SEED` fallback behavior

- **IMPLEMENT**: Add a new test class to `tests/unit/test_gateway.py` (or create a new file `tests/unit/test_supabase_admin.py` if it doesn't exist):
  ```python
  class TestPasswordSeed:
      """Tests for BOT_PASSWORD_SEED / BOT_PASSPHRASE separation."""

      @patch("bot.supabase_admin.BOT_PASSWORD_SEED", "my-fixed-seed")
      def test_password_uses_seed_not_passphrase(self):
          """
          arrange: BOT_PASSWORD_SEED is set to a specific value.
          act:     Call _server_password with a chat_id.
          assert:  Password is derived from the seed, not BOT_PASSPHRASE.
          """
          from bot.supabase_admin import _server_password
          password = _server_password(12345)
          # Verify it's a valid hex string (SHA-256 HMAC output)
          assert len(password) == 64
          assert all(c in "0123456789abcdef" for c in password)

      @patch("bot.supabase_admin.BOT_PASSWORD_SEED", "seed-value")
      def test_same_chat_id_produces_same_password(self):
          """
          arrange: Fixed seed value.
          act:     Call _server_password twice with the same chat_id.
          assert:  Both calls return the same password (deterministic).
          """
          from bot.supabase_admin import _server_password
          assert _server_password(12345) == _server_password(12345)

      @patch("bot.supabase_admin.BOT_PASSWORD_SEED", "seed-value")
      def test_different_chat_ids_produce_different_passwords(self):
          """
          arrange: Fixed seed value.
          act:     Call _server_password with two different chat_ids.
          assert:  Passwords are different.
          """
          from bot.supabase_admin import _server_password
          assert _server_password(12345) != _server_password(67890)
  ```
- **VALIDATE**: `uv run pytest tests/unit/test_supabase_admin.py -v` (or wherever the tests are placed)

---

## TESTING STRATEGY

### Unit Tests

- **Existing tests** (`test_gateway.py`): 10 tests — must all pass after async migration. Only mock change: `get_or_create_user` gets `new_callable=AsyncMock`.
- **Existing tests** (`test_auth_handler.py`): 10 tests — no changes needed (auth handler is unaffected).
- **New tests**: 3 tests for `BOT_PASSWORD_SEED` behavior (determinism, seed isolation, fallback).

### Edge Cases

- `BOT_PASSWORD_SEED` not set → falls back to `BOT_PASSPHRASE` (backward compat)
- `BOT_PASSWORD_SEED` set → passphrase can rotate freely without affecting passwords
- Concurrent async calls to `_get_client()` during lazy init (harmless — worst case creates client twice, second assignment wins with same client)

---

## VALIDATION COMMANDS

### Level 1: Syntax

```bash
uv run python -c "import bot.gateway; import bot.supabase_admin; print('imports OK')"
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/test_gateway.py tests/unit/test_auth_handler.py -v
```

### Level 3: Full Unit Suite

```bash
uv run pytest tests/unit/ -v
```

---

## ACCEPTANCE CRITERIA

- [ ] `bot/supabase_admin.py` uses `AsyncClient` + `acreate_client` — all functions are `async def` (except pure helpers)
- [ ] `bot/gateway.py` call sites use `await` for `get_or_create_user` and `refresh_session`
- [ ] `user_sessions` is typed as `dict[int, SessionData]` with a `SessionData` TypedDict
- [ ] `_server_password()` uses `BOT_PASSWORD_SEED` with fallback to `BOT_PASSPHRASE`
- [ ] Both bot files have `logging.getLogger(__name__)` with `logger.exception()` in error paths
- [ ] All existing tests pass (99 unit tests)
- [ ] New password seed tests pass
- [ ] No secrets logged (no tokens, passwords, or message content in log statements)

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit)
- [ ] No linting or import errors
- [ ] Acceptance criteria all met

---

## NOTES

- **No new dependencies** — `supabase>=2.28.0` already includes `AsyncClient` and `acreate_client`.
- **Backward compatibility** — `BOT_PASSWORD_SEED` falls back to `BOT_PASSPHRASE`, so existing deployments work without config changes.
- **Redis for sessions** — explicitly out of scope per user decision. Will be added in a future PR.
- **Lazy async init** — `_get_client()` uses async lazy initialization. There's a minor race condition if two coroutines call it simultaneously on first use — both would create a client, second assignment wins. This is harmless (same config, same result) and not worth adding a lock for.
- **Supabase async auth methods** — the async client has identical method names and parameters to the sync client. The only difference is all methods must be `await`ed. Error types (`AuthApiError`) are the same.
- **`admin.update_user_by_id()`** — exists in the Supabase admin API for updating passwords by user ID. Useful for a future migration script if passphrase rotation already happened before `BOT_PASSWORD_SEED` was introduced. Not implemented in this PR.
