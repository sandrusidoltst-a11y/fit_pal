# Feature: Remove Custom Auth, Add Shared Secret Middleware, Pass user_id via Config

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Remove the LangGraph custom auth handler from the production deployment config (enterprise-only feature), replace it with a **shared secret middleware** for service-to-service authentication, and update the bot to pass `user_id` directly in the request config body instead of via JWT Authorization headers.

## User Story

As a FitPal developer deploying to Railway
I want the LangGraph server to start without enterprise auth but still verify that requests come from our bot
So that the deployment works on the free self-hosted lite plan with basic service-to-service security

## Problem Statement

The LangGraph server crashes on startup with:
```
ValueError: Custom authentication is currently available in the cloud version of LangSmith Deployment
or with a self-hosting enterprise license.
```

The `"auth"` field in `langgraph.production.json` triggers license validation that fails in lite mode. Additionally, simply removing auth leaves the server with no request verification at all.

## Solution Statement

1. Remove `"auth"` from `langgraph.production.json` so the server starts without enterprise auth
2. Add a **custom FastAPI middleware** (`src/security/internal_auth_middleware.py`) that validates a shared secret via `X-Internal-Token` header — this uses LangGraph's `http.app` config, which does NOT require an enterprise license
3. Update `bot/gateway.py` to send `X-Internal-Token` header and pass `user_id` in the request config body
4. Remove JWT token management from the bot (no more access_token, refresh_token, Authorization headers)
5. Keep `src/security/auth.py` in the codebase for future enterprise use
6. Keep `bot/supabase_admin.py` — still needed for user creation/registration

**Security layers:**
- Shared secret middleware — verifies requests come from our bot
- Railway network isolation — server has no public URL
- Supabase RLS — database-level access control (defense-in-depth)

## Feature Metadata

**Feature Type**: Refactor (deployment adaptation)
**Estimated Complexity**: Low-Medium
**Primary Systems Affected**: `langgraph.production.json`, `bot/gateway.py`, `src/security/internal_auth_middleware.py` (new), `tests/unit/test_gateway.py`
**Dependencies**: None new (FastAPI/Starlette already included in LangGraph server base image)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `langgraph.production.json` — Remove `"auth"` block, add `"http": {"app": ...}` for middleware
- `bot/gateway.py` (lines 52-98) — `_create_thread`, `_call_langgraph`, `_check_interrupted` send `Authorization: Bearer <token>`. Must replace with `X-Internal-Token` header and pass `user_id` in config body.
- `bot/gateway.py` (lines 35-43) — `SessionData` TypedDict has `access_token` and `refresh_token`. Must remove.
- `bot/gateway.py` (lines 101-186) — `_handle_authenticated_message` has token refresh logic. Must simplify.
- `bot/gateway.py` (lines 189-227) — `handle_message` stores tokens in session. Must simplify.
- `bot/supabase_admin.py` — Keep as-is. Still needed for `get_or_create_user()`.
- `src/security/auth.py` — Keep as-is. Not loaded in production but preserved for future enterprise use.
- `src/config.py` (lines 26-50) — `get_user_id()` already supports config-based path. No changes needed.
- `tests/graph_api/test_graph_flows.py` (line 27) — Shows the pattern: `DEV_USER_CONFIG = {"configurable": {"user_id": "..."}}`.
- `tests/unit/test_gateway.py` — Must update mocks for new request format.

### New Files to Create

- `src/security/internal_auth_middleware.py` — FastAPI middleware that validates `X-Internal-Token` header
- `src/security/webapp.py` — FastAPI app that registers the middleware (referenced by `langgraph.production.json`)

### Files to Modify

- `langgraph.production.json` — Remove `"auth"`, add `"http": {"app": ...}`
- `bot/gateway.py` — Replace JWT auth with shared secret header + user_id in config
- `tests/unit/test_gateway.py` — Update mocks for new request format

### Relevant Documentation

