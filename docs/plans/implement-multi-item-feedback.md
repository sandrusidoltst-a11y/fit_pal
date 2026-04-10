# Feature: Implement Multi-Item Feedback Response with Structured Types

## Feature Description
Implement a robust feedback mechanism for the FitPal agent to accurately report the status of multiple food items processed in a single turn. This design replaces simple strings with a **structured TypedDict inheritance pattern** to ensure deep type safety and rich context preservation (e.g., maintaining original input text, specific error details) throughout the processing loop.

## User Story
**As a** user logging multiple food items (e.g., "Egg and Toast"),
**I want** the agent to confirm **both** items were logged with specific details,
**So that** I trust my nutrition tracking is accurate and complete.

## Problem Statement
The current state architecture only tracks `last_action`. In a multi-item loop, the agent processes Item A, updates `last_action`, then processes Item B, overwriting `last_action`. The final response node only sees the result of Item B, which is confusing and feels like data loss to the user.

## Solution Statement
1.  **State Upgrade**: create `ProcessingResult(PendingFoodItem)` which inherits all original fields and adds `status` (Literal) and `message`.
2.  **State Field**: Add `processing_results: List[ProcessingResult]` to `AgentState`.
3.  **Accumulation**: Processing nodes (`calculate_log`, `agent_selection`) will append fully structured result objects to this list.
4.  **Reporting**: Refactor `response_node` to parse these objects and generate a comprehensive summary.

## Feature Metadata
**Feature Type**: Enhancement & Refactor
**Estimated Complexity**: Medium (due to type changes)
**Primary Systems Affected**: State, Logic Nodes (Calc/Selection), Response Node
**Dependencies**: None

---

## CONTEXT REFERENCES

### Relevant Codebase Files
- `src/agents/state.py` (lines 7-18) - **Pattern**: PendingFoodItem definition to inherit from.
- `src/agents/state.py` (lines 57-77) - **Target**: Add `processing_results` field to `AgentState`.
- `src/agents/nodes/input_node.py` (lines 10-47) - **Target**: Reset logic.
- `src/agents/nodes/calculate_log_node.py` (lines 37-64) - **Target**: Create structured success result.
- `src/agents/nodes/selection_node.py` (lines 28-70) - **Target**: Create structured failure result.

### New Files to Create
- `tests/unit/test_feedback_logic.py` - Unit tests for the new response aggregation logic.

### Patterns to Follow
- **TypedDict Inheritance**: `class Child(Parent):` to extend TypedDicts.
- **Manual State Reducer**: Append new items to list manually: `existing_list + [new_item]`.
- **Structured Data**: Prefer dictionaries over strings for internal state.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (Type Definitions)
Define the `ProcessingResult` TypedDict and update the `AgentState` to use it.

### Phase 2: Logic Updates (Data Capture)
Update logic nodes to construct and append `ProcessingResult` objects instead of just returning actions.

### Phase 3: Response Generation (Presentation)
Rewrite `response_node` to consume the structured data and formatting it into a user-friendly string.

### Phase 4: Validation
Verify multi-item flows work as expected through unit tests.

---

## STEP-BY-STEP TASKS

### 1. Define ProcessingResult Schema
*   **UPDATE** `src/agents/state.py`
    *   **IMPLEMENT**: Define `class ProcessingResult(PendingFoodItem):`.
    *   **FIELDS**: Add `status: Literal["LOGGED", "FAILED"]` and `message: str`.
    *   **UPDATE**: Add `processing_results: List[ProcessingResult]` to `AgentState`.
    *   **IMPORTS**: Ensure `Literal` and `List` are available.

### 2. Initialize State in Input Node
*   **UPDATE** `src/agents/nodes/input_node.py`
    *   **IMPLEMENT**: In `input_parser_node`, include `"processing_results": []` in the return dictionary.
    *   **Why**: Clears history from previous turns.

### 3. Capture Success in Calculate Node
*   **UPDATE** `src/agents/nodes/calculate_log_node.py`
    *   **IMPLEMENT**: Construct `ProcessingResult` object:
        ```python
        result_item = {
            **current_item,
            "status": "LOGGED",
            "message": f"Logged {current_item['food_name']} ({macros['calories']}kcal)"
        }
        ```
    *   **IMPLEMENT**: Retrieve existing `state.get("processing_results", [])`.
    *   **RETURN**: `{"processing_results": existing_results + [result_item]}`.

### 4. Capture Failure in Selection Node
*   **UPDATE** `src/agents/nodes/selection_node.py`
    *   **IMPLEMENT**: Locate `NO_MATCH` paths.
    *   **IMPLEMENT**: Construct `ProcessingResult` object:
        ```python
        result_item = {
            **current_item,
            "status": "FAILED",
            "message": f"Could not find match for {current_item['food_name']}"
        }
        ```
    *   **RETURN**: `{"processing_results": existing_results + [result_item]}`.

### 5. Create Feedback Logic Tests
*   **CREATE** `tests/unit/test_feedback_logic.py`
    *   **IMPLEMENT**: Test case with mixed results (1 success, 1 failure).
    *   **IMPLEMENT**: Verify `AgentState` structure holds rich data.
    *   **VALIDATE**: `uv run pytest tests/unit/test_feedback_logic.py` (Expected fail).

### 6. Implement Response Node Aggregation
*   **UPDATE** `src/agents/nutritionist.py`
    *   **IMPLEMENT**: Rewrite `response_node`.
    *   **LOGIC**:
        *   Get `processing_results`.
        *   If present, join `[r['message'] for r in processing_results]`.
        *   Return `{"messages": [summary_string]}`.
    *   **VALIDATE**: `uv run pytest tests/unit/test_feedback_logic.py`

### 7. Integration Verification
*   **UPDATE** `tests/unit/test_state_consistency.py` (if needed) to account for new state field.
*   **VALIDATE**: `uv run pytest`

---

## TESTING STRATEGY

### Unit Tests
*   **`test_feedback_logic.py`**:
    *   **Test**: `response_node` correctly formats a mix of LOGGED and FAILED items.
    *   **Test**: `AgentState` type integrity (ensure inheritance fields like `original_text` are present).

---

## VALIDATION COMMANDS

### Level 1: Syntax
`uv run ruff check src tests`

### Level 2: Unit Tests
`uv run pytest tests/unit/test_feedback_logic.py`

### Level 3: Full Suite
`uv run pytest`

---

## ACCEPTANCE CRITERIA
- [ ] `AgentState` uses `ProcessingResult` (TypedDict inheritance).
- [ ] `input_parser_node` resets results.
- [ ] Logic nodes appends full structured objects, preserving original text.
- [ ] Response node formats clear summaries from the structured list.
- [ ] All tests pass.
