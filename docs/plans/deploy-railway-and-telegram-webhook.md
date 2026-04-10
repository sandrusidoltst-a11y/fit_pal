# Feature: Deploy FitPal to Railway + Telegram Webhook (Phase 3 Steps 7-8)

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Deploy FitPal as a production service on Railway with 4 services (LangGraph Agent Server, Postgres, Redis, Telegram Bot Gateway). Configure Telegram webhook so users can interact with FitPal via Telegram. Smoke test the full end-to-end flow.

## User Story

As a FitPal user
I want to text the Telegram bot with what I ate
So that FitPal logs my food, calculates macros, and tracks my daily nutrition

## Problem Statement

FitPal works locally via `langgraph dev` but has no production deployment. Users cannot access it outside of the development machine.

## Solution Statement

Deploy all services to Railway (managed container platform). Railway provides internal networking between services, public HTTPS domains, and managed Postgres/Redis. The LangGraph server image is built locally via `langgraph build`, pushed to Docker Hub, and deployed on Railway. The Telegram bot gateway gets its own Dockerfile and is deployed separately. Telegram webhook points to the bot's public Railway URL.

## Feature Metadata

**Feature Type**: New Capability (Production Deployment)
**Estimated Complexity**: High
**Primary Systems Affected**: Infrastructure (new), `langgraph.production.json`, `bot/gateway.py`, `.env.production`
**Dependencies**: Railway account (authenticated), Docker Hub account, Docker Desktop, Telegram Bot (BotFather), LangGraph CLI

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `langgraph.production.json` — LangGraph server config (graphs, auth, env)
- `langgraph.json` — Dev server config (no auth, for comparison)
- `bot/gateway.py` — Telegram bot webhook server (aiogram v3, aiohttp, HITL relay)
- `bot/supabase_admin.py` — Supabase admin helpers (user creation, JWT generation)
- `src/security/auth.py` — LangGraph auth handler (Supabase JWT validation)
- `src/config.py` — ENV loading, DATABASE_URL resolution, LLM config, `get_user_id()`
- `src/database.py` — Async DB engine creation, SSL workaround for asyncpg
- `.env.production` — Production environment variables (partially filled)
- `pyproject.toml` — Project dependencies (needed for Docker image build)

### New Files to Create

- `bot/Dockerfile` — Dockerfile for the Telegram bot gateway container
- `docker-compose.railway.yml` — Reference Docker Compose for local testing (optional)

### Files to Modify

- `langgraph.production.json` — Remove `"env": ".env"` to prevent baking dev secrets into Docker image
- `.env.production` — Fill remaining webhook values after Railway deploy

### Relevant Documentation

