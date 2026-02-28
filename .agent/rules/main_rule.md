# FitPal Project Rules

## 1. Executive Summary
FitPal is an intelligent AI fitness and nutrition coach designed to bridge the gap between traditional meal planning and the friction of daily logging. Built on the **LangGraph** framework, the agent acts as a stateful companion that understands natural language, tracks macronutrients (Protein, Carbs, Fats) and Calories in real-time, and provides personalized feedback based on a user's specific meal plan.

The MVP focuses on the core utility: accurately parsing natural language food intake, looking up nutritional values from a local database, and maintaining a session-based state of daily totals.

## 2. Technology Stack
- **Orchestration**: LangGraph.
- **LLM Framework**: LangChain 1.x.
- **Schema Validation**: Pydantic v2.
- **LLM Model**: Claude 3.5 Sonnet or GPT-4o.
- **Data Processing**: Pandas (for CSV/Database lookup).
- **Storage**: SQLite (Checkpointer for state).
- **Language**: Python 3.10+.
- **Package Manager**: uv (Required for dependency management).

## 3. Project Structure
```text
fit_pal/
├── commit_logs/             # History of commits
├── data/
│   ├── nutrition.db         # Nutritional database (SQLite)
│   ├── nutrients_csvfile.csv # Source data (Simple CSV)
│   ├── meal_plan.txt        # User's targets
│   └── logs/                 # Historical daily logs
├── src/
│   ├── agents/
│   │   ├── nutritionist.py   # LangGraph definition
│   │   ├── state.py         # Schema and TypedDict
│   │   └── nodes/           # Node implementations
│   │       ├── input_node.py      # Input parser node
│   │       ├── food_search_node.py # Food search node
│   │       ├── selection_node.py   # Agent selection node
│   │       ├── calculate_log_node.py # Calculate & log node
│   │       ├── stats_node.py       # Stats lookup node
│   │       └── response_node.py    # LLM response generator
│   ├── services/            # Business logic layer
│   │   └── daily_log_service.py # CRUD for daily logs
│   ├── scripts/
│   │   └── ingest_simple_db.py # ETL script (CSV -> SQLite)
│   ├── tools/
│   │   └── food_lookup.py   # Database search logic
│   ├── schemas/             # Pydantic models
│   │   ├── input_schema.py  # FoodIntakeEvent schema
│   │   └── selection_schema.py # FoodSelectionResult schema
│   ├── database.py          # Database connection
│   ├── models.py            # SQLAlchemy models (FoodItem, DailyLog)
│   ├── main.py              # Entry point
│   └── config.py            # Environment & LLM setup
├── tests/
│   ├── unit/                # Unit tests (pytest)
│   ├── conftest.py          # Pytest fixtures
│   └── test_food_lookup.py  # Legacy/Integration tests
├── notebooks/
│   └── evaluate_lookup.ipynb # Analysis notebook
├── langgraph.json       # LangSmith Studio configuration
├── PRD.md
├── prompts/             # System prompts and tool specs
└── README.md
```

## 4. MCP Servers
- **playwright**: Browser automation and interaction tools.

## 5. Architectural Patterns
- **Multiple Schemas**: Defines `InputState`, `OutputState`, and `AgentState`. Allows external callers (like LangSmith Studio) to interact via a clean, narrow public API (chat messages), while internally retaining robust task-specific state fields.
- **TypedDict for State**: `AgentState` uses nested TypedDict schemas (PendingFoodItem, SearchResult, QueriedLog) for type safety and clean serialization.
- **Pydantic for LLM Output**: Structured output validation with `.with_structured_output()`, then `.model_dump()` to dict.
- **Configuration Dictionary Pattern**: Used in `src/config.py` to centrally manage LLM instantiations (`get_llm_for_node`), allowing fallback globals from `.env` and node-specific parameters (like temperature) without hardcoding models in nodes.
- **Service Layer**: Business logic in `src/services/` (e.g., `daily_log_service.py`).
- **Write-Through Pattern**: DB is source of truth; write immediately, then query for state updates.
- **Reporting State**: `AgentState.daily_log_report` (List[QueriedLog]) stores raw log data instead of aggregates, enabling complex LLM reasoning (averages, distributions).
- **LLM Response Validation**: Code-level validation catches inconsistent LLM responses (e.g., SELECTED without food_id).
- **Multi-Item Loop**: Graph conditional routing processes food items sequentially with loop-back edges.
- **Asynchronous DB & Graph**: Usage of `sqlalchemy.ext.asyncio` with `aiosqlite` for non-blocking database queries, and `AsyncSqliteSaver` as the LangGraph checkpointer. Both sync and async DB engines are maintained to support legacy LangChain `@tool`s.

## 6. Reference Table
| File / Resource | Type | Purpose | When to Read |
| :--- | :--- | :--- | :--- |
| [PRD.md](../../PRD.md) | Documentation | Requirements, features, and specs | Start of project / Feature planning |
| [venv-enforcement.md](venv-enforcement.md) | Rule | Python environment management | Before installing packages or running scripts |
| [main_rule.md](main_rule.md) | Rule | Project overview and rules | New session / Context loading |
| [reference/test-strategy.md](../reference/test-strategy.md) | Reference | FitPal testing rules, mock boundaries, validation commands | Before writing any test, before running `/validation`, when a test fails unexpectedly |
| [skills/langchain-architecture](../skills/langchain-architecture/SKILL.md) | Skill | LangGraph state management & type safety | **BEFORE** implementing any LangGraph features |
| [skills/testing-and-logging](../skills/testing-and-logging/SKILL.md) | Skill | **How** to write tests — pytest syntax, AsyncMock patterns, structlog setup | When writing test code and you need implementation guidance |
| [skills/langsmith-fetch](../skills/langsmith-fetch/SKILL.md) | Skill | Debug LangChain traces | Troubleshooting agent behavior |
| [skills/skill-creator](../skills/skill-creator/SKILL.md) | Skill | Guide for creating effective skills | When extending agent capabilities with new skills |
| [workflows/sync_context.md](../workflows/sync_context.md) | Workflow | Sync docs with project state | Periodic context checks |

## 8. Validation Commands

Run these before every commit and after every implementation task.

```bash
# Pre-commit — mandatory gate (fast, ~15s, unit tests only)
uv run pytest tests/unit/ -v

# Full suite — before deploy or after schema/prompt changes (~60s)
uv run pytest tests/ -v

# Single file — during active development
uv run pytest tests/unit/test_<specific>.py -v

# Last-failed only — fix-and-retry loop
uv run pytest --lf -v
```
