# Feature: Off-Menu Fallback + HITL Batch Confirmation Gate

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Combine two features into one cohesive change:

1. **Off-menu fallback**: When food_search returns NO_MATCH, use LLM to estimate macros (instead of failing immediately). Estimated items are tagged with `source: "estimated"` for transparency.

2. **HITL batch confirmation**: Before ANY DB write, accumulate macro calculations for ALL items in a multi-item input, present the full batch to the user as a preview, and wait for conversational confirmation via LangGraph's `interrupt()` primitive. The user can confirm, reject, or edit specific items through natural text messages (not buttons). After any edit, the full updated batch is re-shown.

**Key architectural change**: The current `calculate_log_node` (which calculates AND writes to DB in one step) is split into three nodes: `calculate_macros` (preview only) → `confirmation` (HITL interrupt loop) → `commit` (batch DB write).

## User Story

As a user logging my food intake
I want to see the exact macros the agent will log before it saves them to the database
So that I can verify accuracy, catch typos/errors, and have confidence in estimated values for foods not in the database

## Problem Statement

The current food logging pipeline (`calculate_log_node`) couples macro calculation with DB persistence in a single node. There is no user verification step before data hits the database. When food items are not found in the DB, the pipeline fails with a "NO_MATCH" error — there's no estimation fallback. Users have no way to catch typos (e.g., "2000g" instead of "200g") before they become incorrect entries.

## Solution Statement

1. **Split `calculate_log_node`** into `calculate_macros_node` (preview) + `confirmation_node` (HITL) + `commit_node` (batch DB write)
2. **Accumulate previews**: The multi-item loop now calculates macros for ALL items before presenting the batch
3. **Off-menu estimation**: When `selected_food_id` is None (NO_MATCH), use LLM with structured output to estimate macros. Tag with `source: "estimated"`
4. **Conversational HITL**: `confirmation_node` uses `interrupt()` in a validation loop — user confirms, rejects, or edits via natural text. LLM parses user responses into structured decisions. After any edit, the full batch is re-displayed
5. **Batch commit**: After confirmation, `commit_node` writes ALL items to DB in one pass

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High
**Primary Systems Affected**: `src/agents/nodes/`, `src/agents/state.py`, `src/agents/nutritionist.py`, `src/schemas/`, `tests/`
**Dependencies**: `langgraph.types.interrupt`, `langgraph.types.Command` (already in langgraph package)

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/agents/nodes/calculate_log_node.py` (lines 1-86) - Why: **WILL BE DELETED**. Understand what it does so the split preserves behavior. Key: macro calc (line 31), DB write (lines 49-58), report fetch (lines 61-63), result accumulation (lines 66-74), pending item removal (line 77).
- `src/agents/state.py` (lines 1-125) - Why: State schema changes. Must add `MacroResult` TypedDict, `pending_confirmations` list, update `GraphAction` literals.
- `src/agents/nutritionist.py` (lines 1-83) - Why: Graph definition. Must add 3 new nodes, remove 1, update edges and routing functions. Critical: routing functions (lines 18-39), edge definitions (lines 50-81).
- `src/agents/nodes/selection_node.py` (lines 1-108) - Why: NO_MATCH handling (lines 23-40). Must simplify — stop adding FAILED results on NO_MATCH since calculate_macros will handle estimation instead.
- `src/agents/nodes/food_search_node.py` (lines 1-25) - Why: Upstream node — no changes needed, understand the flow.
- `src/agents/nodes/response_node.py` (lines 1-101) - Why: Downstream node. Must handle new actions (CONFIRMED, REJECTED) in `_build_context` (line 35).
- `src/tools/food_lookup.py` (lines 1-44) - Why: `calculate_food_macros` tool — used by `calculate_macros_node`. `compute_food_macros` helper (lines 7-17) shows pure calculation pattern.
- `src/schemas/input_schema.py` (lines 1-44) - Why: `ActionType` enum (lines 8-12) — must stay in sync with `GraphAction`.
- `src/schemas/selection_schema.py` (lines 1-20) - Why: `SelectionStatus` enum — must stay in sync with `GraphAction`.
- `src/config.py` (lines 21-54) - Why: `NODE_CONFIGS` (lines 22-27) — must add configs for estimation_node and confirmation_node.
- `src/models.py` (line 32) - Why: `DailyLog.food_id` is currently `nullable=False`. Must change to `nullable=True` for estimated items.
- `src/services/daily_log_service.py` (lines 1-201) - Why: `create_log_entry` service function + `log_food_entry` @tool wrapper. Must ensure they accept `food_id=None`.
- `src/database.py` - Why: `get_async_db_session` — used by tools.
- `langgraph.json` (lines 1-8) - Why: Studio graph config — references `define_graph`. Verify compatibility.
- `tests/conftest.py` - Why: Shared fixtures. Reuse patterns for new test fixtures.
- `tests/unit/test_calculate_log_node.py` - Why: **WILL BE DELETED/REPLACED** with new test files.
- `tests/unit/test_multi_item_loop.py` - Why: Tests multi-item processing. Must update for new node names.
- `tests/unit/test_feedback_integration.py` - Why: Graph-level flow test. Must update for new graph shape.
- `tests/unit/test_feedback_logic.py` - Why: Processing result tests. Must update for new node names.
- `tests/unit/test_state_consistency.py` - Why: Validates GraphAction literals. Must update for new actions.
- `tests/graph_api/test_graph_compilation.py` - Why: Node name assertions. Must update expected set.
- `tests/graph_api/test_graph_flows.py` - Why: E2E flow tests. Must add HITL flow test.

### New Files to Create

- `src/agents/nodes/calculate_macros_node.py` - Pure macro calculation (DB lookup OR LLM estimation), no DB write
- `src/agents/nodes/confirmation_node.py` - HITL interrupt node with conversational edit loop
- `src/agents/nodes/commit_node.py` - Batch DB write after user confirmation
- `src/schemas/estimation_schema.py` - Pydantic schema for LLM macro estimation output
- `src/schemas/confirmation_schema.py` - Pydantic schema for LLM confirmation response parsing
- `prompts/macro_estimation.md` - Prompt for LLM macro estimation (off-menu items)
- `prompts/confirmation_parser.md` - Prompt for parsing user confirmation responses
- `tests/unit/test_calculate_macros_node.py` - Unit tests for macro calculation node
- `tests/unit/test_confirmation_node.py` - Unit tests for confirmation interrupt node
- `tests/unit/test_commit_node.py` - Unit tests for batch commit node

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LangGraph Interrupts (Python)](https://docs.langchain.com/oss/python/langgraph/interrupts)
  - Section: "Pause using interrupt" — `from langgraph.types import interrupt` pattern
  - Section: "Resuming interrupts" — `Command(resume=...)` pattern
  - Section: "Validating human input" — `while True: answer = interrupt(prompt)` loop pattern (CRITICAL: this is the exact pattern for our conversational edit loop)
  - Section: "Rules of interrupts" — don't wrap in try/except, side effects must be idempotent, matching is index-based
  - Why: This is the EXACT API we're implementing
- [LangGraph Command Reference](https://docs.langchain.com/oss/python/langgraph/graph-api)
  - Section: "resume" — `Command(resume=...)` usage, `Command` as node return type
  - Why: confirmation_node returns `Command[Literal["commit", "response"]]`
- [LangGraph SQL Agent HITL Example](https://docs.langchain.com/oss/python/langgraph/sql-agent)
  - Section: "6. Implement human-in-the-loop review" — approve/edit/reject pattern with interrupt
  - Why: Reference implementation for our pattern
- [LangGraph Durable Execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)
  - Why: Explains why checkpointer is required for interrupt, idempotency requirements

**Testing Skill — MANDATORY READING before writing ANY test:**

- `.claude/skills/test-engineering/SKILL.md` — Primary test engineering skill. Covers test tiers (unit vs graph_api), mock boundary rules, file structure conventions, AAA docstring standards, and graph-api E2E testing patterns. **READ THIS FIRST.**
- `.claude/skills/test-engineering/references/fitpal-test-strategy.md` — FitPal-specific test strategy, critical paths, and coverage priorities.
- `.claude/skills/test-engineering/references/unit-testing.md` — Unit test patterns: fixture design, mock targets (patch at import location), assertion patterns.
- `.claude/skills/test-engineering/references/graph-api-testing.md` — Graph API test patterns using langgraph-sdk, server lifecycle, thread fixtures.

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

def confirmation_node(state: AgentState) -> Command[Literal["commit", "response"]]:
    # ... interrupt loop ...
    return Command(goto="commit", update={"last_action": "CONFIRMED"})
```

