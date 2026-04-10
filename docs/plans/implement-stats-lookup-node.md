# Feature: Implement Stats Lookup Node with Date Handling

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Implement the logic for the `stats_lookup_node` in the FitPal LangGraph agent. This node is responsible for fulfilling user requests like "How much protein have I eaten today?", "What did I eat yesterday?", or "Average calories last week".

It involves:
1.  Enhancing the `FoodIntakeEvent` schema and `input_parser_node` to capture target dates (single or range) from user input.
2.  Refactoring `AgentState` to store detailed `daily_log_report` (List[QueriedLog]) instead of just `DailyTotals`.
3.  Implementing `stats_lookup_node` to query the database for these logs.
4.  Updating `calculate_log_node` to populate the new state structure.

## User Story

As a **User**
I want to **ask "What did I eat yesterday?" or "How much protein have I eaten in the last 3 days?"**
So that **I can review my nutrition logs and complex aggregates (averages, sums) via the agent.**

## Problem Statement

Currently, the `stats_lookup_node` is a placeholder. The `AgentState` only supports storing simple totals (`DailyTotals`), which prevents advanced reasoning (e.g., "average protein last week"). Additionally, the input parser cannot handle date-specific queries (it defaults to "now" or nothing).

## Solution Statement

1.  **Schema Update**: Add `target_date`, `start_date`, `end_date` to `FoodIntakeEvent` schema. Make `items` field optional with explicit description.
2.  **Prompt Update**: Update `prompts/input_parser.md` to instruct the LLM to extract dates for `QUERY_DAILY_STATS` and ignore `items`.
3.  **State Refactor**: Replace `DailyTotals` with `daily_log_report: List[QueriedLog]` in `AgentState`.
4.  **Node Implementation**:
    *   `input_parser_node`: Extract dates and update `current_date` (or set `start/end_date` in state).
    *   `stats_lookup_node`: Query DB using `daily_log_service` (supporting both single-day and range) and populate `daily_log_report`.
    *   `calculate_log_node`: Update to populate `daily_log_report` instead of `daily_totals`.

## Feature Metadata

**Feature Type**: Refactor & Enhancement
**Estimated Complexity**: Medium
**Primary Systems Affected**: `src/agents/state.py`, `src/schemas/input_schema.py`, `src/agents/nodes/stats_node.py`
**Dependencies**: `sqlalchemy`, `src.services.daily_log_service`

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/agents/state.py` (lines 31-42, 82) - Why: State definition to refactor.
- `src/schemas/input_schema.py` (lines 26-34) - Why: Input schema to extend.
- `src/services/daily_log_service.py` (lines 95-135) - Why: Service methods `get_logs_by_date` and `get_logs_by_date_range`.
- `prompts/input_parser.md` (lines 9-10) - Why: System prompt to update.
- `src/agents/nodes/calculate_log_node.py` (lines 61-63) - Why: Needs to be updated to match new state.

### New Files to Create

- `src/agents/nodes/stats_node.py` - The implementation of the lookup node.
- `tests/unit/test_stats_node.py` - Unit tests.

### Patterns to Follow

**TypedDict Definition:**
```python
class QueriedLog(TypedDict):
    # Mirrors DailyLog model fields
    id: int
    food_id: int
    amount_g: float
    calories: float
    # ...
    timestamp: datetime
