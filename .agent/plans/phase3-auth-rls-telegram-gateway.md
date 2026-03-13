# Feature: Phase 3 Steps 4–6 — Auth, RLS & Telegram Bot Gateway

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files etc.

## Feature Description

Implement Supabase Auth integration with LangGraph's custom auth handler, add Row Level Security policies to Supabase tables, and build a Telegram bot gateway using aiogram v3 — completing FitPal's transition from a single-user dev tool to a multi-user production service.

## User Story

As a FitPal user on Telegram
I want to log food and query stats by simply texting a bot
So that nutrition tracking feels effortless without needing a web app or login page

## Problem Statement

FitPal currently has no authentication — `user_id` is hardcoded as `DEFAULT_DEV_USER_ID`. There's no user-facing interface; it only works through LangSmith Studio. The DB has no RLS, meaning a direct Supabase connection could access any user's data.

## Solution Statement

Three-phase approach:
1. **Auth handler** (Step 4): LangGraph `@auth.authenticate` validates Supabase JWTs, flows `user_id` into the graph via `config["configurable"]["langgraph_auth_user"]`
2. **RLS policies** (Step 5): Defense-in-depth on `food_items` and `daily_logs` tables
3. **Telegram gateway** (Step 6): aiogram v3 webhook bot that auto-registers users in Supabase, generates JWTs, calls LangGraph API, and relays responses — with shared passphrase for access control

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High
**Primary Systems Affected**: `src/config.py`, `src/security/` (new), Supabase DB policies, new `bot/` package
**Dependencies**: `httpx` (async HTTP for JWT validation), `aiogram>=3.25` (Telegram bot), `supabase` (admin user creation), `aiohttp` (webhook server — bundled with aiogram)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `src/config.py` (lines 19–26) — `DEFAULT_DEV_USER_ID` and `get_user_id()` — must update to check `langgraph_auth_user` first
- `src/config.py` (lines 28–32) — `DATABASE_URL` construction from env var — pattern for adding new env vars
- `langgraph.json` (full file) — current config with no auth block; need `langgraph.production.json` with auth
- `src/database.py` (full file) — async engine setup pattern (SSL context for asyncpg)
- `src/agents/nutritionist.py` (full file) — `define_graph(**kwargs)` entry point, graph name is `"fitpal"`
- `tests/conftest.py` (lines 23–26) — `TEST_CONFIG_A`/`TEST_CONFIG_B` pattern — must remain compatible
- `tests/graph_api/conftest.py` (full file) — server auto-start, `lg_client` fixture, thread fixture
- `tests/graph_api/test_graph_flows.py` (lines 27, 80–117) — `DEV_USER_CONFIG`, `_run()` helper pattern
- `src/tools/food_lookup.py` — `search_food` (line 33), `create_food_item` (line 82) — where `get_user_id(config)` is called
- `src/services/daily_log_service.py` — `log_food_entry` (line 190), `query_food_logs` (line 211) — where `get_user_id(config)` is called
- `src/models.py` (full file) — `FoodItem` and `DailyLog` models with `user_id` columns

### New Files to Create

- `src/security/__init__.py` — empty package init
- `src/security/auth.py` — LangGraph custom auth handler (`@auth.authenticate` + `@auth.on`)
- `langgraph.production.json` — production config with auth path
- `bot/__init__.py` — empty package init
- `bot/gateway.py` — Telegram bot gateway (aiogram v3 webhook + aiohttp)
- `bot/supabase_admin.py` — Supabase admin helpers (user lookup/creation, JWT generation)
- `tests/unit/test_auth_handler.py` — unit tests for auth handler
- `tests/unit/test_gateway.py` — unit tests for gateway logic (passphrase check, message routing)

### Relevant Documentation — READ BEFORE IMPLEMENTING

- LangGraph Auth: https://docs.langchain.com/langsmith/set-up-custom-auth
  - `@auth.authenticate` decorator, `Auth.types.MinimalUserDict`, `Auth.exceptions.HTTPException`
  - Why: Core API for the auth handler implementation
- LangGraph Resource Auth: https://docs.langchain.com/langsmith/resource-auth
  - `@auth.on` handlers, metadata filtering, `AuthContext`
  - Why: Thread/run scoping to owning user
- LangGraph Auth + Supabase: https://docs.langchain.com/langsmith/add-auth-server
  - Supabase JWT validation via `/auth/v1/user` endpoint
  - Why: Exact pattern we're implementing
- aiogram v3 Webhook: https://docs.aiogram.dev/en/v3.25.0/dispatcher/webhook
  - `SimpleRequestHandler`, `setup_application`, aiohttp integration
  - Why: Webhook server setup for the Telegram gateway