**Validation Loop Pattern** (from LangGraph docs):
```python
from langgraph.types import interrupt

def node_with_validation(state: State):
    prompt = "Initial prompt"
    while True:
        answer = interrupt(prompt)
        if valid(answer):
            break
        prompt = "Updated prompt after invalid input"
    return {"field": answer}
```

**Tool-First Pattern** (from existing codebase):
```python
# Nodes call tools via await tool.ainvoke(), never DB directly
macros = await calculate_food_macros.ainvoke({"food_id": id, "amount_g": amount})
```

**Processing Result Accumulation Pattern** (from calculate_log_node):
```python
result_item = {**current_item, "status": "LOGGED", "message": "..."}
current_results = state.get("processing_results", [])
updated_results = current_results + [result_item]
```

**Error Handling Pattern**: Nodes return state updates, never raise. Errors are captured in `processing_results` as `"status": "FAILED"`.

**Naming Conventions:**
- Nodes: `snake_case_node` (e.g., `calculate_macros_node`)
- Graph node IDs: `snake_case` without `_node` suffix (e.g., `"calculate_macros"`)
- State fields: `snake_case` (e.g., `pending_confirmations`)

---

## GRAPH FLOW CHANGES

### Current Flow
```
input_parser ──┬──→ food_search → agent_selection ──┬──→ calculate_log ──┬──→ food_search (loop)
               │                                    │                    └──→ response
               ├──→ stats_lookup → response          │
               └──→ response                         └──→ response (NO_MATCH)
```

### New Flow
```
input_parser ──┬──→ food_search → agent_selection ──→ calculate_macros ──┬──→ food_search (loop: more items)
               │                                                         └──→ confirmation ──┬──→ commit ──→ response
               ├──→ stats_lookup → response                                                  └──→ response (rejected)
               └──→ response
```

Key changes:
1. `agent_selection` routes BOTH `SELECTED` AND `NO_MATCH` to `calculate_macros` (estimation handles NO_MATCH)
2. `calculate_macros` loops back to `food_search` if more items, else routes to `confirmation`
3. `confirmation` uses `Command` return for dynamic routing (no conditional edges needed)
4. `commit` always routes to `response`

---

## IMPLEMENTATION PLAN

### Phase 1: State Schema & Types

Update `AgentState` with new types and fields. Create Pydantic schemas for LLM structured output.

### Phase 2: Prompts

Create LLM prompts for macro estimation and confirmation response parsing.

### Phase 3: New Nodes

Implement `calculate_macros_node`, `confirmation_node`, `commit_node`.

### Phase 4: Modify Existing Nodes & Config

Update `selection_node` (simplify NO_MATCH), `response_node` (new actions), `config.py` (new node configs), `models.py` (nullable food_id), `daily_log_service.py` (accept null food_id).

### Phase 5: Rewire Graph

Update `nutritionist.py` with new nodes, edges, and routing functions.

### Phase 6: Delete Old Code

Remove `calculate_log_node.py`.

### Phase 7: Update Existing Tests

Update all affected test files for new node names/actions.

### Phase 8: Write New Tests

Create unit tests for new nodes.

### Phase 9: Validation & Documentation

Full test suite, manual Studio testing, docs update.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Task 1: UPDATE `src/agents/state.py` — Add MacroResult and update GraphAction

