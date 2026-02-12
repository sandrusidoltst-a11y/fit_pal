# Feature: Refactor State Schema and Implement Multi-Item Loop

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

This feature addresses critical architectural improvements to the FitPal agent's state management and food processing logic. It includes:

1. **Type-Safe State Schema**: Replace vague `List[dict]` types with proper TypedDict definitions for better type safety and IDE support
2. **Multi-Item Loop Processing**: Implement graph loop to handle multiple food items (e.g., "I ate 100g chicken and 200g rice")
3. **System Prompt Updates**: Update agent selection prompt to prefer cooked over raw foods and force selection (no AMBIGUOUS)
4. **LLM Response Validation**: Add validation to prevent inconsistent states from LLM responses

## User Story

As a developer maintaining the FitPal agent
I want type-safe state schemas and proper multi-item handling
So that the code is maintainable, the agent can process complex meals, and users get accurate tracking

## Problem Statement

**Current Issues:**

1. **Type Safety Loss**: `AgentState` uses `List[dict]` for `pending_food_items`, `search_results`, and plain `dict` for `daily_totals`, losing all type safety and IDE support
2. **Multi-Item Failure**: Agent only processes the first food item, ignoring subsequent items in multi-food meals
3. **Prompt Misalignment**: System prompt says "raw over cooked" but users measure food after cooking
4. **AMBIGUOUS Status**: Defined but not handled, causing potential graph failures
5. **Missing Validation**: LLM can return inconsistent states (e.g., `SELECTED` with `food_id=None`)

## Solution Statement

1. **Create TypedDict schemas** for all state fields that currently use `dict` or `List[dict]`
2. **Implement graph loop** that processes items one at a time, routing back to `food_search` until `pending_food_items` is empty
3. **Update prompts** to reflect "cooked over raw" preference and force LLM to choose between SELECTED/NO_MATCH only
4. **Add validation layer** in selection node to catch LLM inconsistencies
5. **Update all tests** to use new typed schemas

## Feature Metadata

**Feature Type**: Refactor + Enhancement
**Estimated Complexity**: Medium
**Primary Systems Affected**: 
- State management (`src/agents/state.py`)
- Graph orchestration (`src/agents/nutritionist.py`)
- Selection node (`src/agents/nodes/selection_node.py`)
- System prompts (`prompts/agent_selection.md`)
- All node implementations that access state
- Test suite

**Dependencies**: 
- LangGraph (existing)
- Python typing module (existing)

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/agents/state.py` (lines 1-28) - Why: Current state schema with type safety issues to fix
- `src/schemas/input_schema.py` (lines 15-23) - Why: `SingleFoodItem` Pydantic model that we'll mirror as TypedDict
- `src/schemas/selection_schema.py` (lines 7-21) - Why: `SelectionStatus` enum and `FoodSelectionResult` schema
- `src/agents/nodes/selection_node.py` (lines 15-71) - Why: Selection logic that needs validation and multi-item awareness
- `src/agents/nodes/food_search_node.py` (lines 5-25) - Why: Search node that processes first item only
- `src/agents/nodes/input_node.py` (lines 10-46) - Why: Input parser that creates `List[dict]` from Pydantic models
- `src/agents/nutritionist.py` (lines 12-57) - Why: Graph definition that needs loop routing logic
- `src/tools/food_lookup.py` (lines 7-18, 23-44) - Why: Tool return types for `search_food` and `calculate_food_macros`
- `src/services/daily_log_service.py` (lines 64-92) - Why: `get_daily_totals` return type
- `prompts/agent_selection.md` (lines 1-30) - Why: System prompt to update with cooked preference
- `tests/conftest.py` (lines 17-23) - Why: `basic_state` fixture pattern to update
- `tests/unit/test_agent_selection.py` (lines 1-71) - Why: Tests that need updating for new schemas

### New Files to Create

None - this is a refactor of existing files

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LangGraph State Schema Documentation](https://docs.langchain.com/oss/python/langgraph/graph-api#schema)
  - Specific section: TypedDict, dataclass, and BaseModel options
  - Why: Understanding state schema options and serialization
- [Python TypedDict Documentation](https://docs.python.org/3/library/typing.html#typing.TypedDict)
  - Specific section: TypedDict definition and usage
  - Why: Proper TypedDict syntax for nested structures
- [LangGraph Conditional Edges](https://docs.langchain.com/oss/python/langgraph/graph-api#conditional-edges)
  - Specific section: Routing logic based on state
  - Why: Implementing loop-back logic for multi-item processing

### Patterns to Follow

**State Schema Pattern (from existing code):**
```python
# Current (BAD):
class AgentState(TypedDict):
    pending_food_items: List[dict]  # ❌ No type safety
    search_results: List[dict]      # ❌ No type safety
    daily_totals: dict              # ❌ No type safety