- aiogram v3 Router: https://docs.aiogram.dev/en/v3.25.0/dispatcher/router.rst
  - `@router.message()` decorator, `message.answer()`, `message.from_user`
  - Why: Message handling patterns
- Supabase Auth Admin API: https://supabase.com/docs/reference/python/auth-admin-create-user
  - `supabase.auth.admin.create_user()`, `supabase.auth.admin.get_user_by_id()`
  - Why: Auto-registration of Telegram users

### Patterns to Follow

**Auth handler return type (from LangGraph docs):**
```python
# @auth.authenticate must return Auth.types.MinimalUserDict
return {
    "identity": user_id,         # Required — string
    "is_authenticated": True,    # Optional, defaults to True
    "permissions": ["read", "write"],  # Optional
}
```

**Config flow after auth (from LangGraph docs):**
```python
# After @auth.authenticate returns, LangGraph populates:
config["configurable"]["langgraph_auth_user"]     # Full dict from authenticate
config["configurable"]["langgraph_auth_user_id"]  # Just the "identity" string
```

**Resource authorization filter (from LangGraph docs):**
```python
@auth.on
async def add_owner(ctx: Auth.types.AuthContext, value: dict) -> dict:
    filters = {"owner": ctx.user.identity}
    metadata = value.setdefault("metadata", {})
    metadata.update(filters)
    return filters
```

**Existing user_id extraction pattern (from src/config.py:22-26):**
```python
def get_user_id(config: RunnableConfig | None) -> str:
    if config:
        return config["configurable"].get("user_id", DEFAULT_DEV_USER_ID)
    return DEFAULT_DEV_USER_ID
```

**aiogram v3 webhook pattern (from docs):**
```python
from aiogram import Bot, Dispatcher, Router
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

router = Router()

@router.message()
async def handle_message(message: Message) -> None:
    await message.answer("response text")

dp = Dispatcher()
dp.include_router(router)
app = web.Application()
webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET)
webhook_handler.register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)
web.run_app(app, host=host, port=port)
```

**Tool mock pattern for unit tests (from tests/conftest.py:107-112):**
```python
@pytest.fixture
def mock_search_food():
    with patch("src.agents.nodes.food_search_node.search_food") as mock:
        mock.ainvoke = AsyncMock()
        yield mock
```

---

## IMPLEMENTATION PLAN

### Phase A: Auth Handler (Step 4)

Foundation: Create the LangGraph custom auth handler that validates Supabase JWTs and scopes resources to users.

**Tasks:**
- Create `src/security/auth.py` with `@auth.authenticate` and `@auth.on`
- Update `get_user_id()` in `src/config.py` to check `langgraph_auth_user` first
- Create `langgraph.production.json` with auth path
- Add `httpx` dependency
- Unit test the auth handler

### Phase B: RLS Policies (Step 5)

Defense-in-depth: Add Supabase RLS policies so even direct DB access is scoped.

**Tasks:**
- Enable RLS on `food_items` and `daily_logs`
- Create policies for each table
- Verify via Supabase SQL editor

### Phase C: Telegram Bot Gateway (Step 6)

User interface: Build the aiogram v3 webhook bot that connects Telegram users to FitPal.

**Tasks:**
- Create `bot/` package with gateway and admin helpers
- Implement passphrase-based access control
- Implement auto-registration via Supabase admin API
- Implement message relay to LangGraph API
- Implement HITL interrupt/resume flow over Telegram
- Implement session thread management (30-min timeout)
- Unit test gateway logic

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

---

### Phase A: Auth Handler (Step 4)

#### Task 1: ADD `httpx` dependency

- **IMPLEMENT**: `uv add httpx` — async HTTP client for JWT validation calls to Supabase
- **GOTCHA**: Do NOT use `requests` (sync) — this runs inside async LangGraph nodes
- **VALIDATE**: `uv run python -c "import httpx; print(httpx.__version__)"`

#### Task 2: CREATE `src/security/__init__.py`

- **IMPLEMENT**: Empty file (package init)
- **VALIDATE**: File exists

#### Task 3: CREATE `src/security/auth.py`