- **IMPLEMENT**:
  1. Add `MacroResult` TypedDict class (place after `ProcessingResult`, before `InputState`):
     ```python
     class MacroResult(TypedDict):
         """Calculated macros for a single food item, pending user confirmation.

         Used by calculate_macros_node to accumulate batch previews
         before presenting to user for HITL confirmation.
         """
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
  2. Update `GraphAction` to add `"AWAITING_CONFIRMATION"`, `"CONFIRMED"`, `"REJECTED"` — remove nothing from current literals.
  3. Add `pending_confirmations: List[MacroResult]` field to `AgentState` (after `processing_results`).
  4. Update `ProcessingResult` to add optional `source` field: `source: Optional[Literal["database", "estimated"]]`
- **IMPORTS**: No new imports needed — `Literal` and `Optional` already imported.
- **VALIDATE**: `uv run python -c "from src.agents.state import AgentState, MacroResult; print('OK')"`

### Task 2: CREATE `src/schemas/estimation_schema.py` — LLM estimation output schema

- **IMPLEMENT**: Pydantic schema for LLM-estimated macro output:
  ```python
  from pydantic import BaseModel, Field

  class MacroEstimation(BaseModel):
      """Structured output for LLM macro estimation of off-menu foods."""
      calories: float = Field(..., description="Estimated calories (kcal) for the given amount in grams")
      protein: float = Field(..., description="Estimated protein in grams for the given amount")
      carbs: float = Field(..., description="Estimated carbohydrates in grams for the given amount")
      fat: float = Field(..., description="Estimated fat in grams for the given amount")
  ```
- **VALIDATE**: `uv run python -c "from src.schemas.estimation_schema import MacroEstimation; print(MacroEstimation(calories=100, protein=10, carbs=20, fat=5))"`

### Task 3: CREATE `src/schemas/confirmation_schema.py` — Confirmation response parsing schema

- **IMPLEMENT**: Pydantic schemas for parsing user's conversational confirmation responses:
  ```python
  from typing import List, Literal, Optional
  from pydantic import BaseModel, Field

  class ItemEdit(BaseModel):
      """A single edit to apply to a batch item."""
      item_index: int = Field(..., description="0-based index of the item in the batch to edit")
      edit_type: Literal["change_amount", "remove"] = Field(..., description="Type of edit")
      new_amount_g: Optional[float] = Field(None, description="New amount in grams (only for change_amount)")

  class ConfirmationResponse(BaseModel):
      """Parsed user response to batch confirmation prompt."""
      action: Literal["confirm", "reject", "edit"] = Field(
          ...,
          description="User's intent: 'confirm' to approve all, 'reject' to cancel all, 'edit' to modify specific items"
      )
      edits: Optional[List[ItemEdit]] = Field(
          None,
          description="List of edits to apply (only when action is 'edit')"
      )
  ```
- **VALIDATE**: `uv run python -c "from src.schemas.confirmation_schema import ConfirmationResponse, ItemEdit; print(ConfirmationResponse(action='confirm'))"`

### Task 4: CREATE `prompts/macro_estimation.md` — Off-menu estimation prompt

- **IMPLEMENT**: Create the LLM prompt for estimating macros when food is not in the database:
  ```markdown
  # Macro Estimation

  You are a nutrition expert. The user mentioned a food item that is NOT in our verified database.
  Your job is to estimate the nutritional values based on your knowledge.

  ## Rules
  1. Provide your BEST estimate for the given food and amount.
  2. Use standard USDA/nutrition reference values when available.
  3. Round all values to 1 decimal place.
  4. If the food name is ambiguous, assume the most common variety.
  5. All amounts are in grams. If the user said "1 cup" or "1 piece", the amount in grams has already been estimated for you.
  6. Return values for the SPECIFIC amount given, not per 100g.

  ## Output Format
  Return your estimation as structured data with: calories, protein, carbs, fat (all for the given amount in grams).
  ```
- **VALIDATE**: File exists at `prompts/macro_estimation.md`

### Task 5: CREATE `prompts/confirmation_parser.md` — Confirmation response parser prompt

- **IMPLEMENT**: Create the LLM prompt for parsing user's conversational confirmation responses:
  ```markdown
  # Confirmation Response Parser

  You are parsing a user's response to a food logging confirmation prompt.
  The user was shown a batch of food items with calculated macros and asked to confirm.

  ## Your Job
  Determine the user's intent from their natural language response:
  - **confirm**: User approves the batch as-is (e.g., "yes", "looks good", "confirm", "log it")
  - **reject**: User wants to cancel everything (e.g., "no", "cancel", "nevermind", "don't log")
  - **edit**: User wants to modify specific items (e.g., "change chicken to 150g", "remove the banana", "the rice should be 300g")

  ## Rules for edits
  1. `item_index` is 0-based, matching the order items were presented
  2. `change_amount` means the user wants a different quantity in grams
  3. `remove` means the user wants to drop that item entirely
  4. Parse amounts to grams (e.g., "150g" → 150.0)
  5. Match food names to the closest item in the batch by name

  ## Batch items for reference
  {batch_context}
  ```
- **VALIDATE**: File exists at `prompts/confirmation_parser.md`

### Task 6: CREATE `src/agents/nodes/calculate_macros_node.py` — Preview-only macro calculation

- **IMPLEMENT**: Pure macro calculation node. Two paths:
  1. **DB path** (when `selected_food_id` is not None): Call `calculate_food_macros.ainvoke()` tool, build `MacroResult` with `source="database"`
  2. **Estimation path** (when `selected_food_id` is None AND `last_action == "NO_MATCH"`): Call LLM with `macro_estimation.md` prompt and `MacroEstimation` structured output, build `MacroResult` with `source="estimated"`

  After calculating, accumulate into `pending_confirmations` and pop from `pending_food_items`.

  ```python
  import os
  from src.agents.state import AgentState, MacroResult
  from src.config import get_llm_for_node
  from src.tools.food_lookup import calculate_food_macros
  from src.schemas.estimation_schema import MacroEstimation
  from langchain_core.messages import HumanMessage, SystemMessage

  async def calculate_macros_node(state: AgentState) -> dict:
      """Calculate macros for the current food item (preview only, no DB write).

      Two paths:
      1. DB match (selected_food_id exists): Use calculate_food_macros tool
      2. Off-menu (selected_food_id is None): Use LLM estimation

      Accumulates results into pending_confirmations for batch confirmation.
      """
      pending_items = state.get("pending_food_items", [])
      selected_food_id = state.get("selected_food_id")

      if not pending_items:
          return {}

      current_item = pending_items[0]
      amount = current_item.get("amount", 0.0)
      food_name = current_item.get("food_name", "")

      if selected_food_id:
          # DB path — use tool
          macros = await calculate_food_macros.ainvoke({"food_id": selected_food_id, "amount_g": amount})
          if "error" in macros:
              # Calculation failed — add FAILED result, skip this item
              result_item = {
                  **current_item,
                  "status": "FAILED",
                  "message": f"Could not calculate macros for {food_name}: {macros['error']}"
              }
              remaining = pending_items[1:]
              return {
                  "pending_food_items": remaining,
                  "processing_results": state.get("processing_results", []) + [result_item],
                  "last_action": "NO_MATCH",
                  "selected_food_id": None,
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

      # Accumulate into pending_confirmations
      current_confirmations = state.get("pending_confirmations", [])
      updated_confirmations = current_confirmations + [macro_result]

      # Pop processed item
      remaining = pending_items[1:]

      return {
          "pending_food_items": remaining,
          "pending_confirmations": updated_confirmations,
          "last_action": "AWAITING_CONFIRMATION",
          "selected_food_id": None,
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
          "calories": round(result.calories, 1),
          "protein": round(result.protein, 1),
          "carbs": round(result.carbs, 1),
          "fat": round(result.fat, 1),
          "source": "estimated",
          "original_text": original_text,
          "food_id": None,
      }
  ```
- **GOTCHA**: The `_estimate_macros` function calls a real LLM. In unit tests, mock `get_llm_for_node("estimation_node")`.
- **GOTCHA**: Use `await calculate_food_macros.ainvoke()` (async), not `.invoke()`.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.calculate_macros_node import calculate_macros_node; print('OK')"`

### Task 7: CREATE `src/agents/nodes/confirmation_node.py` — HITL batch confirmation with conversational edit loop

- **IMPLEMENT**: HITL interrupt node using LangGraph's `interrupt()` in a validation loop. The node:
  1. Formats the batch preview from `pending_confirmations`
  2. Calls `interrupt(payload)` to pause and show preview to user
  3. On resume, parses user's natural language response using LLM + `ConfirmationResponse` schema
  4. If confirm → returns `Command(goto="commit")`
  5. If reject → returns `Command(goto="response")` with cleanup
  6. If edit → applies edits, recalculates if needed, re-shows batch, loops back to interrupt

  ```python
  import os
  from typing import Literal
  from langgraph.types import interrupt, Command
  from langchain_core.messages import HumanMessage, SystemMessage

  from src.agents.state import AgentState, MacroResult
  from src.config import get_llm_for_node
  from src.schemas.confirmation_schema import ConfirmationResponse
  from src.tools.food_lookup import calculate_food_macros

  def _format_batch_preview(items: list[MacroResult]) -> dict:
      """Build human-readable batch preview payload for interrupt."""
      formatted_items = []
      for i, item in enumerate(items):
          source_tag = " (estimated)" if item["source"] == "estimated" else ""
          formatted_items.append({
              "index": i,
              "description": f"{item['food_name']} — {item['amount_g']}g{source_tag}",
              "calories": item["calories"],
              "protein": item["protein"],
              "carbs": item["carbs"],
              "fat": item["fat"],
              "source": item["source"],
          })

      totals = {
          "calories": round(sum(it["calories"] for it in items), 1),
          "protein": round(sum(it["protein"] for it in items), 1),
          "carbs": round(sum(it["carbs"] for it in items), 1),
          "fat": round(sum(it["fat"] for it in items), 1),
      }

      return {
          "question": "Please review the following items before I log them. You can confirm, reject, or edit specific items.",
          "items": formatted_items,
          "totals": totals,
      }


  async def confirmation_node(state: AgentState) -> Command[Literal["commit", "response"]]:
      """Present batch preview and await user confirmation via conversational interrupt loop.

      Uses LangGraph's interrupt() in a while loop:
      - Each interrupt() pauses the graph and shows the batch preview
      - User responds with natural text (confirm/reject/edit)
      - LLM parses the response into a structured ConfirmationResponse
      - Edits update the batch and re-show; confirm/reject exit the loop
      """
      batch = list(state.get("pending_confirmations", []))

      if not batch:
          return Command(goto="response")

      preview = _format_batch_preview(batch)

      while True:
          user_response = interrupt(preview)

          # Parse user response with LLM
          decision = await _parse_confirmation(user_response, batch)

          if decision.action == "confirm":
              return Command(
                  goto="commit",
                  update={
                      "pending_confirmations": batch,
                      "last_action": "CONFIRMED",
                  }
              )

          elif decision.action == "reject":
              # Build FAILED results for all items
              failed_results = []
              for item in batch:
                  failed_results.append({
                      "food_name": item["food_name"],
                      "amount": item["amount_g"],
                      "unit": "g",
                      "original_text": item["original_text"],
                      "status": "FAILED",
                      "message": f"User rejected logging {item['food_name']}",
                      "source": item.get("source"),
                  })

              return Command(
                  goto="response",
                  update={
                      "last_action": "REJECTED",
                      "pending_confirmations": [],
                      "processing_results": state.get("processing_results", []) + failed_results,
                  }
              )

          elif decision.action == "edit":
              # Apply edits to batch
              batch = await _apply_edits(batch, decision.edits or [])
              # Re-build preview with updated batch
              preview = _format_batch_preview(batch)
              # Loop continues → interrupt again with updated preview


  async def _parse_confirmation(user_text: str, batch: list[MacroResult]) -> ConfirmationResponse:
      """Use LLM to parse user's natural language confirmation response."""
      prompt_path = os.path.join(os.getcwd(), "prompts", "confirmation_parser.md")
      try:
          with open(prompt_path, "r", encoding="utf-8") as f:
              system_prompt = f.read()
      except FileNotFoundError:
          system_prompt = "Parse the user's response to a food logging confirmation prompt."

      # Build batch context for the prompt
      batch_context = "\n".join(
          f"[{i}] {item['food_name']} — {item['amount_g']}g ({item['source']})"
          for i, item in enumerate(batch)
      )
      system_prompt = system_prompt.replace("{batch_context}", batch_context)

      llm = get_llm_for_node("confirmation_node")
      structured_llm = llm.with_structured_output(ConfirmationResponse)

      messages = [
          SystemMessage(content=system_prompt),
          HumanMessage(content=user_text),
      ]

      return structured_llm.invoke(messages)


  async def _apply_edits(batch: list[MacroResult], edits: list) -> list[MacroResult]:
      """Apply user edits to the batch. Recalculate macros for amount changes."""
      # Process removals in reverse order to preserve indices
      remove_indices = sorted(
          [e.item_index for e in edits if e.edit_type == "remove"],
          reverse=True
      )
      for idx in remove_indices:
          if 0 <= idx < len(batch):
              batch.pop(idx)

      # Process amount changes
      for edit in edits:
          if edit.edit_type == "change_amount" and edit.new_amount_g is not None:
              if 0 <= edit.item_index < len(batch):
                  item = batch[edit.item_index]
                  old_amount = item["amount_g"]
                  new_amount = edit.new_amount_g

                  if item["food_id"] is not None:
                      # DB item — recalculate via tool
                      macros = await calculate_food_macros.ainvoke({
                          "food_id": item["food_id"],
                          "amount_g": new_amount
                      })
                      if "error" not in macros:
                          item["amount_g"] = new_amount
                          item["calories"] = macros["calories"]
                          item["protein"] = macros["protein"]
                          item["carbs"] = macros["carbs"]
                          item["fat"] = macros["fat"]
                  else:
                      # Estimated item — scale proportionally
                      if old_amount > 0:
                          ratio = new_amount / old_amount
                          item["amount_g"] = new_amount
                          item["calories"] = round(item["calories"] * ratio, 1)
                          item["protein"] = round(item["protein"] * ratio, 1)
                          item["carbs"] = round(item["carbs"] * ratio, 1)
                          item["fat"] = round(item["fat"] * ratio, 1)

      return batch
  ```
- **GOTCHA**: `interrupt()` causes the node to re-execute from the top on resume. Code before `interrupt()` is replayed. The `_format_batch_preview()` call is pure (reads state), so this is safe.
- **GOTCHA**: The `Command` return type annotation must list ALL possible target nodes: `Command[Literal["commit", "response"]]`.
- **GOTCHA**: LLM calls inside the loop (`_parse_confirmation`) are near-deterministic at temperature=0. On replay, cached interrupt values ensure the loop path is consistent. For production robustness, consider wrapping in `@task` (future improvement).
- **GOTCHA**: `_apply_edits` processes removals first (in reverse order) to avoid index shifting issues.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.confirmation_node import confirmation_node; print('OK')"`

### Task 8: CREATE `src/agents/nodes/commit_node.py` — Batch DB write

- **IMPLEMENT**: Writes ALL confirmed items to DB in one pass. Called only after user confirms.
  ```python
  from datetime import datetime, timezone
  from src.agents.state import AgentState
  from src.services.daily_log_service import log_food_entry, query_food_logs

  async def commit_node(state: AgentState) -> dict:
      """Write all confirmed food items to the database in batch.

      Only called after user confirms via confirmation_node.
      Reads items from pending_confirmations state field.
      """
      batch = state.get("pending_confirmations", [])

      if not batch:
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

      processing_results = list(state.get("processing_results", []))

      # Write each item to DB
      for item in batch:
          await log_food_entry.ainvoke({
              "food_id": item.get("food_id"),  # None for estimated items
              "amount_g": item["amount_g"],
              "calories": item["calories"],
              "protein": item["protein"],
              "carbs": item["carbs"],
              "fat": item["fat"],
              "timestamp": timestamp.isoformat(),
              "original_text": item.get("original_text", ""),
          })

          processing_results.append({
              "food_name": item["food_name"],
              "amount": item["amount_g"],
              "unit": "g",
              "original_text": item.get("original_text", ""),
              "status": "LOGGED",
              "message": f"Logged {item['food_name']} ({item['calories']}kcal)",
              "source": item.get("source"),
          })

      # Fetch updated daily report
      updated_report = []
      if consumed_at:
          updated_report = await query_food_logs.ainvoke({"target_date": str(consumed_at.date())})

      return {
          "pending_confirmations": [],
          "daily_log_report": updated_report if updated_report else state.get("daily_log_report", []),
          "last_action": "LOGGED",
          "processing_results": processing_results,
      }
  ```
- **GOTCHA**: `log_food_entry` must accept `food_id=None` for estimated items. Verify Task 10 is done first.
- **GOTCHA**: Uses `await tool.ainvoke()` pattern — never direct DB access.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.commit_node import commit_node; print('OK')"`

### Task 9: UPDATE `src/models.py` — Make food_id nullable

- **IMPLEMENT**: Change `DailyLog.food_id` from `nullable=False` to `nullable=True`:
  ```python
  # Before:
  food_id: Mapped[int] = mapped_column(Integer, ForeignKey("food_items.id"), nullable=False)
  # After:
  food_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("food_items.id"), nullable=True)
  ```
  Also add `Optional` to the type import if not already present.
- **GOTCHA**: This is a schema change. For SQLite, this requires either recreating the table or using a migration tool. Since we're in dev mode with a test DB, this is fine. For production, this would need Alembic.
- **VALIDATE**: `uv run python -c "from src.models import DailyLog; print('OK')"`

### Task 10: UPDATE `src/services/daily_log_service.py` — Accept nullable food_id

- **IMPLEMENT**: Check `create_log_entry` function signature. Update `food_id` parameter to accept `Optional[int]`:
  ```python
  async def create_log_entry(
      session: AsyncSession,
      food_id: Optional[int],  # Was: int
      ...
  ) -> DailyLog:
  ```
  Also update the `log_food_entry` @tool wrapper to accept `food_id: Optional[int]`.
- **VALIDATE**: `uv run pytest tests/unit/test_daily_log_service.py -v`

### Task 11: UPDATE `src/agents/nodes/selection_node.py` — Simplify NO_MATCH handling

- **IMPLEMENT**: Remove the FAILED processing_result creation on NO_MATCH. The estimation path in `calculate_macros_node` now handles NO_MATCH items instead of failing them.

  **Before** (lines 23-40):
  ```python
  if not search_results:
      current_item = pending_items[0] if pending_items else None
      if current_item:
          fail_item = cast(ProcessingResult, {
              **current_item,
              "status": "FAILED",
              "message": f"No search results found for {current_item.get('food_name', 'item')}"
          })
          updated_results = state.get("processing_results", []) + [fail_item]
      else:
          updated_results = state.get("processing_results", [])
      return {
          "selected_food_id": None,
          "last_action": "NO_MATCH",
          "processing_results": updated_results
      }
  ```

  **After**:
  ```python
  if not search_results:
      return {
          "selected_food_id": None,
          "last_action": "NO_MATCH",
      }
  ```

  Also simplify AMBIGUOUS handling (lines 92-103) the same way — just return `NO_MATCH` without FAILED result.

- **GOTCHA**: Remove the `from typing import cast` import and `from src.agents.state import ProcessingResult` import if no longer used in this file.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.selection_node import agent_selection_node; print('OK')"`

### Task 12: UPDATE `src/agents/nodes/response_node.py` — Handle new actions

- **IMPLEMENT**: Update `_build_context` (line 35) to handle `CONFIRMED` and `REJECTED` actions:
  ```python
  if last_action in ("LOGGED", "FAILED", "NO_MATCH", "SELECTED", "CONFIRMED", "REJECTED"):
      processing_results = state.get("processing_results", [])
      context["processing_results"] = processing_results
  ```
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

### Task 13: UPDATE `src/config.py` — Add new node configs

- **IMPLEMENT**: Add `estimation_node` and `confirmation_node` to `NODE_CONFIGS`:
  ```python
  NODE_CONFIGS = {
      "input_node": {"temperature": 0.0},
      "selection_node": {"temperature": 0.0},
      "estimation_node": {"temperature": 0.0},      # NEW: off-menu macro estimation
      "confirmation_node": {"temperature": 0.0},     # NEW: parse user confirmation responses
      "response_node": {"temperature": 0.7},
      "default": {"temperature": 0.0}
  }
  ```
- **VALIDATE**: `uv run python -c "from src.config import get_llm_for_node; get_llm_for_node('estimation_node'); get_llm_for_node('confirmation_node'); print('OK')"`

### Task 14: UPDATE `src/agents/nutritionist.py` — Rewire graph

- **IMPLEMENT**: Replace graph definition with new nodes and edges:

  1. **Update imports**: Remove `calculate_log_node`, add `calculate_macros_node`, `confirmation_node`, `commit_node`:
     ```python
     from src.agents.nodes.calculate_macros_node import calculate_macros_node
     from src.agents.nodes.confirmation_node import confirmation_node
     from src.agents.nodes.commit_node import commit_node
     ```

  2. **Update routing functions**:
     ```python
     def route_after_selection(state: AgentState):
         """Route to calculate_macros for both DB matches and off-menu estimation."""
         action = state.get("last_action")
         if action in ["SELECTED", "NO_MATCH"]:
             return "calculate_macros"
         return "response"

     def route_after_calculate_macros(state: AgentState):
         """Loop back if more items pending, else show batch for confirmation."""
         if state.get("pending_food_items", []):
             return "food_search"  # Process next item
         return "confirmation"  # All items calculated, show batch
     ```

  3. **Replace nodes**:
     ```python
     # Remove:
     workflow.add_node("calculate_log", calculate_log_node)
     # Add:
     workflow.add_node("calculate_macros", calculate_macros_node)
     workflow.add_node("confirmation", confirmation_node)
     workflow.add_node("commit", commit_node)
     ```

  4. **Update edges**:
     ```python
     # agent_selection → calculate_macros (both SELECTED and NO_MATCH)
     workflow.add_conditional_edges(
         "agent_selection",
         route_after_selection,
         {
             "calculate_macros": "calculate_macros",
             "response": "response",
         },
     )

     # calculate_macros → food_search (loop) or confirmation (batch ready)
     workflow.add_conditional_edges(
         "calculate_macros",
         route_after_calculate_macros,
         {
             "food_search": "food_search",
             "confirmation": "confirmation",
         },
     )

     # confirmation → uses Command return (no add_conditional_edges needed)
     # commit → response (always)
     workflow.add_edge("commit", "response")
     ```

- **GOTCHA**: `confirmation_node` returns `Command[Literal["commit", "response"]]`. LangGraph handles routing from Command nodes automatically. DO NOT add `add_conditional_edges` for the confirmation node.
- **GOTCHA**: The old `route_after_calculate` function and `"calculate_log"` edges must be fully removed.
- **VALIDATE**: `uv run python -c "from src.agents.nutritionist import define_graph; import asyncio; asyncio.run(define_graph()); print('Graph compiles OK')"`

### Task 15: DELETE `src/agents/nodes/calculate_log_node.py`

- **IMPLEMENT**: Delete the file. Its functionality has been split into `calculate_macros_node.py`, `confirmation_node.py`, and `commit_node.py`.
- **VALIDATE**: `uv run python -c "from src.agents.nutritionist import define_graph; import asyncio; asyncio.run(define_graph()); print('Still compiles OK')"`

### Task 16: UPDATE `tests/unit/test_state_consistency.py` — Add new actions

- **IMPLEMENT**: Update the test that validates `GraphAction` literals. The new literals (`AWAITING_CONFIRMATION`, `CONFIRMED`, `REJECTED`) are additive.
- **GOTCHA**: If the test checks exact count of `GraphAction` values, update the assertion.
- **VALIDATE**: `uv run pytest tests/unit/test_state_consistency.py -v`

### Task 17: UPDATE `tests/unit/test_multi_item_loop.py` — New node references

- **IMPLEMENT**: Update imports and patches to reference `calculate_macros_node` instead of `calculate_log_node`. The loop logic now accumulates into `pending_confirmations` instead of writing to DB.
- **GOTCHA**: The test fixtures and mock targets change from `src.agents.nodes.calculate_log_node.*` to `src.agents.nodes.calculate_macros_node.*`.
- **VALIDATE**: `uv run pytest tests/unit/test_multi_item_loop.py -v`

### Task 18: UPDATE `tests/unit/test_feedback_integration.py` — New graph shape

- **IMPLEMENT**: Update the graph-level flow test to use new node structure:
  - Replace mock for `calculate_log_node` with mocks for `calculate_macros_node`, `confirmation_node`, `commit_node`
  - The `confirmation_node` mock should return a `Command` object (bypass interrupt)
  - Update import patches and expected node names
- **GOTCHA**: Since `confirmation_node` uses `interrupt()` which requires a real checkpointer, the mock should return a `Command(goto="commit")` directly, bypassing the interrupt.
- **VALIDATE**: `uv run pytest tests/unit/test_feedback_integration.py -v`

### Task 19: UPDATE `tests/unit/test_feedback_logic.py` — New node names

- **IMPLEMENT**: Update imports and patches for new node modules. Processing result assertions may need updating for the `source` field.
- **VALIDATE**: `uv run pytest tests/unit/test_feedback_logic.py -v`

### Task 20: DELETE `tests/unit/test_calculate_log_node.py`

- **IMPLEMENT**: Delete the file. Replaced by Task 21 and Task 23.
- **VALIDATE**: File no longer exists

### Task 21: CREATE `tests/unit/test_calculate_macros_node.py`

- **IMPLEMENT**: Unit tests for `calculate_macros_node`:
  1. `test_db_path_success` — mock `calculate_food_macros.ainvoke`, verify `MacroResult` with `source="database"` added to `pending_confirmations`
  2. `test_db_path_error` — mock returns `{"error": "..."}`, verify FAILED result in `processing_results`
  3. `test_estimation_path` — mock `get_llm_for_node("estimation_node")`, verify `MacroResult` with `source="estimated"` and `food_id=None`
  4. `test_empty_pending_items` — returns `{}`
  5. `test_accumulates_confirmations` — call with existing `pending_confirmations`, verify new item is appended
  6. `test_pops_pending_item` — verify first item is removed from `pending_food_items`
- **PATTERN**: Mock `calculate_food_macros.ainvoke` at `src.agents.nodes.calculate_macros_node.calculate_food_macros`
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_macros_node.py -v`

### Task 22: CREATE `tests/unit/test_confirmation_node.py`

- **IMPLEMENT**: Unit tests for `confirmation_node`:
  1. `test_no_pending_confirmations` — returns `Command(goto="response")` immediately
  2. `test_interrupt_payload_structure` — mock `interrupt()` to return "yes", verify payload has `items`, `totals`, `question`
  3. `test_estimated_item_tag` — verify payload item has `(estimated)` in description
  4. `test_confirm_returns_commit_command` — mock `interrupt()` returning "yes" and mock `_parse_confirmation` returning `ConfirmationResponse(action="confirm")`, verify `Command(goto="commit")`
  5. `test_reject_returns_response_command` — mock returning "no", verify `Command(goto="response")` with FAILED processing_results
  6. `test_edit_loops_and_re_shows` — mock `interrupt()` returning "change chicken to 150g" first then "yes", verify recalculation and two interrupt calls
- **PATTERN**: `patch("src.agents.nodes.confirmation_node.interrupt")` to control the interrupt behavior
- **GOTCHA**: `interrupt()` from `langgraph.types` must be patched at the IMPORT location in the target module
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v`

### Task 23: CREATE `tests/unit/test_commit_node.py`

- **IMPLEMENT**: Unit tests for `commit_node`:
  1. `test_commit_batch_success` — mock `log_food_entry.ainvoke` and `query_food_logs.ainvoke`, verify all items written
  2. `test_commit_estimated_item` — verify `food_id=None` is passed for estimated items
  3. `test_no_pending_confirmations` — returns `{}`
  4. `test_processing_results_accumulated` — verify results include all batch items
  5. `test_clears_pending_confirmations` — verify `pending_confirmations` is empty after commit
- **PATTERN**: Mock `log_food_entry.ainvoke` at `src.agents.nodes.commit_node.log_food_entry`
- **VALIDATE**: `uv run pytest tests/unit/test_commit_node.py -v`

### Task 24: UPDATE `tests/graph_api/test_graph_compilation.py` — New node names

- **IMPLEMENT**: Update expected node set:
  ```python
  expected = {"input_parser", "food_search", "agent_selection", "calculate_macros", "confirmation", "commit", "stats_lookup", "response"}
  ```
- **VALIDATE**: `uv run pytest tests/graph_api/test_graph_compilation.py -v`

### Task 25: Full Unit Test Validation

- **VALIDATE**: `uv run pytest tests/unit/ -v` — ALL unit tests pass
- **VALIDATE**: `uv run pytest tests/graph_api/test_graph_compilation.py -v` — graph compiles with new shape
- If any test fails, fix it before proceeding.

### Task 26: UPDATE documentation

- **IMPLEMENT**:
  1. Update `PRD.md` — check off "The Off-Menu Problem" and add HITL batch confirmation as a completed item in Phase 2. Update the graph flow diagram in the mermaid chart.
  2. Update `CLAUDE.md` — update project structure (new files), update architecture patterns section with HITL interrupt pattern.
- **VALIDATE**: Read files and verify coherence.

### Task 27: Final Validation

- **VALIDATE**: `uv run pytest tests/unit/ -v` — ALL unit tests pass
- **VALIDATE**: `uv run pytest tests/graph_api/ -v -s` — ALL graph API tests pass (server auto-starts via conftest)
- **VALIDATE**: Manual test in Studio:
  1. Start: `langgraph dev`
  2. Send: "I had 200g of chicken and a banana"
  3. Expect: Interrupt with batch preview (chicken: source=database, banana: check source)
  4. Resume with: "looks good" → expect items logged
  5. Send: "I had 3 slices of homemade pizza"
  6. Expect: Interrupt with estimated macros (source=estimated)
  7. Resume with: "change to 2 slices" → expect updated preview
  8. Resume with: "yes" → expect logged
  9. Send: "I had a protein shake"
  10. Expect: Interrupt
  11. Resume with: "cancel" → expect rejection acknowledged

---

## TESTING STRATEGY

### Unit Tests

| File | Tests | What it covers |
|------|-------|---------------|
| `test_calculate_macros_node.py` | 6 | DB path, estimation path, error handling, accumulation, empty state |
| `test_confirmation_node.py` | 6 | Payload structure, approve/reject Commands, edit loop, missing state |
| `test_commit_node.py` | 5 | Batch DB write, estimated items, result accumulation, cleanup |
| `test_state_consistency.py` | updated | New GraphAction literals |
| `test_multi_item_loop.py` | updated | New node references for loop drain |
| `test_feedback_integration.py` | updated | New graph shape with confirmation |
| `test_feedback_logic.py` | updated | New node names, source field |

### Graph API Tests

| File | Tests | What it covers |
|------|-------|---------------|
| `test_graph_compilation.py` | updated | New node set |
| `test_graph_flows.py` | existing | E2E flows (may need HITL-specific test later) |

### Edge Cases

- Estimated item with `food_id=None` persists correctly
- User rejects → all items discarded, no DB write
- User edits amount → macros recalculated correctly for DB items
- User edits amount → macros scaled proportionally for estimated items
- User removes an item → batch shrinks, remaining items still confirmable
- Multiple edits in sequence → each shows updated batch
- Single item batch → confirmation still works
- Empty `pending_confirmations` → confirmation_node skips to response
- Macro calculation error → FAILED result, item skipped in batch

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

### Level 3: Graph API Tests

```bash
uv run pytest tests/graph_api/ -v -s
```

### Level 4: Full Suite

```bash
uv run pytest tests/ -v
```

### Level 5: Manual Validation (Studio)

```
1. Start LangGraph Studio: langgraph dev
2. Send: "I had 200g of chicken and a banana"
3. Expect: Interrupt prompt with batch preview
4. Resume with: "looks good"
5. Expect: Logged confirmation response

6. Send: "I had 3 slices of homemade pizza"
7. Expect: Interrupt prompt with estimated macros (source: "estimated")
8. Resume with: "change to 2 slices"
9. Expect: Updated batch preview
10. Resume with: "yes"
11. Expect: Logged response

12. Send: "I ate a protein bar"
13. Expect: Interrupt prompt
14. Resume with: "cancel"
15. Expect: Rejection acknowledged
```

---

## ACCEPTANCE CRITERIA

- [ ] `calculate_log_node.py` is deleted — replaced by 3 new nodes
- [ ] `confirmation_node` uses `langgraph.types.interrupt()` — not hand-rolled routing
- [ ] Graph compiles without error with `AsyncSqliteSaver` checkpointer
- [ ] ALL food items (DB and estimated) go through batch confirmation before DB write
- [ ] Items from DB show `source: "database"` in confirm prompt
- [ ] Items not in DB show `source: "estimated"` with "(estimated)" tag in confirm prompt
- [ ] User can confirm (→ all items logged), reject (→ all items discarded), or edit (→ batch updated and re-shown)
- [ ] Edits recalculate macros (DB items via tool, estimated items via proportional scaling)
- [ ] Multi-item meals accumulate all previews, then show one batch for confirmation
- [ ] `food_id` is nullable in DailyLog model — estimated items stored with `food_id=None`
- [ ] `uv run pytest tests/unit/ -v` passes with all new + updated tests
- [ ] `uv run pytest tests/graph_api/ -v` passes
- [ ] Studio manual test completes without crashes
- [ ] No regressions — chitchat, stats queries all still work
- [ ] Documentation updated (PRD, CLAUDE.md)

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + graph_api)
- [ ] No linting or type checking errors
- [ ] Manual Studio testing confirms feature works
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability

