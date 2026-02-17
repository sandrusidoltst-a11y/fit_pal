# Feature: Implement Calculate Log Node

## Feature Description

Implement the core logic for the `calculate_log_node` in the FitPal LangGraph agent. This node bridges the gap between food selection and data persistence. It takes a selected food item, calculates its nutritional values based on the consumed amount, persists the entry to the SQLite database via the `daily_log_service`, and updates the agent's state with the new daily totals.

## User Story

As a user
I want my food entries to be accurately calculated and saved to my daily log
So that I can track my macros and calories over time without losing data.

## Problem Statement

Currently, the `calculate_log_node` is a placeholder that only removes items from the pending list. It does not perform any calculations or database updates, meaning user data is discarded immediately after input.

## Solution Statement

We will implement the logic to:
1.  Extract the `selected_food_id` and the current `pending_food_item` from the state.
2.  Use `calculate_food_macros` (tool logic) to compute specific values for the user's portion.
3.  Persist the calculated data using `daily_log_service.create_log_entry`.
4.  Immediately fetch updated daily totals using `daily_log_service.get_daily_totals`.
5.  Update the `AgentState` with the new totals and remove the processed item.

## Feature Metadata

**Feature Type**: Enhancement
**Estimated Complexity**: Low
**Primary Systems Affected**: `src/agents/nodes/calculate_log_node.py`
**Dependencies**: `SQLAlchemy`, `daily_log_service`, `food_lookup` tool logic.

---

## CONTEXT REFERENCES

### Relevant Codebase Files
- `src/agents/nodes/calculate_log_node.py` (Current placeholder)
- `src/services/daily_log_service.py` (Persistence API)
- `src/tools/food_lookup.py` (Calculation logic)
- `src/agents/state.py` (State definition)

### New Files to Create
- `tests/unit/test_calculate_log_node.py` - Unit tests for the new node logic.

### Patterns to Follow
- **Service Layer Pattern**: Use `src/services/daily_log_service.py` for all DB interactions.
- **Dependency Injection**: Create explicit DB sessions (`get_db_session()`) within the node and pass them to service functions.
- **State Immutability**: Return a dictionary of schema updates rather than mutating state in place.

---

## IMPLEMENTATION PLAN

### Phase 1: Core Implementation

**Tasks:**

- `UPDATE` `src/agents/nodes/calculate_log_node.py`
    - **IMPLEMENT**: logic to get `selected_food_id` and first item from `pending_food_items`.
    - **IMPLEMENT**: `calculate_food_macros` logic (direct call or import).
    - **IMPLEMENT**: DB session context manager.
    - **IMPLEMENT**: `daily_log_service.create_log_entry` call.
    - **IMPLEMENT**: `daily_log_service.get_daily_totals` call.
    - **IMPORTS**: `datetime`, `timezone`, `get_db_session`, `daily_log_service`.

### Phase 2: Testing & Validation

**Tasks:**

- `CREATE` `tests/unit/test_calculate_log_node.py`
    - **IMPLEMENT**: Unit test for successful logging.
    - **IMPLEMENT**: Unit test for missing food ID (edge case).
    - **IMPLEMENT**: Mocking of DB session and service methods.
    - **VALIDATE**: `pytest tests/unit/test_calculate_log_node.py`

---

## STEP-BY-STEP TASKS

### 1. IMPLEMENT Core Logic in `calculate_log_node.py`

- **UPDATE** `src/agents/nodes/calculate_log_node.py`
    - **IMPORTS**: 
        ```python
        from datetime import datetime, timezone
        from src.database import get_db_session
        from src.services import daily_log_service
        from src.tools.food_lookup import calculate_food_macros
        ```
    - **LOGIC**:
        1. Get `selected_food_id` from state.
        2. Get first item from `pending_food_items`.
        3. Open DB session `with get_db_session() as session:`.
        4. Calculate macros: `macros = calculate_food_macros(selected_food_id, amount)`.
        5. Persist: `daily_log_service.create_log_entry(...)` using `macros` and `current_data`.
        6. Refresh Totals: `new_totals = daily_log_service.get_daily_totals(...)`.
    - **VALIDATE**: `uv run pytest tests/unit/test_calculate_log_node.py` (will fail until tests are created)

### 2. CREATE Unit Tests

- **CREATE** `tests/unit/test_calculate_log_node.py`
    - **IMPORTS**: `pytest`, `MagicMock`, `calculate_log_node`, `AgentState`.
    - **TEST 1**: `test_calculate_log_node_success`:
        - Mock `get_db_session`.
        - Mock `daily_log_service` methods.
        - Setup state with a pending item and `selected_food_id`.
        - Assert `create_log_entry` was called.
        - Assert returned state has updated `daily_totals` and empty `pending_food_items`.
    - **VALIDATE**: `uv run pytest tests/unit/test_calculate_log_node.py`

---

## TESTING STRATEGY

### Unit Tests
- Isolate the node logic.
- Mock the database session and service layer to avoid actual DB writes during unit tests.
- Verify state transitions (pending items removed, totals updated).

### Edge Cases
- **No selected_food_id**: Should handle gracefully (skip logging or raise error).
- **Empty pending items**: Should return empty dict (already handled).

## VALIDATION COMMANDS

### Level 1: Syntax
`uv run ruff check src/agents/nodes/calculate_log_node.py`

### Level 2: Unit Tests
`uv run pytest tests/unit/test_calculate_log_node.py`

## ACCEPTANCE CRITERIA
- [ ] User input of food results in a new row in `daily_logs` table.
- [ ] `daily_totals` in state reflects the sum of all logs for the current date.
- [ ] `pending_food_items` is correctly drained.
