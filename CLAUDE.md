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
| Auth (prod) | Shared secret middleware (`src/security/internal_auth_middleware.py`) — validates `X-Internal-Token` header; bot passes `user_id` in context body |
| Deployment | Railway (4 services: langgraph-server, fitpal-bot, Postgres checkpoints, Redis queue) + Docker Hub (`dolevsan/fitpal-server`, `dolevsan/fitpal-bot`) |
| User Scoping | `user_id` column on all user-scoped tables; FK constraints to `auth.users(id)`; flows via `ContextSchema` → `Runtime` → nodes pass `user_id` string to tools |
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
│   │       └── response_node.py   # LLM response generator (injects Israel-local time, profile, nutrition plan, today's log)
│   ├── services/
│   │   ├── daily_log_service.py   # CRUD for daily logs + @tool wrappers (log_food_entry, query_food_logs) + get_todays_logs_serialized helper for context injection (Israel-local timestamps)
│   │   ├── food_service.py        # FoodItem CRUD + @tool wrappers (search_food, calculate_food_macros, create_food_item) + compute_food_macros helper
│   │   ├── personal_stats_service.py # Personal stats CRUD + @tool wrappers (log_personal_stat, get_latest_personal_stats)
│   │   └── user_profile_service.py # User profile CRUD (onboarding data, nutrition plan set/get)
│   ├── i18n/                      # Bot/agent message localization (en.yaml, he.yaml; selected via BOT_LANGUAGE env var)
│   ├── scripts/
│   │   ├── ingest_simple_db.py    # ETL script (CSV -> Supabase Postgres)
│   │   ├── print_trace.py         # LangSmith thread trace viewer (by thread_id)
│   │   └── set_plan.py            # Coach CLI: upload nutrition plan per user
│   ├── schemas/
│   │   ├── input_schema.py        # UserIntent schema
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
│   ├── context.py                 # ContextSchema dataclass (user_id, user_profile, daily_log_today) for Runtime injection + defaults
│   ├── main.py                    # Entry point
│   └── config.py                  # Environment & LLM setup via get_llm_for_node()
├── bot/
│   ├── gateway.py                 # Telegram bot gateway (aiogram v3, webhook/polling, onboarding, HITL relay, SessionData TypedDict, fetches today's log per message for context injection)
│   ├── supabase_admin.py          # Supabase admin helpers (async client, BOT_PASSWORD_SEED, BOT_EMAIL_DOMAIN, user creation)
│   └── Dockerfile                 # Bot gateway container definition
├── tests/
│   ├── unit/                      # Fast, deterministic tests (mocked DB/LLM)
│   ├── integration/               # Real Supabase DB tests (service layer, models, tool scoping)
│   ├── graph_api/                 # Graph compilation + E2E flow tests via langgraph-sdk
│   │   └── logs/                  # Server logs + error tracebacks (gitignored)
│   ├── ux-loop/                   # live-ux-loop skill output — per-loop folders with inputs/ + runs/run<N>-<tag>/ artifacts
│   └── conftest.py                # Pytest shared fixtures
├── notebooks/
│   ├── evaluate_lookup.ipynb      # Analysis notebook
│   └── evals/
│       ├── eval_input_parser.ipynb # Input parser single-step eval (LangSmith)
│       └── reports/               # Eval debugger reports (gitignored)
├── docs/
│   ├── patterns/                  # Architecture pattern files (tool-first, state-schemas, etc.)
│   ├── plans/                     # Implementation plans (feature plans, refactor plans)
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

Detailed pattern files live in `docs/patterns/`. Each pattern below has a summary (always loaded) and a link to the full description (read before modifying related code).