```

**State Update Pattern:**
```python
return {
    "daily_log_report": [log.to_dict() for log in logs],
    # ...
}
```

---

## IMPLEMENTATION PLAN

### Phase 1: Input & Schema

Enable the agent to understand dates.

**Tasks:**
- Update `FoodIntakeEvent` Pydantic model (optional items, new date fields).
- Update `prompts/input_parser.md` instructions.
- Update `input_parser_node` to handle date logic.

### Phase 2: State Refactoring

Prepare the agent memory for detailed reports.

**Tasks:**
- Define `QueriedLog` TypedDict (mirror of `DailyLog`).
- Update `AgentState` to use `daily_log_report: List[QueriedLog]` instead of `DailyTotals`.
- Add `start_date` and `end_date` to `AgentState` (to support range context).

### Phase 3: Core Implementation

Implement the logic to fetch and store data.

**Tasks:**
- Create `src/agents/nodes/stats_node.py` (handling single and range queries).
- Update `calculate_log_node` to populate the new state field (fetching logs instead of totals).
- Wire up `stats_lookup_node` in `nutritionist.py`.

### Phase 4: Testing

Verify the logic.

**Tasks:**
- Create `tests/unit/test_stats_node.py` (unit tests for new logic).
- Update existing tests aimed at `calculate_log_node` (since state changed).

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### 1. UPDATE src/schemas/input_schema.py

- **IMPORTS**: `from datetime import date`
- **ADD**: `target_date: Optional[date]`, `start_date: Optional[date]`, `end_date: Optional[date]` to `FoodIntakeEvent`.
- **UPDATE**: Change `items` field description: "List of food items. Only used for LOG_FOOD or QUERY_FOOD_INFO actions."
- **VALIDATE**: `uv run python -c "from src.schemas.input_schema import FoodIntakeEvent; print(FoodIntakeEvent.__fields__['items'].description)"`

### 2. UPDATE prompts/input_parser.md

- **UPDATE**: Under `QUERY_DAILY_STATS`:
  > - **EXTRACT DATES**: If the user specifies a date (e.g. "yesterday"), set `target_date`.
  > - For ranges ("last 3 days"), set `start_date` and `end_date`.
  > - Default: If no date specified, assume `target_date` is Today.
- **VALIDATE**: Manual check of file content.

### 3. UPDATE src/agents/state.py

- **REMOVE**: `DailyTotals` class.
- **ADD**: `QueriedLog` TypedDict.
- **UPDATE**: `AgentState`.
  - Replace `daily_totals` with `daily_log_report: List[QueriedLog]`.
  - Add `start_date: Optional[date]` and `end_date: Optional[date]`.
- **VALIDATE**: `uv run python -c "from src.agents.state import AgentState; print(AgentState.__annotations__)"`

### 4. UPDATE src/agents/nodes/input_node.py

- **IMPORTS**: `from datetime import date`
- **IMPLEMENT**: In `input_parser_node` return dict:
  - If `result.start_date` & `result.end_date` -> set `start_date` and `end_date` in state (clear `current_date`).
  - Else if `result.target_date` -> set `current_date` (clear start/end).
  - Else -> default `current_date` to today (clear start/end).
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py`

### 5. CREATE src/agents/nodes/stats_node.py

- **IMPORTS**: `AgentState`, `get_db_session`, `daily_log_service`.
- **IMPLEMENT**: `stats_lookup_node`:
  - If `state.get("start_date")` and `state.get("end_date")`:
    - Call `service.get_logs_by_date_range(session, start, end)`.
  - Else:
    - Call `service.get_logs_by_date(session, state["current_date"])`.
  - Return `{"daily_log_report": [log_to_dict(l) for l in logs]}`.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.stats_node import stats_lookup_node; print('Imported')"`

### 6. UPDATE src/agents/nodes/calculate_log_node.py

- **REFACTOR**: Update to return `daily_log_report` by calling `service.get_logs_by_date(session, timestamp.date())`.
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_log_node.py` (Expect failures, fix assertion logic in test file).

### 7. UPDATE src/agents/nutritionist.py

- **IMPORTS**: Import `stats_lookup_node`.
- **REFACTOR**: Replace placeholder.
- **VALIDATE**: `uv run python src/agents/nutritionist.py`

---

## TESTING STRATEGY

### Unit Tests

- **Parser Date Logic**: Verify "yesterday" maps to `date.today() - 1`.
- **Range Logic**: Verify "last 3 days" maps to start/end dates.
- **State Transition**: Verify `stats_lookup_node` output matches `List[QueriedLog]`.
- **Regression**: Fix `test_calculate_log_node.py` to assert on `daily_log_report` instead of `daily_totals`.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

`uv run ruff check src/agents/nodes/stats_node.py`

### Level 2: Unit Tests

`uv run pytest tests/unit/test_stats_node.py`
`uv run pytest tests/unit/test_calculate_log_node.py`

---

## ACCEPTANCE CRITERIA

- [ ] `AgentState` contains `daily_log_report` (List of logs), not `daily_totals`.
- [ ] User can ask "What are my stats?" and the `daily_log_report` is populated with raw log data.
- [ ] User can ask "Stats for last 3 days" (Range Query) and receive aggregated logs.
- [ ] `calculate_log_node` updates the report after logging.
