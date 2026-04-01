# FitPal — Project Context

## Project Overview

FitPal is a LangGraph-based AI nutrition coach. Users log food in natural language ("I had 200g of chicken and a banana"); the agent parses intent, looks up macros from a Supabase PostgreSQL database, and maintains a stateful daily log.

**Mission**: Make nutrition tracking effortless — logging food should feel like texting a friend.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (StateGraph, async) |
| LLM Framework | LangChain 1.x |
| Schema Validation | Pydantic v2 |
| LLM Models | GPT-4.1-nano (default) / GPT-4o — configured via `src/config.py` `NODE_CONFIGS` |
| Storage | Supabase PostgreSQL + SQLAlchemy (`asyncpg` async engine; `psycopg2` sync engine for ETL scripts only) |
| Primary Keys | UUID (`sqlalchemy.Uuid`, `uuid.uuid4` default) |
| Auth (dev) | Supabase Auth (JWT) + LangGraph custom auth handler (`src/security/auth.py`) — enterprise-only, used in dev/Studio |
| Auth (prod) | Shared secret middleware (`src/security/internal_auth_middleware.py`) — validates `X-Internal-Token` header; bot passes `user_id` in config body |
| Deployment | Railway (4 services: langgraph-server, fitpal-bot, Postgres checkpoints, Redis queue) + Docker Hub (`dolevsan/fitpal-server`, `dolevsan/fitpal-bot`) |
| User Scoping | `user_id` column on all user-scoped tables (`food_items`, `daily_logs`, `user_profiles`, `personal_stats_log`); FK constraints to `auth.users(id)`; extracted via `get_user_id(config)` from `RunnableConfig` |
| RLS | Supabase Row Level Security on `food_items`, `daily_logs`, `personal_stats_log` (defense-in-depth; service role bypasses) |
| Telegram Gateway | aiogram v3 bot (`bot/gateway.py`) — webhook (production) or polling (local dev via `POLLING_MODE=true`); passphrase access control, auto-registration, onboarding, HITL over Telegram |
| Package Manager | `uv` — strictly enforced (see Package Management below) |
| Language | Python 3.13+ |
| Logging | `structlog` — structured logging across all `src/` and `bot/` modules |
| CI/CD | GitHub Actions — CI (lint + unit + integration) on push/PR; CD (Docker build + push + Railway redeploy) on merge to `main` |
| Dev Server | `langgraph dev` → LangSmith Studio |

---

## Project Structure