- [LangGraph Custom Middleware](https://docs.langchain.com/langsmith/custom-middleware)
  - Shows how to create a FastAPI app with middleware and register it via `"http": {"app": "path:app"}` in langgraph.json
  - Why: This is how we add shared secret validation without enterprise auth
- [LangGraph Standalone Server Deployment](https://docs.langchain.com/langsmith/deploy-standalone-server)
  - Docker Compose example shows server running without auth
  - Why: Confirms server works without `"auth"` in config

### Patterns to Follow

**LangGraph custom middleware pattern (from docs):**
```python
# src/security/webapp.py
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI()

class InternalTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # validate token
        ...
        return await call_next(request)

app.add_middleware(InternalTokenMiddleware)
```

**langgraph.json registration:**
```json
{
  "http": {
    "app": "./src/security/webapp.py:app"
  }
}
```

**Config-based user_id injection (from graph-api tests):**
```python
DEV_USER_CONFIG = {"configurable": {"user_id": "00000000-0000-0000-0000-000000000001"}}
```

---

## IMPLEMENTATION PLAN

### Phase 1: Shared Secret Middleware

Create the middleware that validates `X-Internal-Token` header on all requests to the LangGraph server.

### Phase 2: Production Config Update

Remove `"auth"` and add `"http"` with the middleware app reference.

### Phase 3: Update Bot Gateway

Replace JWT auth flow with shared secret header + user_id in config body.

### Phase 4: Update Tests

Update gateway tests for new request format.

### Phase 5: Rebuild and Redeploy

Rebuild Docker images, push, and redeploy on Railway.

---

## STEP-BY-STEP TASKS

### Task 1: CREATE `src/security/internal_auth_middleware.py` — Shared secret middleware

- **IMPLEMENT**: Create a Starlette middleware that validates the `X-Internal-Token` header:
  ```python
  import os

  import structlog
  from starlette.middleware.base import BaseHTTPMiddleware
  from starlette.requests import Request
  from starlette.responses import JSONResponse

  logger = structlog.get_logger(__name__)

  INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "")


  class InternalTokenMiddleware(BaseHTTPMiddleware):
      """Validate that requests come from an authorized internal service.

      Checks the X-Internal-Token header against a shared secret.
      This replaces the enterprise-only @auth.authenticate handler
      for self-hosted lite deployments.
      """

      async def dispatch(self, request: Request, call_next):
          # Allow health check without token
          if request.url.path == "/ok":
              return await call_next(request)

          token = request.headers.get("X-Internal-Token", "")
          if not INTERNAL_API_SECRET or token != INTERNAL_API_SECRET:
              logger.warning(
                  "Request rejected: invalid or missing internal token",
                  path=request.url.path,
              )
              return JSONResponse(
                  status_code=401,
                  content={"detail": "Invalid or missing internal token"},
              )

          return await call_next(request)
  ```
- **GOTCHA**: Must allow `/ok` health check endpoint without token — Railway uses it to verify the service is alive.
- **GOTCHA**: If `INTERNAL_API_SECRET` is empty/unset, ALL requests are rejected. This is fail-closed by design.
- **VALIDATE**: No syntax errors

### Task 2: CREATE `src/security/webapp.py` — FastAPI app with middleware

- **IMPLEMENT**: Create the FastAPI app that registers the middleware:
  ```python
  from fastapi import FastAPI

  from src.security.internal_auth_middleware import InternalTokenMiddleware

  app = FastAPI()
  app.add_middleware(InternalTokenMiddleware)
  ```
- **GOTCHA**: The `app` variable name must match what's referenced in `langgraph.production.json`.
- **VALIDATE**: No syntax errors

### Task 3: UPDATE `langgraph.production.json` — Remove auth, add middleware

- **IMPLEMENT**: Replace `"auth"` with `"http"`:
  ```json
  {
    "dependencies": ["."],
    "graphs": {
      "fitpal": "./src/agents/nutritionist.py:define_graph"
    },
    "python_version": "3.13",
    "http": {
      "app": "./src/security/webapp.py:app"
    }
  }
  ```
- **GOTCHA**: Do NOT add `"http"` to `langgraph.json` (dev config) — dev server should remain open for Studio.
- **VALIDATE**: `cat langgraph.production.json` — confirm `"auth"` removed, `"http"` added

### Task 4: UPDATE `bot/gateway.py` — Simplify SessionData

- **IMPLEMENT**: Remove `access_token` and `refresh_token` from `SessionData`:
  ```python
  class SessionData(TypedDict):
      """Telegram user session -- tracks user identity and LangGraph thread state."""
      user_id: str
      thread_id: str
      last_activity: datetime
      interrupted: bool
  ```
- **IMPLEMENT**: Add `INTERNAL_API_SECRET` to the module-level env vars (near line 29):
  ```python
  INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "")
  ```
- **VALIDATE**: No syntax errors

### Task 5: UPDATE `bot/gateway.py` — Replace Authorization headers with X-Internal-Token

Update `_create_thread`, `_call_langgraph`, and `_check_interrupted`.

- **IMPLEMENT `_create_thread`**: Remove `access_token` param, use shared secret header:
  ```python
  async def _create_thread() -> str:
      """Create a new LangGraph thread and return its ID."""
      async with httpx.AsyncClient(timeout=10) as client:
          response = await client.post(
              f"{LANGGRAPH_API_URL}/threads",
              headers={"X-Internal-Token": INTERNAL_API_SECRET},
              json={},
          )
          response.raise_for_status()
          return response.json()["thread_id"]
  ```

- **IMPLEMENT `_call_langgraph`**: Replace `access_token` with `user_id`, use shared secret header, pass user_id in config:
  ```python
  async def _call_langgraph(
      thread_id: str,
      user_id: str,
      *,
      input: dict | None = None,
      command: dict | None = None,
  ) -> dict:
      """Call LangGraph runs/wait endpoint and return the result."""
      body: dict = {
          "assistant_id": ASSISTANT_ID,
          "config": {"configurable": {"user_id": user_id}},
      }
      if input is not None:
          body["input"] = input
      if command is not None:
          body["command"] = command

      async with httpx.AsyncClient(timeout=120) as client:
          response = await client.post(
              f"{LANGGRAPH_API_URL}/threads/{thread_id}/runs/wait",
              headers={"X-Internal-Token": INTERNAL_API_SECRET},
              json=body,
          )
          response.raise_for_status()
          return response.json()
  ```

- **IMPLEMENT `_check_interrupted`**: Remove `access_token`, use shared secret header:
  ```python
  async def _check_interrupted(thread_id: str) -> bool:
      """Check if the graph is paused at an interrupt."""
      async with httpx.AsyncClient(timeout=10) as client:
          response = await client.get(
              f"{LANGGRAPH_API_URL}/threads/{thread_id}/state",
              headers={"X-Internal-Token": INTERNAL_API_SECRET},
          )
          response.raise_for_status()
          state = response.json()
          tasks = state.get("tasks", [])
          return len(tasks) > 0
  ```

- **VALIDATE**: No syntax errors

### Task 6: UPDATE `bot/gateway.py` — Simplify `_handle_authenticated_message`

Remove all JWT token refresh logic. Simplify error handling.

- **IMPLEMENT**: Rewrite `_handle_authenticated_message`. Key changes:
  - Remove import of `refresh_session` from `bot.supabase_admin` (line 20)
  - Thread creation on stale session: call `_create_thread()` (no access_token)
  - On thread creation failure: remove token refresh attempt, just fail with error message
  - Call `_call_langgraph(thread_id, session["user_id"], ...)` with user_id
  - Call `_check_interrupted(thread_id)` (no access_token)
  - Remove the `httpx.HTTPStatusError` 401 special case — no more token refresh
  - Keep general `httpx.HTTPStatusError` and `Exception` handling for server errors

- **VALIDATE**: No syntax errors

### Task 7: UPDATE `bot/gateway.py` — Simplify `handle_message` registration

- **IMPLEMENT**: In the passphrase success block, simplify session creation:
  ```python
  result = await get_or_create_user(chat_id)
  thread_id = await _create_thread()
  user_sessions[chat_id] = {
      "user_id": result["user_id"],
      "thread_id": thread_id,
      "last_activity": datetime.now(timezone.utc),
      "interrupted": False,
  }
  ```
- **VALIDATE**: No syntax errors

### Task 8: UPDATE `tests/unit/test_gateway.py` — Update mocks for new request format

- **IMPLEMENT**: Read existing tests and update each one:
  - Mock `INTERNAL_API_SECRET` in gateway module (e.g., `@patch("bot.gateway.INTERNAL_API_SECRET", "test-secret")`)
  - Session fixtures: remove `access_token` and `refresh_token` fields
  - HTTP call mocks: verify `X-Internal-Token` header instead of `Authorization: Bearer`
  - `_call_langgraph` mocks: verify config body contains `user_id`
  - `_create_thread` / `_check_interrupted` mocks: no `access_token` arg
  - Remove any test that specifically tests JWT token refresh behavior
  - Keep passphrase tests — passphrase flow is unchanged

- **GOTCHA**: Do NOT change `tests/unit/test_auth_handler.py` — those tests validate `src/security/auth.py` and `get_user_id()` which remain in the codebase.
- **VALIDATE**: `uv run pytest tests/unit/test_gateway.py -v`

### Task 9: Run full validation

- **VALIDATE**:
  ```bash
  uv run pytest tests/unit/ -v
  uv run pytest tests/integration/ -v
  ```

### Task 10: Generate shared secret and set Railway env vars

- **IMPLEMENT**: Generate a secret:
  ```bash
  openssl rand -hex 32
  ```
- **IMPLEMENT**: Set it on BOTH services (must be the same value):
  ```bash
  railway variable --set "INTERNAL_API_SECRET=<generated-secret>" --service langgraph-server
  railway variable --set "INTERNAL_API_SECRET=<generated-secret>" --service fitpal-bot
  ```
- **VALIDATE**: Verify both services have the variable

### Task 11: Rebuild and Push Docker Images

- **IMPLEMENT**:
  ```bash
  PYTHONIOENCODING=utf-8 uv run langgraph build -t fitpal-server -c langgraph.production.json --platform linux/amd64
  docker build -t fitpal-bot -f bot/Dockerfile --platform linux/amd64 .
  docker tag fitpal-server dolevsan/fitpal-server:latest
  docker tag fitpal-bot dolevsan/fitpal-bot:latest
  docker push dolevsan/fitpal-server:latest
  docker push dolevsan/fitpal-bot:latest
  ```
- **VALIDATE**: `docker images | grep fitpal` — both images updated

### Task 12: Redeploy on Railway

- **IMPLEMENT**:
  ```bash
  railway redeploy --service langgraph-server --yes
  railway redeploy --service fitpal-bot --yes
  ```
- **VALIDATE**: `railway logs --service langgraph-server` — should show "All services started" without auth errors
- **VALIDATE**: `railway logs --service fitpal-bot` — should show bot running without errors
- **VALIDATE**: `curl -s "https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo"` — webhook set

---

## TESTING STRATEGY

### Unit Tests

- `tests/unit/test_gateway.py` — Updated for shared secret header + user_id in config
- `tests/unit/test_auth_handler.py` — **Unchanged** — validates `auth.py` and `get_user_id()`

### Integration Tests

- `tests/integration/` — **Unchanged** — tests DB layer, not auth

### Graph-API Tests

- `tests/graph_api/` — **Unchanged** — already use config-based user_id (dev server, no middleware)

### Edge Cases

- Empty `INTERNAL_API_SECRET` → all requests rejected (fail-closed)
- Missing `X-Internal-Token` header → 401
- Wrong `X-Internal-Token` value → 401
- `/ok` health check → allowed without token

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
uv run ruff check bot/gateway.py src/security/internal_auth_middleware.py src/security/webapp.py
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/test_gateway.py -v
uv run pytest tests/unit/test_auth_handler.py -v
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

### Level 4: Railway Deployment Verification

```bash
railway logs --service langgraph-server
railway logs --service fitpal-bot
curl -s "https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo"
```

---

## ACCEPTANCE CRITERIA

- [ ] `langgraph.production.json` has `"http"` with middleware, no `"auth"` field
- [ ] `src/security/internal_auth_middleware.py` validates `X-Internal-Token` header
- [ ] `src/security/webapp.py` registers the middleware as a FastAPI app
- [ ] `/ok` health check works without token
- [ ] Empty/missing token returns 401
- [ ] `bot/gateway.py` sends `X-Internal-Token` header on all requests
- [ ] `bot/gateway.py` passes `user_id` in config body
- [ ] `bot/gateway.py` has no JWT token management
- [ ] `SessionData` only has: `user_id`, `thread_id`, `last_activity`, `interrupted`
- [ ] `src/security/auth.py` is unchanged (kept for future use)
- [ ] `INTERNAL_API_SECRET` set on both Railway services
- [ ] All unit tests pass
- [ ] LangGraph server starts on Railway without errors
- [ ] Telegram bot can communicate with the server
- [ ] Food logging works end-to-end via Telegram

---

## COMPLETION CHECKLIST

- [ ] Task 1: Middleware created
- [ ] Task 2: FastAPI webapp created
- [ ] Task 3: `langgraph.production.json` updated
- [ ] Task 4: `SessionData` simplified, `INTERNAL_API_SECRET` added
- [ ] Task 5: API helpers updated (shared secret header, user_id in config)
- [ ] Task 6: `_handle_authenticated_message` simplified
- [ ] Task 7: Registration flow simplified
- [ ] Task 8: Gateway tests updated
- [ ] Task 9: Full test suite passes
- [ ] Task 10: Shared secret generated and set on Railway
- [ ] Task 11: Docker images rebuilt and pushed
- [ ] Task 12: Railway services redeployed and verified

---

## NOTES

### Security Model (Production)

```
Telegram User
    │
    │ passphrase auth (bot level)
    ▼
fitpal-bot ──── X-Internal-Token: <secret> ────▶ langgraph-server
                + config: {user_id: <uuid>}       │ middleware validates token
                                                   │ get_user_id() reads config
                                                   ▼
                                              Supabase DB
                                              (RLS enforces user_id scoping)
```

Three layers:
1. **Bot passphrase** — authenticates Telegram users
2. **Shared secret middleware** — verifies requests come from our bot (not random services on network)
3. **Supabase RLS** — database-level access control (defense-in-depth)

### What We're NOT Changing

- **`src/security/auth.py`** — Stays for future enterprise use
- **`bot/supabase_admin.py`** — Still needed for user registration and stable UUID identity
- **`tests/unit/test_auth_handler.py`** — Tests `auth.py` and `get_user_id()`, both preserved
- **RLS policies** — Still active on Supabase
- **`langgraph.json` (dev config)** — No middleware in dev, Studio stays open

### Why Custom Middleware Works but @auth.authenticate Doesn't

LangGraph's `@auth.authenticate` / `@auth.on` decorators are enterprise-only features enforced by license validation at startup. The `"http": {"app": ...}` config for custom middleware is a **general-purpose extension point** that works in all modes (lite, enterprise, cloud). It runs as standard Starlette middleware before requests reach the LangGraph API — no license check required.

**Confidence Score: 9/10** — Straightforward refactor. Middleware pattern is well-documented. Main risk is missed mock updates in gateway tests.