- **IMPLEMENT**: LangGraph custom auth handler with two decorators:

  **`@auth.authenticate` handler:**
  - Import `Auth` from `langgraph_sdk`
  - Read `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` from env vars at module level
  - Accept `authorization: str | None` parameter
  - Assert authorization exists, split into `scheme` and `token`
  - Assert scheme is `"bearer"` (case-insensitive)
  - Use `httpx.AsyncClient` to call `{SUPABASE_URL}/auth/v1/user` with headers:
    - `Authorization: Bearer <token>` (pass through the original token)
    - `apiKey: {SUPABASE_SERVICE_KEY}`
  - Assert response status is 200
  - Extract `user["id"]` from response JSON
  - Return `{"identity": user["id"], "is_authenticated": True}`
  - On any failure: raise `Auth.exceptions.HTTPException(status_code=401, detail="...")`

  **`@auth.on` global resource handler:**
  - Accept `ctx: Auth.types.AuthContext` and `value: dict`
  - Set `filters = {"owner": ctx.user.identity}`
  - Add `filters` to `value.setdefault("metadata", {})`
  - Return `filters`
  - This ensures threads/runs are private to their creator

- **PATTERN**: Follow the Supabase JWT example from LangGraph docs (see Context References)
- **IMPORTS**: `from langgraph_sdk import Auth`, `import httpx`, `import os`
- **GOTCHA**: `SUPABASE_URL` is the project URL (e.g., `https://xxx.supabase.co`), NOT the DB connection string (`SUPABASE_DB_URL`). These are different env vars.
- **GOTCHA**: `SUPABASE_SERVICE_KEY` is the service_role key from Supabase dashboard → Project Settings → API. It bypasses RLS — never expose to clients.
- **GOTCHA**: Use `httpx.AsyncClient()` as a context manager to avoid connection leaks.
- **VALIDATE**: `uv run python -c "from src.security.auth import auth; print(type(auth))"`

#### Task 4: UPDATE `src/config.py` — update `get_user_id()`

- **IMPLEMENT**: Modify `get_user_id()` to check for auth handler's identity first:
  ```python
  def get_user_id(config: RunnableConfig | None) -> str:
      """Extract user_id from LangGraph config, falling back to dev default.

      Production: auth handler populates langgraph_auth_user.
      Dev/Studio: manual config["configurable"]["user_id"] or fallback.
      """
      if config:
          # Production path: auth handler sets this
          auth_user = config["configurable"].get("langgraph_auth_user")
          if auth_user:
              return auth_user["identity"]
          # Dev/Studio path: manual user_id in config
          return config["configurable"].get("user_id", DEFAULT_DEV_USER_ID)
      return DEFAULT_DEV_USER_ID
  ```
- **PATTERN**: Mirror existing function signature — still returns `str`, still accepts `RunnableConfig | None`
- **GOTCHA**: `langgraph_auth_user` is a dict with `"identity"` key (string). All existing callers expect a string from `get_user_id()`.
- **GOTCHA**: Must preserve backward compatibility — `TEST_CONFIG_A = {"configurable": {"user_id": TEST_USER_A}}` in tests must still work (no `langgraph_auth_user` key in test configs).
- **GOTCHA**: Dev path via `langgraph dev` (no auth in `langgraph.json`) will NOT have `langgraph_auth_user` — falls through to `user_id` key as before.
- **VALIDATE**: `uv run pytest tests/unit/ -v` — all existing tests must pass unchanged

#### Task 5: CREATE `langgraph.production.json`

- **IMPLEMENT**: Production config file with auth handler path:
  ```json
  {
    "dependencies": ["."],
    "graphs": {
      "fitpal": "./src/agents/nutritionist.py:define_graph"
    },
    "env": ".env",
    "auth": {
      "path": "src/security/auth.py:auth"
    }
  }
  ```
- **PATTERN**: Mirror `langgraph.json` structure, add `auth` block
- **GOTCHA**: `langgraph.json` (dev) stays unchanged — no auth block. This preserves Studio access without authentication.
- **GOTCHA**: The `path` value uses Python module path syntax with colon separator — `src/security/auth.py:auth` points to the `auth = Auth()` instance.
- **VALIDATE**: `uv run python -c "import json; d=json.load(open('langgraph.production.json')); assert 'auth' in d; print('OK')"`

#### Task 6: CREATE `tests/unit/test_auth_handler.py`

