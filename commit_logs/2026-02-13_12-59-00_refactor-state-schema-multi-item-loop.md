# Commit: Refactor State Schema and Multi-Item Loop Processing

**Date**: 2026-02-13 12:59:00  
**Commit Hash**: `6f9dc4e`  
**Branch**: `feat/lookup-calc-logic`  
**Tag**: `refactor`

---

## Summary

Implemented comprehensive refactor of the FitPal agent's state management and graph orchestration to support type-safe schemas and multi-item food processing. This addresses critical architectural improvements needed for maintainability and enables the agent to handle complex meals like "I ate 100g chicken and 200g rice" by processing items sequentially in a loop.

---

## Changes Implemented

### 1. Type-Safe State Schema (Phase 1)

**Problem**: `AgentState` used vague `List[dict]` and `dict` types, losing all type safety and IDE support.

**Solution**: Created three new TypedDict schemas:

- **`PendingFoodItem`** — Mirrors `SingleFoodItem` Pydantic model structure
  - Fields: `food_name`, `amount`, `unit`, `original_text`
- **`SearchResult`** — Mirrors `search_food` tool return type
  - Fields: `id`, `name`
- **`DailyTotals`** — Mirrors `get_daily_totals` service return type
  - Fields: `calories`, `protein`, `carbs`, `fat`

**Files Modified**:
- `src/agents/state.py` — Added TypedDict definitions, updated `AgentState` fields

**Benefits**:
- ✅ Full IDE autocomplete and type checking
- ✅ Self-documenting code with explicit schemas
- ✅ Compatible with LangGraph's SQLite checkpointer serialization

---

### 2. Multi-Item Loop Processing (Phase 2)

**Problem**: Agent only processed the first food item, ignoring subsequent items in multi-food meals.

**Solution**: Implemented graph loop routing with conditional edges:

1. **Created `calculate_log_node.py`** (placeholder)
   - Removes first item from `pending_food_items` after processing
   - Sets `last_action` to `LOGGED`
   - Full implementation (macro calculation + DB persistence) deferred to next feature

2. **Added routing functions** in `nutritionist.py`:
   - `route_after_selection()` — Routes SELECTED → calculate_log, NO_MATCH → response
   - `route_after_calculate()` — Routes to food_search if items remain, else response

3. **Replaced static edges with conditional edges**:
   - `agent_selection` now routes conditionally based on selection result
   - `calculate_log` loops back to `food_search` for remaining items

**Files Modified**:
- `src/agents/nutritionist.py` — Added routing logic, calculate_log node, conditional edges
- `src/agents/nodes/calculate_log_node.py` — **NEW** placeholder implementation

**Graph Flow** (updated):
```
input_parser → food_search → agent_selection → calculate_log → [loop back to food_search if items remain] → response → END
```

---

### 3. LLM Response Validation (Phase 3)

**Problem**: LLM could return inconsistent states (e.g., `SELECTED` with `food_id=None`, or `AMBIGUOUS` status not handled).

**Solution**: Added validation layer in `selection_node.py`:

```python
# Validate LLM response consistency
if result.status == SelectionStatus.SELECTED and result.food_id is None:
    print("Warning: LLM returned SELECTED without food_id, treating as NO_MATCH")
    return {"selected_food_id": None, "last_action": "NO_MATCH"}

if result.status == SelectionStatus.AMBIGUOUS:
    print("Warning: LLM returned AMBIGUOUS (not supported in MVP), treating as NO_MATCH")
    return {"selected_food_id": None, "last_action": "NO_MATCH"}
```

**Files Modified**:
- `src/agents/nodes/selection_node.py` — Added validation logic, imported `SelectionStatus`

---

### 4. Prompt Improvements

**Changes**:
1. **"Cooked over raw"** preference (was "raw over cooked") — aligns with real-world user behavior
2. **Removed edge case handling** from prompt (0/1 results now handled in code)
3. **Added MVP instruction** to avoid AMBIGUOUS status — forces LLM to choose SELECTED or NO_MATCH
4. **Removed AMBIGUOUS** from output format options

**Files Modified**:
- `prompts/agent_selection.md` — Updated selection strategy and instructions

---

### 5. Test Suite Updates (Phase 4)

