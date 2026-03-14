---
name: validation
description: Run comprehensive validation and code review for FitPal. Use after implementing a feature, before committing, or when the user says "validate", "run checks", or "is everything passing?".
---

# Validation Workflow — FitPal

Ensure project quality through automated checks and systematic review.

## 1. Automated Validation

### Linting & Type Checking

```bash
# Lint
uv run ruff check .

# Type check
uv run mypy src/
```

### Test Suites — Select Based on Changes

**Before running any tests**, analyze the diff to determine which suites are needed, then **present a confirmation message to the user** using the format below. Do NOT run tests until the user confirms.

#### Step 1: Analyze changes

```bash
git diff HEAD
git ls-files --others --exclude-standard
```

#### Step 2: Determine which suites to run

Use this decision matrix against the changed files:

| Changed files touch... | Unit | Integration | Graph-API |
|---|---|---|---|
| `src/agents/nodes/` (node logic) | YES | — | — |
| `src/schemas/` (Pydantic schemas) | YES | — | — |
| `src/config.py`, `src/security/` | YES | — | — |
| `bot/` (gateway, admin) | YES | — | — |
| `prompts/` (system prompts) | YES | — | — |
| `src/services/` (service layer) | YES | YES | — |
| `src/models.py` (ORM models) | YES | YES | — |
| `src/tools/` (food_lookup, etc.) | YES | YES | — |
| `src/database.py` (engine/session) | YES | YES | — |
| `src/agents/nutritionist.py` (graph edges) | YES | — | YES |
| `langgraph.json` / `langgraph.production.json` | — | — | YES |
| `tests/unit/` only | YES | — | — |
| `tests/integration/` only | — | YES | — |
| `tests/graph_api/` only | — | — | YES |
| Docs / skills / non-code only | — | — | — |

**Unit tests are always included** unless the change is docs-only. Integration and Graph-API are added only when relevant.

#### Step 3: Present confirmation to user

Before running, show the user a message like this:

```
Validation plan based on changes to [list changed areas]:

  RUN:  Unit tests (tests/unit/)          — always required
  RUN:  Integration tests (tests/integration/) — [reason, e.g. "services/daily_log_service.py changed"]
  SKIP: Graph-API tests (tests/graph_api/)     — [reason, e.g. "no graph edge or config changes"]

Proceed?
```

Wait for user confirmation, then run only the confirmed suites in order.

#### Commands

```bash
# Unit (fast ~5s, offline)
uv run pytest tests/unit/ -v

# Integration (real Supabase DB)
uv run pytest tests/integration/ -v

# Graph-API (server auto-starts via conftest)
uv run pytest tests/graph_api/ -v -s

# Single file during development
uv run pytest tests/<tier>/test_<specific>.py -v

# Last-failed retry loop
uv run pytest --lf -v
```

### Test Tier Decision (for writing new tests)

```
Does the test mock ALL I/O (LLM, DB, tools)?
  YES → tests/unit/
  NO  → Does it need the real DB but NOT the LangGraph server?
    YES → tests/integration/
    NO  → tests/graph_api/
```

## 2. Critical Paths — Must Always Pass

These flows must never lose test coverage. Verify these specifically after any change:

| Critical Path | Test File | What to Watch |
|---|---|---|
| `define_graph()` compilation | `graph_api/test_graph_compilation.py` | Must compile with `MemorySaver()` without `TypeError` |
| Input parsing → all `GraphAction` outcomes | `unit/test_input_parser.py` | `LOG_FOOD`, `QUERY_DAILY_STATS`, `CHITCHAT`, `CONFIRM_ESTIMATION` |
| Routing functions (all branches) | `unit/test_feedback_logic.py` | Every `GraphAction` maps to a valid next node |
| Multi-item loop drain | `unit/test_multi_item_loop.py` | `pending_food_items` reaches `[]` after N iterations |
| HITL flow | `unit/test_calculate_log_node.py` | `CONFIRM_ESTIMATION` → `calculate_log_node` → `LOGGED` |
| Schema enum consistency | `unit/test_state_consistency.py` | `ActionType`, `SelectionStatus`, `GraphAction` stay in sync |
| Service layer write → read | `integration/test_daily_log_service.py` | `create_log_entry` → `get_logs_by_date` returns correct record |
| User data isolation | `integration/test_food_lookup.py` | Estimated foods scoped to owner, shared foods visible to all |

## 3. Code Review

**Goal**: Review recent changes for logic, security, and quality.

1.  **Context**: Check `CLAUDE.md` and `README.md`.
2.  **Analyze Diffs**:
    ```bash
    git diff HEAD
    git ls-files --others --exclude-standard
    ```
3.  **Check For**:
    - **Logic Errors**: Off-by-one, race conditions, incorrect state mutations.
    - **Security**: Injections, exposed secrets, unvalidated inputs.
    - **Performance**: N+1 queries, blocking async calls, memory leaks.
    - **Quality**: DRY, naming conventions, type hints, Pydantic usage.
    - **FitPal Patterns**: Service layer used correctly, no direct DB calls from nodes, LLM output validated with `.with_structured_output()`.
4.  **Verify**: Run specific tests for any issues found.

## 4. System Review (Post-Implementation)

**Goal**: Analyze process adherence and identify improvements.

1.  **Compare**: Planned Approach vs. Actual Implementation.
2.  **Identify Divergences**:
    - **Good**: Justified improvements.
    - **Bad**: Shortcuts, misunderstandings.
3.  **Root Cause**: Why did bad divergences happen?
4.  **Improve**:
    - Update `CLAUDE.md` with new patterns or rules discovered.
    - Update relevant skill files in `.claude/skills/` with clarifications.