- **IMPLEMENT**: Unit tests for the auth handler with mocked Supabase HTTP calls:

  **Test 1: `test_valid_token_returns_user_identity`**
  - Arrange: Mock `httpx.AsyncClient.get` to return 200 with `{"id": "user-uuid-123", "email": "test@example.com"}`
  - Act: Call the authenticate function with `authorization="Bearer valid-token"`
  - Assert: Returns `{"identity": "user-uuid-123", "is_authenticated": True}`

  **Test 2: `test_missing_authorization_raises_401`**
  - Arrange: No mock needed
  - Act: Call authenticate with `authorization=None`
  - Assert: Raises `HTTPException` with status 401

  **Test 3: `test_invalid_token_raises_401`**
  - Arrange: Mock `httpx.AsyncClient.get` to return 401
  - Act: Call authenticate with `authorization="Bearer invalid-token"`
  - Assert: Raises `HTTPException` with status 401

  **Test 4: `test_malformed_authorization_raises_401`**
  - Arrange: No mock needed
  - Act: Call authenticate with `authorization="NotBearer token"`
  - Assert: Raises `HTTPException` with status 401

  **Test 5: `test_get_user_id_prefers_auth_user_over_manual`**
  - Arrange: Config with both `langgraph_auth_user` and `user_id` keys
  - Act: Call `get_user_id(config)`
  - Assert: Returns the `langgraph_auth_user["identity"]` value, not `user_id`

  **Test 6: `test_get_user_id_falls_back_to_manual_user_id`**
  - Arrange: Config with only `user_id` key (no `langgraph_auth_user`)
  - Act: Call `get_user_id(config)`
  - Assert: Returns the `user_id` value

  **Test 7: `test_get_user_id_falls_back_to_default`**
  - Arrange: Config with empty `configurable` dict
  - Act: Call `get_user_id(config)`
  - Assert: Returns `DEFAULT_DEV_USER_ID`

