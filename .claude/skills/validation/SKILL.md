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

### Test Suites — Run in This Order

```bash
# Step 1 — Pre-commit gate (mandatory, fast ~15s)
uv run pytest tests/unit/ -v

# Step 2 — After schema, state, or prompt changes (~60s)
uv run pytest tests/ -v

# Step 3 — After changing graph edges/nodes (server auto-starts via conftest)
uv run pytest tests/graph_api/ -v -s

# Single file during active development
uv run pytest tests/unit/test_<specific>.py -v

# Last-failed retry loop
uv run pytest --lf -v
```

### Test Tier Decision

```
Does the test mock any I/O (LLM, DB)?
  YES → tests/unit/
  NO, but tests compilation/DB/LLM directly → tests/integration/
  NO, tests the full graph via HTTP API runtime → tests/graph_api/
```

## 2. Critical Paths — Must Always Pass

These flows must never lose test coverage. Verify these specifically after any change:

| Critical Path | Test File | What to Watch |
|---|---|---|
| `define_graph()` compilation | `test_feedback_integration.py` | Must compile with `MemorySaver()` without `TypeError` |
| Input parsing → all `GraphAction` outcomes | `test_input_parser.py` | `LOG_FOOD`, `QUERY_DAILY_STATS`, `CHITCHAT`, `CONFIRM_ESTIMATION` |
| Routing functions (all branches) | `test_feedback_logic.py` | Every `GraphAction` maps to a valid next node |
| Multi-item loop drain | `test_multi_item_loop.py` | `pending_food_items` reaches `[]` after N iterations |
| HITL flow | `test_calculate_log_node.py` | `CONFIRM_ESTIMATION` → `calculate_log_node` → `LOGGED` |
| Schema enum consistency | `test_state_consistency.py` | `ActionType`, `SelectionStatus`, `GraphAction` stay in sync |
| Service layer write → read | `test_daily_log_service.py` | `create_log_entry` → `get_logs_by_date` returns correct record |

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