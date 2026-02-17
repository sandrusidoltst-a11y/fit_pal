# Commit: Multi-Item Feedback with Structured State

## Overview
This commit implements a robust feedback mechanism for handling multiple food items in a single turn. It transitions the agent from using simple string-based "last_action" status to a structured `ProcessingResult` list within the state, allowing for detailed per-item tracking (success/failure) and comprehensive summary generation.

## Key Changes
- **State Schema (`src/agents/state.py`)**:
    - Defined `ProcessingResult` TypedDict inheriting from `PendingFoodItem`.
    - Added `processing_results: List[ProcessingResult]` to `AgentState`.
- **Logic Nodes**:
    - **Input Node (`input_node.py`)**: Resets `processing_results` at the start of each turn.
    - **Calculate Node (`calculate_log_node.py`)**: Appends successful `LOGGED` results to the state list. Fixed a bug where a Tool was called incorrectly; updated to use `.invoke()`.
    - **Selection Node (`selection_node.py`)**: Detects and records `FAILED` results for empty searches, AMBIGUOUS results, or missing IDs.
- **Response Node (`nutritionist.py`)**: Refactored to generate a consolidated summary message by iterating over all accumulated `processing_results`.
- **Testing**:
    - Added `tests/unit/test_feedback_logic.py` to verify state accumulation logic.
    - Added `tests/unit/test_feedback_integration.py` to verify the full graph flow from input to response summary.
    - Updated existing tests (`test_calculate_log_node.py`) to match new state structure and tool invocation patterns.

## Next Steps
- **Refine Error Messages**: Make the failure messages more user-friendly and actionable (e.g., suggesting similar items).
- **Ambiguity Handling**: Implement the logic to handle `AMBIGUOUS` results by asking the user for clarification instead of just failing.
- **Frontend Integration**: Ensure the frontend can display these structured summaries effectively (if applicable).
