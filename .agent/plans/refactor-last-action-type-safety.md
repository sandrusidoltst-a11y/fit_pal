# Feature: Refactor AgentState Last Action Type Safety

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

This feature addresses the type safety gap in the `AgentState.last_action` field. Currently, this field is typed as `str` but logically holds values from multiple sources (`InputSchema.ActionType`, `SelectionSchema.SelectionStatus`, and node-specific literals like "LOGGED"). This "magic string" approach is fragile and prone to runtime errors.

This refactor will unify all possible action states into a single `Literal` type definition in `state.py` and enforce its usage across the graph.

## User Story

As a developer maintaining the FitPal agent
I want the `last_action` field in the state to be strictly typed
So that I can trust the graph routing logic and catch typo-related bugs at static analysis time.

## Problem Statement

Checking `state.get("last_action")` against raw strings like `"LOG_FOOD"` or `"SELECTED"` is error-prone. If a node returns `"LOG_FOD"`, the router will silently fail. We need a single source of truth for all valid state transitions.

## Solution Statement

1.  **Define `GraphAction`**: Create a `Literal` type in `src/agents/state.py` that includes all valid values from `ActionType`, `SelectionStatus`, and node literals.
2.  **Update `AgentState`**: Change `last_action: str` to `last_action: GraphAction`.
3.  **Refactor Nodes**: Update all nodes to return values consistent with this type (using constants where possible, or `.value` from Enums).
4.  **Refactor Router**: Update `src/agents/nutritionist.py` to use these constants instead of raw strings.

## Feature Metadata

**Feature Type**: Refactor
**Estimated Complexity**: Low
**Primary Systems Affected**: 
- `src/agents/state.py`
- `src/agents/nutritionist.py` (Router)
- All Node implementations (`input_node`, `selection_node`, `calculate_log_node`)
**Dependencies**: Python `typing` module

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/agents/state.py` (lines 61) - Why: Current `last_action: str` definition to change.
- `src/schemas/input_schema.py` (lines 8-12) - Why: Source of `ActionType` values (`LOG_FOOD`, etc.).
- `src/schemas/selection_schema.py` (lines 7-10) - Why: Source of `SelectionStatus` values (`SELECTED`, etc.).
- `src/agents/nodes/calculate_log_node.py` (line 26) - Why: Source of literal `"LOGGED"`.
- `src/agents/nutritionist.py` (lines 33, 42) - Why: Router logic using raw strings.

### New Files to Create

None. Refactoring existing files.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [Python Literal Types](https://docs.python.org/3/library/typing.html#typing.Literal)
  - Why: We will use `Literal` to define the valid set of strings.

### Patterns to Follow

**Type Definition Pattern:**
```python
# src/agents/state.py
from typing import Literal

# Unified definition of all possible actions
GraphAction = Literal[
    "LOG_FOOD",
    "QUERY_FOOD_INFO",
    "QUERY_DAILY_STATS",
    "CHITCHAT",
    "SELECTED",
    "NO_MATCH",
    "AMBIGUOUS",
    "LOGGED",
    "ERROR"
]

class AgentState(TypedDict):
    # ...
    last_action: GraphAction  # ✅ Type-safe
```

**Router Pattern:**
```python
# src/agents/nutritionist.py
# (We can continue using strings if they match the Literal, or import constants if we define them)
if action == "LOG_FOOD":  # Type checker will validate this against GraphAction
    return "food_search"
```

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation - Type Definition

**Goal**: Establish the `GraphAction` type in `state.py`.

**Tasks**:
- Define `GraphAction` Literal in `src/agents/state.py`.
- Update `AgentState` type definition.

### Phase 2: Refactor Nodes

**Goal**: Ensure all nodes return valid `GraphAction` values.

**Tasks**:
- Verify `input_node.py` returns `action.value` (already does, just verify compatibility).
- Verify `selection_node.py` returns `status.value` (already does).
- Update `calculate_log_node.py` to use a constant or explicit string that matches the Literal.

### Phase 3: Integration - Router Update

**Goal**: Ensure graph routing uses the new type definition for validation (if using mypy) and consistency.

**Tasks**:
- Review `src/agents/nutritionist.py` conditional logic.
- (Optional) Replace string literals with constants if we decide to define them, otherwise relying on Literal type checking is sufficient for this phase.

### Phase 4: Testing & Validation

**Goal**: Verify no regressions.

**Tasks**:
- Run existing tests.
- Add a static analysis check (mypy) if possible to verify the benefits.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### UPDATE `src/agents/state.py`

- **IMPLEMENT**: Add `GraphAction` Literal and update `AgentState`.
- **IMPORTS**: `from typing import Literal`.
- **VALUES**: Include all values from `ActionType` and `SelectionStatus` + "LOGGED".
- **GOTCHA**: Ensure explicit list matches all utilized strings in the codebase.
- **VALIDATE**: `uv run ruff check src/agents/state.py`

### UPDATE `src/agents/nodes/calculate_log_node.py`

- **IMPLEMENT**: No change needed IF the string "LOGGED" is in the Literal. Just ensure it matches.
- **OPTIONAL**: Define `LOGGED_ACTION = "LOGGED"` constant in `state.py` and use it here for extra safety. *Decision: Let's stick to Literal matching for simplicity for now.*
- **VALIDATE**: `uv run python -c "from src.agents.nodes.calculate_log_node import calculate_log_node; print('Node OK')"`

### VERIFY `src/agents/nutritionist.py`

- **IMPLEMENT**: No code change required if strings match, but good to review.
- **VALIDATE**: `uv run python src/agents/nutritionist.py` (Graph compilation check).

### MANUAL VALIDATION

- **CHECK**: Run a quick validation script to ensure all Enums match the Literal.
- **SCRIPT**:
  ```python
  from src.schemas.input_schema import ActionType
  from src.schemas.selection_schema import SelectionStatus
  from src.agents.state import GraphAction
  
  # Get Literal values
  # Note: Accessing __args__ of Literal is runtime introspection
  from typing import get_args
  valid_actions = get_args(GraphAction)
  
  for a in ActionType:
      assert a.value in valid_actions, f"Missing {a.value} in GraphAction"
      
  for s in SelectionStatus:
      assert s.value in valid_actions, f"Missing {s.value} in GraphAction"
      
  assert "LOGGED" in valid_actions
  print("✅ GraphAction Literal covers all required states")
  ```
- **VALIDATE**: Run this script via `uv run python`.

---

## TESTING STRATEGY

### Unit Tests

- `tests/unit/test_state_consistency.py`: Create this test file using the validation script logic above to ensure future schema changes don't break `GraphAction`.

### Integration Tests

- Existing flow tests should pass without modification, as we are changing types, not runtime values.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
uv run ruff check src/agents/state.py
```

### Level 2: Unit Tests

```bash
# Create and run the consistency test
uv run pytest tests/unit/test_state_consistency.py
```

### Level 3: Integration Tests

```bash
uv run pytest tests/ -v
```

---

## ACCEPTANCE CRITERIA

- [ ] `AgentState.last_action` uses `GraphAction` Literal type.
- [ ] `GraphAction` includes all values from `ActionType` and `SelectionStatus` + "LOGGED".
- [ ] New unit test `test_state_consistency.py` verifies synchronization between Enums and Literal.
- [ ] All existing tests pass.

---

## COMPLETION CHECKLIST

- [ ] `src/agents/state.py` updated
- [ ] Consistency test created and passed
- [ ] Full regression suite passed