- **PATTERN**: Follow `tests/conftest.py` mock pattern — `unittest.mock.patch` + `AsyncMock`
- **IMPORTS**: `from src.security.auth import auth`, `from src.config import get_user_id, DEFAULT_DEV_USER_ID`
- **GOTCHA**: The `@auth.authenticate` decorated function is an internal handler — to unit test it, import and call the raw function (`get_current_user`) directly, not through the auth middleware.
- **GOTCHA**: Mock `httpx.AsyncClient` at `src.security.auth.httpx.AsyncClient` (where it's imported)
- **VALIDATE**: `uv run pytest tests/unit/test_auth_handler.py -v`

---

### Phase B: RLS Policies (Step 5)

#### Task 7: APPLY Supabase RLS migration — enable RLS and create policies

- **IMPLEMENT**: Run the following SQL via Supabase SQL Editor (Dashboard → SQL Editor) or via the `supabase` MCP tool's `execute_sql`:

  ```sql
  -- Enable RLS on both tables
  ALTER TABLE daily_logs ENABLE ROW LEVEL SECURITY;
  ALTER TABLE food_items ENABLE ROW LEVEL SECURITY;

  -- daily_logs: full CRUD scoped to owning user
  CREATE POLICY "Users can view own logs"
    ON daily_logs FOR SELECT
    USING (user_id = auth.uid());

  CREATE POLICY "Users can insert own logs"
    ON daily_logs FOR INSERT
    WITH CHECK (user_id = auth.uid());

  CREATE POLICY "Users can update own logs"
    ON daily_logs FOR UPDATE
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

  CREATE POLICY "Users can delete own logs"
    ON daily_logs FOR DELETE
    USING (user_id = auth.uid());

  -- food_items: all users can read shared DB foods; only owner can read/write estimated foods
  CREATE POLICY "Anyone can read shared database foods"
    ON food_items FOR SELECT
    USING (source = 'database' AND user_id IS NULL);

  CREATE POLICY "Users can read own estimated foods"
    ON food_items FOR SELECT
    USING (source = 'estimated' AND user_id = auth.uid());

  CREATE POLICY "Users can create estimated foods"
    ON food_items FOR INSERT
    WITH CHECK (source = 'estimated' AND user_id = auth.uid());

  -- Service role bypass: The LangGraph server connects with the service role key
  -- which bypasses RLS. RLS is defense-in-depth for direct DB access only.
  ```

- **GOTCHA**: `auth.uid()` returns the Supabase Auth user's UUID. This works when queries are made through Supabase client with a user JWT. Our app uses SQLAlchemy with the service role connection string, which bypasses RLS. RLS is a safety net only.
- **GOTCHA**: The service role key (`SUPABASE_SERVICE_KEY`) bypasses RLS by default. This is correct for our architecture — the LangGraph server handles authorization at the app layer.
- **GOTCHA**: Do NOT add RLS policies that block the service role — it needs full access for ETL, admin operations.
- **VALIDATE**: In Supabase Dashboard → Table Editor → click on `daily_logs` → verify "RLS Enabled" badge is shown. Repeat for `food_items`.

---

### Phase C: Telegram Bot Gateway (Step 6)

#### Task 8: ADD bot dependencies

- **IMPLEMENT**: `uv add aiogram httpx supabase`
  - `aiogram>=3.25` — Telegram bot framework (includes aiohttp)
  - `httpx` — already added in Task 1 (for LangGraph API calls from gateway)
  - `supabase` — Supabase Python client (for admin user creation)
- **GOTCHA**: `aiogram` pulls in `aiohttp` as a dependency — no need to add it separately
- **GOTCHA**: `httpx` may already be installed from Task 1 — `uv add` is idempotent
- **VALIDATE**: `uv run python -c "import aiogram; print(aiogram.__version__)"`

#### Task 9: CREATE `bot/__init__.py`

- **IMPLEMENT**: Empty file (package init)
- **VALIDATE**: File exists

#### Task 10: CREATE `bot/supabase_admin.py`

- **IMPLEMENT**: Supabase admin helper functions for user management and JWT generation:

  **Module-level setup:**
  - Import `os`, `hashlib`, `supabase.create_client`
  - Read `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `BOT_PASSPHRASE` from env
  - Create Supabase client with service role key: `supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)`

  **Synthetic email helper:**
  ```python
  def _synthetic_email(telegram_chat_id: int) -> str:
      """Generate a stable synthetic email for a Telegram user.

      Supabase Auth requires email or phone — this synthetic email maps
      chat_id to a unique identifier without needing a real inbox.
      email_confirm=True on creation skips verification.
      """
      return f"{telegram_chat_id}@telegram.fitpal.bot"
  ```

  **Server-side password helper:**
  ```python
  def _server_password(telegram_chat_id: int) -> str:
      """Generate a deterministic server-side password for a Telegram user.

      The password is never shown to the user — it's an implementation detail
      that allows the gateway to call sign_in_with_password() to obtain a JWT.
      Uses HMAC with BOT_PASSPHRASE as key so passwords change if passphrase rotates.
      """
      import hmac
      return hmac.new(
          BOT_PASSPHRASE.encode(),
          str(telegram_chat_id).encode(),
          hashlib.sha256,
      ).hexdigest()
  ```

  **`def get_or_create_user(telegram_chat_id: int) -> dict`:**
  - Build email via `_synthetic_email(chat_id)` and password via `_server_password(chat_id)`
  - Try `supabase_admin.auth.sign_in_with_password({"email": email, "password": password})`
  - If sign-in succeeds: user exists → return `{"user_id": session.user.id, "access_token": session.session.access_token, "refresh_token": session.session.refresh_token, "is_new": False}`
  - If sign-in fails (user doesn't exist): call `supabase_admin.auth.admin.create_user({"email": email, "password": password, "email_confirm": True, "user_metadata": {"telegram_chat_id": telegram_chat_id}})`
  - Then sign in with the newly created user to get a session: `supabase_admin.auth.sign_in_with_password({"email": email, "password": password})`
  - Return `{"user_id": session.user.id, "access_token": session.session.access_token, "refresh_token": session.session.refresh_token, "is_new": True}`

  **`def refresh_session(refresh_token: str) -> dict`:**
  - Call `supabase_admin.auth.refresh_session(refresh_token)`
  - Return `{"access_token": session.session.access_token, "refresh_token": session.session.refresh_token}`
  - Used by gateway when a cached JWT expires (401 from LangGraph auth handler)

  **JWT lifecycle in the gateway:**
  1. First message + passphrase → `get_or_create_user()` → returns `access_token` + `refresh_token`
  2. Subsequent messages → use cached `access_token` from `user_sessions`
  3. If LangGraph returns 401 (token expired) → call `refresh_session()` with cached `refresh_token` → retry
  4. If refresh also fails → re-authenticate via `sign_in_with_password()`

- **PATTERN**: Service module pattern — module-level client, sync functions (gateway is a separate process, not inside async LangGraph nodes)
- **GOTCHA**: `supabase` Python client v2 uses sync API. This is fine — the gateway runs in a separate process from LangGraph. The aiogram message handler can call these sync functions directly (they're fast HTTP calls, not blocking DB queries).
- **GOTCHA**: Synthetic email format (`{chat_id}@telegram.fitpal.bot`) — Supabase Auth requires email or phone. The email doesn't need to be real — it's just a stable unique identifier. `email_confirm: True` skips verification since there's no real inbox.
- **GOTCHA**: The server-side password is deterministic (HMAC of chat_id with BOT_PASSPHRASE as key). If you rotate BOT_PASSPHRASE, existing users' passwords become invalid — they'd need to be re-created or you'd need a migration. For MVP this is acceptable.
- **GOTCHA**: `sign_in_with_password()` returns a full session with `access_token` (JWT) and `refresh_token`. The `access_token` is what gets sent as `Authorization: Bearer <token>` to LangGraph.
- **VALIDATE**: `uv run python -c "from bot.supabase_admin import get_or_create_user; print('OK')"`

#### Task 11: CREATE `bot/gateway.py`

- **IMPLEMENT**: Main Telegram bot gateway with aiogram v3 webhook:

  **Config (from env vars):**
  ```
  BOT_TOKEN          — from BotFather
  WEBHOOK_BASE_URL   — public URL where Telegram sends webhooks (e.g., https://your-domain.com)
  WEBHOOK_PATH       — path for webhook endpoint (e.g., /webhook)
  WEBHOOK_SECRET     — secret token for Telegram webhook validation
  BOT_PASSPHRASE     — shared passphrase for access control
  LANGGRAPH_API_URL  — LangGraph server URL (e.g., http://localhost:2024 or internal VPS URL)
  ```

  **State storage (in-memory dict for now, migrate to Redis/DB later):**
  ```python
  # Maps telegram chat_id -> {"user_id": str, "thread_id": str, "last_activity": datetime, "access_token": str, "refresh_token": str}
  user_sessions: dict[int, dict] = {}
  ```

  **Passphrase flow:**
  - On first message from unknown `chat_id` (not in `user_sessions`):
    - Check if message text matches `BOT_PASSPHRASE`
    - If NO: reply "Send the invite code to get started." — do NOT process further
    - If YES: call `get_or_create_user(chat_id)` → store session → reply "Welcome to FitPal! You can start logging food now."
  - On subsequent messages from known `chat_id`: skip passphrase check

  **Message relay flow (for authenticated users):**
  1. Get or refresh session from `user_sessions[chat_id]`
  2. Check thread freshness: if `last_activity` > 30 min ago, create new thread
  3. Call LangGraph API via `httpx`:
     ```
     POST {LANGGRAPH_API_URL}/threads/{thread_id}/runs/wait
     Headers: Authorization: Bearer {jwt}
     Body: {
       "assistant_id": "fitpal",
       "input": {"messages": [{"role": "human", "content": message.text}]},
       "config": {}
     }
     ```
  4. Check response for interrupt (HITL):
     - If response has `__interrupt__` or tasks with interrupts: extract the preview, format it nicely for Telegram, reply to user
     - Store that the thread is in "interrupted" state
  5. If thread is in "interrupted" state and user sends a new message:
     - Resume with: `POST /threads/{thread_id}/runs/wait` with `command={"resume": message.text}`
  6. Extract final message from response, reply to user via `message.answer()`

  **HITL detection logic:**
  - After each run, call `GET /threads/{thread_id}/state` via httpx
  - Check `state["tasks"]` — if non-empty, the graph is paused at interrupt
  - This mirrors the `_assert_interrupted()` pattern from `tests/graph_api/test_graph_flows.py:120-129`

  **Startup hook:**
  ```python
  async def on_startup(bot: Bot) -> None:
      await bot.set_webhook(
          f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}",
          secret_token=WEBHOOK_SECRET,
      )
  ```

  **Main entry point:**
  ```python
  def main():
      dp = Dispatcher()
      dp.include_router(router)
      dp.startup.register(on_startup)
      bot = Bot(token=BOT_TOKEN)
      app = web.Application()
      webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET)
      webhook_handler.register(app, path=WEBHOOK_PATH)
      setup_application(app, dp, bot=bot)
      web.run_app(app, host="0.0.0.0", port=int(os.getenv("BOT_PORT", "8080")))
  ```

- **PATTERN**: Mirror aiogram v3 webhook example from docs (see Context References)
- **IMPORTS**: `from aiogram import Bot, Dispatcher, Router`, `from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application`, `from aiohttp import web`, `import httpx`
- **GOTCHA**: `WEBHOOK_SECRET` is used by aiogram's `SimpleRequestHandler` to validate that incoming requests are actually from Telegram (checks `X-Telegram-Bot-Api-Secret-Token` header). This is NOT the Supabase service key.
- **GOTCHA**: The LangGraph `runs/wait` endpoint returns the final output when the run completes, but returns intermediate state when it hits an interrupt. Need to detect this.
- **GOTCHA**: `user_sessions` is in-memory — lost on restart. For MVP this is acceptable (users just re-send passphrase). For production, store in Redis or Supabase.
- **GOTCHA**: Thread timeout (30 min) should use UTC timestamps. Compare `datetime.now(timezone.utc) - last_activity > timedelta(minutes=30)`.
- **GOTCHA**: The bot gateway is a SEPARATE process from the LangGraph server. It communicates via HTTP, not in-process.
- **VALIDATE**: `uv run python -c "from bot.gateway import main; print('OK')"` (import check only — don't call main)

#### Task 12: CREATE `tests/unit/test_gateway.py`

- **IMPLEMENT**: Unit tests for gateway logic (mock all external calls):

  **Test 1: `test_unknown_user_prompted_for_passphrase`**
  - Arrange: Message from unknown chat_id with text "hello"
  - Act: Process message
  - Assert: Bot replies with "Send the invite code to get started"

  **Test 2: `test_correct_passphrase_registers_user`**
  - Arrange: Message from unknown chat_id with correct passphrase
  - Mock: `get_or_create_user` returns `{"user_id": "uuid", "is_new": True}`
  - Act: Process message
  - Assert: Bot replies with welcome message, user added to `user_sessions`

  **Test 3: `test_wrong_passphrase_rejected`**
  - Arrange: Message from unknown chat_id with wrong passphrase
  - Act: Process message
  - Assert: Bot replies with "Send the invite code to get started" (same as unknown)

  **Test 4: `test_authenticated_user_message_relayed_to_langgraph`**
  - Arrange: Known user in `user_sessions`, message "I ate 200g of chicken"
  - Mock: httpx POST to LangGraph returns success response
  - Act: Process message
  - Assert: LangGraph API called with correct thread, JWT, and message

  **Test 5: `test_stale_session_creates_new_thread`**
  - Arrange: Known user with `last_activity` 45 min ago
  - Mock: httpx calls
  - Act: Process message
  - Assert: New thread created (httpx POST to `/threads`)

  **Test 6: `test_interrupted_state_resumes_with_command`**
  - Arrange: Known user with thread in interrupted state
  - Mock: httpx POST with `command={"resume": "yes"}`
  - Act: Process "yes" message
  - Assert: LangGraph API called with resume command, not new input

- **PATTERN**: Use `unittest.mock.patch` + `AsyncMock` for httpx and supabase calls
- **VALIDATE**: `uv run pytest tests/unit/test_gateway.py -v`

#### Task 13: UPDATE `CLAUDE.md` — add bot gateway to project structure

- **IMPLEMENT**: Add `bot/` directory to the project structure section and update the tech stack table
- **GOTCHA**: Keep changes minimal — only add what's new
- **VALIDATE**: Visual review

---

## TESTING STRATEGY

### Unit Tests (Phase A + C)

| Test File | Coverage |
|---|---|
| `tests/unit/test_auth_handler.py` | Auth handler validation (valid/invalid/missing tokens), `get_user_id()` priority logic |
| `tests/unit/test_gateway.py` | Passphrase flow, message relay, thread management, HITL resume |

**Mock boundaries:**
- `httpx.AsyncClient` — mock at `src.security.auth.httpx.AsyncClient` and `bot.gateway.httpx.AsyncClient`
- `supabase_admin` — mock at `bot.gateway.get_or_create_user` and `bot.gateway.generate_jwt_for_user`
- LangGraph API calls — mock httpx responses

### Existing Tests (Regression)

All existing unit and graph_api tests must pass unchanged. The `get_user_id()` update is backward-compatible.

### Edge Cases

- JWT expired mid-conversation → auth handler returns 401 → gateway should handle and re-authenticate
- Telegram sends duplicate webhook (retry) → gateway should be idempotent (same message = same response)
- LangGraph server unreachable → gateway should reply with a friendly error message
- User sends non-text message (photo, sticker) → gateway should reply "I can only process text messages"
- Very long message (>4096 chars) → Telegram's own limit, but LangGraph response might exceed it → split into chunks

---

## VALIDATION COMMANDS

### Level 1: Unit Tests (pre-commit gate)

```bash
uv run pytest tests/unit/ -v
```

### Level 2: Import Check

```bash
uv run python -c "from src.security.auth import auth; print('Auth handler OK')"
uv run python -c "from bot.gateway import main; print('Gateway OK')"
```

### Level 3: Auth Handler Manual Test (local)

```bash
# Start LangGraph dev with production config (auth enabled)
uv run langgraph dev -c langgraph.production.json