```text
fit_pal/
├── commit_logs/                   # History of commits
├── data/
│   ├── nutrition.db               # Local SQLite fallback (legacy, untracked)
│   └── nutrients_csvfile.csv      # Source data (Simple CSV) for ETL ingestion
├── src/
│   ├── agents/
│   │   ├── nutritionist.py        # LangGraph graph definition
│   │   ├── state.py               # InputState, AgentState, OutputState TypedDicts
│   │   └── nodes/
│   │       ├── input_node.py      # Input parser node
│   │       ├── food_search_node.py # Food search node
│   │       ├── selection_node.py  # Agent selection node
│   │       ├── calculate_macros_node.py # Macro calculation (DB or LLM estimation)
│   │       ├── confirmation_node.py # HITL batch confirmation via interrupt()
│   │       ├── commit_node.py     # Batch DB write after confirmation
│   │       ├── stats_node.py      # Stats lookup node
│   │       ├── personal_stats_node.py # Personal stats logging (weight, body fat)
│   │       └── response_node.py   # LLM response generator
│   ├── services/
│   │   ├── daily_log_service.py   # CRUD for daily logs + @tool wrappers (log_food_entry, query_food_logs)
│   │   ├── user_profile_service.py # User profile CRUD (onboarding data)
│   │   └── personal_stats_service.py # Personal stats CRUD + @tool wrappers (log_personal_stat, get_latest_personal_stats)
│   ├── scripts/
│   │   ├── ingest_simple_db.py    # ETL script (CSV -> Supabase Postgres)
│   │   └── print_trace.py         # LangSmith thread trace viewer (by thread_id)
│   ├── tools/
│   │   └── food_lookup.py         # Async @tool: search_food, calculate_food_macros, create_food_item + compute_food_macros helper
│   ├── schemas/
│   │   ├── input_schema.py        # FoodIntakeEvent schema
│   │   ├── selection_schema.py    # FoodSelectionResult schema
│   │   ├── estimation_schema.py   # MacroEstimation (LLM off-menu output)
│   │   ├── confirmation_schema.py # ConfirmationResponse + ItemEdit (HITL parsing)
│   │   └── personal_stats_schema.py # PersonalStatsExtraction (weight/body fat parsing)
│   ├── security/
│   │   ├── auth.py                # LangGraph custom auth handler (@auth.authenticate + @auth.on) — enterprise-only, kept for future use
│   │   ├── internal_auth_middleware.py # Shared secret middleware (X-Internal-Token) — used in production
│   │   └── webapp.py              # FastAPI app registering middleware — referenced by langgraph.production.json
│   ├── database.py                # Async DB engine (asyncpg) + sync engine for ETL
│   ├── models.py                  # SQLAlchemy models (FoodItem, DailyLog, UserProfile, PersonalStatsLog — UUID PKs, user_id scoped, FK to auth.users)
│   ├── main.py                    # Entry point
│   └── config.py                  # Environment & LLM setup via get_llm_for_node() + get_user_id() + get_user_profile()
├── bot/
│   ├── gateway.py                 # Telegram bot gateway (aiogram v3, webhook/polling, onboarding, HITL relay, SessionData TypedDict)
│   ├── supabase_admin.py          # Supabase admin helpers (async client, BOT_PASSWORD_SEED, BOT_EMAIL_DOMAIN, user creation)
│   └── Dockerfile                 # Bot gateway container definition
├── tests/
│   ├── unit/                      # Fast, deterministic tests (mocked DB/LLM)
│   ├── integration/               # Real Supabase DB tests (service layer, models, tool scoping)
│   ├── graph_api/                 # Graph compilation + E2E flow tests via langgraph-sdk
│   │   └── logs/                  # Server logs + error tracebacks (gitignored)
│   └── conftest.py                # Pytest shared fixtures
├── notebooks/
│   ├── evaluate_lookup.ipynb      # Analysis notebook
│   └── evals/
│       ├── eval_input_parser.ipynb # Input parser single-step eval (LangSmith)
│       └── reports/               # Eval debugger reports (gitignored)
├── docs/
│   ├── phase3-deployment-plan.md  # Phase 3 deployment steps (Supabase + self-hosted LangGraph)
│   ├── orphaned-langgraph-server.md # Guide for finding/killing zombie langgraph dev processes
│   ├── auth_flow.excalidraw       # Auth flow diagram (Excalidraw source)
│   ├── testing_graph.excalidraw   # Testing architecture diagram (Excalidraw source)
│   ├── fitpal-data-flow.excalidraw # Data flow diagram (Excalidraw source)
│   └── rca/                       # Root cause analysis documents
├── prompts/                       # System prompts and tool specs
├── traces/                        # LangSmith trace exports (JSON)
├── .github/
│   └── workflows/
│       ├── ci.yml                 # CI: lint + unit + integration tests on push/PR
│       └── cd.yml                 # CD: Docker build + push + Railway redeploy on merge to main
├── .dockerignore                  # Excludes .venv, .git, tests, docs from Docker context
├── langgraph.json                 # LangSmith Studio configuration (dev, no auth, python_version 3.13)
├── langgraph.production.json      # Production configuration (shared secret middleware via http.app, python_version 3.13)
├── PRD.md
└── README.md
```

---

## Architecture Patterns