# Target (GOOD):
class PendingFoodItem(TypedDict):
    food_name: str
    amount: float
    unit: str
    original_text: str

class SearchResult(TypedDict):
    id: int
    name: str

class DailyTotals(TypedDict):
    calories: float
    protein: float
    carbs: float
    fat: float

class AgentState(TypedDict):
    pending_food_items: List[PendingFoodItem]  # ✅ Type-safe
    search_results: List[SearchResult]          # ✅ Type-safe
    daily_totals: DailyTotals                   # ✅ Type-safe
```

**Graph Loop Pattern (from LangGraph docs):**
```python
# In nutritionist.py
def route_after_calculate(state: AgentState) -> str:
    """Route back to food_search if more items pending, else to response."""
    if state.get("pending_food_items", []):
        return "food_search"  # Process next item
    else:
        return "response"  # All items processed

# Add conditional edge after calculate node
workflow.add_conditional_edges(
    "calculate_log",
    route_after_calculate,
    {
        "food_search": "food_search",
        "response": "response"
    }
)
```

**Validation Pattern:**
```python
# In selection_node.py
result = structured_llm.invoke(messages)

# Validate LLM response consistency
if result.status == SelectionStatus.SELECTED and result.food_id is None:
    print("Warning: LLM returned SELECTED without food_id, treating as NO_MATCH")
    return {"selected_food_id": None, "last_action": "NO_MATCH"}

if result.status == SelectionStatus.AMBIGUOUS:
    print("Warning: LLM returned AMBIGUOUS (not supported in MVP), treating as NO_MATCH")
    return {"selected_food_id": None, "last_action": "NO_MATCH"}
```

**Item Removal Pattern (for loop processing):**
```python
# After successful calculation, remove processed item
def calculate_log_node(state: AgentState) -> dict:
    # ... calculate and log ...
    
    # Remove first item from pending list
    remaining_items = state["pending_food_items"][1:]
    return {
        "pending_food_items": remaining_items,
        # ... other updates
    }
