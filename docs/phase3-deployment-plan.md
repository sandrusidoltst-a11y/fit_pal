# Phase 3: Production Deployment Plan

## Overview

Deploy FitPal as a multi-user production service using:
- **Supabase** — Postgres database + user authentication
- **LangGraph Standalone Server** — self-hosted (Docker + Postgres + Redis)
- **LangSmith** — tracing/monitoring (free tier, 5k traces/mo)
- **Telegram Bot** — primary messaging interface (WhatsApp planned for later)

### Cost Estimate
| Service | Cost |
|---|---|
| LangGraph library + server | Free (open source) |
| VPS (Fly.io / Railway / DigitalOcean) | ~$5–20/mo (runs all 3 containers) |
| Supabase (DB + Auth) | Free tier (500MB DB, 50k MAU) |
| LangSmith tracing | Free tier (5k traces/mo) |
| LLM API calls (OpenAI / Anthropic) | Pay-as-you-go |

### Infrastructure Architecture

```
┌─────────────────────────────────────────┐
│  VPS (~$5-20/mo) — Docker Compose       │
│                                         │
│  ┌───────────────────┐  Container 1     │
│  │ LangGraph API     │  (your agent)    │
│  │ Server            │                  │
│  └───────────────────┘                  │
│                                         │
│  ┌───────────────────┐  Container 2     │
│  │ Postgres 16       │  (checkpoints,   │
│  │                   │   threads)       │
│  └───────────────────┘                  │
│                                         │
│  ┌───────────────────┐  Container 3     │
│  │ Redis 6           │  (task queue,    │
│  │                   │   streaming)     │
│  └───────────────────┘                  │
└─────────────┬───────────────────────────┘
              │  network call
              ▼
    ┌──────────────────┐
    │ Supabase Cloud   │  ← separate service (free tier)
    │ (food_items,     │     app data + auth
    │  daily_logs,     │
    │  users)          │
    └──────────────────┘
```

### Key Infrastructure Decisions
- **Checkpoint DB is separate from app DB.** A local Postgres container on the VPS stores threads/checkpoints (managed automatically by the LangGraph server). Supabase Postgres stores app data (food_items, daily_logs). This avoids schema collision and resource competition.
- **You never write checkpointer code.** `define_graph(**kwargs)` accepts `checkpointer` from kwargs — the server injects its own. Any manually configured checkpointer is replaced by the built-in one.
- **Redis is lightweight.** Handles task queue and real-time event streaming. Small footprint.

---

## Step 1: Supabase Project Setup ✅

**Goal**: Create the Supabase project and migrate the schema from SQLite to Postgres.

**Status**: Complete.

- Create a Supabase project (choose region closest to VPS)
- Recreate `food_items` and `daily_logs` tables via Supabase migration (not Alembic — Supabase manages its own migrations)
- Seed `food_items` with the nutrition CSV data (ETL script adapted for Postgres)
- Verify tables and data via Supabase dashboard