- **Tool-First Architecture**: All DB access goes through async `@tool` functions. Nodes are thin orchestrators that call tools via `await tool.ainvoke(...)` — they never import `get_async_db_session` or query the DB directly. Tools own their own sessions. This ensures scalability (change the tool, not every node) and avoids `BlockingError` from mixing sync/async.
- **Service + Tool Layer**: `src/services/` contains both raw service functions (accept `session` param for DI/testability) and `@tool` wrappers that create their own session and delegate. `src/tools/` contains food-specific async tools.
- **Multiple Schemas**: `InputState` (messages only, public API) → `AgentState` (internal) → `OutputState`. Enables clean LangSmith Studio chat interface without exposing internal state fields.
- **Configuration Dictionary**: `get_llm_for_node()` in `config.py` centralises all LLM instantiation with per-node overrides (temperature, model). Never hardcode models inside nodes.
- **Write-Through**: DB is source of truth. Write immediately on confirmation, then query for state updates.
- **Fully Async**: All nodes, tools, and DB access use `async`/`await`. The async engine (`asyncpg`) is the primary DB path. A sync engine (`psycopg2`) exists only for ETL scripts.
- **User ID Scoping**: All queries filter by `user_id`. Nodes receive `config: RunnableConfig` and extract the user via `get_user_id(config)` from `src.config`. `user_id` flows through `config["configurable"]["user_id"]`, never through `AgentState`. `DEFAULT_DEV_USER_ID` provides a fallback for local development.
- **Multi-Item Loop**: Conditional routing processes food items sequentially with loop-back edges until the queue is empty.
- **Pydantic for LLM Output**: Always use `.with_structured_output()` then `.model_dump()`. Never parse raw LLM strings.
- **Reporting State**: `AgentState.daily_log_report` stores raw `QueriedLog` list — enables flexible LLM reasoning (averages, distributions) instead of pre-aggregated values.
- **HITL Batch Confirmation**: Before any DB write, all food items are accumulated into `pending_confirmations` as `MacroResult` previews. `confirmation_node` uses LangGraph's `interrupt()` in a validation loop to present the batch and await user confirmation/rejection/edit via natural language. `Command` return enables dynamic routing to `commit` or `response`.
- **Off-Menu Estimation + Persistence**: When food is not found in the DB (NO_MATCH), `calculate_macros_node` uses LLM with `MacroEstimation` structured output to estimate macros. Items are tagged with `source: "estimated"` for transparency. At commit time, `commit_node` creates a `FoodItem` row with `source="estimated"` and back-calculated per-100g values, then uses the returned `food_id` for the `DailyLog` entry. On subsequent searches, `search_food` queries DB foods first, then falls back to estimated foods — so previously estimated items are reused without re-estimation. `FoodItem.source` column (`"database"` | `"estimated"`, NOT NULL, default `"database"`) enables this two-tier search.
- **Schema Management**: Supabase migrations manage the production schema. Never use `Base.metadata.create_all()` or `drop_all()` in production code. ETL script (`ingest_simple_db.py`) clears data via `DELETE FROM`, not schema recreation. Tests use `Base.metadata.create_all()` against a separate Supabase test database.
- **FK Constraints to auth.users**: All user-scoped tables have FK constraints to `auth.users(id)`. `user_profiles`, `personal_stats_log`, `daily_logs` use `ON DELETE CASCADE`. `food_items` uses `ON DELETE SET NULL` (preserves shared food data). FK lives only in Postgres via migration — NOT in SQLAlchemy models (avoids `Base.metadata.create_all()` issues with `auth.users` not in our metadata).
- **Permanent Tagged Auth Users**: Two permanent auth users exist for dev/test workflows: `dev@dev.fitpal.bot` (LangGraph Studio, local dev) and `e2e@test.fitpal.bot` (E2E smoke tests). Identifiable via `user_metadata.source` (`"dev"` / `"e2e_test"`). `DEFAULT_DEV_USER_ID` in `src/config.py` points to the dev auth user.
- **Onboarding Flow**: Bot collects user profile (name, height, age, gender) on first registration via step-by-step conversation. Profile stored in `user_profiles` table, cached on session, injected into LangGraph config as `user_profile`.
- **Personal Stats Logging**: `personal_stats_node` handles `LOG_PERSONAL_STATS` action — extracts weight/body fat from user input via LLM structured output (`PersonalStatsExtraction`), writes to `personal_stats_log` table.
- **Local Dev Bot**: Set `POLLING_MODE=true` + `BOT_EMAIL_DOMAIN=dev.fitpal.bot` in `.env` to run the bot locally against `langgraph dev`. Uses aiogram polling (no public URL needed). Separate email domain creates distinct auth users from production.

---

## Package Management — uv (Mandatory)

Never use `pip`, `pip install`, or `python` directly. Always use `uv`.

| Action | Command |
|---|---|
| Install a package | `uv add <package>` |
| Install dev dependency | `uv add --dev <package>` |
| Run a script | `uv run <script>` |
| Sync environment | `uv sync` |
| Run tests | `uv run pytest ...` |

---

## Validation Commands

Run before every commit and after every implementation task.

```bash
# Pre-commit — mandatory gate (fast, ~15s, unit tests only)
uv run pytest tests/unit/ -v

# Integration — real Supabase DB (service layer, models, tool scoping)
uv run pytest tests/integration/ -v

# Graph-API suite — after changing graph edges/nodes (server auto-starts via conftest)
uv run pytest tests/graph_api/ -v -s

# Single file — during active development
uv run pytest tests/unit/test_<specific>.py -v

# Last-failed only — fix-and-retry loop
uv run pytest --lf -v
```

---

## CI/CD Pipeline

### CI (`.github/workflows/ci.yml`)

Runs on every push and PR to `main`.