| Pattern | Details | When to Read |
|---|---|---|
| **Tool-First + Service Layer**: All DB access through async `@tool` functions. Nodes are thin orchestrators via `await tool.ainvoke(...)` — never import DB sessions. `src/services/` has raw service functions (accept `session` for DI/testability) + `@tool` wrappers that own their session. | [tool-first.md](docs/patterns/tool-first.md) | Before adding tools, nodes, or DB access |
| **State Schemas**: `InputState` (messages only, public API) → `AgentState` (internal) → `OutputState`. Enables clean LangSmith Studio chat interface without exposing internal state fields. | [state-schemas.md](docs/patterns/state-schemas.md) | Before modifying state, adding fields, or changing graph I/O |
| **Runtime Context + User Profile**: `ContextSchema` (dataclass in `src/context.py`) defines `user_id`, `user_profile` (including optional `nutrition_plan`), and `daily_log_today` (list of serialized log dicts, fetched fresh per-message by the bot — not cached), registered on `StateGraph` via `context_schema`. Bot sends `context` field in HTTP body. Nodes access via `runtime: Runtime[ContextSchema]` and pass `user_id` as a plain string to tools. `response_node` injects user profile, nutrition plan, today's log, and current time (Israel local via `USER_TIMEZONE` from `src/config.py`) into `SystemMessage`. `DEFAULT_DEV_USER_ID` fallback for Studio. | [runtime-context.md](docs/patterns/runtime-context.md) | Before touching user_id, user_profile, nutrition_plan, daily_log_today, or context flow |
| **LLM Configuration + Pydantic Output**: `get_llm_for_node()` in `config.py` centralises LLM instantiation with per-node overrides. Never hardcode models. Use `.with_structured_output(Schema)` for typed nodes and access fields as attributes; call `.model_dump()` only at the state-write boundary. `response_node` is the conversational carve-out (no schema). Never parse raw LLM strings. | [llm-config.md](docs/patterns/llm-config.md) | Before adding or configuring LLM calls in nodes |
| **Fully Async**: All nodes, tools, and DB access use `async`/`await`. The async engine (`asyncpg`) is the primary DB path. Sync engine (`psycopg2`) exists only for ETL scripts. | [async-patterns.md](docs/patterns/async-patterns.md) | Before adding any DB, tool, or node code |
| **HITL Batch Confirmation**: All food items accumulated into `pending_confirmations` as `MacroResult` previews. `confirmation_node` uses `interrupt()` in a validation loop for confirm/reject/edit via natural language. `Command` return enables dynamic routing to `commit` or `response`. | [hitl-confirmation.md](docs/patterns/hitl-confirmation.md) | Before modifying confirmation/commit flow |
| **DB Schema Conventions**: Every model uses UUID PKs, `user_id` scoping column (indexed, usually NOT NULL), `DateTime(timezone=True)` timestamps, audit columns (`created_at`/`updated_at` with lambda defaults). FK to `auth.users(id)` in Postgres only, not SQLAlchemy. Supabase migrations for production schema — never `create_all()`/`drop_all()`. | [schema-management.md](docs/patterns/schema-management.md) | Before adding models, DB migrations, or test DB setup |

### Architectural Decisions (future ADRs)

The following are architectural descriptions and decisions that don't fit the "reusable code pattern" format above. They will be migrated to `docs/adr/` as proper Architecture Decision Records in a future session.

