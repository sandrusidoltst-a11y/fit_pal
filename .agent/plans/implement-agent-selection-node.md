# Feature: Agent Selection Node

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Implement the **Agent Selection Node** - an intelligent LLM-based disambiguation system that selects the most appropriate food item from database search results. This node bridges the gap between the `search_food` tool (which returns multiple candidates) and the `calculate_food_macros` tool (which requires a single food_id). The node uses GPT-4o to intelligently match user intent with database entries, handling ambiguous food names gracefully.

## User Story

As a user logging food intake,
I want the agent to intelligently select the correct food item when multiple matches exist,
So that I don't have to manually disambiguate or worry about incorrect nutritional calculations.

## Problem Statement

When users input food names like "chicken" or "bread", the `search_food` tool returns multiple candidates (e.g., "Chicken breast", "Chicken thigh", "Chicken soup"). Currently, there's no mechanism to:
1. Intelligently select the most appropriate match based on user context
2. Handle cases where no good match exists
3. Ask for clarification when truly ambiguous
4. Maintain conversation flow without breaking the graph

This creates a critical gap in the Phase 1 MVP flow between Input Parser → Search → Calculate & Log.

## Solution Statement

Create a dedicated LangGraph node that:
1. Receives search results from the `search_food` tool via `AgentState.search_results`
2. Uses structured LLM output (Pydantic schema) to select the best food_id
3. Handles edge cases: no results, single result (auto-select), multiple results (intelligent selection)
4. Updates state with the selected food_id for downstream nodes
5. Follows existing project patterns (structured output, explicit prompts, type safety)

## Feature Metadata

**Feature Type**: New Capability  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: 
- LangGraph orchestration (`src/agents/nutritionist.py`)
- Agent nodes (`src/agents/nodes/`)
- State schema (`src/agents/state.py`)

**Dependencies**: 
- `langchain-openai` (GPT-4o)
- `pydantic` v2 (structured output schemas)
- Existing `search_food` tool

---

## CONTEXT REFERENCES

### Relevant Codebase Files - IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/agents/nodes/input_node.py` (lines 1-47) - **Why**: Pattern for LLM node implementation with structured output, prompt loading, and state updates
- `src/agents/state.py` (lines 1-26) - **Why**: Current AgentState schema including `search_results` field (line 25)
- `src/schemas/input_schema.py` (lines 1-35) - **Why**: Pattern for Pydantic schemas with Enums and Field descriptions
- `src/agents/nutritionist.py` (lines 1-55) - **Why**: Graph definition and node registration patterns, routing logic
- `src/tools/food_lookup.py` (lines 6-20) - **Why**: `search_food` tool output format: `List[{"id": int, "name": str}]`
- `src/config.py` (lines 1-22) - **Why**: Project configuration patterns (BASE_DIR, environment variables)
- `tests/unit/test_input_parser.py` (lines 1-68) - **Why**: Testing pattern for LLM nodes with mocked state
- `tests/conftest.py` (lines 17-23) - **Why**: `basic_state` fixture pattern for testing nodes
- `prompts/input_parser.md` (lines 1-32) - **Why**: System prompt structure and formatting conventions

### New Files to Create

- `src/schemas/selection_schema.py` - Pydantic schema for agent selection structured output
- `src/agents/nodes/selection_node.py` - Agent Selection Node implementation
- `prompts/agent_selection.md` - System prompt for food selection LLM
- `tests/unit/test_agent_selection.py` - Comprehensive unit tests for selection node

### Files to Modify

- `src/agents/state.py` - Add `selected_food_id` field to AgentState
- `src/agents/nutritionist.py` - Integrate selection node into graph flow

### Relevant Documentation - YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LangChain Structured Output](https://python.langchain.com/docs/how_to/structured_output/)
  - Specific section: `.with_structured_output()` usage with Pydantic
  - Why: Core pattern for getting reliable JSON from LLMs