- [LangGraph Standalone Server Deployment](https://docs.langchain.com/langsmith/deploy-standalone-server)
  - Docker Compose example, required env vars (REDIS_URI, DATABASE_URI, LANGSMITH_API_KEY)
  - Why: Defines the exact server configuration and health check endpoint
- [LangGraph CLI — `langgraph build`](https://docs.langchain.com/langsmith/cli)
  - Build command: `langgraph build -t <tag> -c <config>`
  - Why: Produces the Docker image for the Agent Server
- [Railway Private Networking](https://docs.railway.com/reference/private-networking)
  - Internal DNS: `SERVICE_NAME.railway.internal`
  - Why: LangGraph server and bot communicate internally
- [Railway Public Networking](https://docs.railway.com/reference/public-networking)
  - Auto HTTPS on `*.railway.app` domains
  - Why: Telegram requires HTTPS for webhook callbacks
- [Railway Services](https://docs.railway.com/guides/services)
  - Deploy from Docker images, GitHub repos, or CLI
  - Why: Deployment method for each service
- [LangGraph Custom Dockerfile](https://docs.langchain.com/langsmith/custom-docker)
  - `dockerfile_lines` in langgraph.json for custom image modifications
  - Why: May need system packages for asyncpg SSL

### Patterns to Follow

**LangGraph Docker Compose (from official docs):**
```yaml
services:
    langgraph-redis:
        image: redis:6
        healthcheck:
            test: redis-cli ping
    langgraph-postgres:
        image: postgres:16
        environment:
            POSTGRES_DB: postgres
            POSTGRES_USER: postgres
            POSTGRES_PASSWORD: postgres
        volumes:
            - langgraph-data:/var/lib/postgresql/data
    langgraph-api:
        image: ${IMAGE_NAME}
        ports:
            - "8123:8000"
        env_file:
            - .env
        environment:
            REDIS_URI: redis://langgraph-redis:6379
            DATABASE_URI: postgres://postgres:postgres@langgraph-postgres:5432/postgres
```

**Railway Internal DNS Pattern:**
```
http://SERVICE_NAME.railway.internal:PORT
```
Services discover each other via encrypted Wireguard tunnels. Zero configuration needed.

**Bot Gateway Networking:**
- Bot → LangGraph Server: internal (`http://langgraph-server.railway.internal:8000`)
- Telegram → Bot: public (`https://fitpal-bot-xxx.up.railway.app/webhook`)

---

## IMPLEMENTATION PLAN

### Phase 1: Prerequisites & Image Building

Prepare Docker images for deployment. The LangGraph server image is built via `langgraph build` (special CLI tool). The bot gateway needs a standard Dockerfile.

### Phase 2: Railway Project Setup

Create Railway project and provision all 4 services: Postgres (template), Redis (template), LangGraph server (Docker image), Bot gateway (Docker image or CLI deploy).

### Phase 3: Environment Variables & Networking

Configure each service's env vars on Railway. Set up internal DNS references between services. Generate public domain for the bot.

### Phase 4: Deploy & Webhook Setup

Deploy all services, verify health, configure Telegram webhook to point at the bot's public URL.

### Phase 5: Smoke Test (Phase 3 Step 8)

End-to-end validation: Telegram → Bot → LangGraph → Supabase → response.

---

## STEP-BY-STEP TASKS

### Task 1: UPDATE `langgraph.production.json` — Remove env file reference

The `"env": ".env"` field tells `langgraph build` to bake the `.env` file contents into the Docker image. This would expose development secrets. For production, env vars should be injected at runtime by Railway.

- **IMPLEMENT**: Remove the `"env": ".env"` line from `langgraph.production.json`
- **RESULT**:
  ```json
  {
    "dependencies": ["."],
    "graphs": {
      "fitpal": "./src/agents/nutritionist.py:define_graph"
    },
    "auth": {
      "path": "src/security/auth.py:auth"
    }
  }
  ```
- **GOTCHA**: `src/config.py` calls `load_dotenv()` which silently does nothing if no `.env` file exists in the container. All env vars will come from Railway's runtime injection instead. This is correct behavior.
- **VALIDATE**: `cat langgraph.production.json` — confirm no `env` key

### Task 2: CREATE `bot/Dockerfile` — Bot gateway container

The bot gateway is a separate Python process (aiohttp webhook server). It needs its own Docker image.

- **IMPLEMENT**: Create a minimal Dockerfile:
  ```dockerfile
  FROM python:3.13-slim

  WORKDIR /app

  # Install uv for dependency management
  RUN pip install uv

  # Copy dependency files first (cache layer)
  COPY pyproject.toml uv.lock ./

  # Install production dependencies only
  RUN uv sync --frozen --no-dev --no-install-project

  # Copy bot and src code (bot imports from bot.supabase_admin)
  COPY bot/ bot/
  COPY src/ src/

  # Run the bot gateway
  CMD ["uv", "run", "python", "-m", "bot.gateway"]
  ```
- **GOTCHA**: The bot imports `from bot.supabase_admin import ...` so both `bot/` and `src/` dirs must be copied (bot.supabase_admin uses no src imports, but the shared pyproject.toml installs all deps including supabase, httpx, aiogram).
- **GOTCHA**: `bot/gateway.py` has `if __name__ == "__main__": main()` but also needs to work as `python -m bot.gateway`. Verify the entry point works.
- **VALIDATE**: `docker build -t fitpal-bot -f bot/Dockerfile .` — should build successfully

### Task 3: Build LangGraph Server Docker Image

Use the LangGraph CLI to build the production Docker image.

- **IMPLEMENT**: Run from project root:
  ```bash
  langgraph build -t fitpal-server -c langgraph.production.json --platform linux/amd64
  ```
- **GOTCHA**: `--platform linux/amd64` is important because Railway runs on Linux AMD64. If building on an ARM Mac (M1/M2), the default platform would be `linux/arm64` which won't work on Railway.
- **GOTCHA**: The build installs all dependencies from `pyproject.toml`. Ensure `uv.lock` and `pyproject.toml` are up to date (`uv sync` before building).
- **VALIDATE**: `docker images | grep fitpal-server` — image should appear
- **VALIDATE**: Quick local test:
  ```bash
  docker run --rm -e REDIS_URI=redis://localhost:6379 -e DATABASE_URI=postgres://localhost:5432/test fitpal-server || echo "Expected to fail without Redis/Postgres — just checking image starts"
  ```

### Task 4: Push Docker Images to Docker Hub

Railway needs to pull images from a registry. Docker Hub is the simplest option.

- **PREREQUISITE**: Create a Docker Hub account at https://hub.docker.com if you don't have one
- **IMPLEMENT**:
  ```bash
  # Login to Docker Hub
  docker login

  # Tag and push LangGraph server image
  docker tag fitpal-server YOUR_DOCKERHUB_USERNAME/fitpal-server:latest
  docker push YOUR_DOCKERHUB_USERNAME/fitpal-server:latest

  # Build and push bot image
  docker build -t fitpal-bot -f bot/Dockerfile .
  docker tag fitpal-bot YOUR_DOCKERHUB_USERNAME/fitpal-bot:latest
  docker push YOUR_DOCKERHUB_USERNAME/fitpal-bot:latest
  ```
- **GOTCHA**: Replace `YOUR_DOCKERHUB_USERNAME` with your actual Docker Hub username
- **VALIDATE**: Visit `https://hub.docker.com/r/YOUR_DOCKERHUB_USERNAME/fitpal-server` — image should be listed

### Task 5: Create Railway Project

Set up the Railway project that will host all 4 services.

- **IMPLEMENT**:
  ```bash
  # Create a new Railway project
  railway init

  # Or create via the Railway dashboard at https://railway.com/new
  ```
- **GOTCHA**: Use a descriptive project name like `fitpal-production`
- **VALIDATE**: `railway status` — should show the linked project

### Task 6: Add Postgres Service (Railway Template)

This Postgres instance is for **LangGraph checkpoints** (threads, runs, state). NOT the Supabase app database.

- **IMPLEMENT**: Via Railway dashboard:
  1. Open project → Click "New" → "Database" → "PostgreSQL"
  2. Railway auto-provisions a Postgres 16 instance with credentials
  3. Note the internal connection URL: `${{Postgres.DATABASE_URL}}`
  4. Or via CLI: `railway add --database postgres`
- **GOTCHA**: This is a SEPARATE database from Supabase. Supabase stores app data (food_items, daily_logs). This Postgres stores LangGraph internals (checkpoints, threads, runs).
- **GOTCHA**: Railway Postgres uses the variable name `DATABASE_URL` by default. The LangGraph server expects `DATABASE_URI`. We'll map this in the env var configuration step.
- **VALIDATE**: In Railway dashboard, Postgres service should show "Active" with connection details

### Task 7: Add Redis Service (Railway Template)

Redis is required by the LangGraph server for task queue and streaming.

- **IMPLEMENT**: Via Railway dashboard:
  1. Open project → Click "New" → "Database" → "Redis"
  2. Railway auto-provisions a Redis instance
  3. Note the internal connection URL: `${{Redis.REDIS_URL}}`
  4. Or via CLI: `railway add --database redis`
- **VALIDATE**: In Railway dashboard, Redis service should show "Active"

### Task 8: Add LangGraph Server Service

Deploy the LangGraph Agent Server from the Docker Hub image.

- **IMPLEMENT**: Via Railway dashboard:
  1. Click "New" → "Docker Image"
  2. Enter image: `YOUR_DOCKERHUB_USERNAME/fitpal-server:latest`
  3. Service name: `langgraph-server`
- **GOTCHA**: Do NOT generate a public domain yet. The LangGraph server should be internal-only (only the bot talks to it). If you want direct API access for debugging, you can add a public domain later.
- **VALIDATE**: Service should appear in the project canvas

### Task 9: Add Bot Gateway Service

Deploy the Telegram bot from the Docker Hub image.

- **IMPLEMENT**: Via Railway dashboard:
  1. Click "New" → "Docker Image"
  2. Enter image: `YOUR_DOCKERHUB_USERNAME/fitpal-bot:latest`
  3. Service name: `fitpal-bot`
- **IMPLEMENT**: Generate a public domain:
  1. Go to fitpal-bot service → Settings → Networking → Public Networking
  2. Click "Generate Domain" → get URL like `fitpal-bot-xxx.up.railway.app`
  3. Save this URL — needed for `WEBHOOK_BASE_URL`
- **VALIDATE**: Service should appear with a public domain assigned

### Task 10: Configure Environment Variables — LangGraph Server

Set all required env vars for the LangGraph Agent Server service.

- **IMPLEMENT**: In Railway dashboard, select `langgraph-server` service → Variables tab. Add:

  | Variable | Value | Notes |
  |---|---|---|
  | `REDIS_URI` | `${{Redis.REDIS_URL}}` | Railway variable reference to Redis service |
  | `DATABASE_URI` | `${{Postgres.DATABASE_URL}}` | Railway variable reference to checkpoint Postgres |
  | `LANGSMITH_API_KEY` | `lsv2_pt_...` | From .env.production |
  | `LANGCHAIN_TRACING_V2` | `true` | Enable LangSmith tracing |
  | `LANGCHAIN_ENDPOINT` | `https://api.smith.langchain.com` | LangSmith endpoint |
  | `LANGCHAIN_PROJECT` | `fit-pal-agent` | LangSmith project name |
  | `SUPABASE_DB_URL` | `postgresql://postgres.zpx...` | Supabase app database connection string |
  | `SUPABASE_URL` | `https://zpx...supabase.co` | Supabase project URL (for auth handler) |
  | `SUPABASE_SERVICE_KEY` | `eyJ...` | Supabase service role key (for auth handler) |
  | `SUPABASE_ANON_KEY` | `eyJ...` | Supabase anon key |
  | `OPENAI_API_KEY` | `sk-proj-...` | OpenAI API key for LLM calls |
  | `LLM_PROVIDER` | `openai` | LLM provider |
  | `LLM_MODEL_NAME` | `gpt-4o` | LLM model |
  | `PORT` | `8000` | Railway needs to know which port the server listens on |

- **GOTCHA**: Railway uses `${{ServiceName.VARIABLE}}` syntax to reference variables from other services. Use this for `REDIS_URI` and `DATABASE_URI` so they automatically update if credentials change.
- **GOTCHA**: The LangGraph server listens on port **8000** internally. Railway needs to know this (set `PORT=8000` or configure in service settings).
- **GOTCHA**: `DATABASE_URI` (checkpoints) and `SUPABASE_DB_URL` (app data) are DIFFERENT databases. Don't confuse them.
- **VALIDATE**: All variables should show in the Variables tab

### Task 11: Configure Environment Variables — Bot Gateway

Set all required env vars for the Telegram bot service.

- **IMPLEMENT**: In Railway dashboard, select `fitpal-bot` service → Variables tab. Add:

  | Variable | Value | Notes |
  |---|---|---|
  | `BOT_TOKEN` | `8057...` | From BotFather |
  | `BOT_PASSPHRASE` | `fitpal-2026` | Invite code for new users |
  | `BOT_PASSWORD_SEED` | `96ab35b...` | HMAC seed for synthetic passwords |
  | `BOT_PORT` | `8080` | Port the bot listens on |
  | `WEBHOOK_BASE_URL` | `https://fitpal-bot-xxx.up.railway.app` | Public URL from Task 9 |
  | `WEBHOOK_PATH` | `/webhook` | Webhook endpoint path |
  | `WEBHOOK_SECRET` | `<generate: openssl rand -hex 16>` | Telegram webhook verification |
  | `LANGGRAPH_API_URL` | `http://langgraph-server.railway.internal:8000` | Internal DNS to LangGraph server |
  | `SUPABASE_URL` | `https://zpx...supabase.co` | For user creation |
  | `SUPABASE_SERVICE_KEY` | `eyJ...` | For admin API (create_user) |
  | `PORT` | `8080` | Railway needs to know which port |

- **GOTCHA**: `LANGGRAPH_API_URL` uses Railway's internal DNS: `http://langgraph-server.railway.internal:8000`. The service name must match exactly what you named the service in Task 8.
- **GOTCHA**: `WEBHOOK_BASE_URL` must include `https://` and NOT include a trailing slash or the webhook path.
- **GOTCHA**: Generate `WEBHOOK_SECRET` with `openssl rand -hex 16` — this is a random string Telegram sends back in webhook requests for verification.
- **VALIDATE**: All variables should show in the Variables tab

### Task 12: Deploy All Services

Trigger deployment of all services.

- **IMPLEMENT**: Railway auto-deploys when you save env vars and link images. If services aren't running:
  1. Check each service's "Deployments" tab
  2. Click "Deploy" or "Redeploy" if needed
- **IMPLEMENT**: Wait for all 4 services to show "Active":
  1. Postgres → Active
  2. Redis → Active
  3. langgraph-server → Active (may take 1-2 min to start)
  4. fitpal-bot → Active
- **VALIDATE**: Check LangGraph server health:
  ```bash
  # If you added a public domain to langgraph-server:
  curl https://langgraph-server-xxx.up.railway.app/ok
  # Expected: {"ok": true}
  ```
- **VALIDATE**: Check Railway logs for each service — no crash loops or errors

### Task 13: Verify Telegram Webhook

The bot's `on_startup` handler automatically sets the webhook URL when it starts. Verify it's configured correctly.

- **IMPLEMENT**: Check webhook status via Telegram Bot API:
  ```bash
  curl https://api.telegram.org/bot8057226198:AAEz39wYuC_VHQYmGDq3qjAFitILIWpoAvc/getWebhookInfo
  ```
- **EXPECTED RESPONSE**: JSON with `url` matching your bot's public URL + webhook path, and `last_error_date` should be empty or old.
- **GOTCHA**: If the webhook URL is wrong or not set, the bot's `on_startup` function failed. Check Railway logs for the fitpal-bot service.
- **VALIDATE**: `"url": "https://fitpal-bot-xxx.up.railway.app/webhook"` in the response

### Task 14: Smoke Test — Passphrase & Registration

Test the first-time user flow.

- **IMPLEMENT**:
  1. Open Telegram, search for your bot by username (e.g., @fitpal_nutrition_bot)
  2. Send any message → should get "Send the invite code to get started."
  3. Send the passphrase: `fitpal-2026`
  4. Should get: "Welcome to FitPal! You can start logging food now."
- **VALIDATE**: Check Supabase Auth dashboard — a new user should appear with email `<chat_id>@telegram.fitpal.bot`
- **VALIDATE**: Check Railway logs for fitpal-bot — should show "User registered" or "Signed in existing user"

### Task 15: Smoke Test — Food Logging + HITL

Test the core food logging flow with HITL confirmation.

- **IMPLEMENT**:
  1. Send: "I had 200g of chicken and a banana"
  2. Bot should respond with a confirmation preview (macros for chicken + banana)
  3. Send: "yes" (confirm)
  4. Bot should respond with a confirmation message
- **VALIDATE**: Check Supabase `daily_logs` table — new entries should exist for this user
- **VALIDATE**: Check LangSmith traces at https://smith.langchain.com — traces should appear for the `fit-pal-agent` project

### Task 16: Smoke Test — Stats Query

Test the daily stats query flow.

- **IMPLEMENT**:
  1. Send: "What did I eat today?"
  2. Bot should respond with today's log entries and totals
- **VALIDATE**: Response should include the chicken and banana logged in Task 15

### Task 17: Smoke Test — Session Timeout

Test that session timeout creates a new thread.

- **IMPLEMENT**: This is hard to test naturally (30 min timeout). For now, verify:
  1. Sending multiple messages in quick succession reuses the same thread
  2. Check Railway logs — "Created new thread" should appear once per session, not per message
- **VALIDATE**: Railway bot logs show thread reuse

### Task 18: UPDATE `.env.production` — Fill Webhook Values

Now that Railway has assigned a public URL, fill in the remaining values.

- **IMPLEMENT**: Update `.env.production`:
  ```
  WEBHOOK_BASE_URL=https://fitpal-bot-xxx.up.railway.app
  WEBHOOK_SECRET=<the value you generated in Task 11>
  ```
- **GOTCHA**: This file is for local reference only. The actual production values are in Railway's env var config.
- **VALIDATE**: All placeholder values in `.env.production` should be filled

### Task 19: UPDATE `docs/phase3-deployment-plan.md` — Mark Steps 7-8 Complete

Update the deployment plan to reflect completion.

- **IMPLEMENT**: Update Steps 7 and 8 status markers, and the Migration Order Summary at the bottom. Add Railway-specific details (service names, architecture).
- **VALIDATE**: Read the file — all 8 steps should show ✅

---

## TESTING STRATEGY

### Health Checks

- LangGraph server: `GET /ok` → `{"ok": true}`
- Bot gateway: Check Railway logs for successful startup + webhook set
- Postgres: Railway dashboard shows "Active"
- Redis: Railway dashboard shows "Active"

### End-to-End Tests

- Telegram passphrase flow (new user registration)
- Food logging with HITL confirmation
- Stats query
- Session timeout / thread reuse
- Error handling (invalid messages, network issues)

### Data Isolation Test

- Register two different Telegram accounts
- Log food from each
- Query stats from each — should only see own data
- Check Supabase `daily_logs` — `user_id` column should differ

### Edge Cases

- Send non-text message (photo, sticker) → should get "I can only process text messages"
- Send wrong passphrase → should get "Send the invite code to get started"
- Send very long message → should not crash
- Rapid-fire messages → should not create duplicate threads

---

## VALIDATION COMMANDS

### Level 1: Pre-Build Checks

```bash
# Ensure dependencies are synced
uv sync

# Unit tests still pass (no regressions from config changes)
uv run pytest tests/unit/ -v
```

### Level 2: Docker Build Verification

```bash
# Build LangGraph server image
langgraph build -t fitpal-server -c langgraph.production.json --platform linux/amd64

# Build bot image
docker build -t fitpal-bot -f bot/Dockerfile .

# Verify images exist
docker images | grep fitpal
```

### Level 3: Railway Deployment Verification

```bash
# Check Railway project status
railway status

# Check service logs (replace with actual service names)
railway logs --service langgraph-server
railway logs --service fitpal-bot
```

### Level 4: Production Health Checks

```bash
# LangGraph server health (if public domain enabled)
curl https://LANGGRAPH_PUBLIC_URL/ok

# Telegram webhook status
curl https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo
```

### Level 5: Manual Telegram Testing

1. Send wrong passphrase → rejected
2. Send correct passphrase → registered
3. Log food → HITL confirmation → confirm → logged
4. Query stats → shows logged food
5. Check LangSmith traces → traces visible

---

## ACCEPTANCE CRITERIA

- [ ] LangGraph server running on Railway, health check returns `{"ok": true}`
- [ ] Postgres (checkpoints) and Redis active on Railway
- [ ] Bot gateway running with public HTTPS domain
- [ ] Telegram webhook configured and verified via `getWebhookInfo`
- [ ] New user registration works via passphrase
- [ ] Food logging + HITL confirmation flow works end-to-end
- [ ] Stats query returns correct data
- [ ] LangSmith traces appear for production runs
- [ ] Data is scoped per user (user_id filtering works)
- [ ] No development secrets baked into Docker images
- [ ] `.env.production` fully filled (no remaining placeholders)
- [ ] `docs/phase3-deployment-plan.md` updated with completion status

---

## COMPLETION CHECKLIST

- [ ] `langgraph.production.json` updated (no env file reference)
- [ ] `bot/Dockerfile` created and builds successfully
- [ ] Docker images built and pushed to Docker Hub
- [ ] Railway project created with 4 services
- [ ] All environment variables configured on Railway
- [ ] All services deployed and running
- [ ] Telegram webhook verified
- [ ] Smoke tests passed (registration, food logging, stats, HITL)
- [ ] LangSmith traces flowing
- [ ] Documentation updated
- [ ] Unit tests still pass (no regressions)

---

## NOTES

### Architecture Diagram (Production)

```
Telegram User
    │
    ▼ (HTTPS webhook)
┌─────────────────────────────────────────────────────┐
│  Railway Project                                     │
│                                                      │
│  ┌──────────────┐    HTTP (internal)   ┌──────────┐ │
│  │ fitpal-bot   │ ──────────────────→  │ langgraph│ │
│  │ (public URL) │                      │ -server  │ │
│  │ port 8080    │                      │ port 8000│ │
│  └──────────────┘                      └────┬─────┘ │
│                                             │       │
│                              ┌──────────────┼───┐   │
│                              │              │   │   │
│                         ┌────▼───┐    ┌─────▼─┐ │   │
│                         │ Redis  │    │Postgres│ │   │
│                         │ (queue)│    │(checks)│ │   │
│                         └────────┘    └────────┘ │   │
│                                                  │   │
└──────────────────────────────────────────────────┘   │
                                                       │
                              ┌─────────────────────┐  │
                              │ Supabase Cloud      │◄─┘
                              │ (food_items,        │
                              │  daily_logs, auth)  │
                              └─────────────────────┘
```

### Key Distinction: Two Postgres Databases

| Database | Purpose | Location | Accessed By |
|---|---|---|---|
| Railway Postgres | LangGraph checkpoints, threads, runs | Railway container | LangGraph server (auto-managed) |
| Supabase Postgres | App data (food_items, daily_logs, users) | Supabase Cloud | LangGraph server (via SQLAlchemy) |

### Env Var Naming Gotcha

- `DATABASE_URI` → Railway Postgres (checkpoints) — used by LangGraph server internally
- `SUPABASE_DB_URL` → Supabase Postgres (app data) — used by `src/config.py` → SQLAlchemy
- These are DIFFERENT databases. Confusing them will cause data loss or startup failures.

### Cost Estimate

- Railway Hobby plan: ~$5/mo (4 services fit within limits)
- Supabase: Free tier (500MB DB, 50k MAU)
- LangSmith: Free tier (5k traces/mo)
- OpenAI API: Pay-as-you-go
- Docker Hub: Free tier (1 private repo, unlimited public)

### Future Improvements (Not in This Plan)

- GitHub Actions CI/CD pipeline (auto-build + deploy on push)
- Separate Supabase project for production vs development
- Railway auto-deploy from GitHub (requires custom Dockerfile for LangGraph server)
- Health check monitoring / alerting
- Backup strategy for checkpoint Postgres

### Risk: LANGGRAPH_CLOUD_LICENSE_KEY

The LangGraph docs list `LANGGRAPH_CLOUD_LICENSE_KEY` as a prerequisite. However, the official Docker Compose example does NOT include it, and the FAQ states LangGraph is "MIT-licensed open-source" with "Free self-hosted" deployment. If the server requires this key at startup:
1. Check if `LANGSMITH_API_KEY` doubles as the license key (docs suggest this)
2. Check the LangSmith dashboard for a license key section
3. Contact LangChain support if neither works

**Confidence Score: 7/10** — Main risks are the license key uncertainty and first-time Railway/Docker workflow for the user. All code and architecture are proven locally.
