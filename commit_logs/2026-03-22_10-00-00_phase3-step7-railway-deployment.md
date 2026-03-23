# feat: Railway Deployment — Docker Images, Project Setup, and Service Configuration (Phase 3 Step 7)

**Date**: 2026-03-22
**Branch**: main
**Status**: In Progress — services deployed, smoke testing pending

## Overview

Deployed FitPal to Railway as a production service with 4 services: LangGraph Agent Server, Postgres (checkpoints), Redis (task queue), and Telegram Bot Gateway. Also fixed a Studio bug (`user_id` collision) and created deployment documentation.

## Pre-Deployment Fixes

### Bug Fix: Studio user_id Collision
- **Problem**: LangGraph Studio injects a non-UUID `user_id` into `configurable` for its Store namespacing. Our `get_user_id()` picked it up, and `search_food` crashed with `ValueError: badly formed hexadecimal UUID string`.
- **Root cause**: Studio's `user_id` collides with our field name. The value isn't a UUID, but `get_user_id()` returned it without validation.
- **Fix**: Added UUID validation in `get_user_id()` (`src/config.py`) — if value isn't a valid UUID, falls back to `DEFAULT_DEV_USER_ID` with a warning log.
- **Tests**: Updated existing test to use valid UUID, added 2 new tests (non-UUID string, empty string fallback).
- **RCA**: `docs/rca/studio-user-id-collision.md`
- **Trace**: `traces/7a872aee-thread-trace.txt`

### Documentation
- Created `docs/orphaned-langgraph-server.md` — guide for finding and killing zombie `langgraph dev` processes on Windows.
- Added "Fuzzy Input Disambiguation" to PRD Phase 4 — present multiple candidate interpretations when input parser encounters ambiguous/misspelled food names.

## Phase 1: Docker Image Building (Tasks 1-4)

### Task 1: Updated `langgraph.production.json`
- Removed `"env": ".env"` — prevents baking dev secrets into the Docker image. Production env vars injected at runtime by Railway.

### Task 2: Created `bot/Dockerfile`
- Minimal Dockerfile: `python:3.13-slim` base, installs `uv`, copies `pyproject.toml` + `uv.lock`, syncs deps, copies `bot/` + `src/` code.
- CMD: `uv run python -m bot.gateway`

### Task 3: Built Docker Images
- `fitpal-server` (1.15GB) — built via `langgraph build -t fitpal-server -c langgraph.production.json --platform linux/amd64`
- `fitpal-bot` (657MB) — built via `docker build -t fitpal-bot -f bot/Dockerfile --platform linux/amd64 .`

**Issues encountered and resolved:**
- **Python version mismatch**: LangGraph base image defaulted to Python 3.11, project requires `>=3.13`. Fixed by adding `"python_version": "3.13"` to both `langgraph.json` and `langgraph.production.json`.
- **450MB Docker context**: No `.dockerignore` existed — Docker was sending `.venv/`, `.git/`, etc. Fixed by creating `.dockerignore` excluding `.venv`, `.git`, `tests`, `docs`, `data`, etc.
- **Unicode encoding error on Windows**: `langgraph build` emoji warning crashed on Windows cp1255 encoding. Fixed with `PYTHONIOENCODING=utf-8`.

### Task 4: Pushed to Docker Hub
- Tagged and pushed both images to `dolevsan/fitpal-server:latest` and `dolevsan/fitpal-bot:latest`.
- Docker Hub account: `dolevsan`

## Phase 2: Railway Project Setup (Tasks 5-9)

### Task 5: Created Railway Project
- Project: `fitpal-production`
- URL: `https://railway.com/project/b634c145-ac79-48e5-b197-4ac2793c9d3b`
- CLI: `railway init --name fitpal-production`

### Task 6: Added Postgres Service
- For **LangGraph checkpoints** (threads, runs, state) — NOT the Supabase app database.
- Internal URL: `postgresql://postgres:***@postgres.railway.internal:5432/railway`

### Task 7: Added Redis Service
- For task queue and streaming.
- Internal URL: `redis://default:***@redis.railway.internal:6379`

### Task 8: Added LangGraph Server Service
- Image: `dolevsan/fitpal-server:latest`
- Service name: `langgraph-server`
- Internal only (no public domain)

### Task 9: Added Bot Gateway Service
- Image: `dolevsan/fitpal-bot:latest`
- Service name: `fitpal-bot`
- Public domain: `https://fitpal-bot-production.up.railway.app`

## Phase 3: Environment Variables (Tasks 10-11)