| Decision | Summary |
|---|---|
| **Off-Menu Estimation + Persistence** | NO_MATCH → LLM estimates via `MacroEstimation` structured output, tagged `source: "estimated"`. At commit, `commit_node` creates `FoodItem` row with back-calculated per-100g values. `search_food` two-tier: DB foods first → estimated fallback. |
| **Auth + Tagged Users** | Two permanent auth users: `dev@dev.fitpal.bot` (Studio/dev) and `e2e@test.fitpal.bot` (E2E tests), identifiable via `user_metadata.source`. Shared secret middleware (`X-Internal-Token`) for prod auth. Custom auth handler (`@auth.authenticate`) kept for future enterprise use. |
| **Bot Gateway + Local Dev** | aiogram v3 webhook (prod) or polling (local dev via `POLLING_MODE=true`). `BOT_EMAIL_DOMAIN` creates separate dev auth users. Onboarding collects profile on first registration. HITL interrupt relay via `_get_interrupt_state()` + `command={"resume": ...}`. |
| **Data Flow** | Write-through (DB is source of truth). `daily_log_report` stores raw `QueriedLog` list for flexible LLM reasoning. Multi-item loop processes food items sequentially with loop-back edges. Personal stats via `personal_stats_node` + `LOG_PERSONAL_STATS` action. |

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
| [PRD.md](PRD.md) | Documentation | Full requirements, features, and specs for the FitPal bot/agent | Feature planning / understanding scope |
| [DASHBOARD_PRD.md](DASHBOARD_PRD.md) | Documentation | Coach dashboard PRD — scope, architecture, data model, implementation phases. Most decisions are Claude-proposed defaults flagged for discussion during implementation planning. | Before planning or implementing any coach dashboard work |
| [.claude/skills/test-engineering/SKILL.md](.claude/skills/test-engineering/SKILL.md) | Skill | Test tiers, mock boundaries, file structure, AAA docstrings, graph-api patterns | **Before** writing any test; when a test fails unexpectedly; when adding a new node, route, or schema |
| [.claude/skills/plan-feature/SKILL.md](.claude/skills/plan-feature/SKILL.md) | Skill | Feature planning workflow with deep codebase analysis | When planning a new feature or refactor before implementing |
| [.claude/skills/validation/SKILL.md](.claude/skills/validation/SKILL.md) | Skill | Comprehensive validation and code review workflow | Before committing, after implementing a feature, or when user says "validate" |
| [.claude/skills/sync-context/SKILL.md](.claude/skills/sync-context/SKILL.md) | Skill | Synchronize CLAUDE.md and project skills with actual state | After significant refactors, new skills added, or structural changes |
| [.claude/skills/use-railway/SKILL.md](.claude/skills/use-railway/SKILL.md) | Skill | Railway infrastructure operations (deploy, configure, troubleshoot) | When working with Railway deployment, services, or environment variables |
| [.claude/skills/eval-debugger/SKILL.md](.claude/skills/eval-debugger/SKILL.md) | Skill | Debug eval failures from LangSmith experiments, generate diagnostic reports | After running evals, when failures need investigation |
| [.claude/skills/eval-setup/SKILL.md](.claude/skills/eval-setup/SKILL.md) | Skill | Create single-step evaluation notebooks for graph nodes | When creating a new eval for a node |
| [.claude/skills/focus/SKILL.md](.claude/skills/focus/SKILL.md) | Skill | Plan focused work sessions, recommend prioritized tasks | When starting a session or deciding what to work on next |
| [.claude/skills/skill-creator/SKILL.md](.claude/skills/skill-creator/SKILL.md) | Skill | Create, modify, and benchmark skills | When building or improving a skill |
| [.claude/skills/obsidian-markdown/SKILL.md](.claude/skills/obsidian-markdown/SKILL.md) | Skill | Obsidian-flavored Markdown (wikilinks, callouts, embeds) | When creating or editing Obsidian notes |
| [.claude/skills/obsidian-cli/SKILL.md](.claude/skills/obsidian-cli/SKILL.md) | Skill | Obsidian CLI interactions (read, create, search notes) | When interacting with the Obsidian vault programmatically |
| [.claude/skills/refine-dump/SKILL.md](.claude/skills/refine-dump/SKILL.md) | Skill | Refine raw brain dump notes into structured Obsidian notes | When processing daily brain dump notes |
| [.claude/skills/build-cut-plan/SKILL.md](.claude/skills/build-cut-plan/SKILL.md) | Skill | Build a personalized CUT (fat-loss) nutrition plan via conversational intake; outputs Hebrew or English markdown plan | When user asks to "build a cut plan" / "תפריט קאט" |
| [.claude/skills/build-bulk-plan/SKILL.md](.claude/skills/build-bulk-plan/SKILL.md) | Skill | Build a personalized CLEAN BULK (lean muscle) nutrition plan via conversational intake; outputs Hebrew or English markdown plan | When user asks to "build a bulk plan" / "תפריט מסה" |
| [.claude/skills/live-ux-loop/SKILL.md](.claude/skills/live-ux-loop/SKILL.md) | Skill | Dogfood the bot end-to-end as a real user against the live LangGraph dev server; eval bookends + trace + DB verification + bug routing (prompts fixed in-loop, code bugs handed off as records). Mode B authors `scenarios.md`/`expectations.md` per loop. | When iterating on bot UX, validating prompt changes against scripted scenarios, or authoring scenario/expectations files for a future UX-loop session |
| [.claude/skills/adr/SKILL.md](.claude/skills/adr/SKILL.md) | Skill | Create a new Architecture Decision Record in `docs/adr/` from recent conversation context | After an architectural conversation when the decision should be captured durably |
| [.claude/skills/prime/SKILL.md](.claude/skills/prime/SKILL.md) | Skill | Load and understand project context | At the start of a new session, when switching tasks, or when user says "prime yourself" |
| [docs/orphaned-langgraph-server.md](docs/orphaned-langgraph-server.md) | Documentation | Guide for finding/killing zombie langgraph dev processes on Windows | When `langgraph dev` fails with "port 2024 already in use" |