---

## NOTES

### Interrupt Replay & Idempotency
Code before `interrupt()` re-executes on resume. The confirmation_node builds the batch preview (pure read from state) before the interrupt, so replay is safe. LLM calls inside the loop (`_parse_confirmation`) are near-deterministic at temperature=0. For production robustness, consider wrapping LLM calls in `@task` decorator to ensure caching (future improvement).

### Interrupt Index Matching
LangGraph matches interrupts by index. In the while loop, each resume adds one more interrupt to the chain. The framework replays all previous interrupts with cached values and only the latest gets the new resume value. This is the documented validation loop pattern.

### Checkpointer Requirement
`interrupt()` requires a checkpointer. The graph already uses `AsyncSqliteSaver` in production and `MemorySaver` in tests. No changes needed.

### Studio UX
When the graph hits `interrupt()`, Studio shows the payload in the `__interrupt__` field. The user types in the chat box to resume. Studio sends `Command(resume=<text>)`. The conversation messages (HumanMessage/AIMessage) only contain the initial user input and final response — the confirmation loop is handled via the interrupt channel.

### food_id=None for Estimated Items
The DailyLog model's `food_id` changes from NOT NULL to nullable. This is a schema change. For dev (SQLite), recreating the DB is fine. For production, use Alembic migration (Phase 2 backlog item).

### Scaling Estimated Item Edits
When a user changes the amount of an estimated item, macros are scaled proportionally (ratio-based). This is simpler than re-calling the LLM and gives predictable results. For DB items, the exact tool is called for precise recalculation.

### Old Plan Superseded
This plan replaces `.agent/plans/hitl-confirmation-gate.md` which had per-item confirmation. The batch approach is more user-friendly and reduces interrupt fatigue for multi-item inputs.
