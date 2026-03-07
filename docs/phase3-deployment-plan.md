# Phase 3: Production Deployment Plan

## Overview

Deploy FitPal as a multi-user production service using:
- **Supabase** — Postgres database + user authentication
- **LangGraph Standalone Server** — self-hosted (Docker + Postgres + Redis)
- **LangSmith** — tracing/monitoring (free tier, 5k traces/mo)

### Cost Estimate
| Service | Cost |
|---|---|
| LangGraph library + server | Free (open source) |
| VPS (Fly.io / Railway / DigitalOcean) | ~$5–20/mo |
| Supabase (DB + Auth) | Free tier (500MB DB, 50k MAU) |
| LangSmith tracing | Free tier (5k traces/mo) |
| LLM API calls (OpenAI / Anthropic) | Pay-as-you-go |

---

## Step 1: Supabase Project Setup

**Goal**: Create the Supabase project and migrate the schema from SQLite to Postgres.

- Create a Supabase project (choose region closest to VPS)
- Recreate `food_items` and `daily_logs` tables via Supabase migration (not Alembic — Supabase manages its own migrations)
- Seed `food_items` with the nutrition CSV data (ETL script adapted for Postgres)
- Verify tables and data via Supabase dashboard

### Key Decision
- **Keep SQLAlchemy + asyncpg** as the ORM layer (don't switch to Supabase Python client)
- Supabase is used as a managed Postgres host, not as a REST API backend
- Connection via standard Postgres connection string (session pooler, port 5432)

---

## Step 2: Add User Identity (user_id columns)

**Goal**: Make the schema multi-user ready.

- Add `user_id` (UUID, NOT NULL) column to `daily_logs`
- Add `user_id` (UUID, nullable) column to `food_items` — only populated for `source="estimated"` items; NULL for shared `source="database"` items
- Update all SQLAlchemy queries in tools/services to filter by `user_id`
- Pass `user_id` through the graph via `config["configurable"]` (not AgentState — keeps state clean)

### Key Decision
- Estimated food items are **per-user** (each user builds their own estimated library)
- Shared DB food items (`source="database"`) have `user_id = NULL` and are visible to all

---

## Step 3: Swap Database Engine

**Goal**: Switch FitPal from local SQLite to Supabase Postgres.

- Replace `aiosqlite` with `asyncpg` (`uv add asyncpg`)
- Update `src/config.py`: `DATABASE_URL` reads from env var pointing to Supabase Postgres
- Update `src/database.py`: remove SQLite-specific settings (`check_same_thread`, etc.)
- Update Alembic config: remove `render_as_batch=True` and the nullable-ops filter (SQLite workarounds)
- Decide on Alembic role going forward: Alembic for local dev migrations, Supabase migrations for production — or one unified path
- Run existing tests against Postgres (or keep test DB on in-memory SQLite for speed)

---

## Step 4: Auth Integration (Supabase Auth)

**Goal**: Authenticate users and flow `user_id` into the graph.

- Set up Supabase Auth (email/password to start; OAuth later)
- Create `src/auth.py` — LangGraph custom auth handler:
  - Validates Supabase JWT from `Authorization: Bearer <token>` header
  - Extracts `user_id` from JWT `sub` claim
  - Returns `{"identity": user_id}` for LangGraph to inject into `config`
- Register auth handler in `langgraph.json` under `"auth"` key
- Nodes access user identity via `config["configurable"]["langgraph_auth_user"]["identity"]`

### Key Decision
- Supabase Auth is the **identity provider** (issues JWTs)
- LangGraph auth handler is the **validator** (checks JWTs server-side)
- Service role key used only for admin/ETL operations, never in the graph

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

## Step 6: Deploy LangGraph Standalone Server

**Goal**: Run FitPal as a production API server.

- Set up Docker Compose with:
  - LangGraph server container (runs the graph)
  - Redis container (task queue)
  - Postgres for checkpoints (can reuse Supabase or separate instance)
- Environment variables:
  - `DATABASE_URL` → Supabase Postgres (app data)
  - `REDIS_URL` → Redis instance
  - Checkpoint Postgres connection (server auto-manages `AsyncPostgresSaver`)
  - `SUPABASE_JWT_SECRET` → for auth handler JWT validation
  - LLM API keys (OpenAI/Anthropic)
- Deploy to VPS (Fly.io, Railway, DigitalOcean, or similar)
- Verify: API endpoints respond, auth works, HITL interrupt/resume works over HTTP

### What stays the same (no code changes needed)
- `define_graph(**kwargs)` — server injects its own checkpointer
- `langgraph.json` — already the deployment manifest
- HITL `interrupt()` + `Command` pattern — works identically over the API
- All node implementations and tool-first architecture

---

## Step 7: Smoke Test & Validation

**Goal**: Verify end-to-end flow in production.

- Create a test user via Supabase Auth
- Authenticate and get JWT
- Use `langgraph-sdk` client to:
  - Create a thread
  - Log food ("I had 200g of chicken and a banana")
  - Verify HITL interrupt → confirm → commit flow
  - Query daily stats
  - Verify data is scoped to the test user
- Check LangSmith traces are flowing
- Run security check: verify user A cannot see user B's data

---

## Migration Order Summary

```
Step 1: Supabase project + schema ──┐
Step 2: Add user_id columns ────────┤ (can be done together)
Step 3: Swap DB engine ─────────────┘
Step 4: Auth integration
Step 5: RLS policies
Step 6: Deploy standalone server
Step 7: Smoke test
```

Steps 1–3 can be developed and tested locally before touching deployment.
Steps 4–5 require a running Supabase project but can be tested locally.
Step 6 is the actual deployment — everything before it is preparation.
