# FitPal — Project Context

## Project Overview

FitPal is a LangGraph-based AI nutrition coach. Users log food in natural language ("I had 200g of chicken and a banana"); the agent parses intent, looks up macros from a local SQLite database, and maintains a stateful daily log.

**Mission**: Make nutrition tracking effortless — logging food should feel like texting a friend.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (StateGraph, async) |
| LLM Framework | LangChain 1.x |
| Schema Validation | Pydantic v2 |
| LLM Models | Claude 3.5 Sonnet / GPT-4o — configured via `src/config.py` |
| Storage | SQLite + SQLAlchemy (`aiosqlite` async + sync engine for LangChain tools) |
| Package Manager | `uv` — strictly enforced (see Package Management below) |
| Language | Python 3.13+ |
| Dev Server | `langgraph dev` → LangSmith Studio |

---

## Project Structure

```text
fit_pal/
├── commit_logs/                   # History of commits
├── data/
│   ├── nutrition.db               # Nutritional database (SQLite)
│   ├── nutrients_csvfile.csv      # Source data (Simple CSV)
│   ├── meal_plan.txt              # User's macro targets
│   └── logs/                      # Historical daily logs
├── src/
│   ├── agents/
│   │   ├── nutritionist.py        # LangGraph graph definition
│   │   ├── state.py               # InputState, AgentState, OutputState TypedDicts
│   │   └── nodes/
│   │       ├── input_node.py      # Input parser node
│   │       ├── food_search_node.py # Food search node
│   │       ├── selection_node.py  # Agent selection node
│   │       ├── calculate_log_node.py # Calculate & log node
│   │       ├── stats_node.py      # Stats lookup node
│   │       └── response_node.py   # LLM response generator
│   ├── services/
│   │   └── daily_log_service.py   # CRUD for daily logs
│   ├── scripts/
│   │   └── ingest_simple_db.py    # ETL script (CSV -> SQLite)
│   ├── tools/
│   │   └── food_lookup.py         # Database search logic
│   ├── schemas/
│   │   ├── input_schema.py        # FoodIntakeEvent schema
│   │   └── selection_schema.py    # FoodSelectionResult schema
│   ├── database.py                # Sync + async DB engines
│   ├── models.py                  # SQLAlchemy models (FoodItem, DailyLog)
│   ├── main.py                    # Entry point
│   └── config.py                  # Environment & LLM setup via get_llm_for_node()
├── tests/
│   ├── unit/                      # Fast, deterministic tests (mocked DB/LLM)
│   ├── integration/               # Slower tests (real DB / real LLM / graph compilation)
│   ├── graph_api/                 # End-to-end graph flow tests via langgraph-sdk
│   └── conftest.py                # Pytest shared fixtures
├── notebooks/
│   └── evaluate_lookup.ipynb      # Analysis notebook
├── prompts/                       # System prompts and tool specs
├── langgraph.json                 # LangSmith Studio configuration
├── PRD.md
└── README.md
```

---

## Architecture Patterns

- **Multiple Schemas**: `InputState` (messages only, public API) → `AgentState` (internal) → `OutputState`. Enables clean LangSmith Studio chat interface without exposing internal state fields.
- **Configuration Dictionary**: `get_llm_for_node()` in `config.py` centralises all LLM instantiation with per-node overrides (temperature, model). Never hardcode models inside nodes.
- **Write-Through**: DB is source of truth. Write immediately on confirmation, then query for state updates.
- **Async DB + Graph**: `sqlalchemy.ext.asyncio` + `aiosqlite` for non-blocking queries. Both sync and async engines are maintained — LangChain `@tool` decorators require the sync engine.
- **Multi-Item Loop**: Conditional routing processes food items sequentially with loop-back edges until the queue is empty.
- **Service Layer**: Business logic lives in `src/services/`. Nodes call services, never the DB directly.
- **Pydantic for LLM Output**: Always use `.with_structured_output()` then `.model_dump()`. Never parse raw LLM strings.
- **Reporting State**: `AgentState.daily_log_report` stores raw `QueriedLog` list — enables flexible LLM reasoning (averages, distributions) instead of pre-aggregated values.

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

# Full suite — after schema or prompt changes (~60s)
uv run pytest tests/ -v

# Graph-API suite — after changing graph edges/nodes (requires: uv run langgraph dev)
uv run pytest tests/graph_api/ -v -s

# Single file — during active development
uv run pytest tests/unit/test_<specific>.py -v

# Last-failed only — fix-and-retry loop
uv run pytest --lf -v
```

---

## MCP Servers

| Server | Purpose | When to Use |
|---|---|---|
| `docs-langchain` | Real-time LangChain, LangGraph, and LangSmith documentation search | When implementing LangGraph features, researching SDK patterns, or verifying API signatures |

---

## Reference Table

| Resource | Type | Purpose | When to Read |
|---|---|---|---|
| [PRD.md](PRD.md) | Documentation | Full requirements, features, and specs | Feature planning / understanding scope |
| [.claude/skills/test-engineering/SKILL.md](.claude/skills/test-engineering/SKILL.md) | Skill | Test tiers, mock boundaries, file structure, AAA docstrings, graph-api patterns | **Before** writing any test; when a test fails unexpectedly; when adding a new node, route, or schema |
| [.claude/skills/langchain-architecture/SKILL.md](.claude/skills/langchain-architecture/SKILL.md) | Skill | LangGraph state management, type safety patterns, node/edge best practices | **Before** implementing any LangGraph node, edge, or state change |
| [.claude/skills/langsmith-fetch/SKILL.md](.claude/skills/langsmith-fetch/SKILL.md) | Skill | Fetching and reading LangSmith traces via CLI | When debugging unexpected agent behaviour or tracing tool calls |