**Updated Fixtures**:
- `tests/conftest.py` — `basic_state` now includes all required `AgentState` fields with proper types

**Updated Tests**:
- `tests/unit/test_agent_selection.py` — TypedDict-compatible dicts, removed AMBIGUOUS assertion
- `tests/unit/test_food_search_node.py` — TypedDict-compatible dicts
- `tests/unit/test_input_parser.py` — No changes needed (already compatible)

**New Tests**:
- `tests/unit/test_multi_item_loop.py` — **NEW** 5 comprehensive tests:
  - Item removal logic
  - Empty pending items handling
  - Single item processing
  - Multi-item state setup
  - Sequential processing through 3 items

**Test Results**: ✅ **30/30 tests passing** (was 25/25 before)

---

### 6. Graph Visualization

**Updated**:
- `agent_graph.png` — Regenerated with new loop routing (shows conditional edges)

---

## Files Changed

### Modified (9 files)
1. `src/agents/state.py` — TypedDict schemas
2. `src/agents/nodes/input_node.py` — Comment update
3. `src/agents/nodes/selection_node.py` — LLM validation
4. `src/agents/nutritionist.py` — Graph routing overhaul
5. `prompts/agent_selection.md` — Prompt improvements
6. `tests/conftest.py` — Fixture update
7. `tests/unit/test_agent_selection.py` — Test updates
8. `tests/unit/test_food_search_node.py` — Test updates
9. `agent_graph.png` — Graph visualization

### Created (2 files)
1. `src/agents/nodes/calculate_log_node.py` — Placeholder node
2. `tests/unit/test_multi_item_loop.py` — Loop processing tests

---

## Validation Results

| Check | Result |
|---|---|
| Ruff linting (modified files) | ✅ All checks passed |
| Full test suite | ✅ 30/30 passed |
| Graph compilation | ✅ Compiled successfully |
| TypedDict imports | ✅ All schemas imported |

---

## Design Decisions

1. **TypedDict over Pydantic for State**: LangGraph serializes state to SQLite checkpointer. TypedDict is simpler and natively supported without custom serializers.

2. **Loop Processing over Batch**: Processing items one at a time is simpler for MVP and easier to debug. Can optimize to batch processing in future if needed.

3. **Placeholder Calculate Node**: Full implementation requires integration with `calculate_food_macros` tool and `daily_log_service`. This refactor focuses on architecture — full implementation will be separate feature.

4. **Validation in Code vs Prompt**: Validation logic in Python is more reliable than relying on LLM to follow prompt instructions. Prompt guides behavior, code enforces constraints.

---

## Next Steps

### Immediate (Next Commit)
1. **Implement `calculate_log_node` fully**:
   - Call `calculate_food_macros` tool with `selected_food_id` and `amount_g`
   - Call `daily_log_service.create_log_entry()` to persist to DB
   - Query `daily_log_service.get_daily_totals()` to update state
   - Update `daily_totals` in state

2. **Update `response_node`** to generate rich responses:
   - Show calculated macros for logged food
   - Display updated daily totals
   - Provide contextual feedback

### Future Enhancements
1. **Batch Processing Optimization**: If cost/latency becomes issue, implement batch selection (single LLM call for all items)
2. **AMBIGUOUS Status Implementation**: Add user clarification flow in Phase 2
3. **Single-Result LLM Verification**: Add smart heuristic to verify single search results (e.g., "chicken" → "Chicken soup" should ask for confirmation)

---

## Acceptance Criteria

- [x] All `List[dict]` and plain `dict` types replaced with TypedDict in `AgentState`
- [x] Three new TypedDict classes defined: `PendingFoodItem`, `SearchResult`, `DailyTotals`
- [x] Selection node validates LLM responses and handles SELECTED/AMBIGUOUS edge cases
- [x] Graph implements loop routing to process multiple food items
- [x] Calculate node placeholder removes processed items from pending list
- [x] System prompt updated to "cooked over raw" preference
- [x] System prompt instructs LLM to avoid AMBIGUOUS status
- [x] All existing tests pass with updated schemas
- [x] New multi-item test added
- [x] All validation commands pass with zero errors
- [x] Graph compiles successfully with new routing logic
- [x] No regressions in existing functionality

---

**Status**: ✅ **Complete and Committed**
