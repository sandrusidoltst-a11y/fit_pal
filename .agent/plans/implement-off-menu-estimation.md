# Feature: Off-Menu Estimation and HITL Logging

## Feature Description
The current system drops food items that return no matches from the local SQLite database. This creates friction when users eat custom meals or branded foods not in the DB. This feature implements an "Off-Menu" estimation using the LLM to guess the macros of unknown foods, and introduces a Human-in-The-Loop (HITL) conversational confirmation flow. Following "Option A", known foods in a multi-item meal will be logged immediately, while unknown foods will pause the ingestion loop and ask the user for confirmation via conversational chat.

## User Story
As a disciplined tracker
I want to log off-menu or complex foods (like "Zinger Burger")
So that I can maintain my daily totals even if the food isn't in the database, without breaking my tracking streak.

## Problem Statement
When `food_search_node` returns 0 results, the `selection_node` skips the item, marks it as `FAILED`, and the user's daily totals miss the requested food.

## Solution Statement
Modify the `selection_node` to use the LLM for macro estimation when 0 search results are found, returning an `ESTIMATED` status. The graph will then route to the `response_node` to ask the user for confirmation, leaving the item in `pending_food_items` and storing the estimation in `current_estimation`. When the user replies "yes" or "log it", the `input_parser_node` will output a new action `CONFIRM_ESTIMATION`, which routes directly to `calculate_log_node` to save the item to the database using the estimated values with a `null` `food_id`.

## Feature Metadata

**Feature Type**: Enhancement
**Estimated Complexity**: Medium
**Primary Systems Affected**: State Schema, Graph Routing, Selection Node, Calculate Node, Input Node, Response Node
**Dependencies**: None

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!
- `src/schemas/selection_schema.py` - Why: Needs new `ESTIMATED` enum and fields for estimated float properties.
- `src/agents/state.py` - Why: Target for new GraphAction literals (`ESTIMATED`, `CONFIRM_ESTIMATION`, `REJECT_ESTIMATION`) and `current_estimation` state field.
- `src/agents/nodes/selection_node.py` - Why: Needs to stop returning NO_MATCH by default on 0 results, and instead invoke the LLM for estimation.
- `src/agents/nutritionist.py` - Why: Graph routing rules must accommodate `ESTIMATED` routing to `response` and `CONFIRM_ESTIMATION` routing to `calculate_log`.
- `src/agents/nodes/calculate_log_node.py` - Why: Needs logic to accept estimated macros directly from state rather than calling the `calculate_food_macros` tool when `selected_food_id` is None.
- `prompts/agent_selection.md` - Why: Must instruct the LLM on how to estimate macros when lists are empty.
- `prompts/input_parser.md` - Why: Needs instructions to detect conversational confirmations of estimations.

### Patterns to Follow
**TypedDict State Pattern:** Update `AgentState` carefully. Ensure `current_estimation` uses a TypedDict or is suitably typed.
**(Tool) Write-Through Pattern:** Continue using `daily_log_service.create_log_entry`, passing the estimated floats directly. `food_id` can be Null/None in the DB for custom items.
**Multiple Schemas:** Maintain existing cleanly separate Pydantic output schemas and TypedDict state structures. 

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (Schemas & State)
**Tasks:**
- Add `ESTIMATED` to `SelectionStatus` enum.
- Add optional estimated fields (calories, protein, carbs, fat) to `FoodSelectionResult`.
- Update `GraphAction` in `AgentState` with `"ESTIMATED"`, `"CONFIRM_ESTIMATION"`, `"REJECT_ESTIMATION"`.
- Add `current_estimation: Optional[dict]` to `AgentState` to hold the pending macros while asking the user.

### Phase 2: Estimation Logic (Selection Node)
**Tasks:**
- Update `agent_selection.md` prompt: instruct it that if `Search results` is empty, it MUST estimate the macros based on the user's original text amount and type, returning the `ESTIMATED` status and fields.
- Modify `selection_node.py`: Remove the hardcoded `if not search_results: FAILED` block. Let 0-result cases go to the LLM. 
- Map the LLM's `ESTIMATED` result into a new state update assigning `current_estimation: {"calories": result.estimated_calories, ...}` and `last_action: "ESTIMATED"`.

### Phase 3: Conversational HITL & Graph Routing (Nutritionist & Parser)
**Tasks:**
- Update `src/agents/nutritionist.py`:
  - `route_after_selection`: If `action == "ESTIMATED"`, route to `response` (pause loop to ask user).
  - `route_parser`: If `action == "CONFIRM_ESTIMATION"`, route to `calculate_log`. If `REJECT_ESTIMATION`, route to `response` (or perhaps a cleanup node).
- Update `prompts/input_parser.md`: Add rules to detect "Yes" / "Do it" (Confirmation) and "No" / "Cancel" (Rejection) of previous estimations.
- Update `input_node.py`: Ensure it populates `last_action` with `CONFIRM_ESTIMATION` or `REJECT_ESTIMATION` based on user intent.
- Ensure `input_parser_node` manages state cleanup if REJECTED (e.g., popping the `pending_food_items[0]` and clearing `current_estimation`).