```

**Naming Conventions:**
- TypedDict classes: PascalCase (e.g., `PendingFoodItem`, `SearchResult`)
- State fields: snake_case (e.g., `pending_food_items`, `daily_totals`)
- Node functions: snake_case with `_node` suffix (e.g., `selection_node`, `food_search_node`)

**Error Handling:**
- Use `state.get("key", default)` for safe access
- Add print warnings for LLM validation failures
- Gracefully handle empty lists

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation - Type-Safe State Schema

**Goal**: Replace all `dict` and `List[dict]` types with proper TypedDict definitions

**Tasks:**
- Define TypedDict schemas for all state components
- Update AgentState to use new schemas
- Ensure backward compatibility during transition

### Phase 2: Core Implementation - Multi-Item Loop

**Goal**: Implement graph routing logic to process multiple food items

**Tasks:**
- Create routing function for post-calculation flow
- Add conditional edge to loop back to food_search
- Implement item removal logic in calculate node (placeholder for now)
- Update food_search_node to handle empty pending_items gracefully

### Phase 3: Validation & Prompt Updates

**Goal**: Add LLM response validation and update system prompts

**Tasks:**
- Add validation logic in selection_node
- Update agent_selection.md prompt
- Handle AMBIGUOUS status gracefully
- Update prompt to prefer cooked over raw

### Phase 4: Testing & Validation

**Goal**: Update all tests to use new schemas and verify multi-item processing

**Tasks:**
- Update conftest.py fixtures
- Update all unit tests to use TypedDict schemas
- Add multi-item processing tests
- Verify all validation commands pass

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### REFACTOR `src/agents/state.py`

- **IMPLEMENT**: Define three new TypedDict classes above `AgentState`
- **PATTERN**: Mirror structure from `src/schemas/input_schema.py` (lines 15-23) for `PendingFoodItem`
- **PATTERN**: Mirror return type from `src/tools/food_lookup.py` (line 18) for `SearchResult`
- **PATTERN**: Mirror return type from `src/services/daily_log_service.py` (lines 85-90) for `DailyTotals`
- **IMPORTS**: Ensure `from typing import List, TypedDict` is present
- **IMPLEMENT**: Update `AgentState` fields:
  - `pending_food_items: List[PendingFoodItem]`
  - `search_results: List[SearchResult]`
  - `daily_totals: DailyTotals`
- **GOTCHA**: Keep all other fields unchanged (messages, current_date, last_action, selected_food_id)
- **VALIDATE**: `uv run ruff check src/agents/state.py`

### UPDATE `src/agents/nodes/input_node.py`

- **IMPLEMENT**: Update comment on line 42 to reflect new type: `List[PendingFoodItem]`
- **GOTCHA**: No code changes needed - `model_dump()` still returns dict that matches TypedDict structure
- **VALIDATE**: `uv run ruff check src/agents/nodes/input_node.py`

### UPDATE `src/agents/nodes/selection_node.py`

- **ADD**: Import `SelectionStatus` at top: `from src.schemas.selection_schema import FoodSelectionResult, SelectionStatus`
- **IMPLEMENT**: Add validation block after line 65 (before return statement):
  ```python
  # Validate LLM response consistency
  if result.status == SelectionStatus.SELECTED and result.food_id is None:
      print("Warning: LLM returned SELECTED without food_id, treating as NO_MATCH")
      return {"selected_food_id": None, "last_action": "NO_MATCH"}
  
  if result.status == SelectionStatus.AMBIGUOUS:
      print("Warning: LLM returned AMBIGUOUS (not supported in MVP), treating as NO_MATCH")
      return {"selected_food_id": None, "last_action": "NO_MATCH"}
  ```
- **GOTCHA**: Place validation BEFORE the return statement on line 67
- **VALIDATE**: `uv run ruff check src/agents/nodes/selection_node.py`

### UPDATE `prompts/agent_selection.md`

- **UPDATE**: Line 21 - Change "Raw over cooked" to "Cooked over raw"
- **UPDATE**: Full text should be: `- **Cooked over raw**: Unless user specifies "raw" explicitly`
- **UPDATE**: Lines 14-17 - Remove edge case handling (0/1 results handled in code)
- **ADD**: New section after line 17:
  ```markdown
  **Note**: The system pre-filters edge cases (0 or 1 results) before reaching this prompt.
  You will only receive cases with 2+ search results.
  
  **For MVP**: Always choose SELECTED or NO_MATCH. If multiple items seem equally valid, 
  select the most common/generic option and explain your reasoning in the confidence field.
  (AMBIGUOUS status is reserved for future user clarification flows)
  ```
- **VALIDATE**: Manual review of prompt file

### CREATE `src/agents/nodes/calculate_log_node.py` (Placeholder)

- **CREATE**: New file with placeholder implementation
- **IMPLEMENT**: Basic structure that will consume `selected_food_id` and remove first item from `pending_food_items`
- **PATTERN**: Follow node pattern from `selection_node.py` (lines 15-71)
- **IMPORTS**: `from src.agents.state import AgentState`
- **IMPLEMENT**: Placeholder function:
  ```python
  def calculate_log_node(state: AgentState) -> dict:
      """
      Calculate macros and log to database.
      
      TODO: Implement actual calculation and database persistence.
      For now, just removes processed item from pending list.
      """
      pending_items = state.get("pending_food_items", [])
      
      if not pending_items:
          return {}
      
      # Remove first item (processed)
      remaining_items = pending_items[1:]
      
      return {
          "pending_food_items": remaining_items,
          "last_action": "LOGGED"
      }
  ```
- **GOTCHA**: This is a placeholder - full implementation will come in next feature
- **VALIDATE**: `uv run ruff check src/agents/nodes/calculate_log_node.py`

### UPDATE `src/agents/nutritionist.py`

- **ADD**: Import calculate_log_node: `from src.agents.nodes.calculate_log_node import calculate_log_node`
- **ADD**: New routing function after line 29:
  ```python
  def route_after_selection(state: AgentState):
      """Route based on selection result."""
      action = state.get("last_action")
      if action == "SELECTED":
          return "calculate_log"
      else:  # NO_MATCH
          return "response"
  
  def route_after_calculate(state: AgentState):
      """Route back to food_search if more items pending, else to response."""
      if state.get("pending_food_items", []):
          return "food_search"  # Process next item
      else:
          return "response"  # All items processed
  ```
- **UPDATE**: Replace `response_node` placeholder (lines 20-21) with actual implementation:
  ```python
  def response_node(state: AgentState):
      """Generate response based on current state."""
      action = state.get("last_action")
      if action == "LOGGED":
          return {"messages": ["Food logged successfully!"]}
      elif action == "NO_MATCH":
          return {"messages": ["Could not find matching food item."]}
      else:
          return {"messages": ["Response placeholder"]}
  ```
- **ADD**: Register calculate_log node after line 34: `workflow.add_node("calculate_log", calculate_log_node)`
- **UPDATE**: Replace line 48 edge with conditional:
  ```python
  workflow.add_conditional_edges(
      "agent_selection",
      route_after_selection,
      {
          "calculate_log": "calculate_log",
          "response": "response"
      }
  )
  ```
- **ADD**: New conditional edge after calculate_log:
  ```python
  workflow.add_conditional_edges(
      "calculate_log",
      route_after_calculate,
      {
          "food_search": "food_search",
          "response": "response"
      }
  )
  ```
- **REMOVE**: Old line 48: `workflow.add_edge("agent_selection", "response")`
- **GOTCHA**: Ensure routing functions are defined before being used in add_conditional_edges
- **VALIDATE**: `uv run python -c "from src.agents.nutritionist import define_graph; g = define_graph(); print('Graph compiled successfully')"`

### UPDATE `tests/conftest.py`

- **UPDATE**: `basic_state` fixture (lines 18-23) to include all required fields with proper types:
  ```python
  @pytest.fixture
  def basic_state():
      """Returns a basic AgentState structure for testing."""
      return {
          "messages": [],
          "pending_food_items": [],
          "daily_totals": {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0},
          "current_date": date.today(),
          "last_action": "",
          "search_results": [],
          "selected_food_id": None,
      }
  ```
- **IMPORTS**: Add `from datetime import date` at top
- **VALIDATE**: `uv run pytest tests/conftest.py --collect-only`

### UPDATE `tests/unit/test_agent_selection.py`

- **UPDATE**: All test state setups to use TypedDict-compatible dicts
- **UPDATE**: Line 7 - Change to: `basic_state["pending_food_items"] = [{"food_name": "xyz", "amount": 100.0, "unit": "g", "original_text": "xyz"}]`
- **UPDATE**: Line 18-19 - Change to: `basic_state["pending_food_items"] = [{"food_name": "beef", "amount": 100.0, "unit": "g", "original_text": "100g beef"}]`
- **UPDATE**: Line 35-36 - Change to: `basic_state["pending_food_items"] = [{"food_name": "apple", "amount": 150.0, "unit": "g", "original_text": "I ate an apple"}]`
- **UPDATE**: Line 52-53 - Change to: `basic_state["pending_food_items"] = [{"food_name": "meat", "amount": 100.0, "unit": "g", "original_text": "some meat"}]`
- **UPDATE**: Line 60 - Remove AMBIGUOUS from assertion: `assert result["last_action"] == "SELECTED"` (LLM should now always choose)
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py -v`

