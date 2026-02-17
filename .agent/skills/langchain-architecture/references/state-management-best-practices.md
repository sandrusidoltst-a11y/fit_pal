# LangGraph State Management Best Practices

**Purpose**: Critical patterns and anti-patterns for type-safe state management in LangGraph applications.

**When to read**: Before implementing or refactoring LangGraph state schemas, when debugging type safety issues, or when deciding between Pydantic and TypedDict.

---

## Table of Contents

1. [The Critical Anti-Pattern: Vague Dict Types](#the-critical-anti-pattern-vague-dict-types)
2. [Pydantic vs TypedDict Decision Tree](#pydantic-vs-typeddict-decision-tree)
3. [Nested TypedDict Patterns](#nested-typeddict-patterns)
4. [Conversion Patterns](#conversion-patterns)
5. [LLM Response Validation](#llm-response-validation)
6. [Graph Routing Patterns](#graph-routing-patterns)
7. [Common Mistakes & Fixes](#common-mistakes--fixes)

---

## The Critical Anti-Pattern: Vague Dict Types

### ❌ NEVER Do This

```python
from typing import TypedDict, List

class AgentState(TypedDict):
    pending_items: List[dict]  # ❌ NO TYPE SAFETY
    totals: dict               # ❌ NO TYPE SAFETY
    results: List[dict]        # ❌ NO TYPE SAFETY
```

### Why This Is Bad

1. **No IDE Autocomplete**: You lose all IntelliSense support
2. **No Type Checking**: Typos like `item['food_nam']` won't be caught
3. **Runtime Errors**: Silent failures from accessing wrong keys
4. **Poor Documentation**: Structure is unclear to other developers
5. **Difficult Maintenance**: Changes require hunting through code

### Real-World Impact

```python
# With List[dict] - RUNTIME ERROR
def process_items(state: AgentState):
    items = state["pending_items"]
    first = items[0]
    name = first["food_nam"]  # ❌ Typo! Runtime KeyError

# With proper TypedDict - CAUGHT AT DEVELOPMENT TIME
def process_items(state: AgentState):
    items = state["pending_items"]
    first = items[0]
    name = first["food_nam"]  # ✅ IDE shows error immediately
```

---

## Pydantic vs TypedDict Decision Tree

### Use Pydantic BaseModel When:

1. **LLM Structured Output** (with `.with_structured_output()`)
2. **Input Validation** (user-facing data that needs validation)
3. **API Request/Response Models** (external interfaces)

**Example:**

```python
from pydantic import BaseModel, Field
from enum import Enum

class SelectionStatus(str, Enum):
    SELECTED = "SELECTED"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS = "AMBIGUOUS"

class FoodSelectionResult(BaseModel):
    """LLM output for food selection - Pydantic for validation."""
    status: SelectionStatus = Field(..., description="Selection outcome")
    food_id: Optional[int] = Field(None, description="Selected food ID")
    reasoning: str = Field(..., description="Why this was selected")

# Use with LLM
structured_llm = llm.with_structured_output(FoodSelectionResult)
result = structured_llm.invoke(messages)  # Returns validated Pydantic model
```

### Use TypedDict When:

1. **LangGraph State** (serialization to checkpointer)
2. **Internal Data Structures** (no validation needed)
3. **Node Return Types** (graph state updates)

**Example:**

```python
from typing import TypedDict, Optional

class AgentState(TypedDict):
    """Graph state - TypedDict for serialization."""
    messages: list
    selected_food_id: Optional[int]
    last_action: str

def my_node(state: AgentState) -> dict:
    """Node function returns dict that updates state."""
    return {
        "selected_food_id": 123,
        "last_action": "SELECTED"
    }
```

### Why This Matters

**LangGraph Checkpointer Serialization:**
- TypedDict → JSON → SQLite ✅ (seamless)
- Pydantic → Requires `.model_dump()` → JSON → SQLite ⚠️ (extra step)

**LLM Structured Output:**
- Pydantic ✅ (built-in validation)
- TypedDict ❌ (no validation)

---

## Nested TypedDict Patterns

### Pattern 1: Simple Nested Structure

```python
from typing import TypedDict, List

class PendingFoodItem(TypedDict):
    """Single food item waiting to be processed."""
    food_name: str
    amount: float
    unit: str
    original_text: str

class AgentState(TypedDict):
    """Main graph state with type-safe nested structures."""
    pending_items: List[PendingFoodItem]  # ✅ Type-safe!
```

**Benefits:**
- IDE autocomplete: `state["pending_items"][0]["food_name"]` ✅
- Type checking catches typos ✅
- Self-documenting structure ✅

### Pattern 2: Multiple Nested Structures

```python
from typing import TypedDict, List, Optional
from datetime import date

class SearchResult(TypedDict):
    """Result from food database search."""
    id: int
    name: str
    calories: float
    protein: float

class DailyTotals(TypedDict):
    """Aggregated nutritional totals."""
    calories: float
    protein: float
    carbs: float
    fat: float

class AgentState(TypedDict):
    """Main graph state with multiple nested structures."""
    pending_items: List[PendingFoodItem]
    search_results: List[SearchResult]
    daily_totals: DailyTotals
    current_date: date
    selected_food_id: Optional[int]
```

### Pattern 3: Optional Fields

```python
from typing import TypedDict, Optional, NotRequired

# Python 3.11+ with NotRequired
class AgentState(TypedDict):
    messages: list  # Required
    selected_food_id: NotRequired[Optional[int]]  # Optional field

# Python 3.10 with total=False
class OptionalFields(TypedDict, total=False):
    selected_food_id: Optional[int]

class AgentState(OptionalFields):
    messages: list  # Required from base
```

---

## Conversion Patterns

### Pattern 1: Pydantic → TypedDict (LLM Output → State)

```python
from pydantic import BaseModel

class SingleFoodItem(BaseModel):
    """Pydantic model for LLM output."""
    food_name: str
    amount: float
    unit: str

class PendingFoodItem(TypedDict):
    """TypedDict for state."""
    food_name: str
    amount: float
    unit: str

def input_parser_node(state: AgentState) -> dict:
    """Convert Pydantic LLM output to TypedDict for state."""
    # LLM returns Pydantic
    result: FoodIntakeEvent = structured_llm.invoke(messages)
    
    # Convert to dict for state
    return {
        "pending_items": [item.model_dump() for item in result.items]
    }
```

**Key Point**: The dict structure from `model_dump()` must match your TypedDict definition exactly.

### Pattern 2: TypedDict → Pydantic (State → Validation)

```python
def selection_node(state: AgentState) -> dict:
    """Convert TypedDict state to Pydantic for validation."""
    pending_items = state.get("pending_items", [])
    
    # Reconstruct Pydantic models for validation
    validated_items = [SingleFoodItem(**item) for item in pending_items]
    
    # Now you have type-safe access with validation
    for item in validated_items:
        print(item.food_name)  # ✅ Type-safe
    
    return {"last_action": "PROCESSED"}
```

---

## LLM Response Validation

### Never Trust LLM Output Blindly

```python
from src.schemas.selection_schema import SelectionStatus

def selection_node(state: AgentState) -> dict:
    # Get LLM response
    result = structured_llm.invoke(messages)
    
    # ✅ VALIDATE: Check for inconsistent states
    if result.status == SelectionStatus.SELECTED and result.food_id is None:
        print("Warning: LLM returned SELECTED without food_id")
        return {
            "selected_food_id": None,
            "last_action": "NO_MATCH"
        }
    
    if result.status == SelectionStatus.AMBIGUOUS:
        print("Warning: AMBIGUOUS not supported, treating as NO_MATCH")
        return {
            "selected_food_id": None,
            "last_action": "NO_MATCH"
        }
    
    # Valid response
    return {
        "selected_food_id": result.food_id,
        "last_action": result.status.value
    }
```

### Validation Checklist

- [ ] Check for logically inconsistent states
- [ ] Validate required fields are present
- [ ] Handle unexpected enum values
- [ ] Provide fallback behavior
- [ ] Log warnings for debugging

---

## Graph Routing Patterns

### Pattern 1: Simple Conditional Routing

```python
def route_after_selection(state: AgentState) -> str:
    """Route based on last action."""
    action = state.get("last_action")
    if action == "SELECTED":
        return "calculate_node"
    else:  # NO_MATCH
        return "response_node"

# Add to graph
workflow.add_conditional_edges(
    "selection_node",
    route_after_selection,
    {
        "calculate_node": "calculate_node",
        "response_node": "response_node"
    }
)
```

### Pattern 2: Loop Pattern (Multi-Item Processing)

```python
def route_after_calculate(state: AgentState) -> str:
    """Loop back if more items to process."""
    pending = state.get("pending_items", [])
    
    if pending:
        return "search_node"  # Process next item
    else:
        return "response_node"  # All done

workflow.add_conditional_edges(
    "calculate_node",
    route_after_calculate,
    {
        "search_node": "search_node",    # Loop back
        "response_node": "response_node"  # Exit
    }
)
```

**Critical**: Remove processed items in the node:

```python
def calculate_node(state: AgentState) -> dict:
    pending = state.get("pending_items", [])
    
    if not pending:
        return {}
    
    # Process first item
    current_item = pending[0]
    # ... calculation logic ...
    
    # ✅ REMOVE processed item
    remaining = pending[1:]
    
    return {
        "pending_items": remaining,
        "last_action": "CALCULATED"
    }
```

---

## Common Mistakes & Fixes

### Mistake 1: Returning Pydantic from Node

```python
# ❌ Wrong
def my_node(state: AgentState) -> FoodSelectionResult:
    result = structured_llm.invoke(messages)
    return result  # Pydantic model

# ✅ Correct
def my_node(state: AgentState) -> dict:
    result = structured_llm.invoke(messages)
    return {
        "selected_food_id": result.food_id,
        "last_action": result.status.value
    }
```

### Mistake 2: Not Removing Processed Items

```python
# ❌ Wrong - infinite loop
def calculate_node(state: AgentState) -> dict:
    items = state["pending_items"]
    # Process first item...
    return {"last_action": "DONE"}  # Items still in state!

# ✅ Correct
def calculate_node(state: AgentState) -> dict:
    items = state.get("pending_items", [])
    # Process first item...
    return {
        "pending_items": items[1:],  # Remove processed item
        "last_action": "DONE"
    }
```

### Mistake 3: Unsafe State Access

```python
# ❌ Wrong
def my_node(state: AgentState) -> dict:
    items = state["pending_items"]  # KeyError if missing
    first = items[0]                # IndexError if empty

# ✅ Correct
def my_node(state: AgentState) -> dict:
    items = state.get("pending_items", [])  # Default to empty list
    
    if not items:
        return {}  # Handle empty case
    
    first = items[0]  # Safe now
```

### Mistake 4: Prompt vs Code Duplication

```python
# ❌ Wrong - prompt says "handle 0 results" but code already does it
# This creates confusion about where logic lives

# ✅ Correct - code handles edge cases, prompt handles reasoning
def selection_node(state: AgentState) -> dict:
    results = state.get("search_results", [])
    
    # Edge cases handled in CODE
    if not results:
        return {"last_action": "NO_MATCH"}
    
    if len(results) == 1:
        return {"selected_food_id": results[0]["id"]}
    
    # Only multi-result case reaches LLM
    # Prompt focuses on REASONING, not edge cases
    result = structured_llm.invoke(messages)
    return {"selected_food_id": result.food_id}
```

---

## Anti-Pattern Checklist

Before merging code, verify:

- [ ] No `List[dict]` or plain `dict` in state schemas
- [ ] All state fields have proper TypedDict definitions
- [ ] LLM outputs are validated before returning
- [ ] State access uses `.get()` with defaults
- [ ] Node functions return `dict`, not Pydantic models
- [ ] Routing functions return `str` (node name)
- [ ] Empty list/dict cases are handled
- [ ] Processed items are removed in loop patterns

---

## Quick Reference

| Use Case | Use This | Example |
|----------|----------|---------|
| LLM structured output | Pydantic BaseModel | `FoodSelectionResult(BaseModel)` |
| Graph state | TypedDict | `AgentState(TypedDict)` |
| Nested state structures | Nested TypedDict | `List[PendingFoodItem]` |
| LLM output → state | `.model_dump()` | `[item.model_dump() for item in results]` |
| State → validation | `**dict` unpacking | `SingleFoodItem(**item)` |
| Safe state access | `.get()` with default | `state.get("items", [])` |
| Loop processing | Remove processed items | `pending[1:]` |

---

## Documentation Links

- [LangGraph State Schema](https://langchain-ai.github.io/langgraph/concepts/low_level/#state)
- [Python TypedDict](https://docs.python.org/3/library/typing.html#typing.TypedDict)
- [Pydantic BaseModel](https://docs.pydantic.dev/latest/concepts/models/)
- [LangGraph Conditional Edges](https://langchain-ai.github.io/langgraph/concepts/low_level/#conditional-edges)