### Phase 4: Persistence (Calculate Log)
**Tasks:**
- Update `calculate_log_node.py`:
  - Add logic branch for `selected_food_id` is None BUT `current_estimation` exists.
  - Read macros from `current_estimation` rather than calling the API.
  - Call `daily_log_service.create_log_entry` with `food_id=None`.
  - Clear `current_estimation` (set to `None`) after logging.
  - Update `processing_results` with success message stating "Logged Off-Menu item...".

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### UPDATE src/schemas/selection_schema.py
- **IMPLEMENT**: Add `ESTIMATED = "ESTIMATED"` to `SelectionStatus` enum.
- **IMPLEMENT**: Add `estimated_calories`, `estimated_protein`, `estimated_carbs`, `estimated_fat` as `Optional[float] = None` to `FoodSelectionResult`.
- **VALIDATE**: `uv run python scripts/quick_validate.py` (or format check to ensure schema parses).

### UPDATE src/agents/state.py
- **IMPLEMENT**: Add `"ESTIMATED"`, `"CONFIRM_ESTIMATION"`, `"REJECT_ESTIMATION"` to `GraphAction` Literal.
- **IMPLEMENT**: Add `current_estimation: Optional[dict]` to `AgentState`.
- **VALIDATE**: `uv run pytest tests/unit/test_state_consistency.py` (or typecheck).

### UPDATE prompts/agent_selection.md
- **IMPLEMENT**: Instruct LLM to estimate macros and return `ESTIMATED` with values if no valid search results are available, calculating based on standard nutritional knowledge for the requested amount.
- **VALIDATE**: Read output file to confirm instructions.

### UPDATE src/agents/nodes/selection_node.py
- **IMPLEMENT**: Remove quick-fail for `not search_results`. Allow it to invoke LLM, and if result is `ESTIMATED`, return `last_action: "ESTIMATED"` and save the estimated dict to `current_estimation`.
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py` or run `pytest` generally.

### UPDATE src/agents/nutritionist.py
- **IMPLEMENT**: Update `route_after_selection` to return `response` on `ESTIMATED`. Update `route_parser` to return `calculate_log` on `CONFIRM_ESTIMATION`, and `response` on `REJECT_ESTIMATION` (or handle rejection in the parser and just route to response).
- **VALIDATE**: `uv run pytest` to ensure graph definition works.

### UPDATE prompts/input_parser.md & src/schemas/input_schema.py
- **IMPLEMENT**: Add logic to parser schemas and prompts to identify `CONFIRM_ESTIMATION` and `REJECT_ESTIMATION`.
- **VALIDATE**: tests.

### UPDATE src/agents/nodes/input_node.py
- **IMPLEMENT**: If action is `REJECT_ESTIMATION`, remove the top item from `pending_food_items` and clear `current_estimation` so the graph can move on, or inform user.

### UPDATE src/agents/nodes/calculate_log_node.py
- **IMPLEMENT**: Check if `current_estimation` is populated and `selected_food_id` is missing. If so, pull macros from `current_estimation`, set `food_id=None`, log it, and clear `current_estimation`.
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_log_node.py`

### UPDATE prompts/response_generator.md
- **IMPLEMENT**: Inform LLM to ask user for confirmation if `last_action` is `ESTIMATED`.

---

## TESTING STRATEGY

### Unit Tests
- Create or update mocks in `test_calculate_log_node.py` to ensure it can persist `food_id=None` with estimated macros from state.
- Update `test_agent_selection.py` to test the 0-result edge case resolving to `ESTIMATED` status.

### Integration Tests
- Run full LangGraph simulated flow: input unknown food -> selection estimates -> response asks -> input confirm -> calculate logs it.

### Edge Cases
- User says "No" to the estimation. The pending item should be dropped without crashing the remaining items loop.
- User says "Yes, but it's 300 kcal". (Advanced fallback for later, but for now ensure it either logs or rejects nicely).
- Multi-item: "2 eggs and mom's pie". Eggs log, pie stalls, asks user. User says Yes. Pie logs.

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
`uv run ruff check .`
`uv run ruff format .`

### Level 2: Unit Tests
`uv run pytest tests/ -v`

---

## COMPLETION CHECKLIST

- [ ] All schemas updated for ESTIMATED enums and floats.
- [ ] Graph routes updated to handle HITL suspension.
- [ ] DB Logging logic accepts null food_id and overrides macro calculations with state estimates.
- [ ] Unit tests updated to verify 0-search edge case logic.
- [ ] Full text-based flow validated in LangSmith Studio or test script.

---

## NOTES
Keeping Option A guarantees the least friction for complex meals. Be careful with state mutation inside `input_parser_node` when handling Rejection; if `pending_food_items` is not advanced, it will loop infinitely.