- [Pydantic V2 Models](https://docs.pydantic.dev/latest/concepts/models/)
  - Specific section: Field validators and descriptions
  - Why: Ensures type-safe schema definitions
- [LangGraph State Management](https://langchain-ai.github.io/langgraph/concepts/low_level/#state)
  - Specific section: TypedDict state updates
  - Why: Understanding partial state updates in nodes

### Patterns to Follow

**Naming Conventions:**
```python
# Node functions: {purpose}_node
def agent_selection_node(state: AgentState) -> dict:
    ...

# Schema classes: PascalCase with descriptive names
class FoodSelectionResult(BaseModel):
    ...

# Enums: PascalCase for class, UPPER_SNAKE_CASE for values
class SelectionStatus(str, Enum):
    SELECTED = "SELECTED"
    NO_MATCH = "NO_MATCH"
```

**Error Handling:**
```python
# From input_node.py (lines 17-23)
try:
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()
except FileNotFoundError:
    print(f"Warning: Prompt file not found at {prompt_path}")
    system_prompt = "Fallback prompt..."
```

**Structured LLM Output Pattern:**
```python
# From input_node.py (lines 25-26)
llm = get_parser_llm()  # Returns ChatOpenAI instance
structured_llm = llm.with_structured_output(SchemaClass)
```

**State Update Pattern:**
```python
# From input_node.py (lines 43-46)
return {
    "pending_food_items": [item.model_dump() for item in result.items],
    "last_action": result.action.value
}
```

**Prompt Loading Pattern:**
```python
# From input_node.py (lines 14-19)
prompt_path = os.path.join(os.getcwd(), "prompts", "filename.md")
with open(prompt_path, "r", encoding="utf-8") as f:
    system_prompt = f.read()
```

**Testing Pattern:**
```python
# From test_input_parser.py (lines 4-19)
def test_feature_name(basic_state):
    """Test description."""
    basic_state["messages"] = [HumanMessage(content="test input")]
    result = node_function(basic_state)
    
    assert result["field_name"] == expected_value
    assert len(result.get("list_field", [])) == expected_count
```

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation - Schema & Prompt Design

Create the Pydantic schema for structured LLM output and design the system prompt that guides the selection logic.

**Tasks:**
- Define `FoodSelectionResult` schema with selection status and food_id
- Create comprehensive system prompt for intelligent food matching
- Update `AgentState` to include `selected_food_id` field

### Phase 2: Core Implementation - Selection Node

Implement the agent selection node following existing patterns from `input_node.py`.

**Tasks:**
- Create `selection_node.py` with LLM initialization and structured output
- Implement selection logic with edge case handling (0, 1, or N results)
- Add proper error handling and fallback behavior

### Phase 3: Integration - Graph Orchestration

Integrate the selection node into the LangGraph workflow between search and calculation.

**Tasks:**
- Add selection node to graph definition
- Update routing logic to flow through selection node
- Create placeholder for food_search_node (calls `search_food` tool)

### Phase 4: Testing & Validation

Comprehensive unit tests covering all selection scenarios and edge cases.

**Tasks:**
- Implement unit tests for selection logic (single, multiple, zero results)
- Test edge cases (ambiguous names, exact matches, no matches)
- Validate integration with existing graph flow

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### CREATE `src/schemas/selection_schema.py`

- **IMPLEMENT**: Pydantic schema for agent selection structured output
- **PATTERN**: Mirror `src/schemas/input_schema.py` structure (Enum + BaseModel)
- **IMPORTS**: 
  ```python
  from enum import Enum
  from typing import Optional
  from pydantic import BaseModel, Field
  ```
- **SCHEMA STRUCTURE**:
  ```python
  class SelectionStatus(str, Enum):
      SELECTED = "SELECTED"      # Successfully selected a food item
      NO_MATCH = "NO_MATCH"      # No appropriate match found
      AMBIGUOUS = "AMBIGUOUS"    # Multiple valid matches, need clarification
  
  class FoodSelectionResult(BaseModel):
      status: SelectionStatus = Field(..., description="Selection outcome")
      food_id: Optional[int] = Field(None, description="Selected food item ID (null if NO_MATCH or AMBIGUOUS)")
      confidence: Optional[str] = Field(None, description="Reasoning for selection (for transparency)")
  ```
- **GOTCHA**: Use `Optional[int]` for food_id since it's null when status is NO_MATCH or AMBIGUOUS
- **VALIDATE**: `uv run python -c "from src.schemas.selection_schema import FoodSelectionResult, SelectionStatus; print('Schema imported successfully')"`

### CREATE `prompts/agent_selection.md`

- **IMPLEMENT**: System prompt for intelligent food selection
- **PATTERN**: Follow `prompts/input_parser.md` structure (clear instructions, examples, output format)
- **CONTENT**:
  ```markdown
  You are an intelligent food selection assistant.
  Your goal is to select the most appropriate food item from search results based on user context.
  
  ### Core Instructions:
  1. **Context Analysis**: Consider the user's original input and the available food options.
  2. **Best Match Selection**: Choose the food item that best matches user intent.
     - Prefer exact matches when available
     - Consider common usage (e.g., "chicken" usually means "chicken breast" for tracking)
     - Use nutritional context (if user is tracking, assume whole/raw foods unless specified)
  
  3. **Confidence Assessment**: Provide reasoning for your selection.
  
  4. **Edge Cases**:
     - If NO results provided: status = "NO_MATCH"
     - If SINGLE result: Auto-select with status = "SELECTED"
     - If MULTIPLE results with clear best match: status = "SELECTED"
     - If MULTIPLE results with no clear winner: status = "AMBIGUOUS"
  
  ### Selection Strategy:
  - **Whole foods over processed**: "Chicken" → "Chicken breast" not "Chicken soup"
  - **Raw over cooked**: Unless user specifies cooking method
  - **Common portions**: "Bread" → "Breads... - White" (most common type)
  - **Generic over specific**: Prefer base ingredients
  
  ### Output Format:
  Response must be a valid JSON object matching the `FoodSelectionResult` schema.
  - `status`: "SELECTED", "NO_MATCH", or "AMBIGUOUS"
  - `food_id`: Integer ID of selected food (null if not SELECTED)
  - `confidence`: Brief reasoning (1-2 sentences)
  ```
- **GOTCHA**: Prompt must guide LLM to handle all edge cases (0, 1, N results)
- **VALIDATE**: `uv run python -c "import os; assert os.path.exists('prompts/agent_selection.md'), 'Prompt file created'"`

### UPDATE `src/agents/state.py`

- **IMPLEMENT**: Add `selected_food_id` field to AgentState
- **PATTERN**: Follow existing field definitions (lines 20-25)
- **MODIFICATION**:
  ```python
  # Add after line 25 (search_results)
  selected_food_id: Optional[int]  # Selected food ID from agent selection
  ```
- **IMPORTS**: Add `Optional` to imports from typing (line 2)
- **GOTCHA**: Use `Optional[int]` not `int` since it may be None initially
- **VALIDATE**: `uv run python -c "from src.agents.state import AgentState; import inspect; sig = inspect.signature(AgentState.__annotations__); assert 'selected_food_id' in AgentState.__annotations__, 'Field added'"`

### CREATE `src/agents/nodes/selection_node.py`

- **IMPLEMENT**: Agent selection node with LLM-based food matching
- **PATTERN**: Mirror `src/agents/nodes/input_node.py` structure (lines 1-47)
- **IMPORTS**:
  ```python
  import os
  from typing import Optional
  from langchain_openai import ChatOpenAI
  from langchain_core.messages import SystemMessage, HumanMessage
  from src.agents.state import AgentState
  from src.schemas.selection_schema import FoodSelectionResult, SelectionStatus
  ```
- **IMPLEMENTATION**:
  ```python
  def get_selection_llm():
      """Initialize LLM for agent selection."""
      return ChatOpenAI(model="gpt-4o", temperature=0)
  
  def agent_selection_node(state: AgentState) -> dict:
      """
      Intelligently select the best food item from search results.
      
      Handles edge cases:
      - 0 results: Return NO_MATCH status
      - 1 result: Auto-select
      - N results: Use LLM to select best match
      """
      search_results = state.get("search_results", [])
      pending_items = state.get("pending_food_items", [])
      
      # Edge case: No search results
      if not search_results:
          return {
              "selected_food_id": None,
              "last_action": "NO_MATCH"
          }
      
      # Edge case: Single result - auto-select
      if len(search_results) == 1:
          return {
              "selected_food_id": search_results[0]["id"],
              "last_action": "SELECTED"
          }
      
      # Multiple results - use LLM selection
      prompt_path = os.path.join(os.getcwd(), "prompts", "agent_selection.md")
      
      try:
          with open(prompt_path, "r", encoding="utf-8") as f:
              system_prompt = f.read()
      except FileNotFoundError:
          print(f"Warning: Prompt file not found at {prompt_path}")
          system_prompt = "Select the most appropriate food item from the search results."
      
      llm = get_selection_llm()
      structured_llm = llm.with_structured_output(FoodSelectionResult)
      
      # Construct context for LLM
      user_context = f"User input: {pending_items[0]['original_text'] if pending_items else 'Unknown'}"
      search_context = f"Search results:\n" + "\n".join([f"- ID {r['id']}: {r['name']}" for r in search_results])
      
      messages = [
          SystemMessage(content=system_prompt),
          HumanMessage(content=f"{user_context}\n\n{search_context}")
      ]
      
      result = structured_llm.invoke(messages)
      
      return {
          "selected_food_id": result.food_id,
          "last_action": result.status.value
      }
  ```
- **GOTCHA**: Must handle empty `pending_food_items` gracefully (user might query stats, not log food)
- **VALIDATE**: `uv run python -c "from src.agents.nodes.selection_node import agent_selection_node; print('Node imported successfully')"`

### CREATE `src/agents/nodes/food_search_node.py`

- **IMPLEMENT**: Node that calls `search_food` tool and populates `search_results`
- **PATTERN**: Simple tool-calling node (no LLM needed)
- **IMPORTS**:
  ```python
  from src.agents.state import AgentState
  from src.tools.food_lookup import search_food
  ```
- **IMPLEMENTATION**:
  ```python
  def food_search_node(state: AgentState) -> dict:
      """
      Search for food items based on pending_food_items.
      
      Calls search_food tool for the first pending item and
      populates search_results in state.
      """
      pending_items = state.get("pending_food_items", [])
      
      if not pending_items:
          return {"search_results": []}
      
      # Search for first pending item
      first_item = pending_items[0]
      food_name = first_item.get("food_name", "")
      
      # Call search_food tool
      results = search_food.invoke({"query": food_name})
      
      return {"search_results": results}
  ```
- **GOTCHA**: `search_food` is a LangChain tool, use `.invoke()` method with dict input
- **VALIDATE**: `uv run python -c "from src.agents.nodes.food_search_node import food_search_node; print('Node imported successfully')"`

### UPDATE `src/agents/nutritionist.py`

- **IMPLEMENT**: Integrate selection node into graph flow
- **PATTERN**: Follow existing node registration (lines 30-33) and routing (lines 37-44)
- **IMPORTS**: Add new node imports after line 6:
  ```python
  from src.agents.nodes.selection_node import agent_selection_node
  from src.agents.nodes.food_search_node import food_search_node
  ```
- **MODIFICATIONS**:
  1. **Replace placeholder `food_lookup_node`** (lines 13-14) with actual implementation:
     ```python
     # Remove lines 13-14, nodes now imported from separate files
     ```
  
  2. **Update node registration** (lines 30-33):
     ```python
     workflow.add_node("input_parser", input_parser_node)
     workflow.add_node("food_search", food_search_node)  # NEW
     workflow.add_node("agent_selection", agent_selection_node)  # NEW
     workflow.add_node("stats_lookup", stats_lookup_node)
     workflow.add_node("response", response_node)
     ```
  
  3. **Update routing logic** (lines 22-28):
     ```python
     def route_parser(state: AgentState):
         action = state.get("last_action")
         if action in ["LOG_FOOD", "QUERY_FOOD_INFO"]:
             return "food_search"  # Changed from "food_lookup"
         elif action == "QUERY_DAILY_STATS":
             return "stats_lookup"
         return "response"
     ```
  
  4. **Update edges** (lines 37-49):
     ```python
     workflow.add_conditional_edges(
         "input_parser",
         route_parser,
         {
             "food_search": "food_search",  # Changed
             "stats_lookup": "stats_lookup",
             "response": "response"
         }
     )
     
     workflow.add_edge("food_search", "agent_selection")  # NEW
     workflow.add_edge("agent_selection", "response")  # NEW (placeholder until calc node exists)
     workflow.add_edge("stats_lookup", "response")
     workflow.add_edge("response", END)
     ```
- **GOTCHA**: Keep `stats_lookup_node` and `response_node` as placeholders for now
- **VALIDATE**: `uv run python src/main.py` (should compile graph without errors)

### CREATE `tests/unit/test_agent_selection.py`

- **IMPLEMENT**: Comprehensive unit tests for selection node
- **PATTERN**: Follow `tests/unit/test_input_parser.py` structure (lines 1-68)
- **IMPORTS**:
  ```python
  import pytest
  from src.agents.nodes.selection_node import agent_selection_node
  from src.schemas.selection_schema import SelectionStatus
  ```
- **TEST CASES**:
  ```python
  def test_selection_no_results(basic_state):
      """Test handling of empty search results."""
      basic_state["search_results"] = []
      basic_state["pending_food_items"] = [{"food_name": "xyz", "original_text": "xyz"}]
      
      result = agent_selection_node(basic_state)
      
      assert result["selected_food_id"] is None
      assert result["last_action"] == "NO_MATCH"
  
  def test_selection_single_result(basic_state):
      """Test auto-selection with single search result."""
      basic_state["search_results"] = [{"id": 45, "name": "Beef"}]
      basic_state["pending_food_items"] = [{"food_name": "beef", "original_text": "100g beef"}]
      
      result = agent_selection_node(basic_state)
      
      assert result["selected_food_id"] == 45
      assert result["last_action"] == "SELECTED"
  
  def test_selection_multiple_results_clear_match(basic_state):
      """Test LLM selection with multiple results (clear winner)."""
      basic_state["search_results"] = [
          {"id": 165, "name": "Apples, raw"},
          {"id": 275, "name": "Apple betty"},
          {"id": 163, "name": "Apple juice canned"}
      ]
      basic_state["pending_food_items"] = [
          {"food_name": "apple", "original_text": "I ate an apple"}
      ]
      
      result = agent_selection_node(basic_state)
      
      # Should select "Apples, raw" as most appropriate for whole fruit
      assert result["selected_food_id"] == 165
      assert result["last_action"] == "SELECTED"
  
  def test_selection_multiple_results_ambiguous(basic_state):
      """Test handling of truly ambiguous cases."""
      basic_state["search_results"] = [
          {"id": 44, "name": "Bacon"},
          {"id": 45, "name": "Beef"}
      ]
      basic_state["pending_food_items"] = [
          {"food_name": "meat", "original_text": "some meat"}
      ]
      
      result = agent_selection_node(basic_state)
      
      # LLM should recognize ambiguity or select one with reasoning
      # Accept either SELECTED (with reasoning) or AMBIGUOUS
      assert result["last_action"] in ["SELECTED", "AMBIGUOUS"]
  
  def test_selection_empty_pending_items(basic_state):
      """Test graceful handling when pending_food_items is empty."""
      basic_state["search_results"] = [{"id": 45, "name": "Beef"}]
      basic_state["pending_food_items"] = []
      
      # Should not crash, auto-select single result
      result = agent_selection_node(basic_state)
      assert result["selected_food_id"] == 45
  ```
- **GOTCHA**: LLM tests are non-deterministic; test for valid outcomes, not exact values
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py -v`

### CREATE `tests/unit/test_food_search_node.py`

- **IMPLEMENT**: Unit tests for food search node
- **PATTERN**: Follow existing test patterns
- **TEST CASES**:
  ```python
  def test_food_search_basic(basic_state):
      """Test basic food search functionality."""
      basic_state["pending_food_items"] = [
          {"food_name": "chicken", "original_text": "100g chicken"}
      ]
      
      from src.agents.nodes.food_search_node import food_search_node
      result = food_search_node(basic_state)
      
      assert "search_results" in result
      assert isinstance(result["search_results"], list)
      # Should find at least one chicken-related item
      assert len(result["search_results"]) > 0
  
  def test_food_search_no_pending_items(basic_state):
      """Test handling of empty pending items."""
      basic_state["pending_food_items"] = []
      
      from src.agents.nodes.food_search_node import food_search_node
      result = food_search_node(basic_state)
      
      assert result["search_results"] == []
  ```
- **VALIDATE**: `uv run pytest tests/unit/test_food_search_node.py -v`

---

## TESTING STRATEGY

### Unit Tests

**Framework**: pytest 9.0.2+  
**Fixtures**: Use `basic_state` from `tests/conftest.py`  
**Coverage Target**: 80%+ for new modules

**Test Scope**:
- Schema validation (FoodSelectionResult with all status types)
- Selection node logic (0, 1, N results)
- Edge cases (empty pending_items, malformed search results)
- Food search node (basic search, empty input)

**Mocking Strategy**:
- No mocking needed for selection node (uses real LLM with structured output)
- Food search node uses real database (in-memory SQLite from conftest)

### Integration Tests

**Scope**: End-to-end graph flow from input → search → selection → response

**Test Case**:
```python
def test_full_food_logging_flow():
    """Test complete flow: input → search → selection → response."""
    from src.agents.nutritionist import define_graph
    from langchain_core.messages import HumanMessage
    
    graph = define_graph()
    
    initial_state = {
        "messages": [HumanMessage(content="I ate 100g of chicken")],
        "pending_food_items": [],
        "daily_totals": {},
        "current_date": date.today(),
        "last_action": "",
        "search_results": [],
        "selected_food_id": None
    }
    
    config = {"configurable": {"thread_id": "test-thread"}}
    result = graph.invoke(initial_state, config)
    
    # Verify flow completed
    assert result["selected_food_id"] is not None
    assert result["last_action"] in ["SELECTED", "NO_MATCH"]
```

### Edge Cases

1. **No search results**: User enters food not in database
2. **Single exact match**: User enters "Beef" → finds "Beef"
3. **Multiple similar items**: "chicken" → multiple chicken types
4. **Ambiguous input**: "meat" → bacon, beef, chicken, etc.
5. **Empty pending items**: State inconsistency handling
6. **Malformed search results**: Missing 'id' or 'name' keys

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
# Lint all new and modified files
uv run ruff check src/schemas/selection_schema.py src/agents/nodes/selection_node.py src/agents/nodes/food_search_node.py src/agents/state.py src/agents/nutritionist.py tests/unit/test_agent_selection.py tests/unit/test_food_search_node.py

# Format check
uv run ruff format --check src/schemas/selection_schema.py src/agents/nodes/selection_node.py src/agents/nodes/food_search_node.py src/agents/state.py src/agents/nutritionist.py tests/unit/test_agent_selection.py tests/unit/test_food_search_node.py
```

### Level 2: Unit Tests

```bash
# Run new unit tests
uv run pytest tests/unit/test_agent_selection.py -v
uv run pytest tests/unit/test_food_search_node.py -v

# Run all unit tests (ensure no regressions)
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests

```bash
# Run full test suite
uv run pytest tests/ -v

# Verify graph compilation
uv run python src/main.py
```

### Level 4: Manual Validation

```bash
# Test schema import
uv run python -c "from src.schemas.selection_schema import FoodSelectionResult, SelectionStatus; print(FoodSelectionResult.model_json_schema())"

# Test node import
uv run python -c "from src.agents.nodes.selection_node import agent_selection_node; print('Selection node ready')"

# Test graph compilation
uv run python -c "from src.agents.nutritionist import define_graph; g = define_graph(); print('Graph compiled successfully')"

# Verify state schema
uv run python -c "from src.agents.state import AgentState; print(AgentState.__annotations__)"
```

---

## ACCEPTANCE CRITERIA

- [x] `FoodSelectionResult` schema created with status, food_id, and confidence fields
- [x] `SelectionStatus` enum with SELECTED, NO_MATCH, AMBIGUOUS values
- [x] Agent selection node handles 0, 1, and N search results correctly
- [x] System prompt guides LLM to make intelligent food selections
- [x] Food search node calls `search_food` tool and populates state
- [x] AgentState updated with `selected_food_id` field
- [x] Selection node integrated into graph flow (input → search → selection → response)
- [x] All validation commands pass with zero errors
- [x] Unit tests cover all edge cases (5+ test cases)
- [x] No regressions in existing tests (18/18 still passing)
- [x] Graph compiles successfully with new nodes
- [x] Code follows project conventions (type hints, docstrings, error handling)

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order (top to bottom)
- [ ] Each task validation passed immediately after implementation
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting or type checking errors
- [ ] Manual testing confirms selection logic works
- [ ] Graph flow updated in PRD.md (if needed)
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability

---

## NOTES

### Design Decisions

1. **Three-Status System**: Using SELECTED/NO_MATCH/AMBIGUOUS allows for future expansion (e.g., asking user for clarification on AMBIGUOUS)

2. **Auto-Select Single Results**: When only one result exists, skip LLM call for performance and cost optimization

3. **Confidence Field**: Including reasoning helps with debugging and future UI transparency

4. **Separate Search Node**: Decouples tool calling from selection logic, following single-responsibility principle

5. **Optional food_id**: Using `Optional[int]` allows clean handling of NO_MATCH cases without special sentinel values

### Future Enhancements (Out of Scope)

- **User Clarification Flow**: When status is AMBIGUOUS, ask user to choose from options
- **Semantic Search**: Upgrade from ILIKE to vector similarity search for better matching
- **Selection History**: Learn from past user selections to improve future matches
- **Batch Selection**: Handle multiple pending_food_items in one pass

### Known Limitations

- **LLM Non-Determinism**: Selection may vary slightly between runs (acceptable for MVP)
- **Single Item Processing**: Currently processes only first pending_food_item (multi-item support in future phases)
- **No User Feedback Loop**: Can't ask for clarification yet (Phase 2 feature)

### Integration Notes

- **Placeholder Nodes**: `stats_lookup_node` and `response_node` remain as placeholders
- **Next Phase**: Implement "Calculate & Log Node" to consume `selected_food_id`
- **State Flow**: `selected_food_id` will be used by calc node to call `calculate_food_macros(food_id, amount_g)`
