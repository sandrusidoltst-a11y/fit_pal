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
│   │   └── state.py         # Schema and TypedDict
│   ├── scripts/
│   │   └── ingest_simple_db.py # ETL script (CSV -> SQLite)
│   ├── tools/
│   │   └── food_lookup.py   # Database search logic
│   ├── database.py          # Database connection
│   ├── models.py            # SQLAlchemy models
│   ├── main.py              # Entry point
│   └── config.py            # Environment & LLM setup
├── tests/                   # Integration & Unit tests
├── notebooks/
│   └── evaluate_lookup.ipynb # Analysis notebook
├── PRD.md
├── prompts/             # System prompts and tool specs
└── README.md
```

## 4. MCP Servers
- **playwright**: Browser automation and interaction tools.

## 5. Reference Table
| File / Resource | Type | Purpose | When to Read |
| :--- | :--- | :--- | :--- |
| [PRD.md](../../PRD.md) | Documentation | Requirements, features, and specs | Start of project / Feature planning |
| [venv-enforcement.md](venv-enforcement.md) | Rule | Python environment management | Before installing packages or running scripts |
| [main_rule.md](main_rule.md) | Rule | Project overview and rules | New session / Context loading |
| [skills/langchain-architecture](../skills/langchain-architecture/SKILL.md) | Skill | LangGraph/LangChain patterns | Implementing agent logic or graph flows |
| [skills/testing-and-logging](../skills/testing-and-logging/SKILL.md) | Skill | Testing & Logging standards | Writing tests or debugging code |
| [workflows/sync_context.md](../workflows/sync_context.md) | Workflow | Sync docs with project state | Periodic context checks |
