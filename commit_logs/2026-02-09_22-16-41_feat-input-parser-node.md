# Commit: Implement Input Parser Node and State Persistence

**Date**: 2026-02-09 22:16:41
**Tag**: `feat`

## Changes Implemented

### 1. Input Parser Node (`src/agents/nodes/input_node.py`)
- Implemented `input_parser_node` using `ChatOpenAI` with structured output (`FoodIntakeEvent`).
- Added system prompt `prompts/input_parser.md` to guide the LLM in decomposing meals and normalizing food names.
- Configured the node to distinguish between `LOG_FOOD`, `QUERY_FOOD_INFO`, `QUERY_DAILY_STATS`, and `CHITCHAT`.

### 2. State Management (`src/agents/state.py` & `src/agents/nutritionist.py`)
- Updated `AgentState` to include `pending_food_items`, `daily_totals`, and `last_action`.
- Integrated `SqliteSaver` for persistent state management across conversation turns.
- Configured the graph to use the checkpointer.

### 3. Data Schemas (`src/schemas/`)
- Defined Pydantic models for `FoodIntakeEvent`, `SingleFoodItem`, and `ActionType` to ensure strict typing of LLM outputs.

### 4. Graph Architecture
- Registered `input_parser` as the entry point of the LangGraph workflow.
- Added conditional routing based on the `last_action` determined by the parser.

### 5. Testing & Validation
- Added `tests/verify_input_logic.py` to unit test the parser's logic.
- created `test_agent_flow.py` for integration testing of the graph.
- Added `visualize_graph.py` to generate a visual representation of the graph (`agent_graph.png`).

## Next Steps
- Verify the `search_food` and `calculate_food_macros` tools (currently placeholders/WIP).
- Integrate the food lookup tools into the graph.
- Refine the `prompts/input_parser.md` based on real-world usage data.
