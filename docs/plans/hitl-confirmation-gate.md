# Feature: HITL Confirmation Gate for Food Logging

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Redesign the off-menu food handling by introducing a **Human-in-the-Loop (HITL) Confirmation Gate** using LangGraph's native `interrupt()` primitive. Before any food item (from DB or estimated) is saved to the database, the graph pauses execution using `interrupt()`, presents the calculated macros to the user, and waits for approval via `Command(resume=...)`.

This replaces the failed approach from PR #10 which used hand-rolled state machine routing with `ESTIMATED`/`CONFIRM_ESTIMATION`/`REJECT_ESTIMATION` actions.

## User Story

As a user logging my food intake
I want to see the exact macros the agent will log before it saves them to the database
So that I can verify accuracy and catch errors, especially for foods not found in the database

## Problem Statement

The current food logging pipeline (`calculate_log_node`) couples macro calculation with DB persistence in a single node. There is no user verification step before data hits the database. When food items are not found in the DB, there is no mechanism to estimate macros using LLM knowledge with user awareness.

The previous attempt (PR #10) to solve this used a brittle hand-rolled state machine that:
- Caused Studio crashes due to non-standard graph patterns
- Scattered HITL logic across 5+ files
- Had no test coverage for the pause/resume lifecycle

## Solution Statement

1. **Split `calculate_log_node`** into `calculate_macros_node` (pure calculation) + `log_to_db_node` (DB write)
2. **Insert `confirmation_node`** between them, using LangGraph's `interrupt()` to pause the graph
3. **Add off-menu estimation** in `calculate_macros_node` — when `selected_food_id` is None (NO_MATCH), use LLM to estimate macros
4. **Tag every item with `source: "database" | "estimated"`** for transparency
5. **User approves or rejects** via `Command(resume={"approved": True/False})`

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High
**Primary Systems Affected**: `src/agents/nodes/`, `src/agents/state.py`, `src/agents/nutritionist.py`, `tests/`
**Dependencies**: `langgraph.types.interrupt`, `langgraph.types.Command` (already in langgraph package)

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/agents/nodes/calculate_log_node.py` (lines 1-102) - Why: WILL BE DELETED. Understand what it does so the split preserves all behavior. Key: macro calculation (lines 29-33), DB write (lines 50-61), report fetch (lines 64-79), result accumulation (lines 82-90), pending item removal (lines 92-93).
- `src/agents/state.py` (lines 1-125) - Why: State schema changes. Must add `MacroResult` TypedDict, `pending_confirmation` field. Must update `GraphAction` literals.
- `src/agents/nutritionist.py` (lines 1-85) - Why: Graph definition. Must add 3 new nodes, remove 1, update edges. Critical: routing functions (lines 17-38), edge definitions (lines 49-77).
- `src/agents/nodes/selection_node.py` (lines 1-108) - Why: NO_MATCH handling (lines 23-39). Off-menu items flow through here — `last_action: "NO_MATCH"` triggers the estimation path in `calculate_macros_node`.
- `src/agents/nodes/food_search_node.py` (lines 1-25) - Why: Upstream node — no changes needed, but understand the flow.
- `src/agents/nodes/response_node.py` - Why: Downstream node — may need to handle REJECTED action context.
- `src/tools/food_lookup.py` (lines 22-46) - Why: `calculate_food_macros` tool — used by `calculate_macros_node` for DB items.
- `src/schemas/input_schema.py` (lines 1-44) - Why: `ActionType` enum — must stay in sync with `GraphAction`.
- `src/schemas/selection_schema.py` (lines 1-21) - Why: `SelectionStatus` enum — must stay in sync with `GraphAction`.
- `src/config.py` (lines 21-53) - Why: `NODE_CONFIGS` — must add config for new estimation node.
- `src/database.py` (lines 1-29) - Why: `get_async_db_session` — used by `log_to_db_node`.
- `src/services/daily_log_service.py` - Why: `create_log_entry`, `get_logs_by_date` — used by `log_to_db_node`.
- `langgraph.json` (lines 1-8) - Why: Studio graph config — references `define_graph`. No change needed but verify compatibility.
- `tests/conftest.py` - Why: Shared fixtures. After Phase A, this has the mock fixtures we'll reuse.
- `tests/unit/test_calculate_log_node.py` - Why: WILL BE DELETED/REPLACED with new test files.
- `tests/unit/test_multi_item_loop.py` - Why: Tests multi-item processing. Must be updated for new node names.
- `tests/unit/test_feedback_integration.py` - Why: Graph-level flow test. Must be updated for new graph shape.
- `tests/unit/test_feedback_logic.py` - Why: Tests processing results. Must be updated for new node names.
- `tests/unit/test_state_consistency.py` - Why: Validates GraphAction literals. Must be updated for new actions.
- `.agent/reference/test-strategy.md` - Why: Test rules. Follow mock boundaries when writing new tests.

### New Files to Create

- `src/agents/nodes/calculate_macros_node.py` - Pure macro calculation (DB lookup OR LLM estimation)
- `src/agents/nodes/confirmation_node.py` - HITL interrupt node
- `src/agents/nodes/log_to_db_node.py` - DB write after confirmation
- `prompts/macro_estimation.md` - Prompt for LLM macro estimation (off-menu items)
- `tests/unit/test_calculate_macros_node.py` - Unit tests for macro calculation
- `tests/unit/test_confirmation_node.py` - Unit tests for interrupt payload
- `tests/unit/test_log_to_db_node.py` - Unit tests for DB write
- `tests/integration/test_hitl_lifecycle.py` - Full HITL interrupt→resume test

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LangGraph Interrupts (Python)](https://docs.langchain.com/oss/python/langgraph/interrupts)
  - Section: "Pause using interrupt" — shows `from langgraph.types import interrupt` pattern
  - Section: "Resuming interrupts" — shows `Command(resume=...)` pattern
  - Section: "Approve or reject" — shows `Command[Literal["proceed", "cancel"]]` return type
  - Section: "Rules of interrupts" — CRITICAL: don't wrap in try/except, side effects must be idempotent
  - Why: This is the EXACT API we're implementing
- [LangGraph Types Reference - interrupt](https://reference.langchain.com/python/langgraph/types/interrupt)
  - Why: Function signature and parameters

### Patterns to Follow

**Node Signature Pattern** (from existing nodes):
```python
async def node_name(state: AgentState) -> dict:
    """Docstring."""
    # ... logic ...
    return {"key": value}
```

**Command Return Pattern** (from LangGraph docs):
```python
from langgraph.types import interrupt, Command
from typing import Literal

def confirmation_node(state: AgentState) -> Command[Literal["log_to_db", "response"]]:
    decision = interrupt(payload)
    if decision.get("approved"):
        return Command(goto="log_to_db", update={"last_action": "CONFIRMED"})
    else:
        return Command(goto="response", update={"last_action": "REJECTED"})
```

**Routing Function Pattern** (from `nutritionist.py` lines 17-38):
```python
def route_after_X(state: AgentState):
    action = state.get("last_action")
    if action == "X":
        return "next_node"
    return "fallback_node"
```

**Processing Result Accumulation Pattern** (from `calculate_log_node.py` lines 82-90):
```python
result_item = {**current_item, "status": "LOGGED", "message": "..."}
current_results = state.get("processing_results", [])
updated_results = current_results + [result_item]
```

**Error Handling Pattern**: Nodes return state updates, never raise. Errors are captured in `processing_results` as `"status": "FAILED"`.

**Naming Conventions:**
- Nodes: `snake_case_node` (e.g., `calculate_macros_node`)
- Graph node IDs: `snake_case` without `_node` suffix (e.g., `"calculate_macros"`)
- State fields: `snake_case` (e.g., `pending_confirmation`)

---

## IMPLEMENTATION PLAN

### Phase 1: State Schema Changes

Update `AgentState` with new types and fields for the confirmation flow.

### Phase 2: Create New Nodes (calculate_macros, confirmation, log_to_db)

Implement the three nodes that replace `calculate_log_node`.

### Phase 3: Create Estimation Prompt

Add the LLM prompt for off-menu macro estimation.

### Phase 4: Update Graph Definition

Rewire `nutritionist.py` with new nodes and edges.

### Phase 5: Update Config

Add LLM config for the estimation node.

### Phase 6: Update Existing Tests

Update tests that reference old node names/actions.

### Phase 7: Write New Tests

Create unit and integration tests for the new nodes and HITL lifecycle.

### Phase 8: Update Documentation

Update PRD, main_rule, test-strategy.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Task 1: UPDATE `src/agents/state.py` — Add MacroResult and update GraphAction

- **IMPLEMENT**:
  1. Add `MacroResult` TypedDict class:
     ```python
     class MacroResult(TypedDict):
         """Calculated macros for a single food item, pending user confirmation."""
         food_name: str
         amount_g: float
         calories: float
         protein: float
         carbs: float
         fat: float
         source: Literal["database", "estimated"]
         original_text: str
         food_id: Optional[int]  # None if estimated
     ```
  2. Update `GraphAction` to add `"AWAITING_CONFIRMATION"`, `"CONFIRMED"`, `"REJECTED"` — remove nothing from current literals (they're still used).
  3. Add `pending_confirmation: Optional[MacroResult]` field to `AgentState` (above `processing_results`).
  4. Update `ProcessingResult` to add optional `source` field: `source: Optional[Literal["database", "estimated"]]`
- **IMPORTS**: No new imports needed, `Literal` and `Optional` already imported.
- **VALIDATE**: `uv run pytest tests/unit/test_state_consistency.py -v` — passes (new actions are additive)

### Task 2: CREATE `prompts/macro_estimation.md` — Off-menu estimation prompt

- **IMPLEMENT**: Create the LLM prompt for estimating macros when food is not in the database:
  ```markdown
  # Macro Estimation Prompt

  You are a nutrition expert. The user mentioned a food item that is NOT in our verified database.
  Your job is to estimate the nutritional values based on your knowledge.

  ## Rules
  1. Provide your BEST estimate for the given food and amount.
  2. Use standard USDA/nutrition reference values when available.
  3. Round all values to 1 decimal place.
  4. If the food name is ambiguous, assume the most common variety.
  5. All amounts are in grams. If the user said "1 cup" or "1 piece", the amount in grams has already been estimated for you.

  ## Output Format
  Return your estimation as structured data with: calories, protein, carbs, fat (all per the given amount in grams).
  ```
- **VALIDATE**: File exists at `prompts/macro_estimation.md`

### Task 3: CREATE `src/agents/nodes/calculate_macros_node.py`

- **IMPLEMENT**: Pure macro calculation node. Two paths:
  1. **DB path** (when `selected_food_id` is not None): Call `calculate_food_macros.invoke()` tool, build `MacroResult` with `source="database"`
  2. **Estimation path** (when `selected_food_id` is None AND `last_action == "NO_MATCH"`): Call LLM with `macro_estimation.md` prompt, build `MacroResult` with `source="estimated"`

  ```python
  import os
  from src.agents.state import AgentState, MacroResult
  from src.config import get_llm_for_node
  from src.tools.food_lookup import calculate_food_macros
  from src.schemas.estimation_schema import MacroEstimation
  from langchain_core.messages import HumanMessage, SystemMessage

  async def calculate_macros_node(state: AgentState) -> dict:
      """Calculate macros for the current food item.

      Two paths:
      1. DB match (selected_food_id exists): Use calculate_food_macros tool
      2. Off-menu (selected_food_id is None): Use LLM estimation
      """
      pending_items = state.get("pending_food_items", [])
      selected_food_id = state.get("selected_food_id")

      if not pending_items:
          return {}

      current_item = pending_items[0]
      amount = current_item.get("amount", 0.0)
      food_name = current_item.get("food_name", "")

      if selected_food_id:
          # DB path
          macros = calculate_food_macros.invoke({"food_id": selected_food_id, "amount_g": amount})
          if "error" in macros:
              # Failed to calculate — create failed result, skip confirmation
              result_item = {
                  **current_item,
                  "status": "FAILED",
                  "message": f"Could not calculate macros for {food_name}: {macros['error']}"
              }
              remaining = pending_items[1:]
              return {
                  "pending_food_items": remaining,
                  "processing_results": state.get("processing_results", []) + [result_item],
                  "last_action": "LOGGED",  # Continue to next item
                  "selected_food_id": None,
                  "pending_confirmation": None,
              }

          macro_result: MacroResult = {
              "food_name": food_name,
              "amount_g": amount,
              "calories": macros["calories"],
              "protein": macros["protein"],
              "carbs": macros["carbs"],
              "fat": macros["fat"],
              "source": "database",
              "original_text": current_item.get("original_text", ""),
              "food_id": selected_food_id,
          }
      else:
          # Estimation path — use LLM
          macro_result = await _estimate_macros(food_name, amount, current_item.get("original_text", ""))

      return {
          "pending_confirmation": macro_result,
          "last_action": "AWAITING_CONFIRMATION",
      }


  async def _estimate_macros(food_name: str, amount_g: float, original_text: str) -> MacroResult:
      """Use LLM to estimate macros for an off-menu food item."""
      prompt_path = os.path.join(os.getcwd(), "prompts", "macro_estimation.md")
      try:
          with open(prompt_path, "r", encoding="utf-8") as f:
              system_prompt = f.read()
      except FileNotFoundError:
          system_prompt = "Estimate nutritional values for the given food item and amount."

      llm = get_llm_for_node("estimation_node")
      structured_llm = llm.with_structured_output(MacroEstimation)

      messages = [
          SystemMessage(content=system_prompt),
          HumanMessage(content=f"Estimate macros for: {food_name}, amount: {amount_g}g"),
      ]

      result = structured_llm.invoke(messages)

      return {
          "food_name": food_name,
          "amount_g": amount_g,
          "calories": result.calories,
          "protein": result.protein,
          "carbs": result.carbs,
          "fat": result.fat,
          "source": "estimated",
          "original_text": original_text,
          "food_id": None,
      }
  ```
- **GOTCHA**: The `_estimate_macros` function calls a real LLM. In unit tests, mock `get_llm_for_node("estimation_node")`.
- **VALIDATE**: File exists, no syntax errors: `uv run python -c "from src.agents.nodes.calculate_macros_node import calculate_macros_node"`

### Task 4: CREATE `src/schemas/estimation_schema.py`

- **IMPLEMENT**: Pydantic schema for LLM-estimated macro output:
  ```python
  from pydantic import BaseModel, Field

  class MacroEstimation(BaseModel):
      """Structured output for LLM macro estimation."""
      calories: float = Field(..., description="Estimated calories for the given amount")
      protein: float = Field(..., description="Estimated protein in grams")
      carbs: float = Field(..., description="Estimated carbohydrates in grams")
      fat: float = Field(..., description="Estimated fat in grams")
  ```
- **VALIDATE**: `uv run python -c "from src.schemas.estimation_schema import MacroEstimation; print(MacroEstimation(calories=100, protein=10, carbs=20, fat=5))"`

### Task 5: CREATE `src/agents/nodes/confirmation_node.py`

- **IMPLEMENT**: HITL interrupt node using `langgraph.types.interrupt`:
  ```python
  from typing import Literal
  from langgraph.types import interrupt, Command
  from src.agents.state import AgentState

  def confirmation_node(state: AgentState) -> Command[Literal["log_to_db", "response"]]:
      """Present calculated macros to user and await confirmation.

      Uses LangGraph's interrupt() to pause graph execution.
      Resumes when caller sends Command(resume={"approved": True/False}).
      """
      item = state.get("pending_confirmation")
      if not item:
          return Command(goto="response")

      # Build human-readable confirmation payload
      source_note = ""
      if item["source"] == "estimated":
          source_note = "⚠️ These macros were ESTIMATED by AI (not from our verified database)."

      payload = {
          "question": f"Confirm logging {item['food_name']} ({item['amount_g']}g)?",
          "macros": {
              "calories": item["calories"],
              "protein": item["protein"],
              "carbs": item["carbs"],
              "fat": item["fat"],
          },
          "source": item["source"],
          "note": source_note,
      }

      # PAUSE — graph state saved, Studio renders as a prompt
      decision = interrupt(payload)

      if decision.get("approved", False):
          return Command(goto="log_to_db", update={"last_action": "CONFIRMED"})
      else:
          # Reject: clear pending, add FAILED result, pop item from queue
          pending = state.get("pending_food_items", [])
          remaining = pending[1:] if pending else []
          reject_result = {
              **state.get("pending_food_items", [{}])[0],
              "status": "FAILED",
              "message": f"User rejected logging {item['food_name']}",
              "source": item.get("source"),
          }
          return Command(
              goto="response",
              update={
                  "last_action": "REJECTED",
                  "pending_confirmation": None,
                  "pending_food_items": remaining,
                  "processing_results": state.get("processing_results", []) + [reject_result],
              }
          )
  ```
- **GOTCHA**: `interrupt()` causes the node to re-execute from the top on resume. Any code before `interrupt()` runs twice. Since we only read state (no side effects), this is safe.
- **GOTCHA**: The `Command` return type annotation must list ALL possible target nodes: `Command[Literal["log_to_db", "response"]]`.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.confirmation_node import confirmation_node"`

### Task 6: CREATE `src/agents/nodes/log_to_db_node.py`

- **IMPLEMENT**: DB persistence node — only called after user confirms:
  ```python
  from datetime import datetime, timezone
  from src.agents.state import AgentState
  from src.database import get_async_db_session
  from src.services import daily_log_service

  async def log_to_db_node(state: AgentState) -> dict:
      """Write confirmed food item to the database.

      Only called after user confirms via confirmation_node.
      Reads macros from pending_confirmation state field.
      """
      item = state.get("pending_confirmation")
      pending_items = state.get("pending_food_items", [])

      if not item:
          return {}

      # Prepare timestamp
      consumed_at = state.get("consumed_at")
      now = datetime.now(timezone.utc)

      if consumed_at:
          if consumed_at.tzinfo is None:
              timestamp = consumed_at.replace(tzinfo=timezone.utc)
          else:
              timestamp = consumed_at
      else:
          timestamp = now

      async with get_async_db_session() as session:
          await daily_log_service.create_log_entry(
              session=session,
              food_id=item.get("food_id"),  # None for estimated items
              amount_g=item["amount_g"],
              calories=item["calories"],
              protein=item["protein"],
              carbs=item["carbs"],
              fat=item["fat"],
              timestamp=timestamp,
              original_text=item.get("original_text"),
          )

          # Fetch updated daily report
          updated_report = []
          if consumed_at:
              logs = await daily_log_service.get_logs_by_date(session, consumed_at.date())
              for log in logs:
                  updated_report.append({
                      "id": log.id,
                      "food_id": log.food_id,
                      "amount_g": log.amount_g,
                      "calories": log.calories,
                      "protein": log.protein,
                      "carbs": log.carbs,
                      "fat": log.fat,
                      "timestamp": log.timestamp,
                      "meal_type": log.meal_type,
                      "original_text": log.original_text,
                  })

      # Create success result
      result_item = {
          **(pending_items[0] if pending_items else {}),
          "status": "LOGGED",
          "message": f"Logged {item['food_name']} ({item['calories']}kcal)",
          "source": item.get("source"),
      }

      remaining = pending_items[1:] if pending_items else []
      current_results = state.get("processing_results", [])

      return {
          "pending_food_items": remaining,
          "daily_log_report": updated_report if updated_report else state.get("daily_log_report", []),
          "last_action": "LOGGED",
          "selected_food_id": None,
          "pending_confirmation": None,
          "processing_results": current_results + [result_item],
      }
  ```
- **GOTCHA**: `food_id` can be `None` for estimated items. The `daily_log_service.create_log_entry` must accept `None` for `food_id`. Check and update if needed.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.log_to_db_node import log_to_db_node"`

### Task 7: UPDATE `src/services/daily_log_service.py` — Allow nullable food_id

- **IMPLEMENT**: Check if `create_log_entry` accepts `food_id=None`. If the `DailyLog` model requires a non-null `food_id`, we need to update the model.
- **GOTCHA**: If `FoodItem` has a foreign key constraint, `food_id=None` will fail. Check `src/models.py` — if `food_id` is `Column(Integer, ForeignKey("food_items.id"))` without `nullable=True`, update it to `nullable=True`.
- **VALIDATE**: Run `uv run pytest tests/unit/test_daily_log_service.py -v` — still passes

### Task 8: UPDATE `src/config.py` — Add estimation_node config

- **IMPLEMENT**: Add `estimation_node` to `NODE_CONFIGS`:
  ```python
  NODE_CONFIGS = {
      "input_node": {"temperature": 0.0},
      "selection_node": {"temperature": 0.0},
      "estimation_node": {"temperature": 0.0},  # NEW
      "response_node": {"temperature": 0.7},
      "default": {"temperature": 0.0}
  }
  ```
- **VALIDATE**: `uv run python -c "from src.config import get_llm_for_node; llm = get_llm_for_node('estimation_node'); print('OK')"`

### Task 9: UPDATE `src/agents/nutritionist.py` — Rewire graph

- **IMPLEMENT**: Replace graph definition:
  1. Update imports: remove `calculate_log_node`, add `calculate_macros_node`, `confirmation_node`, `log_to_db_node`
  2. Replace nodes:
     - Remove: `workflow.add_node("calculate_log", calculate_log_node)`
     - Add: `workflow.add_node("calculate_macros", calculate_macros_node)`
     - Add: `workflow.add_node("confirmation", confirmation_node)`
     - Add: `workflow.add_node("log_to_db", log_to_db_node)`
  3. Update `route_after_selection`: `"SELECTED"` → `"calculate_macros"`, `"NO_MATCH"` → also `"calculate_macros"` (estimation path handles it)
  4. Update edges:
     - `"agent_selection"` → conditional → `calculate_macros` or `response`
     - `"calculate_macros"` → `"confirmation"` (direct edge)
     - `"confirmation"` uses `Command()` to route dynamically (no conditional edges needed — LangGraph uses the Command return)
     - `"log_to_db"` → conditional → `food_search` (more items) or `response` (done)
  5. Rename `route_after_calculate` to `route_after_log`

  **Updated routing:**
  ```python
  def route_after_selection(state: AgentState):
      action = state.get("last_action")
      if action in ["SELECTED", "NO_MATCH"]:
          return "calculate_macros"
      return "response"

  def route_after_log(state: AgentState):
      if state.get("pending_food_items", []):
          return "food_search"
      return "response"
  ```

  **Updated edges:**
  ```python
  workflow.add_conditional_edges("agent_selection", route_after_selection, {
      "calculate_macros": "calculate_macros",
      "response": "response",
  })
  workflow.add_edge("calculate_macros", "confirmation")
  # confirmation_node returns Command — no add_conditional_edges needed
  workflow.add_conditional_edges("log_to_db", route_after_log, {
      "food_search": "food_search",
      "response": "response",
  })
  ```

- **GOTCHA**: `confirmation_node` returns `Command[Literal["log_to_db", "response"]]`. LangGraph handles routing from Command nodes automatically. DO NOT add `add_conditional_edges` for the confirmation node.
- **GOTCHA**: The `route_after_selection` now sends BOTH `SELECTED` and `NO_MATCH` to `calculate_macros` (instead of `NO_MATCH` → `response`). This is because the `calculate_macros_node` handles both DB and estimation paths.
- **VALIDATE**: `uv run python -c "from src.agents.nutritionist import define_graph; import asyncio; asyncio.run(define_graph())"` — compiles without error

### Task 10: DELETE `src/agents/nodes/calculate_log_node.py`

- **IMPLEMENT**: Delete the file. Its functionality has been split into `calculate_macros_node.py`, `confirmation_node.py`, and `log_to_db_node.py`.
- **VALIDATE**: `uv run python -c "from src.agents.nutritionist import define_graph; import asyncio; asyncio.run(define_graph())"` — still compiles

### Task 11: UPDATE `src/agents/nodes/response_node.py` — Handle REJECTED context

- **IMPLEMENT**: Update `_build_context` to handle `REJECTED` and `CONFIRMED` actions the same way as `LOGGED` — include `processing_results` in context. This may already work if the function uses a catch-all for non-stats actions, but verify.
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v` — all tests pass

### Task 12: UPDATE `tests/unit/test_state_consistency.py` — Add new actions

- **IMPLEMENT**: Verify the test still passes with the updated `GraphAction`. The new literals (`AWAITING_CONFIRMATION`, `CONFIRMED`, `REJECTED`) are additive.
- **GOTCHA**: If the test checks exact count of `GraphAction` values, update the assertion.
- **VALIDATE**: `uv run pytest tests/unit/test_state_consistency.py -v` — passes

### Task 13: UPDATE `tests/unit/test_feedback_integration.py` — New graph shape

- **IMPLEMENT**: Update the graph-level flow test to use the new node structure:
  - Replace `mock_calc` (calculate_log_node) with mocks for `calculate_macros_node`, `confirmation_node`, `log_to_db_node`
  - Update the mock return values and import patches
  - The confirmation_node mock should return a `Command` object
- **GOTCHA**: Since `confirmation_node` uses `interrupt()` which requires a real checkpointer, the mock should return a `Command(goto="log_to_db")` directly, bypassing the interrupt.
- **VALIDATE**: `uv run pytest tests/unit/test_feedback_integration.py -v` — passes

### Task 14: CREATE `tests/unit/test_calculate_macros_node.py`

- **IMPLEMENT**: Unit tests for `calculate_macros_node`:
  1. `test_db_path_success` — mock `calculate_food_macros`, verify `MacroResult` with `source="database"`
  2. `test_db_path_error` — mock returns `{"error": "..."}`, verify FAILED result
  3. `test_estimation_path` — mock `get_llm_for_node`, verify `MacroResult` with `source="estimated"`
  4. `test_empty_pending_items` — returns `{}`
- **PATTERN**: Mock `calculate_food_macros.invoke()` and `get_llm_for_node("estimation_node")`
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_macros_node.py -v` — all tests pass

### Task 15: CREATE `tests/unit/test_confirmation_node.py`

- **IMPLEMENT**: Unit tests for `confirmation_node`:
  1. `test_no_pending_confirmation` — returns `Command(goto="response")` immediately
  2. `test_interrupt_payload_structure_db` — mock `interrupt()` to return immediately, verify payload has `source="database"` and no warning note
  3. `test_interrupt_payload_structure_estimated` — mock `interrupt()`, verify payload has `source="estimated"` and warning note
  4. `test_approved_returns_log_command` — mock `interrupt()` returning `{"approved": True}`, verify `Command(goto="log_to_db")`
  5. `test_rejected_returns_response_command` — mock `interrupt()` returning `{"approved": False}`, verify `Command(goto="response")`
- **PATTERN**: `patch("src.agents.nodes.confirmation_node.interrupt")` to control the interrupt behavior
- **GOTCHA**: `interrupt()` from `langgraph.types` must be patched at the IMPORT location: `src.agents.nodes.confirmation_node.interrupt`
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v` — all tests pass

### Task 16: CREATE `tests/unit/test_log_to_db_node.py`

- **IMPLEMENT**: Unit tests for `log_to_db_node`:
  1. `test_log_success` — mock DB session and service, verify `create_log_entry` called with correct args
  2. `test_log_estimated_item` — verify `food_id=None` is passed for estimated items
  3. `test_no_pending_confirmation` — returns `{}`
  4. `test_pending_items_removal` — verify first item is popped from queue
  5. `test_result_accumulation` — verify results accumulate across multiple calls
- **PATTERN**: Reuse shared fixtures from `conftest.py` (after Phase A). Create new fixtures targeted at `log_to_db_node` module.
- **VALIDATE**: `uv run pytest tests/unit/test_log_to_db_node.py -v` — all tests pass

### Task 17: UPDATE existing test files

- **IMPLEMENT**:
  1. DELETE `tests/unit/test_calculate_log_node.py` — replaced by Task 14 and 16
  2. UPDATE `tests/unit/test_multi_item_loop.py` — import from new `log_to_db_node` instead of `calculate_log_node`, update any references
  3. UPDATE `tests/unit/test_feedback_logic.py` — imports and patches target new node modules
- **GOTCHA**: `test_multi_item_loop.py` tests sequential item removal — this now happens in `log_to_db_node`, not `calculate_log_node`. Update imports and fixture targets accordingly.
- **VALIDATE**: `uv run pytest tests/unit/ -v` — all unit tests pass

### Task 18: CREATE `tests/integration/test_hitl_lifecycle.py`

- **IMPLEMENT**: Integration test for the full HITL lifecycle:
  ```python
  from unittest.mock import patch, MagicMock, AsyncMock
  from langchain_core.messages import AIMessage, HumanMessage
  from langgraph.checkpoint.memory import MemorySaver
  from langgraph.types import Command
  from src.agents.nutritionist import define_graph

  async def test_hitl_approve_flow():
      """Full graph: LOG_FOOD → calculate → interrupt → approve → log to DB."""
      with patch("src.agents.nutritionist.AsyncSqliteSaver") as mock_saver, \
           patch("src.agents.nutritionist.input_parser_node") as mock_input, \
           patch("src.agents.nutritionist.food_search_node") as mock_search, \
           patch("src.agents.nutritionist.agent_selection_node") as mock_select, \
           patch("src.agents.nutritionist.calculate_macros_node") as mock_calc, \
           patch("src.agents.nutritionist.log_to_db_node") as mock_log, \
           patch("src.agents.nodes.response_node.get_llm_for_node") as mock_get_llm:

          mock_saver.from_conn_string.return_value = MemorySaver()
          # ... setup mock returns ...
          # Note: confirmation_node should NOT be mocked — we test the real interrupt

          graph = await define_graph()
          config = {"configurable": {"thread_id": "test-hitl-1"}}

          result = await graph.ainvoke(
              {"messages": [HumanMessage(content="I had 200g of chicken")]},
              config=config,
          )

          # Verify interrupt was raised
          assert "__interrupt__" in result

          # Resume with approval
          final = await graph.ainvoke(
              Command(resume={"approved": True}),
              config=config,
          )
  ```
- **GOTCHA**: For this test to work, `confirmation_node` must NOT be mocked — it must call real `interrupt()`. All other nodes should be mocked.
- **VALIDATE**: `uv run pytest tests/integration/test_hitl_lifecycle.py -v` — passes

### Task 19: UPDATE `tests/integration/test_graph_compilation.py`

- **IMPLEMENT**: Update the node name assertions to reflect new graph structure:
  ```python
  expected = {"input_parser", "food_search", "agent_selection", "calculate_macros", "confirmation", "log_to_db", "stats_lookup", "response"}
  ```
- **VALIDATE**: `uv run pytest tests/integration/test_graph_compilation.py -v` — passes

### Task 20: UPDATE documentation

- **IMPLEMENT**:
  1. Update `PRD.md` — add HITL confirmation flow description, update graph flow diagram
  2. Update `.agent/rules/main_rule.md` — update project structure (new files), update architectural patterns (add HITL with interrupt()), update reference table
  3. Update `.agent/reference/test-strategy.md` — add HITL test entries to Critical Paths table, update folder structure
  4. Update `README.md` if it references the graph structure
- **VALIDATE**: Read files and verify coherence

### Task 21: Final Validation

- **VALIDATE**: `uv run pytest tests/unit/ -v` — ALL unit tests pass
- **VALIDATE**: `uv run pytest tests/integration/ -v` — ALL integration tests pass
- **VALIDATE**: `uv run pytest tests/ -v` — full suite passes
- **VALIDATE**: Manual test in Studio: send "I had 200g of chicken" → expect interrupt prompt with macros → resume with `{"approved": true}` → expect logged response

---

## TESTING STRATEGY

### Unit Tests

| File | Tests | What it covers |
|------|-------|---------------|
| `test_calculate_macros_node.py` | 4 | DB path, estimation path, error handling, empty state |
| `test_confirmation_node.py` | 5 | Payload structure, approve/reject Commands, missing state |
| `test_log_to_db_node.py` | 5 | DB write, estimated item, pending removal, result accumulation |
| `test_state_consistency.py` | 1 | Updated GraphAction literals |
| `test_feedback_integration.py` | 1 | Updated graph flow |
| `test_multi_item_loop.py` | 5 | Updated for log_to_db_node |

### Integration Tests

| File | Tests | What it covers |
|------|-------|---------------|
| `test_hitl_lifecycle.py` | 2 | Full interrupt→resume approve/reject flow |
| `test_graph_compilation.py` | 2 | Updated node names |

### Edge Cases

- Estimated item with `food_id=None` is persisted correctly
- User rejects → item is popped from queue, no DB write
- Multiple items → confirmation for each, sequential processing
- `pending_confirmation` is `None` → confirmation_node skips to response
- Macro calculation error → FAILED result, skip confirmation

---

## VALIDATION COMMANDS

### Level 1: Syntax & Import Check

```bash
uv run python -c "from src.agents.nutritionist import define_graph; import asyncio; asyncio.run(define_graph()); print('Graph compiles OK')"
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

### Level 4: Full Suite

```bash
uv run pytest tests/ -v
```

### Level 5: Manual Validation (Studio)

```
1. Start LangGraph Studio: langgraph dev
2. Send: "I had 200g of chicken"
3. Expect: Interrupt prompt with macros (source: "database")
4. Resume with: {"approved": true}
5. Expect: Logged confirmation response

6. Send: "I ate 3 slices of homemade pizza"
7. Expect: Interrupt prompt with estimated macros (source: "estimated", warning note)
8. Resume with: {"approved": false}
9. Expect: Rejection acknowledged response
```

---

## ACCEPTANCE CRITERIA

- [ ] `calculate_log_node.py` is deleted — replaced by 3 new nodes
- [ ] `confirmation_node` uses `langgraph.types.interrupt()` — not hand-rolled routing
- [ ] Graph compiles without error with `AsyncSqliteSaver` checkpointer
- [ ] ALL food items (DB and estimated) go through confirmation before DB write
- [ ] Items from DB show `source: "database"` in confirm prompt
- [ ] Items not in DB show `source: "estimated"` with warning in confirm prompt
- [ ] User can approve (→ item logged) or reject (→ item discarded, no DB write)
- [ ] Multi-item meals process each item sequentially with individual confirmation
- [ ] `uv run pytest tests/unit/ -v` passes with all new + updated tests
- [ ] `uv run pytest tests/integration/test_hitl_lifecycle.py -v` passes
- [ ] Studio manual test completes without crashes
- [ ] No regressions — chitchat, stats queries, single-item logging all still work
- [ ] Documentation updated (PRD, main_rule, test-strategy)

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting or type checking errors
- [ ] Manual Studio testing confirms feature works
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability

---

## NOTES

- **Checkpointer compatibility**: The user reported Studio crashes with the previous approach. The `interrupt()` approach is LangGraph's recommended pattern and is tested with Studio. However, verify with both `MemorySaver` (tests) and `AsyncSqliteSaver` (production). If issues arise, check the checkpointer docs at https://docs.langchain.com/oss/python/langgraph/interrupts#using-langsmith-studio.
- **`food_id=None` for estimated items**: The DailyLog model may need a schema change to allow `food_id` to be nullable. This is a small DB migration but important to validate.
- **`Command` return type**: Nodes that return `Command` objects MUST annotate their return type as `Command[Literal["node_a", "node_b"]]`. LangGraph uses this to validate graph structure at compile time.
- **Interrupt idempotency**: Code before `interrupt()` re-executes on resume. The confirmation_node only reads state before the interrupt, so this is safe. But `calculate_macros_node` does NOT have an interrupt — it runs once per invocation.
- **PR #10 cleanup**: After this implementation is complete and merged, close PR #10 with a comment linking to the new approach.