# In another terminal — should get 401 (no token)
curl -s http://localhost:2024/threads | head -5

# With a valid Supabase JWT — should get 200
curl -s -H "Authorization: Bearer <your-jwt>" http://localhost:2024/threads | head -5
```

### Level 4: Graph-API Tests (regression)

```bash
uv run pytest tests/graph_api/ -v -s
```

### Level 5: Bot Smoke Test (manual)

1. Set all env vars (`BOT_TOKEN`, `WEBHOOK_BASE_URL`, etc.)
2. Run gateway: `uv run python -m bot.gateway`
3. Open Telegram, send passphrase to bot
4. Send "I ate 200g of chicken" — verify HITL flow works
5. Send "yes" — verify commit and response

---

## ACCEPTANCE CRITERIA

- [ ] `src/security/auth.py` validates Supabase JWTs and returns user identity
- [ ] `@auth.on` handler scopes threads/runs to owning user via metadata
- [ ] `get_user_id()` checks `langgraph_auth_user` first, falls back to `user_id`, then default
- [ ] All existing unit tests pass unchanged (backward compatibility)
- [ ] All existing graph_api tests pass unchanged
- [ ] `langgraph.production.json` includes auth path, `langgraph.json` unchanged
- [ ] RLS enabled on `daily_logs` and `food_items` with correct policies
- [ ] Telegram bot accepts passphrase from new users, rejects without passphrase
- [ ] Telegram bot relays messages to LangGraph and returns responses
- [ ] HITL interrupt/resume works over Telegram (2-turn flow)
- [ ] Session threads timeout after 30 min inactivity
- [ ] Auth handler unit tests cover valid, invalid, missing, and malformed tokens
- [ ] Gateway unit tests cover passphrase flow, message relay, and HITL resume

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + graph_api)
- [ ] No linting or type checking errors
- [ ] Manual testing confirms auth handler works
- [ ] Manual testing confirms Telegram bot works end-to-end
- [ ] Acceptance criteria all met

---

## NOTES

### Decisions Made in This Conversation

1. **JWT validation method**: HTTP call to Supabase `/auth/v1/user` (not local JWT decode)
2. **Access control**: Shared passphrase (`BOT_PASSPHRASE` env var) — Option 1 from discussion
3. **Telegram library**: aiogram v3 (async-native, Pydantic integration, lightweight)
4. **Security layers**: Firewall (VPS-internal LangGraph) + JWT validation (double layer)
5. **Code on GitHub is safe**: Validation logic is public, secrets in `.env` only
6. **Steps 4-6 in one plan**: Three phases (Auth → RLS → Gateway)

### Environment Variables (new)

| Variable | Purpose | Where Used |
|---|---|---|
| `SUPABASE_URL` | Supabase project URL (e.g., `https://xxx.supabase.co`) | `src/security/auth.py`, `bot/supabase_admin.py` |
| `SUPABASE_SERVICE_KEY` | Service role key (admin access) | `src/security/auth.py`, `bot/supabase_admin.py` |
| `BOT_TOKEN` | Telegram bot token from BotFather | `bot/gateway.py` |
| `WEBHOOK_BASE_URL` | Public URL for webhook (e.g., `https://your-domain.com`) | `bot/gateway.py` |
| `WEBHOOK_PATH` | Webhook path (e.g., `/webhook`) | `bot/gateway.py` |
| `WEBHOOK_SECRET` | Secret for Telegram webhook validation | `bot/gateway.py` |
| `BOT_PASSPHRASE` | Shared passphrase for access control | `bot/gateway.py` |
| `LANGGRAPH_API_URL` | LangGraph server URL | `bot/gateway.py` |
| `BOT_PORT` | Gateway server port (default: 8080) | `bot/gateway.py` |