| Job | Depends On | What | Secrets Needed |
|---|---|---|---|
| Lint & Unit Tests | — | `ruff check .` + `pytest tests/unit/` | None |
| Integration Tests | Lint & Unit | `pytest tests/integration/` | `SUPABASE_DB_URL` |
| E2E Graph-API Tests | — (manual only) | `pytest tests/graph_api/` | `SUPABASE_DB_URL`, `OPENAI_API_KEY` |

E2E tests run only via manual `workflow_dispatch` trigger (GitHub Actions UI → "Run workflow" → check "Run E2E").

### CD (`.github/workflows/cd.yml`)

Runs on push to `main` when production-relevant files change. Path filter: `src/**`, `bot/**`, `pyproject.toml`, `uv.lock`, `langgraph.production.json`, `.dockerignore`, `prompts/**`, `.github/workflows/cd.yml`. Builds both Docker images, pushes to Docker Hub, and redeploys on Railway.

Steps: checkout → install uv → install deps → Docker login → build bot image → build server image (`langgraph build`) → push both → install Railway CLI → redeploy both services.

### Required GitHub Secrets (Settings → Secrets → Actions)

| Secret | Purpose |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub login (`dolevsan`) |
| `DOCKERHUB_TOKEN` | Docker Hub access token |
| `RAILWAY_TOKEN` | Railway API token for redeploy |
| `SUPABASE_DB_URL` | Integration test DB connection |
| `OPENAI_API_KEY` | E2E tests (manual trigger only) |

### Build Commands (for reference)

```bash
# Bot image
docker build -f bot/Dockerfile -t dolevsan/fitpal-bot:latest --platform linux/amd64 .

# Server image (requires langgraph-cli)
PYTHONIOENCODING=utf-8 uv run langgraph build -t dolevsan/fitpal-server:latest -c langgraph.production.json --platform linux/amd64
```

---

## MCP Servers

| Server | Purpose | When to Use |
|---|---|---|
| `docs-langchain` | Real-time LangChain, LangGraph, and LangSmith documentation search | When implementing LangGraph features, researching SDK patterns, or verifying API signatures |
| `supabase` | Supabase docs, SQL execution, migrations, project management | When working on Supabase integration, database setup, auth, or RLS policies |

---

## Reference Table

| Resource | Type | Purpose | When to Read |
|---|---|---|---|
| [PRD.md](PRD.md) | Documentation | Full requirements, features, and specs | Feature planning / understanding scope |
| [.claude/skills/test-engineering/SKILL.md](.claude/skills/test-engineering/SKILL.md) | Skill | Test tiers, mock boundaries, file structure, AAA docstrings, graph-api patterns | **Before** writing any test; when a test fails unexpectedly; when adding a new node, route, or schema |
| [.claude/skills/langchain-architecture/SKILL.md](.claude/skills/langchain-architecture/SKILL.md) | Skill | LangGraph state management, type safety patterns, node/edge best practices | **Before** implementing any LangGraph node, edge, or state change |
| [.claude/skills/plan-feature/SKILL.md](.claude/skills/plan-feature/SKILL.md) | Skill | Feature planning workflow with deep codebase analysis | When planning a new feature or refactor before implementing |
| [.claude/skills/validation/SKILL.md](.claude/skills/validation/SKILL.md) | Skill | Comprehensive validation and code review workflow | Before committing, after implementing a feature, or when user says "validate" |
| [.claude/skills/sync-context/SKILL.md](.claude/skills/sync-context/SKILL.md) | Skill | Synchronize CLAUDE.md and project skills with actual state | After significant refactors, new skills added, or structural changes |
| [.claude/skills/use-railway/SKILL.md](.claude/skills/use-railway/SKILL.md) | Skill | Railway infrastructure operations (deploy, configure, troubleshoot) | When working with Railway deployment, services, or environment variables |
| [.claude/skills/eval-debugger/SKILL.md](.claude/skills/eval-debugger/SKILL.md) | Skill | Debug eval failures from LangSmith experiments, generate diagnostic reports | After running evals, when failures need investigation |
| [.claude/skills/eval-setup/SKILL.md](.claude/skills/eval-setup/SKILL.md) | Skill | Create single-step evaluation notebooks for graph nodes | When creating a new eval for a node |
| [docs/orphaned-langgraph-server.md](docs/orphaned-langgraph-server.md) | Documentation | Guide for finding/killing zombie langgraph dev processes on Windows | When `langgraph dev` fails with "port 2024 already in use" |