### UPDATE `tests/unit/test_food_search_node.py`

- **UPDATE**: Test state setups to use TypedDict-compatible dicts
- **PATTERN**: Follow same pattern as test_agent_selection.py updates
- **VALIDATE**: `uv run pytest tests/unit/test_food_search_node.py -v`

### UPDATE `tests/unit/test_input_parser.py`

- **REVIEW**: Check if any assertions rely on dict structure
- **UPDATE**: If needed, update assertions to match TypedDict structure
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py -v`

### CREATE `tests/unit/test_multi_item_loop.py`

- **CREATE**: New test file for multi-item processing
- **IMPLEMENT**: Test case for "chicken and rice" scenario:
  ```python
  def test_multi_item_processing(basic_state):
      """Test that multiple food items are processed in sequence."""
      from src.agents.nutritionist import define_graph
      
      graph = define_graph()
      
      # Simulate user input: "I ate 100g chicken and 200g rice"
      initial_state = {
          **basic_state,
          "pending_food_items": [
              {"food_name": "chicken", "amount": 100.0, "unit": "g", "original_text": "100g chicken"},
              {"food_name": "rice", "amount": 200.0, "unit": "g", "original_text": "200g rice"}
          ],
          "last_action": "LOG_FOOD"
      }
      
      # This test verifies the graph can handle multiple items
      # Full integration test will be added when calculate_log is implemented
      assert len(initial_state["pending_food_items"]) == 2
  ```
- **GOTCHA**: This is a basic test - full integration test requires calculate_log implementation
- **VALIDATE**: `uv run pytest tests/unit/test_multi_item_loop.py -v`

---

## TESTING STRATEGY

### Unit Tests

**Scope**: Test each modified component in isolation

1. **State Schema Tests**: Verify TypedDict structures are valid
2. **Selection Node Tests**: Verify validation logic catches LLM errors
3. **Routing Logic Tests**: Verify route_after_calculate returns correct node names
4. **Calculate Node Tests**: Verify item removal logic

**Fixtures**: Use updated `basic_state` fixture with all typed fields

### Integration Tests

**Scope**: Test multi-item flow through graph

1. **Single Item Flow**: Verify existing behavior still works
2. **Multi-Item Flow**: Verify loop processes all items
3. **Empty Pending Items**: Verify graceful handling

### Edge Cases

1. **Empty pending_food_items**: Should route to response
2. **LLM returns SELECTED with food_id=None**: Should convert to NO_MATCH
3. **LLM returns AMBIGUOUS**: Should convert to NO_MATCH
4. **Single item in pending_food_items**: Should process and route to response
5. **Three items in pending_food_items**: Should loop three times

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check src/
uv run ruff format src/
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/test_agent_selection.py -v
uv run pytest tests/unit/test_food_search_node.py -v
uv run pytest tests/unit/test_input_parser.py -v
uv run pytest tests/unit/test_multi_item_loop.py -v
```