### Architecture Diagram

```
Telegram Cloud
    │ webhook POST
    ▼
Bot Gateway (bot/gateway.py)           ← public-facing, port 8080
    │  1. Validate WEBHOOK_SECRET
    │  2. Check passphrase / session
    │  3. Get/create Supabase user
    │  4. Generate JWT
    │  5. Call LangGraph API with JWT
    ▼
LangGraph Server                       ← VPS-internal only, port 2024
    │  1. @auth.authenticate → validate JWT via Supabase
    │  2. @auth.on → scope resources to user
    │  3. Run graph (input → ... → response)
    │  4. Return result
    ▼
Supabase                               ← cloud, auth + app data
    │  - /auth/v1/user → JWT validation
    │  - food_items, daily_logs → RLS protected
    ▼
Bot Gateway ← response
    │
    ▼
Telegram Cloud → User sees response
```

### Resolved: Supabase JWT Generation Strategy

Gateway creates users with `admin.create_user()` using a **server-generated deterministic password** (HMAC of `chat_id` with `BOT_PASSPHRASE` as key). Then calls `sign_in_with_password()` to get a valid session with `access_token` (JWT) + `refresh_token`. The password is an implementation detail — never shown to the Telegram user. Token refresh handled via `refresh_session()` when LangGraph returns 401.

### Dev vs Production Unchanged

| | Dev (Studio) | Production |
|---|---|---|
| Config | `langgraph.json` (no auth) | `langgraph.production.json` (auth) |
| User ID | `DEFAULT_DEV_USER_ID` | From JWT via `langgraph_auth_user` |
| Command | `langgraph dev` | `langgraph up -c langgraph.production.json` |