### Task 10: LangGraph Server Variables
| Variable | Purpose |
|---|---|
| `REDIS_URI` | Railway Redis (with auth credentials) |
| `DATABASE_URI` | Railway Postgres (checkpoints) |
| `LANGSMITH_API_KEY` | LangSmith tracing |
| `LANGCHAIN_TRACING_V2` | Enable tracing |
| `LANGCHAIN_ENDPOINT` | LangSmith endpoint |
| `LANGCHAIN_PROJECT` | `fit-pal-agent` |
| `SUPABASE_DB_URL` | Supabase Postgres (app data) |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key |
| `SUPABASE_ANON_KEY` | Supabase anon key |
| `OPENAI_API_KEY` | OpenAI API key |
| `LLM_PROVIDER` | `openai` |
| `LLM_MODEL_NAME` | `gpt-4o` |
| `PORT` | `8000` |

### Task 11: Bot Gateway Variables
| Variable | Purpose |
|---|---|
| `BOT_TOKEN` | Telegram bot token |
| `BOT_PASSPHRASE` | Invite code (`fitpal-2026`) |
| `BOT_PASSWORD_SEED` | HMAC seed for synthetic passwords |
| `BOT_PORT` | `8080` |
| `PORT` | `8080` |
| `WEBHOOK_BASE_URL` | `https://fitpal-bot-production.up.railway.app` |
| `WEBHOOK_PATH` | `/webhook` |
| `WEBHOOK_SECRET` | Random hex string for Telegram verification |
| `LANGGRAPH_API_URL` | `http://langgraph-server.railway.internal:8000` |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key |

## Phase 4: Deploy and Verify (Tasks 12-13)

### Issues Encountered and Resolved
1. **Bot image not found on Docker Hub**: The initial `docker push` for the bot was interrupted. Re-pushed successfully.
2. **Redis authentication error**: Railway Redis requires a password. Initial `REDIS_URI` was `redis://redis.railway.internal:6379` (no auth). Fixed to include `default:PASSWORD@` credentials.
3. **WEBHOOK_PATH mangled by Git Bash**: Windows Git Bash expanded `/webhook` to `C:/Program Files/Git/webhook`. Fixed with `MSYS_NO_PATHCONV=1` prefix.

### Deployment Status
- **Postgres**: Active
- **Redis**: Active
- **langgraph-server**: Running — connected to Postgres + Redis, custom auth loaded
- **fitpal-bot**: Running — Telegram webhook verified at `https://fitpal-bot-production.up.railway.app/webhook`

## Remaining (Not Yet Done)
- **Tasks 14-17**: Smoke tests via Telegram (passphrase, food logging, HITL, stats)
- **Task 18**: Update `.env.production` with final webhook values
- **Task 19**: Update `docs/phase3-deployment-plan.md` to mark Steps 7-8 complete

## Files Created
- `bot/Dockerfile` — Bot gateway container definition
- `.dockerignore` — Excludes `.venv`, `.git`, tests, docs from Docker context
- `docs/orphaned-langgraph-server.md` — Guide for zombie process cleanup
- `docs/rca/studio-user-id-collision.md` — RCA for Studio user_id bug
- `traces/7a872aee-thread-trace.txt` — Failed thread trace

## Files Modified
- `langgraph.production.json` — Removed `"env"` key, added `"python_version": "3.13"`
- `langgraph.json` — Added `"python_version": "3.13"`
- `src/config.py` — UUID validation in `get_user_id()`
- `tests/unit/test_auth_handler.py` — Fixed test + 2 new tests
- `PRD.md` — Added Fuzzy Input Disambiguation to Phase 4

## Architecture (Production)
```
Telegram User
    │ (HTTPS webhook)
    ▼
┌──────────────────────────────────────────┐
│  Railway Project: fitpal-production      │
│                                          │
│  ┌──────────────┐    ┌───────────────┐   │
│  │ fitpal-bot   │───▶│ langgraph-    │   │
│  │ (public URL) │    │ server        │   │
│  │ port 8080    │    │ port 8000     │   │
│  └──────────────┘    └───────┬───────┘   │
│                              │           │
│                    ┌─────────┼─────┐     │
│                    │         │     │     │
│               ┌────▼──┐ ┌───▼───┐ │     │
│               │ Redis │ │Postgres│ │     │
│               │(queue)│ │(chkpt) │ │     │
│               └───────┘ └───────┘  │     │
│                                    │     │
└────────────────────────────────────┘     │
                                           │
                         ┌─────────────┐   │
                         │ Supabase    │◀──┘
                         │ (app data,  │
                         │  auth)      │
                         └─────────────┘
```