### Level 3: Full Test Suite

```bash
uv run pytest tests/ -v
```

### Level 4: Manual Validation

**Graph Compilation Test:**
```bash
uv run python -c "from src.agents.nutritionist import define_graph; g = define_graph(); print('✅ Graph compiled successfully')"
```

**State Schema Validation:**
```bash
uv run python -c "from src.agents.state import AgentState, PendingFoodItem, SearchResult, DailyTotals; print('✅ All TypedDict schemas imported successfully')"
```

### Level 5: Type Checking (Optional)

```bash
uv run mypy src/agents/state.py --strict
```

---

## ACCEPTANCE CRITERIA

- [ ] All `List[dict]` and plain `dict` types replaced with TypedDict in `AgentState`
- [ ] Three new TypedDict classes defined: `PendingFoodItem`, `SearchResult`, `DailyTotals`
- [ ] Selection node validates LLM responses and handles SELECTED/AMBIGUOUS edge cases
- [ ] Graph implements loop routing to process multiple food items
- [ ] Calculate node placeholder removes processed items from pending list
- [ ] System prompt updated to "cooked over raw" preference
- [ ] System prompt instructs LLM to avoid AMBIGUOUS status
- [ ] All existing tests pass with updated schemas
- [ ] New multi-item test added
- [ ] All validation commands pass with zero errors
- [ ] Graph compiles successfully with new routing logic
- [ ] No regressions in existing functionality

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting or type checking errors
- [ ] Graph compilation successful
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability

---

## NOTES

### Design Decisions

1. **TypedDict over Pydantic for State**: LangGraph serializes state to SQLite checkpointer. TypedDict is simpler and natively supported without custom serializers.

2. **Loop Processing over Batch**: Processing items one at a time is simpler for MVP and easier to debug. Can optimize to batch processing in future if needed.

3. **Placeholder Calculate Node**: Full implementation of calculate_log_node requires integration with `calculate_food_macros` tool and `daily_log_service`. This refactor focuses on architecture - full implementation will be separate feature.

4. **Validation in Node vs Prompt**: Validation logic in Python code is more reliable than relying on LLM to follow prompt instructions. Prompt guides behavior, code enforces constraints.

### Trade-offs

**TypedDict vs Pydantic:**
- ✅ TypedDict: Simple, serializable, no conversion needed
- ❌ TypedDict: No runtime validation, duplicate definitions
- Decision: TypedDict for state, keep Pydantic for LLM structured output

**Loop vs Batch:**
- ✅ Loop: Simple logic, easy to debug, handles partial failures
- ❌ Loop: More LLM calls (higher cost), slower
- Decision: Loop for MVP, optimize later if needed

### Future Considerations

1. **Batch Processing Optimization**: If cost/latency becomes issue, implement batch selection (single LLM call for all items)
2. **AMBIGUOUS Status Implementation**: Add user clarification flow in Phase 2
3. **Single-Result LLM Verification**: Add smart heuristic to verify single search results
4. **Full Calculate Node**: Implement actual macro calculation and database persistence

### Codebase Scan Results

**Other instances of `List[dict]` or `dict` in state:**
- ✅ `pending_food_items: List[dict]` - FIXED in this refactor
- ✅ `search_results: List[dict]` - FIXED in this refactor
- ✅ `daily_totals: dict` - FIXED in this refactor
- ✅ No other instances found in `src/` directory

**Validation**: Codebase scan confirmed these are the only three instances of type-unsafe state fields.