### Key Decision
- **Keep SQLAlchemy + asyncpg** as the ORM layer (don't switch to Supabase Python client)
- Supabase is used as a managed Postgres host, not as a REST API backend
- Connection via standard Postgres connection string (session pooler, port 5432)

---

## Step 2: Add User Identity (user_id columns) ✅

**Goal**: Make the schema multi-user ready.

**Status**: Complete.

- Add `user_id` (UUID, NOT NULL) column to `daily_logs`
- Add `user_id` (UUID, nullable) column to `food_items` — only populated for `source="estimated"` items; NULL for shared `source="database"` items
- Update all SQLAlchemy queries in tools/services to filter by `user_id`
- Pass `user_id` through the graph via `config["configurable"]` (not AgentState — keeps state clean)

### Key Decision
- Estimated food items are **per-user** (each user builds their own estimated library)
- Shared DB food items (`source="database"`) have `user_id = NULL` and are visible to all

---

## Step 3: Swap Database Engine ✅

**Goal**: Switch FitPal from local SQLite to Supabase Postgres.

**Status**: Complete.

- Replace `aiosqlite` with `asyncpg` (`uv add asyncpg`)
- Update `src/config.py`: `DATABASE_URL` reads from env var pointing to Supabase Postgres
- Update `src/database.py`: remove SQLite-specific settings (`check_same_thread`, etc.)
- Alembic removed — Supabase migrations manage production schema
- Tests migrated to run against Supabase Postgres test DB (`TEST_DATABASE_URL` env var)

---

## Step 4: Auth Integration (Supabase Auth)

**Goal**: Authenticate users and flow `user_id` into the graph.

### Authentication Flow (Messaging Platform)

FitPal is a conversational bot on Telegram/WhatsApp — there is no web login page. The messaging platform authenticates the user (they verified their phone to use Telegram). The bot gateway trusts that identity.

```
User (Telegram)
    │
    ▼
Bot Gateway (webhook server)     ← identifies user by phone/chat_id
    │
    ▼
LangGraph Server (FitPal agent)  ← receives JWT, validates via auth handler
    │
    ▼
Supabase (DB + Auth)             ← issues JWTs, stores users
```

**Login flow (no login page needed):**
1. User sends first message on Telegram
2. Bot Gateway receives webhook with user's `chat_id` / phone number
3. Gateway checks Supabase Auth — does this user exist?
   - **No** → Gateway calls `supabase.auth.admin.create_user()` to auto-register (no OTP needed for server-side admin API)
   - **Yes** → User already exists
4. Gateway generates/retrieves a JWT for this user
5. Gateway calls LangGraph API with `Authorization: Bearer <jwt>` and the user's message
6. LangGraph auth handler validates the JWT, extracts `user_id`, injects into config
7. All nodes access user identity via `get_user_id(config)` — queries are scoped

### Implementation Steps

- **4a.** Create `src/security/auth.py` — LangGraph custom auth handler:
  ```python
  @auth.authenticate
  async def get_current_user(authorization: str | None):
      # Validate JWT via Supabase /auth/v1/user endpoint
      # Extract user_id from response
      # Return {"identity": user_id, "is_authenticated": True}
  ```
- **4b.** Update `get_user_id()` in `src/config.py` to support both dev and production paths:
  ```python
  def get_user_id(config):
      if config:
          # Production: auth handler populates this
          auth_user = config["configurable"].get("langgraph_auth_user")
          if auth_user:
              return auth_user["identity"]
          # Dev/Studio: manual config or fallback
          return config["configurable"].get("user_id", DEFAULT_DEV_USER_ID)
      return DEFAULT_DEV_USER_ID
  ```
- **4c.** Create `langgraph.production.json` with auth key:
  ```json
  {
    "auth": { "path": "./src/security/auth.py:auth" }
  }
  ```
- **4d.** Add `@auth.on` resource authorization handler to scope threads/runs to owning user
- **4e.** Unit test the auth handler (mock Supabase HTTP call)
- **4f.** Create a test user in Supabase Auth (manual, for E2E validation)

### Key Decisions
- Supabase Auth is the **identity provider** (issues JWTs)
- LangGraph auth handler is the **validator** (checks JWTs server-side via `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`)
- Service role key used only for admin/ETL/gateway operations, never in the graph
- **Auto-registration**: Users are created automatically on first message — no signup flow needed
- Nodes access user identity via `config["configurable"]["langgraph_auth_user"]["identity"]` in production, falling back to `config["configurable"]["user_id"]` in dev

### Environment Isolation (Dev vs Production)

```
┌─────────────────────────────────┐
│  Development (local)            │
│                                 │
│  langgraph dev                  │
│  → Studio (no auth)             │
│  → langgraph.json (no auth key) │
│  → .env → test DB               │
│  → user_id = DEFAULT_DEV_USER_ID│
└─────────────────────────────────┘

┌─────────────────────────────────┐
│  Production (VPS Docker)        │
│                                 │
│  langgraph up -c langgraph      │
│    .production.json             │
│  → auth handler active          │
│  → .env.production → prod DB    │
│  → user_id from JWT             │
│  → traces → LangSmith Cloud     │──→ smith.langchain.com
└─────────────────────────────────┘
```

| | Dev (Studio) | Production |
|---|---|---|
| Config file | `langgraph.json` | `langgraph.production.json` |
| Auth | None — `DEFAULT_DEV_USER_ID` | Supabase Auth + JWT validation |
| DB | Supabase test project | Supabase prod project |
| Monitoring | Studio (interactive) | LangSmith Cloud (traces, replays) |
| Run command | `langgraph dev` | `langgraph up -c langgraph.production.json` |

---

## Step 5: Row Level Security (Defense in Depth)

**Goal**: Add RLS as a safety net on top of application-level filtering.

- Enable RLS on `food_items` and `daily_logs` tables
- Policies:
  - `daily_logs`: full CRUD scoped to `user_id = auth.uid()`
  - `food_items`: all authenticated users can SELECT `source="database"` items; only owner can SELECT/INSERT `source="estimated"` items
- RLS is secondary — primary isolation is SQLAlchemy `WHERE user_id = ...` clauses
- RLS activates only if something bypasses the app layer (direct API access, Supabase dashboard queries)

---

## Step 6: Telegram Bot Gateway

**Goal**: Connect FitPal to Telegram as the user-facing interface.

### Architecture
- Telegram Bot API (python-telegram-bot or aiogram)
- Webhook server receives messages, maps `chat_id` to Supabase user
- Calls LangGraph API with JWT + user message
- Returns agent response to Telegram chat

### Thread Management (Session-Based)
- **Strategy**: One thread per conversation session, with inactivity timeout (~30 min)
- On each message: find the user's latest thread — if it's less than 30 min old, reuse it; otherwise, create a new one
- HITL interrupt/resume always works (happens within the same session)
- Context stays manageable (a few exchanges per session, not months of history)
- Daily stats queries scope by date via `consumed_at` in the DB — not by thread

### Key Decisions
- **Telegram first**, WhatsApp later (keep dev simple)
- **Auto-registration**: First message auto-creates Supabase user from Telegram `chat_id`
- **Session threads with timeout**: Balances HITL safety, context size, and natural chat UX
- Thread mapping stored as: `user_id → latest_thread_id + last_activity_timestamp`

---

## Step 7: Deploy LangGraph Standalone Server

**Goal**: Run FitPal as a production API server.

- Build Docker image: `langgraph build -c langgraph.production.json`
- Set up Docker Compose with:
  - LangGraph server container (runs the graph)
  - Postgres 16 container (checkpoints + threads — auto-managed by server)
  - Redis 6 container (task queue + streaming)
- Environment variables:
  - `DATABASE_URL` → Supabase Postgres (app data)
  - `DATABASE_URI` → local Postgres container (checkpoints — `postgres://postgres:postgres@langgraph-postgres:5432/postgres`)
  - `REDIS_URI` → local Redis container (`redis://langgraph-redis:6379`)
  - `SUPABASE_URL` → Supabase project URL (for auth handler)
  - `SUPABASE_SERVICE_KEY` → service role key (for auth handler)
  - `LANGSMITH_API_KEY` → for tracing
  - LLM API keys (OpenAI/Anthropic)
- Deploy to VPS (Fly.io, Railway, DigitalOcean, or similar)
- Verify: API endpoints respond, auth works, HITL interrupt/resume works over HTTP

### What stays the same (no code changes needed)
- `define_graph(**kwargs)` — server injects its own checkpointer
- `langgraph.json` / `langgraph.production.json` — deployment manifest
- HITL `interrupt()` + `Command` pattern — works identically over the API
- All node implementations and tool-first architecture

---

## Step 8: Smoke Test & Validation

**Goal**: Verify end-to-end flow in production.

- Create a test user via Supabase Auth
- Authenticate and get JWT
- Test via `langgraph-sdk` client:
  - Create a thread
  - Log food ("I had 200g of chicken and a banana")
  - Verify HITL interrupt → confirm → commit flow
  - Query daily stats
  - Verify data is scoped to the test user
- Test via Telegram bot:
  - Send first message → verify auto-registration
  - Log food → verify HITL flow over Telegram
  - Verify session thread reuse and timeout
- Check LangSmith traces are flowing
- Run security check: verify user A cannot see user B's data

---

## Migration Order Summary

```
Step 1: Supabase project + schema ──┐
Step 2: Add user_id columns ────────┤ ✅ Complete
Step 3: Swap DB engine ─────────────┘
Step 4: Auth integration (Supabase Auth + LangGraph handler)
Step 5: RLS policies
Step 6: Telegram bot gateway
Step 7: Deploy standalone server (Docker Compose on VPS)
Step 8: Smoke test & validation
```

Steps 1–3: Complete.
Steps 4–5: Require Supabase project (exists). Can be developed and unit-tested locally.
Step 6: Can be developed in parallel with steps 4–5.
Step 7: The actual deployment — everything before it is preparation.
Step 8: Post-deployment validation.
